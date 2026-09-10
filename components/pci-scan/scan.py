"""Atlas POS — PCI-DSS card-data scan of a live merchant kassa DB.

Connects to the Venue A terminal (venue-a-till) over Tailscale and scans the
payment-bearing tables for full PAN, masked PAN, auth codes, tokens, CVV/track/PIN.
Read-only. Redacts actual values; reports only classifications + counts.
"""
import re
import sys
import pymysql

HOST = "192.0.2.10"
USER = "remote"
PW = "<MYSQL_PASSWORD>"
DB = "kassa"

TABLES_TEXT_COLS = {
    "bestelling": None,        # discover at runtime
    "bestelling_detail": None,
    "bestelling_h": None,
    "hh_bestelling": None,
    "kasboek": None,
}

def luhn_ok(num: str) -> bool:
    s, alt = 0, False
    for ch in reversed(num):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        alt = not alt
    return s % 10 == 0

def redact(run: str) -> str:
    if len(run) <= 10:
        return run[:2] + "*" * (len(run) - 4) + run[-2:]
    return run[:6] + "*" * (len(run) - 10) + run[-4:]

conn = pymysql.connect(host=HOST, user=USER, password=PW, database=DB, charset="utf8mb4", connect_timeout=8)
cur = conn.cursor()

# 1. discover all text-capable columns in the 5 target tables
cur.execute("""
    SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ('bestelling','bestelling_detail','bestelling_h','hh_bestelling','kasboek')
      AND DATA_TYPE IN ('varchar','char','text','tinytext','mediumtext','longtext','blob','json')
    ORDER BY TABLE_NAME, ORDINAL_POSITION
""", (DB,))
cols = {}
for t, c in cur.fetchall():
    cols.setdefault(t, []).append(c)

PAN_RE = re.compile(r"\d{13,19}")
MASK_RE = re.compile(r"\d{6}x{4,8}\d{4}", re.I)
SAD_RE = re.compile(r"\b(cvv|cvc|cvc2|cid|cav2|track[12]?|magstripe|pin\s*block|pinblock)\b", re.I)
EXP_RE = re.compile(r"(vervaldat|\bexpir|geldig\s*tot)", re.I)

summary = {
    "rows_scanned": 0,
    "cells_with_long_digits": 0,
    "kaart_lines_total": 0,
    "kaart_lines_masked": 0,
    "kaart_lines_unmasked": 0,
    "digit_runs_by_ctx": {},
    "raw_pan_on_kaart": [],
    "sad_hits": [],
    "expiry_hits": [],
    "unmasked_examples": [],
    "stray_digit_cells": [],   # long digit runs in non-pinbon columns
}

for table, collist in cols.items():
    if not collist:
        continue
    pk = "B_ID" if table.startswith("bestelling") else ("HH_ID" if table == "hh_bestelling" else "KB_ID")
    # confirm pk exists
    cur.execute(f"SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION LIMIT 1", (DB, table))
    first_col = cur.fetchone()[0]
    select_cols = ", ".join([f"`{c}`" for c in collist])
    cur.execute(f"SELECT `{first_col}`, {select_cols} FROM `{table}`")
    rows = cur.fetchall()
    for row in rows:
        summary["rows_scanned"] += 1
        rid = row[0]
        for ci, colname in enumerate(collist, start=1):
            val = row[ci]
            if val is None:
                continue
            text = val if isinstance(val, str) else str(val)
            if not text:
                continue
            # Kaart line analysis (pinbon only)
            for line in re.split(r"\r?\n", text):
                if re.search(r"Kaart\s*:", line):
                    summary["kaart_lines_total"] += 1
                    if MASK_RE.search(line):
                        summary["kaart_lines_masked"] += 1
                    elif re.search(r"\d{12,}", line):
                        summary["kaart_lines_unmasked"] += 1
                        summary["unmasked_examples"].append(f"{table}#{rid} {colname}: {line.strip()[:60]}")
                    else:
                        summary["kaart_lines_masked"] += 1  # masked some other way / short
            # long digit runs
            has_long = False
            for m in PAN_RE.finditer(text):
                has_long = True
                run = m.group()
                cs = max(0, m.start() - 25)
                ctx = re.sub(r"\s+", " ", text[cs:cs + 55])
                if re.search(r"Token", ctx):
                    label = "Token"
                elif re.search(r"Kaart", ctx):
                    label = "KAART"
                elif re.search(r"PAR", ctx):
                    label = "PAR"
                elif re.search(r"Merchant", ctx):
                    label = "Merchant"
                elif re.search(r"POI|Terminal|Transactie|Periode", ctx):
                    label = "terminal-id"
                else:
                    label = "other"
                key = f"{len(run)}d Luhn={luhn_ok(run)} ctx={label}"
                summary["digit_runs_by_ctx"][key] = summary["digit_runs_by_ctx"].get(key, 0) + 1
                # A genuine full-PAN candidate must (a) pass Luhn AND (b) NOT be a
                # known non-CHD surrogate (token / PAR / EMV AID). EMV AIDs start
                # with the EMV RID prefix 'A000000003/4' which appears as the
                # 13-digit run '0000000xxxxx' right after a '(A' on the brand line.
                is_aid = bool(re.match(r"^00000000[34]", run)) and "(A" in ctx
                summary.setdefault("luhn_valid_non_surrogate", [])
                if luhn_ok(run) and label not in ("Token", "PAR") and not is_aid:
                    summary["luhn_valid_non_surrogate"].append(f"{table}#{rid}: {redact(run)} ctx='{ctx[:40]}'")
                if colname not in ("B_PINBON",) and label == "other":
                    summary["stray_digit_cells"].append(f"{table}#{rid} {colname}: {redact(run)} ctx='{ctx[:40]}'")
            if has_long:
                summary["cells_with_long_digits"] += 1
            if SAD_RE.search(text):
                summary["sad_hits"].append(f"{table}#{rid} {colname}")
            if EXP_RE.search(text):
                summary["expiry_hits"].append(f"{table}#{rid} {colname}")

conn.close()

print("=" * 64)
print("ATLAS POS — PCI card-data scan  (host:", HOST, "db:", DB, ")")
print("=" * 64)
print(f"Text-capable columns scanned per table:")
for t, cl in cols.items():
    print(f"  {t}: {len(cl or [])} cols -> {cl}")
print()
print(f"Rows scanned: {summary['rows_scanned']}")
print(f"Cells containing a 13-19 digit run: {summary['cells_with_long_digits']}")
print()
print(f"Kaart lines: total={summary['kaart_lines_total']} masked={summary['kaart_lines_masked']} UNMASKED={summary['kaart_lines_unmasked']}")
for ex in summary["unmasked_examples"]:
    print(f"   !! {ex}")
print()
print("13-19 digit runs by context (token/PAR/terminal = NOT cardholder data):")
for k in sorted(summary["digit_runs_by_ctx"]):
    print(f"   {k}: {summary['digit_runs_by_ctx'][k]}")
print()
luhn_valid = summary.get("luhn_valid_non_surrogate", [])
print(f"Luhn-VALID 13-19 digit runs that are NOT token/PAR/AID (a real PAN MUST pass Luhn): {len(luhn_valid)}")
for h in luhn_valid:
    print(f"   !! {h}")
print()
print(f"SAD markers (CVV/CVC/track/PINblock) hits: {len(summary['sad_hits'])}  {summary['sad_hits'][:5]}")
print(f"Card-expiry-date markers: {len(summary['expiry_hits'])}  {summary['expiry_hits'][:5]}")
print(f"Stray long-digit runs in non-pinbon free-text cells: {len(summary['stray_digit_cells'])}")
for s in summary["stray_digit_cells"][:10]:
    print(f"   ? {s}")
print()
# Verdict — a real blocker = an unmasked card line, a Luhn-valid non-surrogate PAN,
# or any SAD. Note: every digit run here is Luhn=False, so luhn_valid is the
# authoritative PAN test (immune to context-window mislabeling).
unmasked = summary["kaart_lines_unmasked"]
sad = len(summary["sad_hits"])
print("-" * 64)
print(f"unmasked_kaart_lines={unmasked}  luhn_valid_non_surrogate_pans={len(luhn_valid)}  sad_hits={sad}  expiry_hits={len(summary['expiry_hits'])}")
if unmasked == 0 and len(luhn_valid) == 0 and sad == 0:
    print("VERDICT: PASS — NO full PAN, NO SAD. Card lines store only truncated PAN")
    print("         (first6+last4, middle masked) + token + PAR + auth code + IDs.")
    print("         => kassa DB and its mysqldump.gz mirror are OUT OF PCI-DSS PAN-storage scope.")
else:
    print(f"VERDICT: BLOCKER — unmasked={unmasked} luhn_valid_pan={len(luhn_valid)} sad={sad}. Mirror inherits scope.")
