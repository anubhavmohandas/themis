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
# a synthetic multi-chain file: the chain is stated per row, some identifiers are invalid on their chain
# (lowercased Base58, a URL-ish string), and each row may carry several labels
import hashlib
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def _btc(i):
    payload = b"\x00" + hashlib.sha256(f"e2e-{i}".encode()).digest()[:20]
    raw = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n, out = int.from_bytes(raw, "big"), ""
    while n:
        n, r = divmod(n, 58); out = _B58[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out
with open(os.path.join(c, "multichain.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["chain", "address", "categories", "entity", "source"])
    for i in range(60):
        w.writerow(["ethereum_mainnet", "0x" + hashlib.sha256(f"eth-{i}".encode()).hexdigest()[:40],
                    ["exchange", "mixer", "exchange,mixer", "scam"][i % 4], "acme" if i % 3 == 0 else "", ["heuristic", "external", "ground_truth"][i % 3]])
    for i in range(20):
        w.writerow(["bitcoin_mainnet", _btc(i), "exchange", "", "external"])
    for i in range(30):
        w.writerow(["bitcoin_mainnet", _btc(100 + i).lower(), "exchange", "", "external"])   # case-folded: fails its checksum

with open(os.path.join(c, "xss.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["address", "label", "source", HOSTILE])
    for i in range(15):
        w.writerow([btc_address(i), "<script>window.__xss=1</script>", HOSTILE, "=cmd()"])
print("fixtures in", out)
