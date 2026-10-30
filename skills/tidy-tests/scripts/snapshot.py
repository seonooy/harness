#!/usr/bin/env python3
"""Record a repo's state before an audit or test run, and report what changed afterwards.

    python3 snapshot.py start REPO STATE.json     # before running suites / starting the audit
    python3 snapshot.py check REPO STATE.json     # after: files written since start, HEAD/branch/status drift

`check` lists every file created or modified under REPO since `start` (caches and dependency
dirs excluded) — test runs that write into the owner's tree show up here, including gitignored
paths — and says whether HEAD, the branch, or the working-tree status changed underneath you
(someone committed, switched branches, or kept editing). Exit 1 when anything changed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", ".vite", ".turbo", ".next", "dist", "build", "coverage", ".cache"}


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def state(repo: Path) -> dict:
    status = git(repo, "status", "--porcelain")
    return {
        "head": git(repo, "rev-parse", "HEAD"),
        "branch": git(repo, "branch", "--show-current"),
        "status_hash": hashlib.sha1(status.encode()).hexdigest()[:12],
        "dirty_files": len(status.splitlines()),
    }


def written_since(repo: Path, since: float) -> list[str]:
    hits = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if path.stat().st_mtime >= since:
                    hits.append(str(path.relative_to(repo)))
            except OSError:
                pass
    return sorted(hits)


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] not in {"start", "check"}:
        sys.exit(__doc__)
    mode, repo, state_file = sys.argv[1], Path(sys.argv[2]).resolve(), Path(sys.argv[3])
    if mode == "start":
        record = {"repo": str(repo), "time": time.time(), **state(repo)}
        state_file.write_text(json.dumps(record, indent=1))
        print(f"recorded {repo} @ {record['branch']} {record['head'][:9]} ({record['dirty_files']} dirty files)")
        return
    before = json.loads(state_file.read_text())
    now = state(repo)
    changed = False
    for key in ("branch", "head", "status_hash"):
        if before[key] != now[key]:
            changed = True
            print(f"{key} changed: {before[key]} → {now[key]}")
    files = written_since(repo, before["time"])
    if files:
        changed = True
        print(f"{len(files)} file(s) written under the repo since start:")
        print("\n".join(f"  {f}" for f in files[:200]))
    if not changed:
        print("no change since start")
    sys.exit(1 if changed else 0)


if __name__ == "__main__":
    main()
