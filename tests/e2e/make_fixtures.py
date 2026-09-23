"""Synthetic fixtures for the browser workflows (no third-party records).

    python tests/e2e/make_fixtures.py OUT_DIR   ->  OUT_DIR/dbdir/*.db|sqlite, OUT_DIR/csv/*.csv
"""
import csv, os, sqlite3, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from test_relational import make_relational_db
from test_preflight import btc_address
from generate_case_study_demo_db import build

out = sys.argv[1]
d, c = os.path.join(out, "dbdir"), os.path.join(out, "csv")
os.makedirs(d, exist_ok=True); os.makedirs(c, exist_ok=True)
for name in ("healthy.db", "recovered.db", "corrupt.db"):
    make_relational_db(os.path.join(d, name))
with open(os.path.join(d, "corrupt.db"), "r+b") as f:      # truncated to a third: fails its integrity check
    f.truncate(f.seek(0, 2) // 3)
build(os.path.join(d, "dependent.sqlite"), n=200)           # two declared sources, one naming the other
HOSTILE = "<img src=x onerror=window.__xss=1>"
con = sqlite3.connect(os.path.join(d, "xss.db"))
con.execute(f'CREATE TABLE "{HOSTILE}" (address TEXT, label TEXT, "<script>window.__xss=1</script>" TEXT)')
con.executemany(f'INSERT INTO "{HOSTILE}" VALUES (?,?,?)',
                [(btc_address(i), HOSTILE, "<script>window.__xss=1</script>") for i in range(15)])
con.commit(); con.close()
with open(os.path.join(c, "normal.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["address", "label", "source"])
    for i in range(40):
        w.writerow([btc_address(i), ("exchange", "ransomware", "mixer")[i % 3], "Src A" if i % 2 else "Src B"])
with open(os.path.join(c, "xss.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["address", "label", "source", HOSTILE])
    for i in range(15):
        w.writerow([btc_address(i), "<script>window.__xss=1</script>", HOSTILE, "=cmd()"])
print("fixtures in", out)
