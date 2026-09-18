"""STEP 37 - address validation tests. Real mainnet vectors: P2PKH, P2SH,
segwit v0 and taproot (bech32m), plus deliberately corrupted checksums."""
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from themis.chains.bitcoin import BitcoinAdapter

a = BitcoinAdapter()


class TestBitcoinAddress(unittest.TestCase):
    def test_valid_p2pkh(self):
        self.assertTrue(a.validate_address("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"))

    def test_valid_p2sh(self):
        self.assertTrue(a.validate_address("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"))

    def test_valid_segwit_v0(self):
        self.assertTrue(a.validate_address("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"))

    def test_valid_taproot_bech32m(self):
        self.assertTrue(a.validate_address(
            "bc1p5d7rjq7g6rdk2yhzks9smlaqtedr4dekq08ge8ztwac72sfr9rusxg3297"))

    def test_bad_checksum_base58_rejected(self):
        self.assertFalse(a.validate_address("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN3"))

    def test_bad_checksum_segwit_rejected(self):
        self.assertFalse(a.validate_address("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5"))

    def test_garbage_rejected(self):
        self.assertFalse(a.validate_address("not-an-address"))

    def test_empty_rejected(self):
        self.assertFalse(a.validate_address(""))

    def test_txid_valid(self):
        self.assertTrue(a.validate_transaction_hash("a" * 64))

    def test_txid_wrong_length_rejected(self):
        self.assertFalse(a.validate_transaction_hash("a" * 63))

    def test_txid_non_hex_rejected(self):
        self.assertFalse(a.validate_transaction_hash("z" * 64))

    def test_v0_encoded_as_bech32m_rejected(self):
        # same witness v0 program as test_valid_segwit_v0, re-encoded with the
        # bech32m checksum constant instead of bech32 - BIP-350 forbids this
        self.assertFalse(a.validate_address("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kemeawh"))

    def test_v1_encoded_as_bech32_rejected(self):
        # same witness v1 (taproot) program as test_valid_taproot_bech32m,
        # re-encoded with the bech32 checksum constant instead of bech32m
        self.assertFalse(a.validate_address(
            "bc1p5d7rjq7g6rdk2yhzks9smlaqtedr4dekq08ge8ztwac72sfr9rusn5pxqu"))

    def test_all_uppercase_segwit_accepted(self):
        # BIP-173: a bech32 string may be entirely lowercase or entirely
        # uppercase - both are valid, only *mixed* case is forbidden.
        self.assertTrue(a.validate_address("BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4"))

    def test_mixed_case_segwit_rejected(self):
        addr = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
        mixed = addr[:5] + addr[5:].upper()
        self.assertFalse(a.validate_address(mixed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
