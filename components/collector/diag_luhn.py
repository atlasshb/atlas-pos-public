import pymysql, re

c = pymysql.connect(host="127.0.0.1", port=3306, user="remote",
                    password="<MYSQL_PASSWORD>", database="kassa", charset="utf8mb4")
cur = c.cursor()

def luhn(b):
    s, a = 0, False
    for ch in reversed(b):
        d = ch - 48
        if a:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        a = not a
    return s % 10 == 0

PAN = re.compile(rb"\d{13,19}")
cur.execute("SHOW TABLES")
tables = [r[0] for r in cur.fetchall()]
hits = {}
samples = {}
for t in tables:
    cur.execute("SELECT * FROM `{}`".format(t))
    desc = [d[0] for d in cur.description]
    for row in cur.fetchall():
        for col, val in zip(desc, row):
            if val is None:
                continue
            s = val if isinstance(val, (bytes, bytearray)) else str(val).encode("utf-8", "ignore")
            for m in PAN.finditer(s):
                run = m.group()
                if luhn(run):
                    key = "{}.{}".format(t, col)
                    hits[key] = hits.get(key, 0) + 1
                    if key not in samples:
                        cs = max(0, m.start() - 18)
                        samples[key] = s[cs:m.start() + len(run) + 4].decode("utf-8", "ignore")
print("Luhn-valid 13-19 digit runs by table.column:")
for k, v in sorted(hits.items(), key=lambda x: -x[1]):
    print("  {}: {}  e.g. ...{}...".format(k, v, samples[k]))
print("total:", sum(hits.values()))
c.close()
