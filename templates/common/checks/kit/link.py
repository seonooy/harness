from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from .config import load_config
from .gitio import is_ignored, is_tracked, main_checkout, toplevel
from .install import INSTALL_RECORD, append_exclude

# Linking a worktree to the private files of the main checkout.
#
# The personal placement keeps the kit and the private instruction files out of git, so a worktree
# made with `git worktree add` starts without them. install.json lists what a worktree needs under
# `links`, as paths relative to the repository root, and stages.json lists the virtual environments
# (`venvs`) the tools run from. `harness.py link` makes each a symlink to the same path in the main
# checkout, so every worktree shares one kit, one record and one tool environment. `check doctor`
# asks missing_links what is still missing.
#
# Both follow one rule for what a worktree should have: what the main checkout has, unless git
# tracks that path in the worktree (the branch has a file of its own there).

CHECKS = Path(".ai") / "checks"


def _wanted(top: Path, main: Path, paths: List[str]) -> List[str]:
    """Of `paths` (relative, a leading "/" allowed), the ones the worktree at `top` should have."""
    wanted: List[str] = []
    for raw in paths:
        rel = raw.strip("/")
        if not rel or rel in wanted:
            continue
        if os.path.lexists(str(main / rel)) and not is_tracked(top, rel):
            wanted.append(rel)
    return wanted


def _links_of(main: Path) -> List[str]:
    """The `links` of the main checkout's install record. Raises OSError or ValueError when it
    cannot be read."""
    record = json.loads((main / INSTALL_RECORD).read_text(encoding="utf-8"))
    links = record.get("links", []) if isinstance(record, dict) else []
    return [link for link in links if isinstance(link, str)]


def missing_links(cwd: Path) -> List[str]:
    """The links the work tree that holds cwd should have and does not. A link whose target is
    gone does not exist either.

    install.json is read from the main checkout: a worktree that is not linked yet has none.
    Raises OSError or ValueError when it cannot be read.
    """
    top, main = toplevel(cwd), main_checkout(cwd)
    return [rel for rel in _wanted(top, main, _links_of(main)) if not (top / rel).exists()]


def link_worktree(cwd: Path) -> List[Path]:
    """Make the links and virtual environments of the main checkout symlinks in the linked
    worktree that holds cwd, each an absolute link to the same path in the main checkout. Return
    the links it made. A path that is there already is left alone; the main checkout itself gets
    nothing.

    A link is a file to git, so a folder-only ignore rule (".venv/") does not hide it: a link git
    would show is added to .git/info/exclude.
    """
    top, main = toplevel(cwd), main_checkout(cwd)
    if top == main:
        return []
    venvs = load_config(main / CHECKS / "stages.json").venvs
    made: List[Path] = []
    for rel in _wanted(top, main, _links_of(main) + venvs):
        path = top / rel
        if os.path.lexists(str(path)):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(main / rel), str(path))
        made.append(path)
    shown = [path.relative_to(top).as_posix() for path in made]
    append_exclude(top, [rel for rel in shown if not is_ignored(top, rel)])
    return made
