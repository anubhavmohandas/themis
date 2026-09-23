"""Case-study demo fixture (docs/case_studies/walletclassification.md): a
small SYNTHETIC database reproducing the same evidential pattern as the
WalletClassification case study - valid addresses, plausible labels, and two
declared-source strings where one textually names the other - without
redistributing any real third-party record.

Run from the repository root: python scripts/generate_case_study_demo_db.py [OUT.sqlite]
Then open the result through the Database workflow (or the sqlite API)
exactly like any other file. Extraction will show unresolved provenance and
a documented dependency between the two declared-source strings, never a
fabricated independent-roots count.
"""
import hashlib, sqlite3, sys

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _demo_address(i: int) -> str:
    """A syntactically valid P2PKH address for no known key (checksum
    computed) - the same construction tests/test_preflight.py:btc_address
    uses, so a demo row is indistinguishable, by validity alone, from a real
    one. That is the point of the case study: validity is not the question."""
    payload = b"\x00" + hashlib.sha256(f"themis-case-study-demo-{i}".encode()).digest()[:20]
    raw = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n, out = int.from_bytes(raw, "big"), ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


LABELS = ["exchange", "mixer", "ransomware"]
# One declared-source string textually names the other - a synthetic stand-in
# for BABD-13 documenting WalletExplorer as one of its own sources. THEMIS's
# dependency_candidates() flags this as a potential/documented dependency; it
# is never applied to any independence or corroboration count.
SOURCES = ["DemoCorpus-13", "DemoCorpus-13 (labels via DemoExplorer)"]


def build(path: str, n: int = 200) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE wallets (address TEXT PRIMARY KEY, label TEXT, source TEXT, first_seen TEXT)")
    con.executemany("INSERT INTO wallets VALUES (?,?,?,?)", [
        (_demo_address(i), LABELS[i % len(LABELS)], SOURCES[i % len(SOURCES)], f"2024-0{1 + i % 9}-01")
        for i in range(n)
    ])
    con.commit()
    con.close()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "case_study_demo.sqlite"
    build(out)
    print(f"wrote {out}")
