"""STEP 18 - the provenance lineage graph: claims -> datasets -> declared
sources -> resolved/unresolved roots. Built straight from config/sources/,
so a new source only means a new node here, never new graph-drawing code.
No edge is asserted as fact beyond what `kind` says: DECLARED (the config
states this root outright), INFERRED (decoded from an undocumented code, or
a residue/fallback guess), UNKNOWN (no provenance rule at all).
"""
from __future__ import annotations
from . import config_io

_cfg = config_io.load()


def _root_node(nodes, seen, root, resolved):
    rid = f"root:{root}"
    if rid not in seen:
        nodes.append(dict(id=rid, type="root" if resolved else "root_unresolved", label=root))
        seen.add(rid)
    return rid


def lineage_graph(sources: dict | None = None) -> dict:
    sources = sources if sources is not None else _cfg.sources
    nodes = [dict(id="claims", type="claims", label="Claims")]
    edges = []
    seen_roots: set[str] = set()

    for sid, cfg in sorted(sources.items()):
        did = f"dataset:{sid}"
        nodes.append(dict(id=did, type="dataset", label=cfg.get("display_name", sid)))
        edges.append(dict(source="claims", target=did, kind="DECLARED"))

        prov = cfg.get("provenance")
        if not prov:
            rid = _root_node(nodes, seen_roots, f"{sid}:unresolved", False)
            edges.append(dict(source=did, target=rid, kind="UNKNOWN"))
            continue

        mode = prov["mode"]
        if mode == "fixed_root":
            rid = _root_node(nodes, seen_roots, prov["root"], prov.get("resolved", False))
            edges.append(dict(source=did, target=rid, kind="DECLARED"))
        elif mode == "field_map":
            for entry in (prov.get("map") or {}).values():
                rid = _root_node(nodes, seen_roots, entry["root"], entry.get("resolved", False))
                edges.append(dict(source=did, target=rid, kind="DECLARED"))
            d = prov.get("default") or {}
            if d.get("root"):
                rid = _root_node(nodes, seen_roots, d["root"], d.get("resolved", False))
                edges.append(dict(source=did, target=rid, kind="INFERRED"))
        elif mode in ("contains_rules", "substring_map"):
            for rule in prov.get(mode, []):
                rid = _root_node(nodes, seen_roots, rule["root"], rule.get("resolved", False))
                edges.append(dict(source=did, target=rid, kind="INFERRED"))
            for root in (prov.get("residue_prefix_map") or {}).values():
                rid = _root_node(nodes, seen_roots, root, prov.get("residue_resolved", True))
                edges.append(dict(source=did, target=rid, kind="INFERRED"))
            tmpl = prov.get("fallback_template", "")
            if tmpl:
                label = tmpl if "{" not in tmpl else tmpl.split("{", 1)[0] + "*"
                rid = _root_node(nodes, seen_roots, label, prov.get("fallback_resolved", False))
                edges.append(dict(source=did, target=rid, kind="INFERRED"))

    return dict(nodes=nodes, edges=edges)
