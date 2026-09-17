"""STEP 27/29/38 - one canonical result object. The CLI, JSON export and any
future UI all read from what this module assembles, so no statistic is ever
computed a second, possibly-divergent way somewhere else. Also builds the
STEP 38 audit trail: what code, what config and what input produced a result,
so a run can be reproduced or challenged.
"""
from __future__ import annotations
import datetime, hashlib, json

from . import config_io, analysis, reliability


def _hash_file(path) -> str | None:
    if not path:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_config() -> str:
    cfg = config_io.load()
    blob = json.dumps(dict(taxonomy=cfg.taxonomy, thresholds=cfg.thresholds,
                           trust_rules=cfg.trust_rules, sources=cfg.sources,
                           notable_roots=cfg.notable_roots),
                      sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def audit_trail(input_path=None, parameters: dict | None = None, warnings: list | None = None) -> dict:
    from . import __version__   # local: avoids import-order coupling to themis/__init__.py
    return dict(
        software_version=__version__,
        analysis_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        input_file=str(input_path) if input_path else None,
        input_file_hash=_hash_file(input_path),
        config_hash=_hash_config(),
        config_dir=str(config_io.config_dir()),
        parameters=parameters or {},
        warnings=warnings or [],
    )


def build_corpus_report(corpus, include_bootstrap: bool = False, bootstrap_kwargs: dict | None = None,
                        input_path=None) -> dict:
    """STEP 27 - the canonical result for a corpus already fully loaded
    (bundled sample or a full local build): every figure `themis audit` /
    `drift` print, assembled once."""
    agreement = analysis.agreement(corpus)
    independence = analysis.independence(corpus)
    kappa = analysis.cohen_kappa(corpus)
    fresh = analysis.freshness(corpus.claims)
    uncertainty = analysis.bootstrap(corpus, **(bootstrap_kwargs or {})) if include_bootstrap else None

    validation = dict(n_input=corpus.n_claims, n_valid=corpus.n_claims,
                      n_rejected=0, rejected_by_reason={})
    profile = reliability.build_profile(validation, agreement=agreement, independence=independence,
                                        freshness=fresh, kappa=kappa)

    limitations = []
    if corpus.sample_note:
        limitations.append(corpus.sample_note)

    return dict(
        dataset_summary=dict(n_claims=corpus.n_claims, n_addresses=corpus.n_addresses,
                             sources=corpus.source_sizes()),
        agreement=agreement, independence=independence, kappa=kappa,
        freshness=fresh, uncertainty=uncertainty, reliability_profile=profile,
        limitations=limitations, audit_trail=audit_trail(input_path=input_path),
    )


def to_json(result: dict, path: str) -> None:
    with open(path, "w") as f:
        json.dump(result, f, indent=1, default=str)
