from .base import BlockchainAdapter, register, get, all_adapters, alias_map   # noqa: F401
from . import bitcoin   # noqa: F401  (registers itself on import)
