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
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        out = []
        for n in names:
            cols = con.execute(f"PRAGMA table_info({_quote(n)})").fetchall()
            n_rows = count_rows(con, n, cfg()["count_timeout_seconds"]) if count else None
            out.append(dict(table=n, n_columns=len(cols), n_rows=n_rows,
                            row_count_status="exact" if n_rows is not None else
                            ("not_counted" if not count else "not_counted_within_time_limit")))
        return out


def columns(path: str, table: str) -> list[dict]:
    with open_readonly(path) as con:
        _require_table(con, table)
        return [dict(name=r[1], declared_type=r[2], primary_key=bool(r[5]))
                for r in con.execute(f"PRAGMA table_info({_quote(table)})")]


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
