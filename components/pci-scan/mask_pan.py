"""Atlas POS-Ops — defensive PAN scrubber for the mirror pipeline.

Belt-and-suspenders: even though the current kassa.exe build stores only
truncated PAN, this stream filter guarantees the off-site mirror can NEVER
contain a full PAN — if a future vendor build ever writes one, it's redacted
before it leaves the terminal.

Usage (wrap mysqldump):
    mysqldump ... kassa | py mask_pan.py | gzip > mirror.sql.gz

It replaces any Luhn-valid 13-19 digit run with [REDACTED-PANnn] and leaves
tokens/PAR/AID (Luhn-invalid) and already-masked PANs untouched. Reports a
count to stderr so the collector can log how many (if any) were scrubbed.
"""
import re
import sys

PAN_RE = re.compile(rb"\d{13,19}")


def luhn_ok(b: bytes) -> bool:
    s, alt = 0, False
    for ch in reversed(b):
        d = ch - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        alt = not alt
    return s % 10 == 0


def scrub_line(line: bytes, counter: list) -> bytes:
    def repl(m: "re.Match[bytes]") -> bytes:
        run = m.group()
        # Real PAN = Luhn-valid AND digit-diverse. All-same-digit runs (template
        # padding like 0000000000000) pass Luhn but aren't cards; leave intact.
        if len(set(run)) > 1 and luhn_ok(run):
            counter[0] += 1
            return b"[REDACTED-PAN%d]" % len(run)
        return run
    return PAN_RE.sub(repl, line)


def main() -> int:
    counter = [0]
    out = sys.stdout.buffer
    for line in sys.stdin.buffer:
        out.write(scrub_line(line, counter))
    out.flush()
    sys.stderr.write(f"mask_pan: redacted {counter[0]} Luhn-valid PAN candidate(s)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
