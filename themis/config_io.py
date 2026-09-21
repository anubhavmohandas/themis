"""Loads every tunable out of themis/config/ instead of burying it in code.

Taxonomy, per-source provenance rules, trust-rule policies and numeric
thresholds all live here as YAML so they can be inspected or overridden
without touching analysis code (mission rule: parameters must be
configurable). Set THEMIS_CONFIG_DIR to point at a different config tree
entirely - e.g. to audit a dataset whose taxonomy or trust rules differ from
the bundled research profile.
"""
from __future__ import annotations
import os, pathlib, functools
import yaml

PKG_CONFIG = pathlib.Path(__file__).resolve().parent / "config"


def config_dir() -> pathlib.Path:
    override = os.environ.get("THEMIS_CONFIG_DIR")
    return pathlib.Path(override) if override else PKG_CONFIG


def _load_yaml(path: pathlib.Path) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


class Config:
    """One immutable snapshot of taxonomy, sources, trust rules and thresholds."""

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.taxonomy = _load_yaml(root / "taxonomy.yml").get("categories", {})
        self.thresholds = _load_yaml(root / "thresholds.yml")
        self.trust_rules = _load_yaml(root / "trust_rules.yml")
        # a custom THEMIS_CONFIG_DIR predating the pre-flight has no preflight.yml: use the bundled one
        # rather than run without the gate
        pf = root / "preflight.yml"
        self.preflight = _load_yaml(pf if pf.exists() else PKG_CONFIG / "preflight.yml")
        notable = root / "notable_roots.yml"
        self.notable_roots = (_load_yaml(notable) or []) if notable.exists() else []
        self.sources = {}
        src_dir = root / "sources"
        if src_dir.is_dir():
            for f in sorted(src_dir.glob("*.yml")):
                cfg = _load_yaml(f)
                sid = cfg.get("id", f.stem)
                self.sources[sid] = cfg


@functools.lru_cache(maxsize=None)
def _cached(root_str: str) -> Config:
    return Config(pathlib.Path(root_str))


def load() -> Config:
    """The active configuration. Cached per config directory for the process
    lifetime; tests that swap THEMIS_CONFIG_DIR should call load.cache_clear()."""
    return _cached(str(config_dir()))


load.cache_clear = _cached.cache_clear  # type: ignore[attr-defined]
