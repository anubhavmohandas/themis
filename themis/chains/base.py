"""STEP - blockchain adapter contract. A new chain is a new adapter
registered here, never a branch inside the analysis engine."""
from __future__ import annotations
import abc, re


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


def _normalize_chain_name(value: str) -> str:
    """"Polygon-Mainnet" -> "polygon": lowercase, non-alphanumeric runs -> "_", and one
    configured network suffix (config/chains.yml network_suffixes) dropped. A testnet
    name keeps its "testnet" token and so never resolves."""
    from .. import config_io
    name = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    for suffix in config_io.load().chains.get("network_suffixes", []):
        if name.endswith("_" + suffix):
            return name[: -len(suffix) - 1]
    return name


def resolve_chain(value: str) -> str | None:
    """The registered chain id a data file's chain name refers to, or None. Never guesses."""
    return alias_map().get(_normalize_chain_name(value))
