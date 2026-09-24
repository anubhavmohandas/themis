"""EVM-family address/transaction validation (0x + hex), one adapter per chain listed in
config/chains.yml. Stdlib only: Keccak-256 is implemented here because `hashlib` ships
NIST SHA3, which pads differently and gives different digests (EIP-55 needs Keccak).

Validity, precisely:
  * syntax: "0x" followed by exactly 40 hexadecimal characters, nothing else. No trimming,
    no repair: whitespace, zero-width characters or trailing text make a value invalid.
  * EIP-55 is a separate question. An all-lowercase or all-uppercase address does not encode
    a checksum: it is syntactically valid, and `checksum_state` says "not_encoded" (it is NOT
    a failed checksum). A mixed-case address DOES claim a checksum, and one that does not
    match is invalid.
"""
from __future__ import annotations
import re
from .. import config_io
from .base import BlockchainAdapter, register

# fullmatch, never `$`: `$` also matches before a trailing "\n", which would accept "0x...\n"
_ADDR_RE = re.compile(r"0x[0-9a-fA-F]{40}")
_TX_RE = re.compile(r"0x[0-9a-fA-F]{64}")
_MASK = (1 << 64) - 1
_RC = (0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B,
       0x0000000080000001, 0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088,
       0x0000000080008009, 0x000000008000000A, 0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
       0x8000000000008003, 0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008)
_ROT = (0, 1, 62, 28, 27, 36, 44, 6, 55, 20, 3, 10, 43, 25, 39, 41, 45, 15, 21, 8, 18, 2, 61, 56, 14)


def _keccak_f(a: list[int]) -> None:
    for rc in _RC:
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ (((c[(x + 1) % 5] << 1) | (c[(x + 1) % 5] >> 63)) & _MASK) for x in range(5)]
        a[:] = [a[i] ^ d[i % 5] for i in range(25)]
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                r = _ROT[x + 5 * y]
                v = a[x + 5 * y]
                b[y + 5 * ((2 * x + 3 * y) % 5)] = ((v << r) | (v >> (64 - r))) & _MASK if r else v
        a[:] = [b[i] ^ (~b[(i % 5 + 1) % 5 + 5 * (i // 5)] & b[(i % 5 + 2) % 5 + 5 * (i // 5)]) for i in range(25)]
        a[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136
    padded = bytearray(data) + b"\x01"
    padded += b"\x00" * (-len(padded) % rate)
    padded[-1] |= 0x80
    a = [0] * 25
    for off in range(0, len(padded), rate):
        for i in range(rate // 8):
            a[i] ^= int.from_bytes(padded[off + 8 * i: off + 8 * i + 8], "little")
        _keccak_f(a)
    return b"".join(a[i].to_bytes(8, "little") for i in range(4))


def eip55(address_hex: str) -> str:
    """The EIP-55 mixed-case form of 40 hex characters (no 0x)."""
    low = address_hex.lower()
    h = keccak256(low.encode("ascii")).hex()
    return "".join(ch.upper() if ch.isalpha() and int(h[i], 16) >= 8 else ch for i, ch in enumerate(low))


class EvmAdapter(BlockchainAdapter):
    def __init__(self, chain_id: str, display_name: str, aliases: tuple[str, ...]):
        self.id, self.display_name, self.symbol_aliases = chain_id, display_name, aliases

    def checksum_state(self, value: str) -> str | None:
        """None: not an EVM address at all. "not_encoded": all one case, no checksum to
        check. "valid" / "invalid": a mixed-case address, checked against EIP-55."""
        if not isinstance(value, str) or not _ADDR_RE.fullmatch(value):
            return None
        body = value[2:]
        if body.lower() == body or body.upper() == body:
            return "not_encoded"
        return "valid" if eip55(body) == body else "invalid"

    def validate_address(self, value: str) -> bool:
        return self.checksum_state(value) in ("not_encoded", "valid")

    def validate_transaction_hash(self, value: str) -> bool:
        return isinstance(value, str) and bool(_TX_RE.fullmatch(value))

    def normalize_address(self, value: str) -> str:
        """EVM addresses are hex: two spellings differing only in case are one address."""
        return value.strip().lower()


def _register_configured() -> None:
    for chain_id, spec in (config_io.load().chains.get("evm") or {}).items():
        register(EvmAdapter(chain_id, spec["display_name"], tuple(spec.get("aliases", ()))))


_register_configured()
