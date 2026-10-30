from __future__ import annotations

import sys
from pathlib import Path
from typing import List

# python3 .ai/checks/check.py <doctor|fast|all|fix|profile> [--staged] [paths...]
#
# Exit codes: 0 passed, 1 failed, 2 incomplete. The kit next to this script does the work. The
# repository it checks is the one that holds the current directory, not the one this file is in,
# so the main checkout's check.py run from a linked worktree checks that worktree.

USAGE = "사용법: python3 .ai/checks/check.py <doctor|fast|all|fix|프로필> [--staged] [경로...]"


def main(argv: List[str]) -> int:
    """`check.py <doctor|profile> [--staged] [paths...]`, run from inside the tree to check."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from kit.doctor import doctor
    from kit.runner import EXIT_INCOMPLETE, run

    for stream in (sys.stdout, sys.stderr):  # Korean output whatever the locale
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    if not argv or argv[0].startswith("-"):
        sys.stderr.write(USAGE + "\n")
        return EXIT_INCOMPLETE
    profile, rest = argv[0], argv[1:]
    # A mistyped option read as a path selects no file, and the run would pass on nothing.
    unknown = [arg for arg in rest if arg.startswith("-") and arg != "--staged"]
    if unknown:
        sys.stderr.write(f"알 수 없는 옵션: {' '.join(unknown)}\n{USAGE}\n")
        return EXIT_INCOMPLETE
    if profile == "doctor":
        return doctor(Path.cwd(), out=sys.stdout)
    paths = [arg for arg in rest if arg != "--staged"]
    return run(Path.cwd(), profile, paths, staged="--staged" in rest, out=sys.stdout)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
