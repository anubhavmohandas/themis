"""STEP - blockchain adapter contract. A new chain is a new adapter
registered here, never a branch inside the analysis engine."""
from __future__ import annotations
import abc


class BlockchainAdapter(abc.ABC):
    #: short id used in config and reports, e.g. "bitcoin"
    id: str = ""
    display_name: str = ""
    #: lowercase ticker/name aliases, used only by ingest/detect.py to tell
    #: "this chain's data, but not an attribution dataset" (e.g. a price
    #: history CSV with a "symbol" column of "BTC-USD") apart from data with
    #: no crypto signal at all. Never consulted for address validation or
    #: any forensic analysis.
    symbol_aliases: tuple[str, ...] = ()

    @abc.abstractmethod
    def validate_address(self, value: str) -> bool:
        """Is `value` a structurally valid address on this chain (checksum
        included where the chain defines one)? This is a syntax check, not
        an on-chain existence check."""

    @abc.abstractmethod
    def validate_transaction_hash(self, value: str) -> bool:
        ...

    def normalize_address(self, value: str) -> str:
        """Canonical form for deduplication. Default: no case-folding,
        since Bitcoin's base58 addresses are case-sensitive; a chain whose
        addresses are case-insensitive (e.g. Ethereum's hex form) overrides
        this."""
        return value.strip()

    def network_metadata(self) -> dict:
        return dict(id=self.id, display_name=self.display_name)


_REGISTRY: dict[str, BlockchainAdapter] = {}


def register(adapter: BlockchainAdapter) -> None:
    _REGISTRY[adapter.id] = adapter


def get(chain_id: str) -> BlockchainAdapter | None:
    return _REGISTRY.get(chain_id)


def all_adapters() -> dict[str, BlockchainAdapter]:
    return dict(_REGISTRY)


def alias_map() -> dict[str, str]:
    """lowercase symbol/name alias -> chain id, over every registered adapter.
    Shared by ingest/preflight.py and ingest/relational.py so a per-row
    "chain"/"blockchain" column resolves identically wherever it is read."""
    return {a.lower(): cid for cid, ad in _REGISTRY.items() for a in ad.symbol_aliases}
