from .base import BlockchainAdapter, register, get, all_adapters, alias_map, resolve_chain   # noqa: F401
from . import bitcoin, evm   # noqa: F401  (each registers its adapters on import)
