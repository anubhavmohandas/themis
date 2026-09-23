"""SQLite inputs (.db / .sqlite / .sqlite3), built for databases too large to
load: a multi-GB wallet-classification DB is opened read-only, inspected through
its metadata, and read as a stream of bounded chunks. Nothing here ever
materialises a table, and nothing converts it to a CSV.

    open -> list tables (+ row counts) -> pick a table -> list columns
         -> sample rows -> pre-flight on the sample -> [stream chunks]

Only the first five steps are used by the API today; `iter_rows` is the
interface a streaming analysis will consume (see preflight.yml:
analysis_supported_inputs).
"""
from __future__ import annotations
import contextlib, pathlib, sqlite3, time
from collections.abc import Iterator

from .. import config_io


def cfg() -> dict:
    return config_io.load().preflight["sqlite"]


def is_sqlite_path(path: str) -> bool:
    return pathlib.Path(path).suffix.lower() in cfg()["extensions"]


@contextlib.contextmanager
def open_readonly(path: str):
    """Read-only, so inspecting a database can never modify it (or create a
    journal next to it)."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"no such database: {path}")
    con = sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro", uri=True)
    try:
        yield con
    finally:
        con.close()


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _require_table(con: sqlite3.Connection, table: str) -> None:
    # identifiers cannot be bound as parameters, so a table name is only ever
    # used after it has been found in the database's own catalogue
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?", (table,)).fetchone():
        raise ValueError(f"no table {table!r} in this database")


def count_rows(con: sqlite3.Connection, table: str, timeout_s: float) -> int | None:
    """Exact COUNT(*), or None if it did not finish within `timeout_s`: on a
    multi-GB table it is a full scan, and inspection must not hang on it."""
    deadline = time.monotonic() + timeout_s
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        return con.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0]
    except sqlite3.OperationalError:      # "interrupted"
        return None
    finally:
        con.set_progress_handler(None, 0)


def list_tables(path: str, count: bool = True) -> list[dict]:
    with open_readonly(path) as con:
        rows = con.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name")
        out = []
        for n, kind in rows.fetchall():
            cols = con.execute(f"PRAGMA table_info({_quote(n)})").fetchall()
            n_rows = count_rows(con, n, cfg()["count_timeout_seconds"]) if (count and kind == "table") else None
            out.append(dict(table=n, kind=kind, n_columns=len(cols), n_rows=n_rows,
                            row_count_status="exact" if n_rows is not None else
                            ("not_counted" if not count or kind != "table" else "not_counted_within_time_limit")))
        return out


def columns(path: str, table: str) -> list[dict]:
    with open_readonly(path) as con:
        _require_table(con, table)
        return [dict(name=r[1], declared_type=r[2], not_null=bool(r[3]), default=r[4], primary_key=bool(r[5]))
                for r in con.execute(f"PRAGMA table_info({_quote(table)})")]


def sqlite_version(path: str) -> str:
    with open_readonly(path) as con:
        return con.execute("SELECT sqlite_version()").fetchone()[0]


def integrity_check(path: str, quick: bool = True, timeout_s: float | None = None) -> dict:
    """`quick_check` reads every page but skips the (much slower) cross-checks
    of `integrity_check`; still a full scan of a multi-GB file, so it is time-
    limited like `count_rows`. Never raises: a malformed database is a result,
    not a crash."""
    timeout_s = timeout_s if timeout_s is not None else cfg()["count_timeout_seconds"]
    pragma = "quick_check" if quick else "integrity_check"
    deadline = time.monotonic() + timeout_s
    try:
        with open_readonly(path) as con:
            con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 50_000)
            try:
                rows = [r[0] for r in con.execute(f"PRAGMA {pragma}").fetchall()]
            except sqlite3.OperationalError:
                return dict(status="not_checked_within_time_limit", errors=[])
            finally:
                con.set_progress_handler(None, 0)
        ok = rows == ["ok"]
        return dict(status="ok" if ok else "malformed", errors=[] if ok else rows)
    except sqlite3.DatabaseError as e:
        return dict(status="unreadable", errors=[str(e)])


def indexes(path: str, table: str) -> list[dict]:
    with open_readonly(path) as con:
        _require_table(con, table)
        out = []
        for _, name, unique, origin, _partial in con.execute(f"PRAGMA index_list({_quote(table)})").fetchall():
            cols = [r[2] for r in con.execute(f"PRAGMA index_info({_quote(name)})").fetchall() if r[2] is not None]
            out.append(dict(name=name, columns=cols, unique=bool(unique), origin=origin))
        return out


def foreign_keys(path: str, table: str) -> list[dict]:
    """Declared FKs only (`PRAGMA foreign_key_list`) - a real relationship the
    schema itself states, distinct from one `relational.infer_relationships`
    only guesses from column names."""
    with open_readonly(path) as con:
        _require_table(con, table)
        out = []
        for _id, _seq, ref_table, frm, to, on_update, on_delete, match in \
                con.execute(f"PRAGMA foreign_key_list({_quote(table)})").fetchall():
            out.append(dict(table=ref_table, from_column=frm, to_column=to,
                            on_update=on_update, on_delete=on_delete))
        return out


def inspect(path: str, *, count: bool = True, sample_size: int = 5) -> dict:
    """Everything THEMIS shows before analysis may even be considered: the
    file, the schema, and enough of the data to judge it by eye. Nothing here
    reads more than a bounded sample of any table's rows.

    `integrity_check` never raises; this function must not either - a file
    damaged enough that `sqlite_master` itself cannot be read would otherwise
    raise sqlite3.DatabaseError out of `list_tables`/`sqlite_version` before
    the caller ever sees why. The schema is only read once the file passes
    its own integrity check."""
    p = pathlib.Path(path)
    integrity = integrity_check(path)
    if integrity["status"] != "ok":
        return dict(filename=p.name, size_bytes=p.stat().st_size, sqlite_version=None,
                    integrity=integrity, tables=[], views=[])
    tables = list_tables(path, count=count)
    out_tables = []
    for t in tables:
        name = t["table"]
        cols = columns(path, name)
        entry = dict(t, columns=cols)
        if t["kind"] == "table":
            entry["indexes"] = indexes(path, name)
            entry["foreign_keys"] = foreign_keys(path, name)
            try:
                sample, _ = sample_rows(path, name, sample_size)
            except sqlite3.OperationalError:
                sample = []
            entry["sample_rows"] = sample
        out_tables.append(entry)
    return dict(filename=p.name, size_bytes=p.stat().st_size, sqlite_version=sqlite_version(path),
                integrity=integrity, tables=[t for t in out_tables if t["kind"] == "table"],
                views=[t for t in out_tables if t["kind"] == "view"])


def _as_text(v) -> str:
    """Rows are handed to the pre-flight as text, exactly as a CSV cell would be."""
    if v is None:
        return ""
    return v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v)


def sample_rows(path: str, table: str, n: int) -> tuple[list[dict], list[str]]:
    """`n` rows spread across the table (a rowid-strided sample), so a table sorted
    by label or date is not judged on its first rows alone. Falls back to the
    first `n` rows for a WITHOUT ROWID table or a view."""
    chunks = cfg()["sample_chunks"]
    with open_readonly(path) as con:
        _require_table(con, table)
        q = _quote(table)
        cur = con.cursor()
        try:
            lo, hi = cur.execute(f"SELECT MIN(rowid), MAX(rowid) FROM {q}").fetchone()
            strided = lo is not None and hi is not None
        except sqlite3.OperationalError:
            strided = False
        if not strided:
            cur.execute(f"SELECT * FROM {q} LIMIT ?", (n,))
            names = [d[0] for d in cur.description]
            return [dict(zip(names, map(_as_text, r))) for r in cur.fetchall()], names
        per = max(1, -(-n // chunks))
        step = max(1, (hi - lo + 1) // chunks)
        rows, names = [], []
        for i in range(chunks):
            cur.execute(f"SELECT * FROM {q} WHERE rowid >= ? LIMIT ?", (lo + i * step, per))
            names = [d[0] for d in cur.description]
            rows.extend(dict(zip(names, map(_as_text, r))) for r in cur.fetchall())
        return rows[:n], names


def iter_rows(path: str, table: str, chunk_rows: int | None = None) -> Iterator[list[dict]]:
    """The whole table as bounded chunks of rows (constant memory). This is the
    interface a streaming analysis will consume."""
    size = chunk_rows or cfg()["fetch_chunk_rows"]
    with open_readonly(path) as con:
        _require_table(con, table)
        cur = con.execute(f"SELECT * FROM {_quote(table)}")
        names = [d[0] for d in cur.description]
        while True:
            batch = cur.fetchmany(size)
            if not batch:
                return
            yield [dict(zip(names, map(_as_text, r))) for r in batch]
