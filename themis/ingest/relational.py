"""Multi-table SQLite ingestion: table-role candidates, relationship
discovery, joined streaming extraction, dataset profiling, and provenance/
conflict classification for claims that were assembled from more than one
table.

Nothing here loads a table whole. `iter_joined_rows` streams a single SQL
JOIN query in bounded chunks (`sqlite_source`'s `fetchmany` pattern); the
schema-mapping, validation and claim-normalization logic already built for a
single table (preflight.py, chains, ingest/claims.py) is reused unchanged -
a joined row is, to those functions, just a row with more columns, each
named by an unambiguous `table__column` alias.

    inspect -> candidate_roles -> infer_relationships -> (user confirms a
    JoinSpec) -> joined sample -> preflight.run -> extract -> profile_dataset
    -> provenance_states -> conflicts

`extract()` returns the same result shape as `ingest.pipeline.ingest()`, so
every downstream page/route (trust, provenance, conflicts, export) built for
an uploaded CSV works on a relationally-extracted SQLite claim set with no
changes.
"""
from __future__ import annotations
import re, sqlite3, time
from collections.abc import Iterator

from .. import chains, config_io, provenance as _provenance, taxonomy
from ..errors import InputError
from . import claims as _claims, gating as _gating, preflight as _preflight, sqlite_source as _sq
from .pipeline import sha256_file as _sha256_file

_quote = _sq._quote

#: sha-256 of a multi-GB database is a full read; cache it per (path, size,
#: mtime) for this process's lifetime so re-running the same file (a second
#: stage of the same analysis, or a re-run after a table/mapping change) does
#: not re-hash it. Section 12's "resumable" requirement without a persisted
#: job store: this cache is memory-only, deterministic, and never fakes a
#: result - a changed file (new mtime/size) always re-hashes.
_sha256_cache: dict[tuple[str, int, float], str] = {}


def _cached_sha256(path: str) -> str:
    import os as _os
    st = _os.stat(path)
    key = (path, st.st_size, st.st_mtime)
    if key not in _sha256_cache:
        _sha256_cache.clear()   # one entry: the file just hashed is the one about to be reused
        _sha256_cache[key] = _sha256_file(path)
    return _sha256_cache[key]


def cfg() -> dict:
    return config_io.load().preflight["sqlite"]


#: Optional, free-text context an analyst supplies about an analysis's own
#: evidential standing - e.g. "this database is a recovered subset of a
#: truncated original, so its source labels cannot be treated as independent
#: roots." THEMIS never infers these values from data; it only carries and
#: displays what the caller asserts. Absent for an ordinary dataset - never
#: required, never scored.
CASE_METADATA_FIELDS = ("analysis_origin", "integrity_status", "recovery_status",
                        "source_identity_status", "provenance_resolution_status", "limitations")


#: control characters other than tab / newline / carriage return: never legitimate in a note a person wrote
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _validate_case_metadata(case_metadata: dict | None) -> dict | None:
    """Descriptive text only: known field names and text values of bounded length with no
    control characters (markup and newlines are fine - they are only ever rendered as text).
    An empty value is no value; a request whose every value is empty carries no metadata."""
    if not case_metadata:
        return None
    unknown = sorted(set(case_metadata) - set(CASE_METADATA_FIELDS))
    if unknown:
        raise InputError(f"unknown case_metadata field(s): {', '.join(unknown)} "
                         f"(allowed: {', '.join(CASE_METADATA_FIELDS)})")
    limit = cfg()["case_metadata_max_chars"]
    out = {}
    for field, value in case_metadata.items():
        if value is None:
            continue
        if not isinstance(value, str):
            raise InputError(f"case_metadata field {field!r} must be text")
        if len(value) > limit:
            raise InputError(f"case_metadata field {field!r} is longer than {limit:,} characters")
        if _CONTROL_CHARS.search(value):
            raise InputError(f"case_metadata field {field!r} contains control characters")
        if value.strip():
            out[field] = value
    return out or None


# --------------------------------------------------------------- table roles
def candidate_roles(path: str, sample_size: int | None = None) -> list[dict]:
    """For every table: does it look like a claim-subject/attribution table
    (a `preflight.run` pass over its own sample says so already - the same
    schema detection a single-table upload gets), or - being small, with no
    subject/label of its own - a lookup/provenance table (labels, sources)?
    Never a guess from the table's name."""
    c = cfg()
    n = sample_size or _preflight.cfg()["sample_size"]
    out = []
    for t in _sq.list_tables(path, count=True):
        if t["kind"] != "table":
            continue
        name = t["table"]
        sample, names = _sq.sample_rows(path, name, n)
        pf = _preflight.run(sample, names, input_type="sqlite", table=name, total_rows=t["n_rows"])
        subject = pf["subject"]
        label = next((r for r in pf["columns"]
                     if r["semantic_type"] in ("attribution_label", "attribution_category")
                     and r["status"] != "invalid"), None)
        small = (t["n_rows"] or 0) <= c["lookup_table_max_rows"]
        pk_cols = [col["name"] for col in _sq.columns(path, name) if col["primary_key"]]
        if subject and subject["status"] != "invalid":
            role, why = "claim_subject", (f"a valid claim-subject column ('{subject['column']}', "
                                          f"{pf['dataset_type_label'].lower()})")
            confidence = subject["confidence"] or 0.0
        elif label:
            role, why = "attribution", f"an attribution label/category column ('{label['column']}')"
            confidence = label["confidence"] or 0.0
        elif small and pk_cols:
            role, why = "lookup_or_provenance", (
                f"small ({t['n_rows'] if t['n_rows'] is not None else 'unknown'} rows), keyed by "
                f"{', '.join(pk_cols)}, with no claim-subject or attribution column of its own")
            confidence = c["lookup_role_confidence"]
        else:
            role, why = "unknown", "no claim-subject, attribution, or small-lookup shape was detected"
            confidence = 0.0
        out.append(dict(table=name, role=role, confidence=round(confidence, 4), reason=why,
                        n_rows=t["n_rows"], n_columns=t["n_columns"], preflight_summary=dict(
                            dataset_type=pf["dataset_type"], dataset_type_label=pf["dataset_type_label"])))
    return sorted(out, key=lambda r: (-r["confidence"], r["table"]))


# ---------------------------------------------------------- relationships
def _sample_distinct_share(sample: list[str]) -> float:
    return len(set(sample)) / len(sample) if sample else 0.0


def infer_relationships(path: str, sample_size: int = 200) -> list[dict]:
    """Declared foreign keys (confidence 1.0, kind "declared"), plus
    undeclared relationships proposed only when both columns normalize to the
    same name AND the referenced column is unique enough over its sample to
    plausibly be a key - never from name alone, and never claimed as fact."""
    c = cfg()
    tables = [t["table"] for t in _sq.list_tables(path, count=False) if t["kind"] == "table"]
    out = []
    cols_by_table = {t: _sq.columns(path, t) for t in tables}
    for t in tables:
        for fk in _sq.foreign_keys(path, t):
            if fk["table"] in cols_by_table:
                out.append(dict(from_table=t, from_column=fk["from_column"], to_table=fk["table"],
                                to_column=fk["to_column"], kind="declared", confidence=1.0,
                                reason="PRAGMA foreign_key_list"))
    declared = {(r["from_table"], r["from_column"]) for r in out}
    samples: dict[tuple[str, str], list[str]] = {}
    for a in tables:
        for ca in cols_by_table[a]:
            if (a, ca["name"]) in declared:
                continue
            for b in tables:
                if a == b:
                    continue
                for cb in cols_by_table[b]:
                    if _preflight._norm(ca["name"]) != _preflight._norm(cb["name"]):
                        continue
                    key = (b, cb["name"])
                    if key not in samples:
                        rows, _ = _sq.sample_rows(path, b, sample_size)
                        samples[key] = [r[cb["name"]] for r in rows if r[cb["name"]] != ""]
                    if _sample_distinct_share(samples[key]) >= c["inferred_relationship_min_distinct_share"] \
                            and cb["primary_key"]:
                        out.append(dict(from_table=a, from_column=ca["name"], to_table=b, to_column=cb["name"],
                                        kind="inferred", confidence=c["inferred_relationship_confidence"],
                                        reason=f"same normalized column name; '{b}.{cb['name']}' is a primary key "
                                               f"and looks unique over its sample"))
    return out


# ------------------------------------------------------------- join spec
def _table_names(spec: dict) -> list[str]:
    return [spec["driving_table"]] + [j["table"] for j in spec.get("joins", [])]


def validate_join_spec(path: str, spec: dict) -> dict:
    """Structural + performance validation of a JoinSpec. Raises ValueError
    for a spec that cannot be run at all (unknown table/column, a join whose
    local table was never introduced); returns `{ok, warnings}` for one that
    can run but may be slow (an unindexed join key on a large table)."""
    if "driving_table" not in spec:
        raise InputError("a join spec needs a driving_table")
    tables = _table_names(spec)
    all_counts = {x["table"]: x["n_rows"] for x in _sq.list_tables(path, count=True)}
    cols_by_table = {}
    row_counts = {}
    for t in tables:
        cols_by_table[t] = {c["name"]: c for c in _sq.columns(path, t)}   # raises ValueError if t doesn't exist
        row_counts[t] = all_counts.get(t)

    introduced = {spec["driving_table"]}
    warnings = []
    for j in spec.get("joins", []):
        local_table = j.get("local_table", spec["driving_table"])
        if local_table not in introduced:
            raise InputError(f"join on {j['table']!r} uses local_table {local_table!r}, "
                             "which is not the driving table or an earlier join")
        for side, table, col in ((local_table, local_table, j["local_key"]), (j["table"], j["table"], j["foreign_key"])):
            if col not in cols_by_table.get(table, {}):
                raise InputError(f"{table}.{col} does not exist")
        idx_cols = {c for ix in _sq.indexes(path, j["table"]) for c in ix["columns"]}
        pk_cols = {n for n, c in cols_by_table[j["table"]].items() if c["primary_key"]}
        if j["foreign_key"] not in idx_cols and j["foreign_key"] not in pk_cols and (row_counts.get(j["table"]) or 0) > cfg()["unindexed_join_warn_rows"]:
            warnings.append(f"'{j['table']}.{j['foreign_key']}' has no index or primary key: this join will scan "
                            f"the table ({row_counts[j['table']]:,} rows) for every driving-table row")
        introduced.add(j["table"])
    return dict(ok=True, warnings=warnings)


def _select_list(con, table: str, alias_prefix: str) -> tuple[list[str], str | None]:
    """Every column of `table`, each aliased `table__column`, plus the row
    identity expression to use for provenance (rowid, or the PK columns for a
    WITHOUT ROWID table)."""
    cols = con.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    # every identifier goes through _quote: a column called  a"b  (or worse) is data from the file, never SQL
    select = [f'{_quote(table)}.{_quote(c[1])} AS {_quote(f"{alias_prefix}__{c[1]}")}' for c in cols]
    rowid_alias = _quote(f"{alias_prefix}__rowid")
    try:
        con.execute(f"SELECT rowid FROM {_quote(table)} LIMIT 0")
        return select, f"{_quote(table)}.rowid AS {rowid_alias}"
    except sqlite3.OperationalError:     # WITHOUT ROWID table or a view: identify a row by its first key column
        pk = [c[1] for c in cols if c[5]]
        return select, None if not pk else f"{_quote(table)}.{_quote(pk[0])} AS {rowid_alias}"


def _build_sql(con, spec: dict) -> tuple[str, list[str]]:
    driving = spec["driving_table"]
    select_all: list[str] = []
    join_clauses: list[str] = []
    sel, ident = _select_list(con, driving, driving)
    select_all += sel + ([ident] if ident else [])
    for j in spec.get("joins", []):
        local_table = j.get("local_table", driving)
        jtype = "LEFT" if j.get("type", "left") == "left" else "INNER"
        sel, ident = _select_list(con, j["table"], j["table"])
        select_all += sel + ([ident] if ident else [])
        join_clauses.append(f'{jtype} JOIN {_quote(j["table"])} ON {_quote(local_table)}.{_quote(j["local_key"])} '
                            f'= {_quote(j["table"])}.{_quote(j["foreign_key"])}')
    sql = f"SELECT {', '.join(select_all)}\nFROM {_quote(driving)}\n" + "\n".join(join_clauses)
    return sql, _table_names(spec)


def _names_of(cur) -> list[str]:
    """The joined column aliases. Two columns can only share one when table and column names
    contain the "__" separator in a colliding way; zipping them into a row dict would silently
    let one column's value overwrite the other's, so refuse instead."""
    names = [d[0] for d in cur.description]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise InputError(f"these tables have column names that collide once joined: {', '.join(dup)}")
    return names


def joined_fieldnames(path: str, spec: dict) -> list[str]:
    with _sq.open_readonly(path) as con:
        sql, _ = _build_sql(con, spec)
        return _names_of(con.execute(sql + " LIMIT 0"))


def joined_sample(path: str, spec: dict, n: int) -> tuple[list[dict], list[str]]:
    """A joined sample for schema mapping / pre-flight - the same purpose
    `sqlite_source.sample_rows` serves for one table."""
    with _sq.open_readonly(path) as con:
        sql, _ = _build_sql(con, spec)
        cur = con.execute(sql + " LIMIT ?", (n,))
        names = _names_of(cur)
        return [dict(zip(names, map(_sq._as_text, r))) for r in cur.fetchall()], names


def iter_joined_rows(path: str, spec: dict, chunk_rows: int | None = None) -> Iterator[list[dict]]:
    """The whole join as bounded chunks (constant memory): one open cursor,
    `fetchmany`, exactly `sqlite_source.iter_rows`'s pattern extended to a
    multi-table SELECT. Row identity columns (`table__rowid`) ride along for
    provenance and are stripped by the caller before they reach the claim
    builder."""
    size = chunk_rows or _sq.cfg()["fetch_chunk_rows"]
    with _sq.open_readonly(path) as con:
        sql, _ = _build_sql(con, spec)
        cur = con.execute(sql)
        names = _names_of(cur)
        while True:
            batch = cur.fetchmany(size)
            if not batch:
                return
            yield [dict(zip(names, map(_sq._as_text, r))) for r in batch]


# ------------------------------------------------------------- extraction
def _row_identity(row: dict, table: str) -> str | None:
    v = row.get(f"{table}__rowid")
    return v if v not in (None, "") else None


def _stream_validate_and_build(path: str, spec: dict, mapping: dict, chain_id: str | None, source_id: str,
                               dedupe: bool = True, progress=None) -> dict:
    """The streaming equivalent of `ingest.validate.validate_rows` +
    `ingest.claims.build_claims`: one pass over the joined rows, chunk by
    chunk, so a table too large to hold in memory is still fully validated.

    occam: `seen_rows`/`seen_claims` are in-memory sets - the dedupe ceiling
    for this pass. Fine up to tens of millions of claims; a corpus beyond
    that would need an on-disk (e.g. temp-table) dedupe set instead.
    """
    tables = _table_names(spec)
    addr_field, label_field = mapping.get("address"), mapping.get("category") or mapping.get("label")
    chain_field = mapping.get("chain")

    claims: list[dict] = []
    rejected: list[dict] = []
    by_reason: dict[str, int] = {}
    seen_rows: set = set()
    seen_claims: set = set()
    n_scanned = n_checked = n_invalid = n_null_address = 0
    per_chain_checked: dict[str, int] = {}
    per_chain_invalid: dict[str, int] = {}

    def reject(i, reason, **extra):
        nonlocal n_invalid
        by_reason[reason] = by_reason.get(reason, 0) + 1
        if len(rejected) < _preflight.cfg()["rejected_examples"]:
            rejected.append(dict(row=i, reason=reason, **extra))

    for chunk in iter_joined_rows(path, spec):
        for row in chunk:
            i = n_scanned
            n_scanned += 1
            row_key = tuple(sorted(row.items())) if dedupe else None
            if dedupe and row_key in seen_rows:
                reject(i, "duplicate row")
                continue
            if dedupe:
                seen_rows.add(row_key)

            address = (row.get(addr_field) or "").strip() if addr_field else ""
            if not addr_field or not address:
                n_null_address += 1
                reject(i, "empty address")
                continue

            row_chain = chain_id
            if chain_field:
                declared = (row.get(chain_field) or "").strip()
                # a blank per-row value falls back to the dataset's overall chain; an explicit
                # but unrecognized one is never silently folded into it - it is simply a chain
                # THEMIS cannot validate yet, and the row is rejected as such below (`aliases.get`
                # with no default returns None for an unrecognized value, which must not become
                # the falsy "use chain_id" case `row_chain = chain_id` above already covered)
                row_chain = chains.resolve_chain(declared) if declared else chain_id
            adapter = chains.get(row_chain) if row_chain else None
            if adapter is None:
                reject(i, "unresolved chain", address=address)
                continue

            n_checked += 1
            per_chain_checked[row_chain or "?"] = per_chain_checked.get(row_chain or "?", 0) + 1
            if not adapter.validate_address(address):
                n_invalid += 1
                per_chain_invalid[row_chain or "?"] = per_chain_invalid.get(row_chain or "?", 0) + 1
                reject(i, "invalid address", address=address, chain=row_chain)
                continue

            label = (row.get(label_field) or "").strip() if label_field else ""
            if label_field and not label:
                reject(i, "missing label", address=address)
                continue

            claim_key = (row_chain, adapter.normalize_address(address), label,
                         _claims.declared_source(row, mapping))   # see validate.validate_rows
            if dedupe and claim_key in seen_claims:
                reject(i, "duplicate claim", address=address)
                continue
            if dedupe:
                seen_claims.add(claim_key)

            prov = dict(
                source_database=path, driving_table=dict(table=spec["driving_table"],
                                                          row_key=_row_identity(row, spec["driving_table"])),
                joined_tables=[dict(table=j["table"], local_key=j["local_key"], foreign_key=j["foreign_key"],
                                    row_key=_row_identity(row, j["table"]))
                              for j in spec.get("joins", [])],
                original_values={role: row.get(col) for role, col in mapping.items() if col},
            )
            claims.append(_claims.build_claim(row, mapping, source_id, record_id=i, blockchain=row_chain,
                                              provenance_record=prov))
        if progress is not None:
            progress("progress", "validate", f"{n_scanned:,} rows scanned · {len(claims):,} claims so far")

    return dict(claims=claims, rejected=rejected, rejected_by_reason=by_reason,
                n_input=n_scanned, n_valid=len(claims), n_rejected=n_scanned - len(claims),
                n_identifiers_checked=n_checked, n_identifiers_invalid=n_invalid,
                n_null_address=n_null_address, per_chain_checked=per_chain_checked, per_chain_invalid=per_chain_invalid,
                tables_scanned=tables)


def extract(path: str, spec: dict, source_id: str, semantics: dict | None = None, chain: str | None = None,
           confirmed: bool = False, reference=None, analysis_as_of_date=None, progress=None,
           sample_size: int | None = None, case_metadata: dict | None = None) -> dict:
    """Joined streaming extraction, shaped exactly like
    `ingest.pipeline.ingest()`'s return value so every downstream analysis
    route (trust, provenance, conflicts, export) works on it unchanged.

    `case_metadata` (see CASE_METADATA_FIELDS) is caller-asserted context
    carried onto the result unchanged - never mandatory, never derived here.
    """
    from .. import __version__, analysis, target_audit
    case_metadata = _validate_case_metadata(case_metadata)

    def _p(event, stage, detail=None):
        if progress is not None:
            progress(event, stage, detail)

    _p("start", "inspect")
    integrity = _sq.integrity_check(path)
    if integrity["status"] != "ok":
        from . import detect as _detect
        msg = cfg()["integrity_gate_message"]
        detection = dict(blockchain=None, address_field=None, confidence=_detect.NONE)
        pf = dict(status="blocked", can_analyze=False, dataset_type=None,
                  blockers=[dict(code="database_corrupt", message=msg)], message=msg,
                  detection=detection, integrity=integrity, case_metadata=case_metadata)
        _p("complete", "inspect", integrity["status"])
        return dict(source_id=source_id, stopped=True, message=msg, detection=detection,
                    dataset_preflight=pf, analysis_states=_gating.blocked(pf), claims=[], validation=None,
                    basic_quality=None)

    join_check = validate_join_spec(path, spec)
    _p("complete", "inspect", "; ".join(join_check["warnings"]) or "join keys look indexed")

    _p("start", "detect")
    n = sample_size or _preflight.cfg()["sample_size"]
    sample, names = joined_sample(path, spec, n)
    display_cols = [f for f in names if not f.endswith("__rowid")]
    overrides = _preflight.overrides_from_roles(None, display_cols)
    overrides.update({k: v for k, v in (semantics or {}).items() if k in display_cols})
    with _sq.open_readonly(path) as con:
        driving_count = _sq.count_rows(con, spec["driving_table"], _sq.cfg()["count_timeout_seconds"])
    pf = _preflight.run([{k: v for k, v in r.items() if k in display_cols} for r in sample], display_cols,
                        filename=path.rsplit("/", 1)[-1], input_type="sqlite", table=spec["driving_table"],
                        total_rows=driving_count, overrides=overrides, chain=chain, confirmed=confirmed)
    pf["relational"] = dict(join_spec=spec, join_warnings=join_check["warnings"],
                            tables=_table_names(spec), relationships=infer_relationships(path))
    if case_metadata:
        pf["case_metadata"] = case_metadata
    detection = pf["detection"]
    _p("complete", "detect", f"{pf['dataset_type']} · {pf['chain']['value'] or 'no chain'} · {pf['status']}")
    if not pf["can_analyze"]:
        return dict(source_id=source_id, stopped=True, message=pf["message"], detection=detection,
                    dataset_preflight=pf, analysis_states=_gating.blocked(pf), claims=[], validation=None,
                    basic_quality=dict(rows=driving_count, columns=display_cols))

    mapping, chain_id = pf["mapping"], pf["chain"]["value"]
    _p("start", "validate")
    t0 = time.monotonic()
    validation = _stream_validate_and_build(path, spec, mapping, chain_id, source_id, progress=progress)
    elapsed = time.monotonic() - t0
    _p("complete", "validate", f"{len(validation['claims']):,} claims from {validation['n_input']:,} rows scanned "
       f"in {elapsed:.1f}s")
    floor = _preflight.cfg()["min_identifier_valid_rate"]
    n_chk, n_bad = validation["n_identifiers_checked"], validation["n_identifiers_invalid"]
    if not n_chk or (n_chk - n_bad) / n_chk < floor:
        pf["blockers"].append(dict(code="subject_invalid_full", message=(
            f"Only {n_chk - n_bad:,} of {n_chk:,} joined values in '{mapping['address']}' are valid identifiers "
            f"(minimum {floor:.0%}); no claims were created.")))
        pf.update(status="blocked", can_analyze=False,
                  message=_preflight._message("blocked", "attribution_claims", pf["blockers"], detection))
        return dict(source_id=source_id, stopped=True, message=pf["message"], detection=detection,
                    dataset_preflight=pf, analysis_states=_gating.blocked(pf), claims=[],
                    validation={k: v for k, v in validation.items() if k != "claims"},
                    basic_quality=dict(rows=validation["n_input"], columns=display_cols))

    # occam: from here on, `claims` (one dict per VALID claim, not per scanned
    # row) is held in memory - the same assumption every other THEMIS input
    # (CSV, the reference corpus) already makes, since trust/graph/export all
    # read a claims list directly. Scanning and validation above are chunked
    # and bounded regardless of table size; this list is not. For a driving
    # table in the tens of millions of rows, this is the real memory ceiling,
    # not the SQL side - upgrade path is a disk-backed claim store (e.g. a
    # temp SQLite table) if a corpus that large needs analysing whole.
    claims = validation["claims"]
    capabilities = {"address_validation": True, "claim_normalization": True, "internal_consistency": True,
                    "relational_provenance": True, "chunked_processing": True}
    limitations = []
    basis = pf["currency_basis"]
    if basis is None:
        limitations.append("Staleness / currency not computed: no attribution timestamp is mapped.")
    else:
        capabilities["freshness"] = True

    target_result = None
    _p("start", "compare")
    if reference is not None and claims:
        target_result = target_audit.audit_target_against_reference(claims, reference,
                                                                     analysis_as_of_date=analysis_as_of_date)
        capabilities["cross_source_comparison"] = True
    else:
        limitations.append("Cross-source comparison unavailable: no reference corpus was supplied.")
        limitations.append("Provenance extraction limited: this database has no declared provenance rule, so "
                           "every claim's root is UNRESOLVED by default.")
        fresh = analysis.freshness(claims, as_of=analysis_as_of_date) if basis else None
        target_result = dict(
            n_target_addresses=len({c["address"] for c in claims}), n_target_claims=len(claims),
            address_comparability={}, address_resolution={},
            profile=dict(
                data_quality=dict(available=True, target_addresses=len({c["address"] for c in claims}),
                                  target_claims=len(claims)),
                reference_comparability=dict(available=False, reason="no reference corpus was supplied"),
                agreement=dict(available=False, reason="no reference corpus was supplied"),
                provenance=dict(available=False, reason="no reference corpus was supplied"),
                independence=dict(available=False, reason="no reference corpus was supplied"),
                currency=(dict(available=True, **fresh) if fresh is not None
                         else dict(available=False, reason="no attribution timestamp is mapped")),
                evidence_class=target_audit.evidence_class_tally(claims),
            ),
            limitations=[], inheritance_candidates=[],
        )
    states = _gating.evaluate(pf, claims, target_result, reference)
    if basis is None:
        target_result["profile"]["currency"] = dict(available=False, state=states["staleness"]["state"],
                                                    reason=states["staleness"]["reason"])
    else:
        target_result["profile"]["currency"].update(state=states["staleness"]["state"], basis=basis)
    if states["conflicts"]["state"] != _gating.COMPUTED:
        target_result["profile"]["agreement"]["state"] = states["conflicts"]["state"]
    _p("complete", "compare", "provenance and currency" if reference is None else
       "provenance, reference comparison, independence and currency")

    _p("start", "profile")
    profile = profile_dataset(path, spec, claims, mapping, validation, driving_count)
    deps = dependency_candidates([c.get("prov_family", "") for c in claims])
    prov_states = provenance_states(claims, deps)
    conflict_report = conflicts(claims)
    _p("complete", "profile", f"{profile['scale']['unique_addresses']:,} unique addresses · "
       f"{len(conflict_report['conflicting_addresses'])} intra-dataset conflicts")

    summary = {k: v for k, v in validation.items() if k not in ("claims", "rejected")}
    summary["rejected_examples"] = validation["rejected"][:_preflight.cfg()["rejected_examples"]]
    summary["elapsed_seconds"] = round(elapsed, 3)
    pf["validation"] = summary
    pf["analysis_states"] = states
    pf["sqlite_metadata"] = _export_metadata(path, spec, mapping, pf, validation, __version__)
    return dict(
        source_id=source_id, stopped=False, detection=detection, schema_mapping=mapping,
        dataset_preflight=pf, analysis_states=states, validation=summary, claims=claims,
        capabilities=capabilities, limitations=limitations, target_audit=target_result,
        reliability_profile=target_result["profile"], dataset_profile=profile,
        relational_provenance=prov_states, conflicts=conflict_report, dependency_candidates=deps,
    )


def _export_metadata(path: str, spec: dict, mapping: dict, pf: dict, validation: dict, version: str) -> dict:
    """Section 14: what a database-sourced analysis adds to preflight.json,
    on top of what every dataset already gets there."""
    import pathlib as _pl
    p = _pl.Path(path)
    return dict(
        database_path=p.name, database_sha256=_cached_sha256(path), database_size_bytes=p.stat().st_size,
        sqlite_version=_sq.sqlite_version(path),
        selected_tables=_table_names(spec), selected_joins=spec.get("joins", []),
        schema_mapping=mapping, mapping_confidence={r["column"]: r["confidence"] for r in pf["columns"]},
        user_confirmations=dict(confirmed=pf["user_confirmed"], chain=pf["user_selected_chain"]),
        n_rows_scanned=validation["n_input"], n_claims_normalized=validation["n_valid"],
        n_rejected=validation["n_rejected"], rejection_reasons=validation["rejected_by_reason"],
        extraction_query_version="themis-relational/1.0", themis_version=version,
    )


# ------------------------------------------------------------ dataset profile
def profile_dataset(path: str, spec: dict, claims: list[dict], mapping: dict, validation: dict,
                    total_records: int | None = None) -> dict:
    """Section 7: scale, distributions, source coverage and data-quality
    observations - never called a reliability conclusion here. `total_records`
    is the driving table's row count, already known to the caller (extract())
    from the pre-flight stage; a fresh COUNT(*) is deliberately not repeated."""
    addr_field = mapping.get("address")
    driving = spec["driving_table"]
    unique_raw = None
    if addr_field and total_records is not None:
        # the alias is "<table>__<column>"; recover the pair by the table's known name, not by splitting
        # on "__" (a table or column name may contain it)
        table_of_col = next((t for t in _table_names(spec) if addr_field.startswith(f"{t}__")), None)
        try:
            if table_of_col is None:
                raise sqlite3.OperationalError("address column is not a joined column")
            col = addr_field[len(table_of_col) + 2:]
            with _sq.open_readonly(path) as con:
                unique_raw = con.execute(
                    f"SELECT COUNT(DISTINCT {_quote(col)}) FROM {_quote(table_of_col)}").fetchone()[0]
        except sqlite3.DatabaseError:
            unique_raw = None

    blockchain_dist: dict = {}
    label_dist: dict = {}
    with_source = with_source_url = with_evidence = with_confidence = with_date = 0
    for c in claims:
        blockchain_dist[c.get("blockchain") or "unknown"] = blockchain_dist.get(c.get("blockchain") or "unknown", 0) + 1
        label_dist[c.get("canon") or "unknown"] = label_dist.get(c.get("canon") or "unknown", 0) + 1
        if (c.get("prov_family") or "").strip():
            with_source += 1
        if (c.get("source_url") or "").strip():
            with_source_url += 1
        if (c.get("notes") or "").strip() or (c.get("confidence_raw") or "").strip():
            with_evidence += 1
        if (c.get("confidence_raw") or "").strip():
            with_confidence += 1
        if (c.get("lastmod") or "").strip():
            with_date += 1

    addr_counts: dict[str, int] = {}
    for c in claims:
        addr_counts[c["address"]] = addr_counts.get(c["address"], 0) + 1
    duplicate_addresses = sum(1 for n in addr_counts.values() if n > 1)

    orphan_joins = []
    for j in spec.get("joins", []):
        with _sq.open_readonly(path) as con:
            try:
                local_table = j.get("local_table", driving)
                lk, fk = _quote(local_table) + "." + _quote(j["local_key"]), _quote(j["table"]) + "." + _quote(j["foreign_key"])
                n = con.execute(
                    f'SELECT COUNT(*) FROM {_quote(local_table)} LEFT JOIN {_quote(j["table"])} '
                    f"ON {lk} = {fk} WHERE {lk} IS NOT NULL AND {fk} IS NULL").fetchone()[0]
                orphan_joins.append(dict(table=j["table"], local_key=j["local_key"],
                                        foreign_key=j["foreign_key"], orphan_rows=n))
            except sqlite3.DatabaseError:
                pass

    return dict(
        scale=dict(total_tables=len(_table_names(spec)), total_candidate_records=total_records,
                   total_normalized_claims=len(claims), unique_addresses=len(addr_counts),
                   unique_raw_values_in_driving_table=unique_raw,
                   unique_labels=len({c["canon"] for c in claims}),
                   unique_sources=len({c["prov_family"] for c in claims if c.get("prov_family")})),
        blockchain_distribution=blockchain_dist,
        label_distribution=label_dist,
        source_coverage=dict(claims_with_declared_source=with_source, claims_without_source=len(claims) - with_source,
                             claims_with_source_url=with_source_url, claims_with_evidence=with_evidence,
                             claims_with_confidence=with_confidence, claims_with_dates=with_date),
        data_quality=dict(
            duplicate_claims=validation["rejected_by_reason"].get("duplicate claim", 0),
            duplicate_addresses=duplicate_addresses,
            null_addresses_seen=validation["n_null_address"],
            malformed_identifiers=validation["n_identifiers_invalid"],
            orphan_foreign_keys=orphan_joins,
            rejection_reasons=validation["rejected_by_reason"],
        ),
    )


# --------------------------------------------------------------- provenance
def provenance_states(claims: list[dict], dependencies: list[dict] | None = None) -> dict:
    """Section 8: resolved / inherited / inferred / unresolved, kept
    strictly separate. A claim that names a label with no evidence for why
    (THEMIS's own "Binance" example) is `unresolved`, whatever the label is.

    `inherited` needs a CONFIRMED lineage from a resolved root, which a claim
    extracted from a database has no way to show: it is 0 here. A dependency
    candidate (one declared-source string containing another; unverified text
    matching, see `dependency_candidates`) is not a lineage, so it moves no
    claim out of `unresolved` - it is counted on its own line,
    `dependency_candidate_claims`, so the two are never mistaken for each other."""
    _cfg = config_io.load()
    citing_sources = {d["citing"] for d in (dependencies or [])}
    counts = {"resolved": 0, "inherited": 0, "inferred": 0, "unresolved": 0}
    by_state: dict[str, list[str]] = {k: [] for k in counts}
    n_candidate = 0
    for c in claims:
        r = _provenance.resolve(c, _cfg.sources)
        if r["kind"] == "DECLARED" and r["resolved"]:
            state = "resolved"
        elif r["kind"] == "INFERRED":
            state = "inferred"
        else:
            state = "unresolved"
        counts[state] += 1
        if (c.get("prov_family") or "").strip() in citing_sources:
            n_candidate += 1
        if len(by_state[state]) < 20:
            by_state[state].append(c["claim_id"])
    return dict(counts=counts, examples=by_state, dependency_candidate_claims=n_candidate,
                note="'inherited' requires a confirmed lineage and is 0 for a database extraction. "
                     "dependency_candidate_claims counts claims whose declared source appears to cite another "
                     "declared source in the same extraction: a possible dependency, unverified, that moves no "
                     "claim out of its provenance state and is not corroboration.")


def dependency_candidates(declared_sources: list[str]) -> list[dict]:
    """Section 9 architecture: does one declared-source string appear to cite
    another declared-source string also present in this dataset? Stored as a
    candidate relationship only - never used to shrink an independence count."""
    distinct = sorted({s.strip() for s in declared_sources if s and s.strip()})
    min_len = cfg()["dependency_min_descriptor_length"]
    out = []
    low = {s: s.lower() for s in distinct}
    for a in distinct:
        for b in distinct:
            if a == b:
                continue
            if low[b] in low[a] and len(b) >= min_len:
                out.append(dict(citing=a, cited=b,
                                relation="citing may contain/reference cited; unverified, not applied to any "
                                         "independence or corroboration count"))
    return out


# ------------------------------------------------------------------ conflicts
def conflicts(claims: list[dict]) -> dict:
    """Section 10, intra-dataset case: the same address given incompatible
    classifications *within one extraction* (e.g. two rows for one address
    after a join fans it out). This is not cross-source corroboration -
    `taxonomy.classify_address` (which THEMIS's cross-source agreement uses)
    requires >=2 distinct sources by design, and a joined dataset is one
    source - so the outcome classes are computed directly here, reusing the
    same taxonomy primitives (polarity, generic placeholders, ancestors)."""
    by_addr: dict[str, list[dict]] = {}
    for c in claims:
        by_addr.setdefault(c["address"], []).append(c)
    conflicting = []
    for addr, group in by_addr.items():
        cats = {c["canon"] for c in group if c["canon"] != "unknown"}
        if len(cats) < 2:
            continue
        outcome = _pairwise_outcome(cats)
        # THEMIS's own conflict vocabulary (themis/views.py's _CONFLICT_KIND_MAP)
        # only ever calls "entity-type conflict" and "licit/illicit conflict" a
        # conflict; "exact" agrees, and "hierarchical refinement" is a category
        # granularity difference, not a contradiction (spec Section 10).
        if outcome not in ("entity-type conflict", "licit/illicit conflict"):
            continue
        conflicting.append(dict(address=addr, outcome=outcome, categories=sorted(cats),
                                claims=[dict(claim_id=c["claim_id"], canon=c["canon"], raw_label=c["raw_label"],
                                            provenance_record=c.get("provenance_record")) for c in group]))
    return dict(conflicting_addresses=conflicting,
                n_addresses_checked=sum(1 for g in by_addr.values() if len(g) > 1),
                note="conflicts among rows of the SAME extraction (duplicate/joined-fanout rows), not cross-source "
                     "corroboration; see /api/analysis/{id}/conflicts for cross-source agreement against a "
                     "reference corpus.")


def _pairwise_outcome(cats: set) -> str:
    if len(cats) == 1:
        return "exact"
    pol = {taxonomy.POLARITY.get(c, "unknown") for c in cats} - {"unknown"}
    if len(pol) > 1:
        return "licit/illicit conflict"
    specific = cats - taxonomy.GENERIC
    if len(specific) <= 1:
        return "hierarchical refinement"
    anc = {c: taxonomy.ancestors(c) for c in specific}
    if all(a in anc[b] or b in anc[a] for a in specific for b in specific):
        return "hierarchical refinement"
    return "entity-type conflict"
