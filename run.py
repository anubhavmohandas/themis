#!/usr/bin/env python3
"""Pull latest, sync deps, then run the API (FastAPI) and the frontend (Vite) together.

Windows, macOS, Linux:  python run.py     (python3 run.py on mac/linux)
Ctrl-C stops both. Env: THEMIS_API_PORT (default 5001), NO_PULL=1 to skip the git pull.
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIN = os.name == "nt"
PORT = os.environ.get("THEMIS_API_PORT", "5001")


BANNER = r"""
  _____ _   _ _____ __  __ ___ ____
 |_   _| | | | ____|  \/  |_ _/ ___|
   | | | |_| |  _| | |\/| || |\___ \
   | | |  _  | |___| |  | || | ___) |
   |_| |_| |_|_____|_|  |_|___|____/

        created by Anubhav Mohandas
"""


STOPS = [(0, 229, 255), (170, 80, 255), (255, 60, 160)]  # cyan -> violet -> pink


def color_at(t):
    """RGB along STOPS for t in [0, 1]."""
    x = t * (len(STOPS) - 1)
    i = min(int(x), len(STOPS) - 2)
    a, b = STOPS[i], STOPS[i + 1]
    return [round(p + (q - p) * (x - i)) for p, q in zip(a, b)]


def fg(r, g, b):
    if os.environ.get("COLORTERM") in ("truecolor", "24bit"):
        return f"\033[1;38;2;{r};{g};{b}m"
    # 256-colour cube fallback (macOS Terminal.app, older Windows consoles)
    return f"\033[1;38;5;{16 + 36 * round(r / 51) + 6 * round(g / 51) + round(b / 51)}m"


def banner():
    os.system("")  # no-op elsewhere; enables ANSI escapes on Windows 10+ consoles
    if not sys.stdout.isatty() or "NO_COLOR" in os.environ:
        return print(BANNER)
    lines = BANNER.split("\n")
    w = max(map(len, lines)) - 1
    for line in lines:
        print("".join(c if c == " " else fg(*color_at(i / w)) + c for i, c in enumerate(line)) + "\033[0m")


def run(cmd, cwd=ROOT, check=True):
    return subprocess.run(cmd, cwd=cwd, check=check)


def sync(stamp, deps, cmd, cwd=ROOT):
    """Run the install only on first run or when a dep file is newer than the stamp
    (e.g. after a pull changes it) - pip -e rebuilds and hits the network every time otherwise."""
    if stamp.exists() and all(d.stat().st_mtime <= stamp.stat().st_mtime for d in deps):
        return
    run(cmd, cwd=cwd)
    stamp.touch()


def stop(p):
    if p.poll() is not None:
        return
    if WIN:  # npm.cmd spawns node; /T kills the whole tree
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        import signal
        os.killpg(p.pid, signal.SIGTERM)


def main():
    banner()
    if not shutil.which("git") or not (npm := shutil.which("npm")):
        sys.exit("error: git and npm (Node.js) must be on PATH")

    if os.environ.get("NO_PULL") != "1":
        # --ff-only never merges or rewrites; a dirty/diverged tree warns instead of aborting
        if run(["git", "pull", "--ff-only"], check=False).returncode:
            print("warning: git pull failed (local changes or diverged branch); "
                  "running current checkout", file=sys.stderr)

    venv = ROOT / ".venv"
    if not venv.exists():
        run([sys.executable, "-m", "venv", str(venv)])
    py = str(venv / ("Scripts/python.exe" if WIN else "bin/python"))
    sync(venv / ".deps-stamp", [ROOT / "pyproject.toml"],
         [py, "-m", "pip", "install", "-q", "-e", ".[ui]"])
    web = ROOT / "frontend"
    sync(web / "node_modules" / ".deps-stamp", [web / "package.json", web / "package-lock.json"],
         [npm, "install", "--no-audit", "--no-fund", "--silent"], cwd=web)

    procs = [
        subprocess.Popen([py, "-m", "themis.api"], cwd=ROOT,
                         env={**os.environ, "THEMIS_API_PORT": PORT},
                         start_new_session=not WIN),
        subprocess.Popen([npm, "run", "dev"], cwd=ROOT / "frontend",
                         env={**os.environ, "VITE_API_URL": f"http://127.0.0.1:{PORT}"},
                         start_new_session=not WIN),
    ]
    print(f"API:      http://127.0.0.1:{PORT}\nFrontend: http://localhost:5173")
    try:
        while all(p.poll() is None for p in procs):  # either one dying ends the run
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            stop(p)


if __name__ == "__main__":
    main()
