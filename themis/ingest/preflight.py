"""The mandatory dataset pre-flight. Nothing reaches claim normalization,
provenance, reference matching, conflict detection, staleness or trust analysis
until this module has said the file holds a defensible attribution schema.

It answers, from the file's own content and never from its name or from a
column's primitive type alone:

* what does each column mean (a semantic field, with a confidence and a status),
* is the claim subject a valid identifier for a known chain,
* which chain, and how do we know (metadata, data, or the user),
* which timestamp dates the ATTRIBUTION (the only one staleness may use),
* what is missing, and therefore what must not run.

A user's mapping is an input to this function, never a way around it: a column
the user names as the subject is validated exactly like an inferred one.
Every rule and threshold is read from config/preflight.yml.
"""
from __future__ import annotations
import collections, datetime, hashlib, json, re

from .. import chains, config_io
from ..errors import InputError
from . import detect as _detect

_NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ].*)?$")
_URL_RE = re.compile(r"^https?://", re.I)

#: semantic types assigned by the file's shape, never proposed from a name
_SHAPE_ONLY = ("ts_market_candle", "market_numeric", "numeric_unclassified", "unmapped")

HEADLINE_UNSUPPORTED = "Unsupported dataset for attribution analysis"
NO_SCHEMA = "No defensible cryptocurrency attribution schema was detected."

NOT_CRYPTO_MESSAGE = (
    "This dataset does not appear to contain cryptocurrency attribution data.\n\n"
    "THEMIS's forensic reliability methodology is designed for cryptocurrency "
    "attribution datasets.\n\n"
    "Basic structural data-quality checks can still be performed, but "
    "provenance-aware cryptocurrency attribution analysis is not applicable."
)
MARKET_MESSAGE = (
    "This file is market data (a price / volume time series), not a set of "
    "attribution claims: no column holds a claim subject such as a wallet address, "
    "and none holds an attribution label.\n\n"
    "THEMIS audits who says an address belongs to which entity. Price candles and "
    "trade counts make no such claim, so no claims were created from this file."
)
UNSUPPORTED_CHAIN_MESSAGE = (
    "Cryptocurrency attribution data appears to be present, but this blockchain "
    "is not currently supported for full forensic reliability analysis.\n\n"
    "Column '{field}' contains address-shaped identifiers that no registered "
    "chain adapter ({supported}) validates. THEMIS V1 only ships full address "
    "validation, provenance resolution and cross-source comparison for the "
    "chains it has an adapter for.\n\n"
    "Basic structural data-quality checks can still be performed."
)
CRYPTO_NON_ATTRIBUTION_MESSAGE = (
    "Cryptocurrency data was detected (column '{field}' references a recognized "
    "cryptocurrency), but no usable attribution-label structure was identified.\n\n"
    "This looks like price, market, or transaction data rather than an attribution "
    "dataset (addresses linked to entities or categories). THEMIS's forensic "
    "reliability methodology audits attribution claims, not raw market data.\n\n"
    "Basic structural data-quality checks can still be performed."
)


ATTRIBUTION_LIKE_HEADLINE = ("This file looks like attribution data (an identifier column next to attribution "
                             "labels), but THEMIS could not establish a schema for it automatically. "
                             "Nothing was analysed. What THEMIS established:")


def cfg() -> dict:
    return config_io.load().preflight


def config_hash() -> str:
    return hashlib.sha256(json.dumps(cfg(), sort_keys=True, default=str).encode()).hexdigest()


# ------------------------------------------------------------------ profiling
def _norm(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name.strip())
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _is_number(v: str) -> bool:
    return bool(_NUM_RE.match(v.strip()))


def _is_date(v: str) -> bool:
    v = v.strip()
    if not _DATE_RE.match(v):
        return False
    try:
        datetime.date.fromisoformat(v[:10])
        return True
    except ValueError:
        return False


class _Profile:
    """What a column's sampled values look like, independent of its name."""

    def __init__(self, name: str, sample: list[str], positions: list[int] | None = None):
        self.name, self.sample, self.n = name, sample, len(sample)
        positions = list(range(len(sample))) if positions is None else positions
        n = self.n or 1
        num = [_is_number(v) for v in sample]
        date = [_is_date(v) for v in sample]
        url = [bool(_URL_RE.match(v)) for v in sample]
        self.numeric = sum(num) / n
        self.date = sum(date) / n
        self.url = sum(url) / n
        self.text = sum(1 for a, b, c in zip(num, date, url) if not (a or b or c)) / n
        self.distinct = len(set(sample))
        ints = [int(v) for v, isnum in zip(sample, num) if isnum and re.fullmatch(r"[+-]?\d+", v.strip())]
        # a 0,1,2,3... (or 1,2,3...) counter is a row index, whatever it is called: each value
        # is its row position plus one constant, whichever rows were sampled
        self.sequential = (self.n >= cfg()["min_sequence_sample"] and len(ints) == self.n
                           and len({v - i for v, i in zip(ints, positions)}) == 1
                           and all(b > a for a, b in zip(ints, ints[1:])))

    def is_numeric(self, c) -> bool:
        return self.n > 0 and self.numeric >= c["numeric_share_min"]

    def is_date(self, c) -> bool:
        return self.n > 0 and self.date >= c["date_shape_min_share"]


def _rate(sample: list[str], validator) -> float:
    return (sum(1 for v in sample if validator(v)) / len(sample)) if sample else 0.0


# ------------------------------------------------------------ semantic scoring
def _name_score(column: str, hints: dict, c: dict) -> float:
    n = _norm(column)
    if n in hints.get("exact", []):
        return c["name_score"]["exact"]
    if set(n.split("_")) & set(hints.get("tokens", [])):
        return c["name_score"]["token"]
    return 0.0


def _group(sem: str) -> str:
    return "subject" if sem.startswith("subject_") else sem


def _is_unique(sem: str, c: dict) -> bool:
    return c["semantic_fields"][sem].get("unique", True)


class _Ctx:
    """Per-run state shared by the scoring helpers."""

    def __init__(self, c: dict, profiles: dict, chain_id: str | None):
        self.c, self.profiles, self.chain_id = c, profiles, chain_id
        self._rates: dict = {}

    def adapters(self) -> dict:
        allc = chains.all_adapters()
        return {self.chain_id: allc[self.chain_id]} if self.chain_id in allc else allc

    def subject_rates(self, column: str, kind: str) -> dict[str, float]:
        """{chain id: share of the column's sampled values valid for that chain}."""
        key = (column, kind)
        if key not in self._rates:
            validator = self.c["subject_kinds"][kind]["validator"]
            p = self.profiles[column]
            self._rates[key] = {} if validator is None else {
                cid: _rate(p.sample, getattr(ad, validator))
                for cid, ad in self.adapters().items()}
        return self._rates[key]


def _identifier_shaped(column: str, ctx: _Ctx) -> bool:
    """Do the column's values validate as identifiers (addresses) for some supported chain?"""
    p = ctx.profiles[column]
    if p.n == 0 or p.sequential or p.is_numeric(ctx.c):
        return False
    return max(ctx.subject_rates(column, "address").values(), default=0.0) >= ctx.c["min_identifier_valid_rate"]


def _value_score(sem: str, column: str, name_score: float, ctx: _Ctx) -> float:
    c, p = ctx.c, ctx.profiles[column]
    f = c["semantic_fields"][sem]
    if p.n == 0:
        return 0.0
    kind = f.get("subject_kind")
    if kind:
        kcfg = c["subject_kinds"][kind]
        if p.sequential:
            return 0.0                       # a row index is never a subject
        if kcfg["validator"] is None:
            return kcfg["value_score"]
        if p.is_numeric(c):
            return 0.0                       # digits-only values are not addresses or hashes
        return max(ctx.subject_rates(column, kind).values(), default=0.0)
    if sem in c["identifier_excluded_semantics"] and _identifier_shaped(column, ctx):
        return 0.0                           # an address is not a label, a grade, a source or a chain name
    if sem in ("attribution_label", "attribution_category", "attribution_entity", "attribution_actor",
               "attribution_evidence"):
        return p.text
    if sem == "attribution_source":
        return p.url if name_score == 0 else min(1.0, p.url + p.text)
    if sem == "attribution_confidence":
        grades = set(c["confidence_grades"])
        graded = sum(1 for v in p.sample if _norm(v) in grades) / p.n
        return 1.0 if p.is_numeric(c) or graded >= c["numeric_share_min"] else 0.0
    if sem == "chain":
        return sum(1 for v in p.sample if chains.resolve_chain(v)) / p.n
    if sem.startswith("ts_"):
        return p.date
    if sem in ("market_numeric", "numeric_unclassified"):
        return p.numeric
    return 0.0


def _confidence(name_score: float, value_score: float, c: dict) -> float:
    w = c["confidence_weights"]
    return round(w["name"] * name_score + w["value"] * value_score, 4)


def _has_market_signature(fieldnames: list[str], profiles: dict, c: dict) -> bool:
    sig = c["market_signature"]
    present = {_norm(f) for f in fieldnames
               if _norm(f) in sig["tokens"] and profiles[f].is_numeric(c)}
    return len(present) >= sig["min_present"]


# ------------------------------------------------------------------ overrides
def overrides_from_roles(role_map: dict | None, fieldnames: list[str]) -> dict:
    """{role: column} -> {column: semantic type}. A role is a semantic type id or
    a legacy role name (address, label, category, actor, source, confidence,
    timestamp). A None column leaves that role to inference. An unknown role or
    a column not in the file is an error, not a silent no-op."""
    c, out = cfg(), {}
    for role, col in (role_map or {}).items():
        if col is None:
            continue
        sem = c["legacy_roles"].get(role, role)
        if sem not in c["semantic_fields"]:
            raise InputError(f"unknown mapping role {role!r}")
        if col not in fieldnames:
            raise InputError(f"mapping names column {col!r}, which is not in the file")
        if out.get(col, sem) != sem:
            raise InputError(f"column {col!r} is mapped to two roles")
        out[col] = sem
    return out


def _check_overrides(overrides: dict, fieldnames: list[str], c: dict) -> None:
    seen: dict[str, str] = {}
    for col, sem in overrides.items():
        if col not in fieldnames:
            raise InputError(f"mapping names column {col!r}, which is not in the file")
        if sem not in c["semantic_fields"]:
            raise InputError(f"unknown semantic field {sem!r}")
        if _is_unique(sem, c):
            g = _group(sem)
            if g in seen and seen[g] != col:
                raise InputError(f"columns {seen[g]!r} and {col!r} are both mapped to {sem!r}")
            seen[g] = col


# ------------------------------------------------------------------ the run
def run(rows: list[dict], fieldnames: list[str], *, filename: str | None = None, sha256: str | None = None,
        input_type: str = "csv", table: str | None = None, total_rows: int | None = None,
        overrides: dict | None = None, chain: str | None = None, confirmed: bool = False,
        sample_size: int | None = None) -> dict:
    """Pre-flight `rows` (a sample is enough; `total_rows` says how many the
    input really has). `overrides` is {column: semantic type} and `chain` a
    user-selected chain id; `confirmed` records that the user reviewed a
    low-confidence mapping. Never raises for a bad DATASET, only for a bad
    REQUEST (an override naming a column the file lacks)."""
    from .. import __version__
    c = cfg()
    overrides = dict(overrides or {})
    _check_overrides(overrides, fieldnames, c)
    if chain is not None and chain not in chains.all_adapters():
        raise InputError(f"unknown chain {chain!r}; supported: {', '.join(sorted(chains.all_adapters())) or 'none'}")

    n_total = total_rows if total_rows is not None else len(rows)
    n_sample = sample_size or c["sample_size"]
    profiles = {}
    for f in fieldnames:
        pairs = _detect.sample_pairs(rows, f, n_sample)
        profiles[f] = _Profile(f, [v for _, v in pairs], [i for i, _ in pairs])
    market = _has_market_signature(fieldnames, profiles, c)
    ctx = _Ctx(c, profiles, chain)
    fields = c["semantic_fields"]

    assigned: dict[str, dict] = {}          # column -> record
    used_groups: set[str] = set()

    def _put(col, sem, conf, origin, notes=()):
        assigned[col] = dict(sem=sem, conf=conf, origin=origin, notes=list(notes))
        if _is_unique(sem, c):
            used_groups.add(_group(sem))

    # 1. what the user set is fixed first
    for col, sem in overrides.items():
        _put(col, sem, None, "user")

    # 2. market-data shape: numbers and dates in an OHLCV file are market data
    if market:
        for f in fieldnames:
            if f in assigned:
                continue
            p = profiles[f]
            if p.is_numeric(c):
                _put(f, "market_numeric", round(p.numeric, 4), "inferred", ["part of an OHLCV market-data signature"])
            elif p.is_date(c):
                _put(f, "ts_market_candle", round(p.date, 4), "inferred", ["date column of an OHLCV market-data signature"])

    # 3. propose the rest from name AND values
    cands, rejected = [], {}
    for f in fieldnames:
        if f in assigned:
            continue
        for order, (sem, fld) in enumerate(fields.items()):
            if sem in _SHAPE_ONLY or (_is_unique(sem, c) and _group(sem) in used_groups):
                continue
            ns = _name_score(f, fld.get("hints", {}), c)
            if ns == 0 and sem not in c["value_inferable"]:
                continue
            vs = _value_score(sem, f, ns, ctx)
            conf = _confidence(ns, vs, c)
            if conf >= c["review_confidence"]:
                cands.append((-conf, order, f, sem, conf))
            elif ns > 0:
                rejected.setdefault(f, []).append((conf, order, sem, vs))
    for _, _, f, sem, conf in sorted(cands):
        if f in assigned or (_is_unique(sem, c) and _group(sem) in used_groups):
            continue
        _put(f, sem, conf, "inferred")

    # 4. what is left: dates whose role is unknown, numbers whose meaning is unknown
    for f in fieldnames:
        if f in assigned:
            continue
        p = profiles[f]
        notes = []
        if f in rejected:
            conf, _, sem, vs = sorted(rejected[f])[-1]
            notes.append(f"the name suggests '{fields[sem]['label']}', but the values do not fit ({vs:.0%})")
        if p.sequential:
            notes.append("a consecutive 0/1..n counter: a row index, not an identifier")
        if p.is_date(c):
            _put(f, "ts_unclassified", round(p.date * c["confidence_weights"]["value"], 4), "inferred",
                 notes + ["a date, but nothing says what it dates: never used for staleness"])
        elif p.is_numeric(c):
            _put(f, "numeric_unclassified", None, "inferred", notes)
        else:
            _put(f, "unmapped", None, "inferred", notes)

    # 5. columns table with a validation status each
    columns = [_column_record(f, assigned[f], profiles[f], ctx, rejected.get(f)) for f in fieldnames]
    by_sem = {r["semantic_type"]: r for r in columns if _is_unique(r["semantic_type"], c)}

    subject = _subject_of(columns, ctx)
    chain_res = _resolve_chain(subject, columns, ctx, chain, rows)
    if subject and subject["kind"] == "address":
        if chain_res["status"] == "per_row":
            rate = chain_res["per_row"]["overall_rate"]
            _rescore_subject(columns, subject, rate, c)
            _revalidate_subject(columns, subject, rate, "supported-chain", ctx)
            subject = _subject_of(columns, ctx)
        elif chain_res["value"]:
            # the subject's status is what it is under the chosen/detected chain
            _revalidate_subject(columns, subject, subject["rates"].get(chain_res["value"]), chain_res["value"], ctx)
            subject = _subject_of(columns, ctx)

    detection = _detection(rows, fieldnames, subject, chain_res, n_sample)
    label_col = next((by_sem[s] for s in ("attribution_category", "attribution_label", "attribution_entity")
                      if s in by_sem and by_sem[s]["status"] != "invalid"), None)
    dataset_type = _dataset_type(subject, label_col, market, detection, columns, c)
    label_structure = _label_structure(rows, by_sem, c)
    extra_warnings = _extra_warnings(columns, chain_res, profiles, c, n_total)

    established = _established(columns, label_col, profiles) if dataset_type == "attribution_like_unresolved" else []
    blockers = _blockers(subject, chain_res, label_col, columns, detection, dataset_type, confirmed, input_type, c)
    warnings = [f"{r['column']}: {n}" for r in columns for n in r["notes"]
                if r["status"] in ("review", "invalid")] + extra_warnings
    status = ("unsupported" if dataset_type not in ("attribution_claims", "unsupported_subject_kind",
                                                    "attribution_like_unresolved", "mapping_unresolved")
              else "blocked" if any(b["code"] != "needs_confirmation" for b in blockers)
              else "needs_confirmation" if blockers else "ready")

    basis = _currency_basis(columns, c)
    mapping = _claim_mapping(columns, basis, c)
    required = [dict(name=r["name"], satisfied=any(s in by_sem and by_sem[s]["status"] != "invalid" for s in r["any_of"]),
                     column=next((by_sem[s]["column"] for s in r["any_of"] if s in by_sem), None),
                     accepts=[fields[s]["label"] for s in r["any_of"]]) for r in c["required"]]

    return dict(
        schema_version=c["schema_version"], parser=f"themis-ingest/{__version__}",
        config_hash=config_hash(),
        analysis_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        input=dict(filename=filename, sha256=sha256, type=input_type, table=table,
                   n_rows=n_total, n_rows_profiled=len(rows), n_columns=len(fieldnames),
                   original_columns=list(fieldnames)),
        dataset_type=dataset_type, dataset_state=DATASET_STATES[dataset_type], established=established, status=status,
        can_analyze=(status == "ready"), label_structure=label_structure,
        subject=subject, chain=chain_res, columns=columns, required=required,
        mapping=mapping, currency_basis=basis,
        timestamp_roles={r["column"]: r["semantic_type"] for r in columns
                         if r["semantic_type"].startswith("ts_") and r["status"] != "invalid"},
        blockers=blockers, warnings=warnings, detection=detection,
        dataset_type_label=DATASET_TYPE_LABELS[dataset_type],
        checks=_checks(dataset_type, subject, chain_res, columns, basis, label_col,
                       {r["column"]: r["semantic_type"] for r in columns
                        if r["semantic_type"].startswith("ts_") and r["status"] != "invalid"},
                       input_type, c, _source_class(columns, profiles, c, n_total)),
        user_confirmed=bool(confirmed), user_overrides=overrides,
        user_selected_chain=chain,
        message=_message(status, dataset_type, blockers, detection, established),
    )


# ---------------------------------------------------------------- the pieces
def _column_record(col: str, a: dict, p: _Profile, ctx: _Ctx, rej) -> dict:
    c, sem = ctx.c, a["sem"]
    fld = c["semantic_fields"][sem]
    notes, user = list(a["notes"]), a["origin"] == "user"
    # a user's choice is judged on the values alone: what the column is called is not evidence for it
    ns = 1.0 if user else _name_score(col, fld.get("hints", {}), c)
    # a shape-only semantic is assigned by the file's shape when inferred, but a user's choice of
    # one is still a claim about the values and is checked against them like any other
    value = None if sem == "unmapped" or (sem in _SHAPE_ONLY and not user) else _value_score(sem, col, ns, ctx)
    strict = sem in c["strict_value_semantics"] or sem.startswith("ts_")
    status = "ok"
    if sem == "unmapped":
        status = "unused"
    elif p.n == 0 and user:
        status, notes = "invalid", notes + ["the column has no values"]
    elif sem.startswith("subject_") and c["subject_kinds"][fld["subject_kind"]]["validator"] is not None \
            and value < c["min_identifier_valid_rate"]:
        status = "invalid"
        notes.append(f"only {value:.0%} of sampled values are valid identifiers for any supported chain "
                     f"(minimum {c['min_identifier_valid_rate']:.0%})")
    elif user and sem.startswith("ts_") and not p.is_date(c):
        status = "invalid"
        notes.append(f"only {p.date:.0%} of sampled values are ISO dates: this column cannot date a claim")
    elif user and sem in c["identifier_excluded_semantics"] and _identifier_shaped(col, ctx):
        status = "invalid"
        notes.append(f"the values are identifiers (addresses), not '{fld['label']}': a mapping cannot make an "
                     "identifier column mean something else")
    elif user and strict and value is not None and value < c["review_confidence"]:
        status = "invalid"
        notes.append(f"only {value:.0%} of sampled values fit '{fld['label']}': choosing a column never waives "
                     "the check of what it contains")
    elif sem == "numeric_unclassified":
        status = "unused"
    elif user and value is not None and value < c["review_confidence"]:
        notes.append(f"the values look unlike '{fld['label']}' ({value:.0%} fit); kept because you set it")
    elif not user and sem == "ts_unclassified":
        status = "review"
    elif not user and a["conf"] is not None and a["conf"] < c["auto_accept_confidence"] \
            and sem not in ("market_numeric", "ts_market_candle"):
        status = "review"
    if rej and sem in ("unmapped", "numeric_unclassified") and any(s.startswith("subject_") for _, _, s, _ in rej):
        status = "invalid"
    conf = (None if value is None else round(value, 4)) if user else a["conf"]
    return dict(column=col, semantic_type=sem, semantic_label=fld["label"], confidence=conf,
                status=status, origin=a["origin"], sample_values=[v[:60] for v in list(dict.fromkeys(p.sample))[:3]],
                notes=notes, subject_kind=fld.get("subject_kind"),
                rejected_as_subject=bool(rej and any(s.startswith("subject_") for _, _, s, _ in rej)))


def _subject_of(columns: list[dict], ctx: _Ctx) -> dict | None:
    r = next((r for r in columns if r["semantic_type"].startswith("subject_")), None)
    if r is None:
        return None
    kind = r["subject_kind"]
    return dict(column=r["column"], kind=kind, status=r["status"], origin=r["origin"],
                confidence=r["confidence"], analyzable=ctx.c["subject_kinds"][kind]["analyzable"],
                rates=ctx.subject_rates(r["column"], kind))


def _revalidate_subject(columns, subject, rate, where, ctx) -> None:
    """Re-decide the subject's status under the chain(s) it will really be validated
    against (`where` names them), not the best of all chains."""
    for r in columns:
        if r["column"] != subject["column"]:
            continue
        if rate is not None and rate < ctx.c["min_identifier_valid_rate"]:
            if r["status"] != "invalid":       # already explained by the all-chains check
                r["notes"].append(f"{rate:.0%} of sampled values are valid {where} identifiers "
                                  f"(minimum {ctx.c['min_identifier_valid_rate']:.0%})")
            r["status"] = "invalid"
    subject["rate_under_chain"] = rate


def _rescore_subject(columns, subject, rate: float, c: dict) -> None:
    """The column-level value fit (best of all chains) says nothing when each row states its own
    chain: rescore the subject on the row-paired rate, identifiers judged under their own chains."""
    for r in columns:
        if r["column"] != subject["column"] or r["semantic_type"] != "subject_address":
            continue
        if r["origin"] == "user":
            r["confidence"] = round(rate, 4)
            continue
        ns = _name_score(r["column"], c["semantic_fields"]["subject_address"].get("hints", {}), c)
        r["confidence"] = _confidence(ns, rate, c)
        if r["status"] in ("ok", "review"):
            r["status"] = "ok" if r["confidence"] >= c["auto_accept_confidence"] else "review"


def _per_row_chain(rows, subject, col, ctx: _Ctx) -> dict:
    """Validate the sampled (chain, identifier) PAIRS: each identifier under the chain its own
    row states. A pair whose chain name resolves to no supported chain is counted apart."""
    adapters = chains.all_adapters()
    per: dict[str, list[int]] = {}
    unresolved = 0
    pairs = _detect.paired_sample(rows, (col["column"], subject["column"]), ctx.c["sample_size"])
    for chain_name, addr in pairs:
        cid = chains.resolve_chain(chain_name)
        if cid is None:
            unresolved += 1
            continue
        tot = per.setdefault(cid, [0, 0])
        tot[0] += 1
        tot[1] += bool(adapters[cid].validate_address(addr))
    n_res = sum(t[0] for t in per.values())
    return dict(column=col["column"], n_pairs=len(pairs),
                unresolved_share=round(unresolved / len(pairs), 4) if pairs else 0.0,
                overall_rate=round(sum(t[1] for t in per.values()) / n_res, 4) if n_res else 0.0,
                chains={cid: dict(share=round(t[0] / len(pairs), 4), n_sampled=t[0], valid_rate=round(t[1] / t[0], 4))
                        for cid, t in sorted(per.items())})


def _resolve_chain(subject, columns, ctx: _Ctx, user_chain: str | None, rows) -> dict:
    """Chain from, in order: what the user chose, an explicit chain column (one chain for the
    whole file, or a chain PER ROW), then the subject's values. Unknown or ambiguous is
    reported as such: it is never defaulted, and a chain-dependent analysis waits for the user."""
    c = ctx.c
    base = dict(value=None, status="not_required", source=None, confidence=None, candidates={}, per_row=None)
    if subject is None or not c["subject_kinds"][subject["kind"]]["chain_dependent"]:
        return base
    rates = subject["rates"] if not user_chain else {
        cid: _rate(ctx.profiles[subject["column"]].sample,
                   getattr(ad, c["subject_kinds"][subject["kind"]]["validator"]))
        for cid, ad in chains.all_adapters().items()}
    base["candidates"] = {k: round(v, 4) for k, v in rates.items()}
    if user_chain:
        return dict(base, value=user_chain, status="determined", source="user",
                    confidence=round(rates.get(user_chain, 0.0), 4))
    col = next((r for r in columns if r["semantic_type"] == "chain" and r["status"] != "invalid"), None)
    if col:
        seen = [chains.resolve_chain(v) for v in ctx.profiles[col["column"]].sample]
        known = {x for x in seen if x}
        if len(known) == 1 and None not in seen:
            return dict(base, value=next(iter(known)), status="determined",
                        source=f"column:{col['column']}", confidence=col["confidence"])
        if known and subject["kind"] == "address":
            pr = _per_row_chain(rows, subject, col, ctx)
            return dict(base, status="per_row", source=f"column:{col['column']}", confidence=pr["overall_rate"],
                        per_row=pr)
    viable = sorted(((r, cid) for cid, r in rates.items() if r >= c["min_identifier_valid_rate"]), reverse=True)
    if not viable:
        return dict(base, status="undetermined")
    if len(viable) > 1 and viable[0][0] - viable[1][0] <= c["chain_ambiguity_margin"]:
        return dict(base, status="ambiguous")
    return dict(base, value=viable[0][1], status="determined", source="detected", confidence=round(viable[0][0], 4))


def _detection(rows, fieldnames, subject, chain_res, n_sample) -> dict:
    """The legacy detection block (UI/CLI/tests read it), corrected to the
    subject and chain the pre-flight actually settled on."""
    d = _detect.detect(rows, fieldnames, n_sample)
    if subject and subject["kind"] == "address" and subject["status"] != "invalid" and chain_res["status"] == "per_row":
        pr = chain_res["per_row"]
        d.update(blockchain=None, blockchains=sorted(pr["chains"]), address_field=subject["column"],
                 sample_hit_rate=pr["overall_rate"], confidence=_detect.confidence_of(pr["overall_rate"]))
    elif subject and subject["kind"] == "address" and chain_res["value"] and subject["status"] != "invalid":
        rate = subject["rates"].get(chain_res["value"], 0.0)
        d.update(blockchain=chain_res["value"], address_field=subject["column"], sample_hit_rate=rate,
                 confidence=_detect.confidence_of(rate))
    else:
        d.update(blockchain=None, address_field=None, confidence=_detect.NONE)
    return d


def _dataset_type(subject, label_col, market, detection, columns, c) -> str:
    if subject and subject["status"] != "invalid":
        if not subject["analyzable"]:
            return "unsupported_subject_kind"
        return "attribution_claims"
    if any(r["origin"] == "user" and r["status"] == "invalid" for r in columns):
        return "mapping_unresolved"         # what you set does not fit the file: say that, not what the file is
    # an identifier-like column that failed validation next to an attribution label: the file has the
    # SHAPE of attribution data, and what failed is the identifiers or THEMIS's schema, not proof the
    # data is something else
    candidate = any(r["rejected_as_subject"] or (r["semantic_type"].startswith("subject_") and r["status"] == "invalid")
                    for r in columns)
    stated_chain = any(r["semantic_type"] == "chain" and r["status"] != "invalid" for r in columns)
    if label_col is not None and candidate and stated_chain:
        return "attribution_like_unresolved"        # the file names a supported chain: these identifiers fail ON it
    if detection.get("unsupported_chain_field"):
        return "unsupported_chain_attribution"
    if market:
        return "market_timeseries"
    if label_col is not None and candidate:
        return "attribution_like_unresolved"
    if detection.get("crypto_asset_field") or any(r["semantic_type"] == "chain" for r in columns):
        return "crypto_non_attribution"
    return "non_crypto"


def _established(columns, label_col, profiles) -> list[str]:
    """What THEMIS DID establish about a file it could not analyse: a list of facts, each traceable
    to a column, so a person learns what was found and not only what was not."""
    out = []
    if label_col:
        out.append(f"'{label_col['column']}' holds attribution labels ({label_col['semantic_label']}).")
    for r in columns:
        if r["semantic_type"] == "chain" and r["status"] != "invalid":
            seen = collections.Counter(chains.resolve_chain(v) or "unrecognised" for v in profiles[r["column"]].sample)
            out.append(f"'{r['column']}' names the chain per row: " + ", ".join(
                f"{k} {n / profiles[r['column']].n:.0%}" for k, n in seen.most_common()) + " of sampled rows.")
        if r["rejected_as_subject"] or (r["semantic_type"].startswith("subject_") and r["status"] == "invalid"):
            out.append(f"'{r['column']}' looks like an identifier column, but its sampled values do not validate "
                       "as identifiers on the chain(s) the file states or that THEMIS supports.")
    return out


def _blockers(subject, chain_res, label_col, columns, detection, dataset_type, confirmed, input_type, c) -> list[dict]:
    out = []

    def add(code, message):
        out.append(dict(code=code, message=message))

    if dataset_type == "attribution_claims":
        if chain_res["status"] == "undetermined":
            add("chain_required", "The blockchain could not be determined from the file. Choose the chain the "
                "identifiers belong to: address validation is chain-specific and will not be skipped.")
        elif chain_res["status"] == "ambiguous":
            add("chain_required", "The identifiers validate on more than one chain "
                f"({', '.join(sorted(k for k, v in chain_res['candidates'].items() if v >= c['min_identifier_valid_rate']))}). "
                "Choose which chain they belong to.")
        if label_col is None or label_col["status"] == "invalid":
            add("missing_label", "No attribution label or category column was identified. A claim needs a subject "
                "AND what is being claimed about it; THEMIS will not invent labels.")
        subj = next((r for r in columns if r["column"] == subject["column"]), None)
        need = [r for r in (subj, label_col) if r and r["status"] == "review"]
        if need and not confirmed:
            add("needs_confirmation", "Low-confidence mapping for " + ", ".join(
                f"'{r['column']}' ({r['semantic_label']}, {r['confidence']:.0%})" for r in need) +
                ": review it and confirm before running.")
    elif dataset_type == "mapping_unresolved":
        for r in columns:
            if r["origin"] == "user" and r["status"] == "invalid":
                add("user_mapping_invalid", f"'{r['column']}' -> {r['semantic_label']}: " + "; ".join(r["notes"]))
        if subject is not None and subject["status"] == "invalid":
            rec = next(r for r in columns if r["column"] == subject["column"])
            add("subject_invalid", f"Column '{subject['column']}' cannot be the claim subject: "
                + "; ".join(rec["notes"]) + ". THEMIS does not accept a subject that fails validation.")
        add("reset_hint", "Reset to THEMIS's inferred mapping to see what THEMIS established on its own; "
            "nothing was analysed.")
    elif dataset_type == "unsupported_subject_kind":
        add("subject_kind_unsupported", f"Column '{subject['column']}' is a {subject['kind']} identifier. THEMIS "
            "recognises that kind of claim subject, but its claim pipeline (reference matching, provenance, "
            "agreement, trust policies) is keyed on addresses; nothing was analysed.")
    else:
        if subject is not None and subject["status"] == "invalid":
            rec = next(r for r in columns if r["column"] == subject["column"])
            add("subject_invalid", f"Column '{subject['column']}' cannot be the claim subject: "
                + "; ".join(rec["notes"]) + ". THEMIS does not accept a subject that fails validation.")
        else:
            add("missing_subject", "No column holds a valid claim subject (a wallet address or another supported "
                "identifier).")
        if label_col is None:
            add("missing_label", "No attribution label or category column was identified.")
    if input_type not in c["analysis_supported_inputs"]:
        add("input_type_unsupported", f"Analysis of '{input_type}' inputs is not implemented in this build: the "
            "table was inspected and pre-flighted on a sample only.")
    return out


def _label_structure(rows, by_sem, c) -> dict:
    """Is the claim's label column (every row of it) a list of tokens ("a,b")? Decided from the column's own values,
    never assumed: most multi-token cells must be built only from tokens that also occur, on their
    own, as whole cells elsewhere in the column. Whitespace inside a token, a quoted literal that
    merely contains a separator, or a one-off combination never qualifies."""
    ml = c["multi_label"]
    rec = next((by_sem[k] for k in ("attribution_category", "attribution_label") if k in by_sem
                and by_sem[k]["status"] != "invalid"), None)
    none = dict(status="single_label", column=rec["column"] if rec else None, separator=None)
    if rec is None:
        return none
    # every row, not the profile sample: whether a rare token also occurs on its own is exactly what a
    # sample gets wrong, and one pass over a column that is already in memory is cheap
    values = [v for v in ((r.get(rec["column"]) or "").strip() for r in rows) if v]
    tok = re.compile(ml["token_pattern"])
    for sep in ml["separators"]:
        whole = collections.Counter(v for v in values if sep not in v)
        multi = [v for v in values if sep in v and all(tok.fullmatch(t) for t in v.split(sep))]
        if not values or len(multi) / len(values) < ml["min_multi_share_of_cells"]:
            continue
        known = [v for v in multi if all(whole[t] >= ml["min_atomic_occurrences"] for t in v.split(sep))]
        if len(known) / len(multi) >= ml["min_known_token_share"]:
            return dict(status="multi_label", column=rec["column"], separator=sep, n_cells=len(values),
                        n_multi_token_cells=len(multi), known_token_share=round(len(known) / len(multi), 4),
                        n_established_tokens=sum(1 for n in whole.values() if n >= ml["min_atomic_occurrences"]))
    return none


def _source_class(columns, profiles, c, n_total) -> int | None:
    """The number of distinct values of a declared-source column that has so few (against many rows)
    that it names a class or method of evidence rather than where each claim came from; else None."""
    for r in columns:
        if r["semantic_type"] == "attribution_source" and r["status"] != "invalid":
            d = profiles[r["column"]].distinct
            if d <= c["source_class_max_distinct"] and n_total > 10 * d:
                return d
    return None


def _extra_warnings(columns, chain_res, profiles, c, n_total) -> list[str]:
    out = []
    if chain_res["status"] == "per_row":
        pr = chain_res["per_row"]
        out += [f"{cid}: only {v['valid_rate']:.0%} of sampled identifiers are valid on this chain "
                f"(minimum {c['min_identifier_valid_rate']:.0%}); its rows will be rejected"
                for cid, v in pr["chains"].items() if v["valid_rate"] < c["min_identifier_valid_rate"]]
        if pr["unresolved_share"]:
            out.append(f"{pr['unresolved_share']:.0%} of sampled rows name a chain THEMIS has no adapter for; "
                       "those rows will be rejected, not assigned a chain")
    d = _source_class(columns, profiles, c, n_total)
    if d is not None:
        src = next(r for r in columns if r["semantic_type"] == "attribution_source" and r["status"] != "invalid")
        out.append(f"{src['column']}: only {d} distinct values across {n_total:,} rows. A handful of values names a "
                   "class or method of evidence, not where each claim came from: it does not establish provenance, "
                   "and different values are not independent sources")
    return out


def _currency_basis(columns, c) -> dict | None:
    """The one timestamp that dates the ATTRIBUTION, if any, and the rule that
    turns it into staleness. A market, transaction, observation, publication or
    unclassified date is never a candidate."""
    by_sem = {r["semantic_type"]: r for r in columns}
    for role in c["currency_roles"]:
        r = by_sem.get(role)
        if r and r["status"] != "invalid":
            years = config_io.load().thresholds.get("staleness_years", 3.0)
            return dict(column=r["column"], role=role, role_label=r["semantic_label"], threshold_years=years,
                        rule=f"a claim is stale when '{r['column']}' ({r['semantic_label'].split(': ')[-1]}) is more "
                             f"than {years} years before the analysis date; a claim with no parseable date is "
                             "currency-unknown, never stale")
    return None


def _claim_mapping(columns, basis, c) -> dict:
    """The legacy {role: column} dict the claim builder reads. `timestamp` is
    populated only from an attribution timestamp (see _currency_basis)."""
    roles = {f["claim_role"]: None for f in c["semantic_fields"].values() if "claim_role" in f}
    for r in columns:
        role = c["semantic_fields"][r["semantic_type"]].get("claim_role")
        if role and r["status"] != "invalid":
            roles[role] = r["column"]
    roles["timestamp"] = basis["column"] if basis else None
    if roles.get("entity") and not roles.get("label") and not roles.get("category"):
        roles["label"] = roles["entity"]      # no other claim content: the entity is what is claimed
    return roles


# what THEMIS established about the file, in the three terms a person acts on
DATASET_STATES = {
    "attribution_claims": "supported_attribution_data",
    "unsupported_subject_kind": "attribution_like_schema_unresolved",
    "unsupported_chain_attribution": "attribution_like_schema_unresolved",
    "attribution_like_unresolved": "attribution_like_schema_unresolved",
    "mapping_unresolved": "schema_unresolved",
    "market_timeseries": "not_attribution_data",
    "crypto_non_attribution": "not_attribution_data",
    "non_crypto": "not_attribution_data",
}
DATASET_TYPE_LABELS = {
    "mapping_unresolved": "Schema unresolved: a mapping you set does not fit this file",
    "attribution_like_unresolved": "Attribution-like data: THEMIS could not establish a schema automatically",
    "attribution_claims": "Attribution claims (a subject and what is claimed about it)",
    "unsupported_subject_kind": "Attribution claims about a subject THEMIS does not analyse yet",
    "unsupported_chain_attribution": "Attribution data on a chain THEMIS has no adapter for",
    "market_timeseries": "Market data (price / volume time series)",
    "crypto_non_attribution": "Cryptocurrency-related data, but not attribution claims",
    "non_crypto": "Not cryptocurrency attribution data",
}


def _checks(dataset_type, subject, chain_res, columns, basis, label_col, timestamp_roles, input_type, c,
            source_class=None) -> list[dict]:
    """The pre-flight as a short reviewable list: {level: ok|warn|fail, text, detail}.
    Built here so no screen re-derives what was checked."""
    by_col = {r["column"]: r for r in columns}
    out = [dict(level="ok" if dataset_type == "attribution_claims" else "fail",
                text=f"Dataset type: {DATASET_TYPE_LABELS[dataset_type]}", detail=None)]
    if subject and subject["status"] != "invalid":
        r = by_col[subject["column"]]
        rate = subject.get("rate_under_chain")
        if rate is None and subject["rates"]:
            rate = max(subject["rates"].values())
        out.append(dict(level="ok" if r["status"] == "ok" else "warn",
                        text=f"Claim subject: '{subject['column']}' ({r['semantic_label']})",
                        detail=None if rate is None else f"{rate:.0%} of sampled values are valid identifiers"))
    else:
        out.append(dict(level="fail", text="Claim subject: none found",
                        detail=(next((n for r in columns if subject and r["column"] == subject["column"]
                                      for n in r["notes"]), None)
                                or "no column holds valid wallet addresses or another supported identifier")))
    if chain_res["status"] == "per_row":
        pr = chain_res["per_row"]
        out.append(dict(level="ok", text=f"Blockchain: stated per row by '{pr['column']}' ({len(pr['chains'])} chains)",
                        detail="; ".join(f"{cid} {v['share']:.0%} of rows, {v['valid_rate']:.0%} valid identifiers"
                                         for cid, v in pr["chains"].items())
                        + (f"; {pr['unresolved_share']:.0%} name a chain THEMIS cannot validate"
                           if pr["unresolved_share"] else "")))
    elif chain_res["status"] == "determined":
        how = {"user": "selected by you", "detected": "detected from the identifier values"}.get(
            chain_res["source"], f"stated by {chain_res['source']}")
        out.append(dict(level="ok", text=f"Blockchain: {chain_res['value']} ({how})",
                        detail=None if chain_res["confidence"] is None else f"confidence {chain_res['confidence']:.0%}"))
    elif chain_res["status"] in ("undetermined", "ambiguous"):
        out.append(dict(level="fail", text=f"Blockchain: {chain_res['status']}: choose one",
                        detail="address validation is chain-specific and is never skipped"))
    if label_col:
        out.append(dict(level="ok" if label_col["status"] == "ok" else "warn",
                        text=f"Attribution label: '{label_col['column']}' ({label_col['semantic_label']})", detail=None))
    else:
        out.append(dict(level="fail", text="Attribution label: none found", detail=None))
    if basis:
        out.append(dict(level="ok", text=f"Staleness uses '{basis['column']}' ({basis['role_label'].split(': ')[-1]})",
                        detail=basis["rule"]))
    else:
        others = ", ".join(f"{col} ({c['semantic_fields'][sem]['label'].split(': ')[-1]})"
                           for col, sem in timestamp_roles.items())
        out.append(dict(level="warn", text="No attribution timestamp mapped: staleness will not be computed",
                        detail=(f"date columns present but none dates the attribution: {others}" if others else None)))
    src = next((r for r in columns if r["semantic_type"] == "attribution_source" and r["status"] != "invalid"), None)
    if src and source_class:
        out.append(dict(level="warn", text=f"Declared source: '{src['column']}' (a class of evidence, not a per-claim source)",
                        detail=f"only {source_class} distinct values: it says how a label was made, not where it came "
                               "from, so it establishes no provenance and different values are not independent sources"))
    else:
        out.append(dict(level="ok" if src else "warn",
                        text=f"Declared source: '{src['column']}'" if src else "No declared-source column mapped",
                        detail=None if src else "provenance of these claims cannot be established"))
    if input_type not in c["analysis_supported_inputs"]:
        out.append(dict(level="fail", text=f"Input type '{input_type}': analysis not implemented",
                        detail="inspected and pre-flighted on a sample only"))
    return out


def _message(status, dataset_type, blockers, detection, established=()) -> str | None:
    if status == "ready":
        return None
    if dataset_type == "unsupported_chain_attribution":
        supported = ", ".join(sorted(chains.all_adapters())) or "none registered"
        body = UNSUPPORTED_CHAIN_MESSAGE.format(field=detection["unsupported_chain_field"], supported=supported)
    elif dataset_type == "market_timeseries":
        body = MARKET_MESSAGE
    elif dataset_type == "crypto_non_attribution":
        body = CRYPTO_NON_ATTRIBUTION_MESSAGE.format(field=detection.get("crypto_asset_field") or "chain")
    elif dataset_type == "non_crypto":
        body = NOT_CRYPTO_MESSAGE
    elif dataset_type == "mapping_unresolved":
        return "Schema unresolved: a mapping you set does not fit this file.\n" + "\n".join(f"- {b['message']}" for b in blockers)
    elif dataset_type == "attribution_like_unresolved":
        return (ATTRIBUTION_LIKE_HEADLINE + "\n" + "\n".join(f"- {t}" for t in established)
                + "\n\nWhy nothing was analysed:\n" + "\n".join(f"- {b['message']}" for b in blockers))
    else:
        return "Analysis blocked at pre-flight.\n\n" + "\n".join(f"- {b['message']}" for b in blockers)
    return f"{HEADLINE_UNSUPPORTED}.\n{NO_SCHEMA}\n\n{body}"
