"""Generic regressions for what an unseen multi-chain attribution file exposed. Every fixture here
is synthetic and names no real dataset: each test pins a rule that must hold for ANY file.

  * EVM identifiers are validated strictly (no repair), EIP-55 is a separate question
  * a chain name resolves through a generic normaliser, never guessed
  * what a column is profiled on does not depend on the order of the rows
  * a chosen mapping is still judged on the column's values
  * the chain may be stated per row; the same string on two chains is two subjects
  * a label cell is split only when the column itself shows it is a token list
  * an evidence-class column is not a source, an entity is not evidence, rows/addresses/claims differ
  * a file that looks like attribution data is not called "not attribution data"
"""
import csv, hashlib, io, json, os, pathlib, random, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from themis import chains, corpus as corpus_mod, provenance, target_audit
from themis.chains.evm import keccak256
from themis.ingest import detect, gating, pipeline, preflight, validate
from test_preflight import btc_address, to_csv, write_tmp


def evm(i: int) -> str:
    return "0x" + hashlib.sha256(f"evm-{i}".encode()).hexdigest()[:40]


def run(rows, fields, **kw):
    return preflight.run(rows, fields, total_rows=len(rows), **kw)


def ingest(rows, fields, **kw):
    path = write_tmp(to_csv(rows, fields))
    try:
        return pipeline.ingest(path, "synthetic_upload", reference=None, **kw)
    finally:
        os.remove(path)


class TestEvmIdentifiers(unittest.TestCase):
    eth = chains.get("ethereum")

    def test_keccak_matches_the_published_vectors(self):
        self.assertEqual(keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(keccak256(b"abc").hex(), "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_lowercase_is_valid_and_has_no_checksum_to_fail(self):
        a = "0xde709f2102306220921060314715629080e2fb77"
        self.assertTrue(self.eth.validate_address(a))
        self.assertEqual(self.eth.checksum_state(a), "not_encoded")      # absent, NOT failed

    def test_mixed_case_is_checked_against_eip55(self):
        good = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"               # EIP-55 test vector
        self.assertEqual(self.eth.checksum_state(good), "valid")
        bad = "0x5AAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
        self.assertEqual(self.eth.checksum_state(bad), "invalid")
        self.assertFalse(self.eth.validate_address(bad))

    def test_nothing_is_repaired_or_tolerated(self):
        ok = evm(1)
        for bad in (ok + "\n", ok + " ", "\u200b" + ok, ok + "\u200b", ok[:-1], ok + "0", ok.replace("0x", "0X", 1),
                    ok + "') and 1=1--", "3976", "protocol:name", ""):
            with self.subTest(bad=bad[:30]):
                self.assertFalse(self.eth.validate_address(bad))

    def test_the_same_string_is_valid_on_every_evm_chain_so_the_chain_must_be_stated(self):
        evm_ids = [cid for cid in chains.all_adapters() if cid != "bitcoin"]
        self.assertGreaterEqual(len(evm_ids), 4)
        self.assertTrue(all(chains.get(c).validate_address(evm(2)) for c in evm_ids))
        rows = [{"address": evm(i), "category": "exchange"} for i in range(40)]
        pf = run(rows, ["address", "category"])
        self.assertEqual(pf["chain"]["status"], "ambiguous")             # never defaulted to one of them
        self.assertIn("chain_required", {b["code"] for b in pf["blockers"]})


class TestChainNames(unittest.TestCase):
    def test_names_resolve_generically(self):
        for name, want in [("ethereum", "ethereum"), ("Ethereum_Mainnet", "ethereum"), ("Polygon-Mainnet", "polygon"),
                           ("bnb_chain_mainnet", "bnb_smart_chain"), ("BTC", "bitcoin"), ("bitcoin mainnet", "bitcoin"),
                           ("avalanche_c_chain", "avalanche_c")]:
            self.assertEqual(chains.resolve_chain(name), want, name)

    def test_unknown_and_testnet_names_never_resolve(self):
        for name in ("solana", "ethereum_testnet", "goerli", "", "mainnet"):
            self.assertIsNone(chains.resolve_chain(name), name)


class TestChainPerRow(unittest.TestCase):
    fields = ["chain", "address", "category"]

    def test_a_reference_source_on_another_chain_never_matches_by_string(self):
        s = "ransomwhere"                                                 # a bundled source that declares chain: bitcoin
        ref = corpus_mod.Corpus([dict(address=evm(7), source=s, raw_label="ransomware", canon="ransomware",
                                      polarity="illicit", prov_family="", lastmod="", heuristic="", subcat="")])
        self.assertEqual(len(ref.for_subject("ethereum", evm(7))), 0)
        self.assertEqual(len(ref.for_subject("bitcoin", evm(7))), 1)
        claim = lambda ch: dict(address=evm(7), blockchain=ch, source="up", canon="exchange", raw_label="exchange",
                                polarity="licit", prov_family="", lastmod="", heuristic="unknown", subcat="")
        eth = target_audit.audit_target_against_reference([claim("ethereum")], ref)
        self.assertEqual(eth["profile"]["reference_comparability"]["comparable"], 0)
        btc = target_audit.audit_target_against_reference([claim("bitcoin")], ref)
        self.assertEqual(btc["profile"]["reference_comparability"]["comparable"], 1)





if __name__ == "__main__":
    unittest.main()
