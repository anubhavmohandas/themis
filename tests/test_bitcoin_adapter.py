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

    def test_testnet_bech32_rejected_by_mainnet_only_adapter(self):
        # the official BIP-173 testnet test vector for the same witness
        # program as test_valid_segwit_v0's mainnet one - correctly-formed
        # and correctly-checksummed, wrong network only.
        self.assertFalse(a.validate_address("tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx"))

    def test_witness_version_above_16_rejected(self):
        # BIP-173 caps witness versions at 16 (encoded 0-16); version 17 is
        # a structurally valid bech32 string with a checksum THEMIS's own
        # encoder produced, but must still be rejected.
        self.assertFalse(a.validate_address("bc13w508d6qejxtdg4y5r3zarvary0c5xw7kxflzvg"))

    def test_v0_with_21_byte_program_rejected(self):
        # BIP-141 restricts witness v0 programs to exactly 20 (P2WPKH) or
        # 32 (P2WSH) bytes; 21 is within the generic 2-40 byte range but
        # invalid specifically for v0.
        self.assertFalse(a.validate_address("bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqj9pecr"))

    def test_v0_below_minimum_program_length_rejected(self):
        self.assertFalse(a.validate_address("bc1qqqglchaj"))

    def test_v1_with_20_byte_program_is_structurally_valid(self):
        # BIP-350's witness-version-agnostic length rule (2-40 bytes)
        # applies here, not BIP-341's taproot-specific 32-byte rule - v1+
        # only gets the narrower 20/32 restriction when witver == 0.
        # Structurally valid per the spec THEMIS implements even though a
        # real Taproot output is always 32 bytes; locked in so this isn't
        # "fixed" into a false rejection by a future reader.
        self.assertTrue(a.validate_address("bc1pw508d6qejxtdg4y5r3zarvary0c5xw7kj9wkru"))

    def test_invalid_base58_character_rejected(self):
        # '0' is not in the base58 alphabet (visually confusable with 'O').
        self.assertFalse(a.validate_address("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN0"))

    def test_valid_checksum_wrong_network_version_byte_rejected(self):
        # a real Bitcoin testnet P2PKH address (version byte 0x6f) with a
        # genuinely valid checksum - must still be rejected: THEMIS only
        # accepts mainnet version bytes 0x00 (P2PKH) / 0x05 (P2SH).
        self.assertFalse(a.validate_address("mipcBbFg9gMiCh81Kj8tqqdgoZub1ZJRfn"))

    def test_too_short_base58_rejected(self):
        self.assertFalse(a.validate_address("1BvBMSEYstWet"))

    def test_too_long_base58_rejected(self):
        self.assertFalse(a.validate_address("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2" + "A" * 20))


if __name__ == "__main__":
    unittest.main(verbosity=2)
