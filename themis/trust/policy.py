"""STEP 20/21 - trust-rule policies as reusable objects, loaded from
config/trust_rules.yml. A policy is just a name, a label, an aggregation
mode, and a list of eligibility predicates - nothing here knows what task
will consume its output.
"""
from __future__ import annotations
from . import predicates
from .. import config_io


def _predicate_spec(spec):
    if isinstance(spec, str):
        return predicates.REGISTRY[spec], {}
    (name, params), = spec.items()
    return predicates.REGISTRY[name], dict(params or {})


class Policy:
    def __init__(self, name: str, label: str, aggregation: str, eligibility: list):
        self.name = name
        self.label = label
        self.aggregation = aggregation
        self._predicates = [_predicate_spec(p) for p in eligibility]

    def eligible(self, claims, context) -> list:
        return [c for c in claims
                if all(fn(c, context, **params) for fn, params in self._predicates)]


def load_policies(trust_rules_cfg: dict | None = None):
    """Returns (policies: {name: Policy}, baseline_name)."""
    cfg = trust_rules_cfg if trust_rules_cfg is not None else config_io.load().trust_rules
    policies = {name: Policy(name, p.get("label", name), p["aggregation"], p.get("eligibility", []))
                for name, p in cfg.get("policies", {}).items()}
    return policies, cfg.get("baseline")
