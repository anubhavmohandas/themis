"""Bitcoin address/transaction validation - base58check (P2PKH/P2SH) and
bech32/bech32m (native segwit, including taproot). Reference algorithms
(BIP-173/BIP-350) reimplemented against stdlib `hashlib` only; no network
calls, no third-party address libraries. Mainnet only.

# occam: mainnet-only prefixes; add testnet (m/n/2/tb1...) if a testnet
# dataset shows up - the decode logic below is network-agnostic already.
"""
from __future__ import annotations
import hashlib, re
from .base import BlockchainAdapter, register

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_TXID_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_CONST = 1
_BECH32M_CONST = 0x2bc830a3


def _b58decode(s: str) -> bytes | None:
    n = 0
    for ch in s:
        idx = _B58_ALPHABET.find(ch)
        if idx == -1:
            return None
        n = n * 58 + idx
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + body


def _validate_base58check(address: str) -> bool:
    if not address or not (25 <= len(address) <= 35):
        return False
    raw = _b58decode(address)
    if raw is None or len(raw) != 25:
        return False
    payload, checksum = raw[:-4], raw[-4:]
    digest = hashlib.sha256(hashlib.sha256(payload).digest()).digest()
    return digest[:4] == checksum and payload[0] in (0x00, 0x05)   # P2PKH, P2SH


def _bech32_polymod(values) -> int:
    gen = (0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3)
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if (b >> i) & 1 else 0
    return chk


def _bech32_hrp_expand(hrp: str):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_decode(bech: str):
    """Returns (hrp, data, const) where const identifies which checksum
    constant validated - BIP-350 requires the caller to then check that
    constant against the witness version (v0 -> bech32, v1+ -> bech32m);
    decoding alone does not establish that."""
    if any(ord(c) < 33 or ord(c) > 126 for c in bech):
        return None, None, None
    if bech.lower() != bech and bech.upper() != bech:
        return None, None, None
    bech = bech.lower()
    pos = bech.rfind("1")
    if pos < 1 or pos + 7 > len(bech) or len(bech) > 90:
        return None, None, None
    hrp, data_part = bech[:pos], bech[pos + 1:]
    if not all(c in _BECH32_CHARSET for c in data_part):
        return None, None, None
    data = [_BECH32_CHARSET.index(c) for c in data_part]
    values = _bech32_hrp_expand(hrp) + data
    const = _bech32_polymod(values)
    if const not in (_BECH32_CONST, _BECH32M_CONST):
        return None, None, None
    return hrp, data[:-6], const


def _convertbits(data, frombits: int, tobits: int, pad: bool = True):
    acc, bits, ret = 0, 0, []
    maxv, max_acc = (1 << tobits) - 1, (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def _validate_segwit(address: str) -> bool:
    hrp, data, const = _bech32_decode(address)
    if hrp != "bc" or not data:
        return False
    witver, witprog = data[0], _convertbits(data[1:], 5, 8, False)
    if witprog is None or not (2 <= len(witprog) <= 40) or witver > 16:
        return False
    if witver == 0 and len(witprog) not in (20, 32):
        return False
    # BIP-350: witness v0 must be encoded Bech32, v1+ must be Bech32m
    required = _BECH32_CONST if witver == 0 else _BECH32M_CONST
    return const == required


class BitcoinAdapter(BlockchainAdapter):
    id = "bitcoin"
    display_name = "Bitcoin"
    symbol_aliases = ("btc", "xbt", "bitcoin")

    def validate_address(self, value: str) -> bool:
        if not value:
            return False
        value = value.strip()
        if value[:1] in ("1", "3"):
            return _validate_base58check(value)
        if value.lower().startswith("bc1"):
            return _validate_segwit(value)
        return False

    def validate_transaction_hash(self, value: str) -> bool:
        return bool(value) and bool(_TXID_RE.match(value.strip()))


register(BitcoinAdapter())
