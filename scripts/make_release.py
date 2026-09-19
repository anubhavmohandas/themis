#!/usr/bin/env python3
"""Build the clean submission directory (and optionally its ZIP) from a pinned
git commit - never from the working tree, so untracked files, virtualenvs,
node_modules, caches, logs, downloaded datasets and concurrent edits cannot get in.

    python scripts/make_release.py [--commit HEAD] [--out release/themis] [--zip release/THEMIS_v1.0-paper-rc1.zip] [--tag v1.0-paper-rc1]

What it removes from what git tracks: the third-party-derived data files under
demo_data/ and provenance_register.html (the paper says the derived observation
table is not redistributed - THIRD_PARTY_DATA.md), the previous dashboard kept
under frontend/legacy, and this script (packaging tooling, needs git). It then
writes demo_data/README.md and RELEASE_MANIFEST.json (commit, per-file sha256).
The ZIP is deterministic: sorted entries, fixed timestamps, fixed modes.
"""
from __future__ import annotations
import argparse, datetime, hashlib, io, json, os, pathlib, re, shutil, stat, subprocess, sys, tarfile, zipfile

EXCLUDE = ("demo_data/manifest.json", "demo_data/observations_sample.csv.gz", "demo_data/revenue.csv.gz",
           "demo_data/verified_anchors.txt.gz", "demo_data/ground_truth.csv",
           "provenance_register.html", "frontend/legacy", "scripts/make_release.py")
FORBIDDEN = re.compile(r"(^|/)(\.git|\.venv|venv|node_modules|__pycache__|\.pytest_cache|dist|external_data|results|"
                       r"__MACOSX|\.idea|\.vscode)(/|$)|\.DS_Store$|\.pyc$|\.egg-info(/|$)")
DEMO_README = """# demo_data

Intentionally empty in a release. The paper's data statement is that the derived
observation table is not redistributed, because the redistribution terms of the
constituent sources differ (see ../THIRD_PARTY_DATA.md), so the reference corpus is
not shipped.

Build it from the sources you fetch yourself:

    python scripts/build_corpus.py --out build/ --tagpack ... (see ../REPRODUCE.md section 3)

then point THEMIS at it with `--data-dir build` or `THEMIS_DATA_DIR=build`.
`themis --observations build/observations.csv.gz ... audit` reads the corpus itself;
`--data-dir` supplies the task inputs (revenue, anchors, ground truth).
"""


def sh(*a, **k):
    return subprocess.run(a, check=True, capture_output=True, **k).stdout


def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", default="HEAD"); ap.add_argument("--out", default="release/themis")
    ap.add_argument("--zip", help="also write a deterministic ZIP of the directory")
    ap.add_argument("--tag", default="v1.0-paper-rc1", help="release label recorded in RELEASE_MANIFEST.json")
    a = ap.parse_args()
    commit = sh("git", "rev-parse", a.commit, text=True).strip()
    when = datetime.datetime.fromtimestamp(int(sh("git", "show", "-s", "--format=%ct", commit, text=True)),
                                           datetime.timezone.utc)
    if sh("git", "status", "--porcelain", text=True).strip():
        print("warning: working tree has uncommitted changes; they are NOT in the release (built from "
              f"{commit[:12]})", file=sys.stderr)
    out = pathlib.Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(sh("git", "archive", "--format=tar", commit)), mode="r:") as t:
        t.extractall(out, filter="data")
    for rel in EXCLUDE:
        p = out / rel
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    (out / "demo_data").mkdir(exist_ok=True)
    (out / "demo_data" / "README.md").write_text(DEMO_README)
    files = sorted(p for p in out.rglob("*") if p.is_file())
    bad = [str(p.relative_to(out)) for p in files if FORBIDDEN.search(p.relative_to(out).as_posix())]
    if bad:
        sys.exit(f"forbidden paths in release: {bad}")
    manifest = dict(name="themis", version=re.search(r'version = "([^"]+)"', (out / "pyproject.toml").read_text()).group(1),
                    tag=a.tag, git_commit=commit, commit_time_utc=when.isoformat(),
                    files={p.relative_to(out).as_posix(): sha256(p) for p in files})
    (out / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"{len(manifest['files'])} files -> {out} (commit {commit[:12]})")
    if a.zip:
        z = pathlib.Path(a.zip); z.parent.mkdir(parents=True, exist_ok=True)
        stamp = (max(when.year, 1980), when.month, when.day, when.hour, when.minute, when.second)
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for p in sorted(out.rglob("*")):
                if not p.is_file():
                    continue
                info = zipfile.ZipInfo(f"{out.name}/{p.relative_to(out).as_posix()}", stamp)
                info.external_attr = ((0o755 if os.access(p, os.X_OK) else 0o644) | stat.S_IFREG) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, p.read_bytes())
        print(f"{z} {z.stat().st_size:,} bytes sha256 {sha256(z)}")


if __name__ == "__main__":
    main()
