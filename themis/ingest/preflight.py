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
import datetime, hashlib, json, re

from .. import chains, config_io
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

    def __init__(self, name: str, sample: list[str]):
        self.name, self.sample, self.n = name, sample, len(sample)
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
        # a 0,1,2,3... (or 1,2,3...) counter is a row index, whatever it is called
        self.sequential = (self.n >= 3 and len(ints) == self.n
                           and all(b - a == 1 for a, b in zip(ints, ints[1:])))

    def is_numeric(self, c) -> bool:
        return self.n > 0 and self.numeric >= c["numeric_share_min"]

    def is_date(self, c) -> bool:
        return self.n > 0 and self.date >= c["date_shape_min_share"]


def _rate(sample: list[str], validator) -> float:
    return (sum(1 for v in sample if validator(v)) / len(sample)) if sample else 0.0


def _chain_aliases() -> dict[str, str]:
    return {a.lower(): cid for cid, ad in chains.all_adapters().items() for a in ad.symbol_aliases}


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
    if sem in ("attribution_label", "attribution_category", "attribution_actor", "attribution_evidence"):
        return p.text
    if sem == "attribution_source":
        return p.url if name_score == 0 else min(1.0, p.url + p.text)
    if sem == "attribution_confidence":
        return 1.0 if (p.is_numeric(c) or p.distinct <= c["confidence_categorical_max_distinct"]) else 0.0
    if sem == "chain":
        al = _chain_aliases()
        return sum(1 for v in p.sample if v.strip().lower() in al) / p.n
    if sem.startswith("ts_"):
        return p.date
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
            raise ValueError(f"unknown mapping role {role!r}")
        if col not in fieldnames:
            raise ValueError(f"mapping names column {col!r}, which is not in the file")
        if out.get(col, sem) != sem:
            raise ValueError(f"column {col!r} is mapped to two roles")
        out[col] = sem
    return out


def _check_overrides(overrides: dict, fieldnames: list[str], c: dict) -> None:
    seen: dict[str, str] = {}
    for col, sem in overrides.items():
        if col not in fieldnames:
            raise ValueError(f"mapping names column {col!r}, which is not in the file")
        if sem not in c["semantic_fields"]:
            raise ValueError(f"unknown semantic field {sem!r}")
        if _is_unique(sem, c):
            g = _group(sem)
            if g in seen and seen[g] != col:
                raise ValueError(f"columns {seen[g]!r} and {col!r} are both mapped to {sem!r}")
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
        raise ValueError(f"unknown chain {chain!r}; supported: {', '.join(sorted(chains.all_adapters())) or 'none'}")

    n_total = total_rows if total_rows is not None else len(rows)
    n_sample = sample_size or c["sample_size"]
    profiles = {f: _Profile(f, _detect.sample_values(rows, f, n_sample)) for f in fieldnames}
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
    chain_res = _resolve_chain(subject, columns, ctx, chain)
    if subject and subject["kind"] == "address" and chain_res["value"]:
        # the subject's status is what it is under the chosen/detected chain
        _revalidate_subject(columns, subject, chain_res["value"], ctx)
        subject = _subject_of(columns, ctx)

    detection = _detection(rows, fieldnames, subject, chain_res, n_sample)
    label_col = next((by_sem[s] for s in ("attribution_label", "attribution_category")
                      if s in by_sem and by_sem[s]["status"] != "invalid"), None)
    dataset_type = _dataset_type(subject, label_col, market, detection, columns, c)

    blockers = _blockers(subject, chain_res, label_col, columns, detection, dataset_type, confirmed, input_type, c)
    warnings = [f"{r['column']}: {n}" for r in columns for n in r["notes"]
                if r["status"] in ("review", "invalid")]
    status = ("unsupported" if dataset_type not in ("attribution_claims", "unsupported_subject_kind")
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
        dataset_type=dataset_type, status=status, can_analyze=(status == "ready"),
        subject=subject, chain=chain_res, columns=columns, required=required,
        mapping=mapping, currency_basis=basis,
        timestamp_roles={r["column"]: r["semantic_type"] for r in columns if r["semantic_type"].startswith("ts_")},
        blockers=blockers, warnings=warnings, detection=detection,
        dataset_type_label=DATASET_TYPE_LABELS[dataset_type],
        checks=_checks(dataset_type, subject, chain_res, columns, basis, label_col,
                       {r["column"]: r["semantic_type"] for r in columns if r["semantic_type"].startswith("ts_")},
                       input_type, c),
        user_confirmed=bool(confirmed), user_overrides=overrides,
        user_selected_chain=chain,
        message=_message(status, dataset_type, blockers, detection),
    )


# ---------------------------------------------------------------- the pieces
def _column_record(col: str, a: dict, p: _Profile, ctx: _Ctx, rej) -> dict:
    c, sem = ctx.c, a["sem"]
    fld = c["semantic_fields"][sem]
    notes, user = list(a["notes"]), a["origin"] == "user"
    # a user's choice is judged on the values alone: what the column is called is not evidence for it
    ns = 1.0 if user else _name_score(col, fld.get("hints", {}), c)
    value = None if sem in _SHAPE_ONLY else _value_score(sem, col, ns, ctx)
    status = "ok"
    if sem in ("unmapped", "numeric_unclassified"):
        status = "unused"
    elif p.n == 0 and user:
        status, notes = "invalid", notes + ["the column has no values"]
    elif sem.startswith("subject_") and c["subject_kinds"][fld["subject_kind"]]["validator"] is not None \
            and value < c["min_identifier_valid_rate"]:
        status = "invalid"
        notes.append(f"only {value:.0%} of sampled values are valid identifiers for any supported chain "
                     f"(minimum {c['min_identifier_valid_rate']:.0%})")
    elif user and sem.startswith("ts_") and sem not in _SHAPE_ONLY and sem != "ts_unclassified" and not p.is_date(c):
        status = "invalid"
        notes.append(f"only {p.date:.0%} of sampled values are ISO dates: this column cannot date a claim")
    elif user and value is not None and value < 0.5:
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
                notes=notes, subject_kind=fld.get("subject_kind"))


def _subject_of(columns: list[dict], ctx: _Ctx) -> dict | None:
    r = next((r for r in columns if r["semantic_type"].startswith("subject_")), None)
    if r is None:
        return None
    kind = r["subject_kind"]
    return dict(column=r["column"], kind=kind, status=r["status"], origin=r["origin"],
                confidence=r["confidence"], analyzable=ctx.c["subject_kinds"][kind]["analyzable"],
                rates=ctx.subject_rates(r["column"], kind))


def _revalidate_subject(columns, subject, chain_id, ctx) -> None:
    """Re-decide the subject's status under the chain it will really be
    validated against, not the best of all chains."""
    rate = subject["rates"].get(chain_id)
    for r in columns:
        if r["column"] != subject["column"]:
            continue
        if rate is not None and rate < ctx.c["min_identifier_valid_rate"]:
            if r["status"] != "invalid":       # already explained by the all-chains check
                r["notes"].append(f"{rate:.0%} of sampled values are valid {chain_id} identifiers "
                                  f"(minimum {ctx.c['min_identifier_valid_rate']:.0%})")
            r["status"] = "invalid"
    subject["rate_under_chain"] = rate


def _resolve_chain(subject, columns, ctx: _Ctx, user_chain: str | None) -> dict:
    """Chain from, in order: what the user chose, an explicit chain column, then
    the subject's values. Unknown or ambiguous is reported as such: it is never
    defaulted, and a chain-dependent analysis waits for the user."""
    c = ctx.c
    base = dict(value=None, status="not_required", source=None, confidence=None, candidates={})
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
        al = _chain_aliases()
        seen = {al.get(v.strip().lower()) for v in ctx.profiles[col["column"]].sample}
        if len(seen) == 1 and None not in seen:
            return dict(base, value=next(iter(seen)), status="determined",
                        source=f"column:{col['column']}", confidence=col["confidence"])
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
    if subject and subject["kind"] == "address" and chain_res["value"] and subject["status"] != "invalid":
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
    if detection.get("unsupported_chain_field"):
        return "unsupported_chain_attribution"
    if market:
        return "market_timeseries"
    if detection.get("crypto_asset_field") or any(r["semantic_type"] == "chain" for r in columns):
        return "crypto_non_attribution"
    return "non_crypto"


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
    return roles


DATASET_TYPE_LABELS = {
    "attribution_claims": "Attribution claims (a subject and what is claimed about it)",
    "unsupported_subject_kind": "Attribution claims about a subject THEMIS does not analyse yet",
    "unsupported_chain_attribution": "Attribution data on a chain THEMIS has no adapter for",
    "market_timeseries": "Market data (price / volume time series)",
    "crypto_non_attribution": "Cryptocurrency-related data, but not attribution claims",
    "non_crypto": "Not cryptocurrency attribution data",
}


def _checks(dataset_type, subject, chain_res, columns, basis, label_col, timestamp_roles, input_type, c) -> list[dict]:
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
    if chain_res["status"] == "determined":
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
    out.append(dict(level="ok" if src else "warn",
                    text=f"Declared source: '{src['column']}'" if src else "No declared-source column mapped",
                    detail=None if src else "provenance of these claims cannot be established"))
    if input_type not in c["analysis_supported_inputs"]:
        out.append(dict(level="fail", text=f"Input type '{input_type}': analysis not implemented",
                        detail="inspected and pre-flighted on a sample only"))
    return out


def _message(status, dataset_type, blockers, detection) -> str | None:
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
    else:
        return "Analysis blocked at pre-flight.\n\n" + "\n".join(f"- {b['message']}" for b in blockers)
    return f"{HEADLINE_UNSUPPORTED}.\n{NO_SCHEMA}\n\n{body}"
