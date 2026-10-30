from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .config import Stage
from .gitio import export_tree
from .parsers import Violation, il_pair

# What the work tree's violations are compared with.
#
# A violation is new when the reference does not have it. The reference is one of two things:
#   * personal placement: the same tool run on an export of the merge-base (exported). The result
#     is kept in ReferenceCache, because the merge-base stays put while a branch is worked on and
#     running a tool on it again would only repeat itself.
#   * shared placement: the baseline file. It lists the violations that were there when the kit
#     was installed, each with the reason it is allowed. It only ever shrinks. An entry the tree
#     no longer has is stale: stale() reports it so that it gets deleted (prune_baseline).
#
# Violations are compared by fingerprint, and counted. A line can be flagged twice in the same
# words, and the reference having one of them does not excuse the second. In the personal
# placement a violation that the merge-base has at another path, where the work tree no longer
# has it, moved with its line and is not new either (new_and_moved).

BASELINE_VERSION = 1

# What an entry of the baseline file says. `reason` is why the violation is allowed; nothing reads
# it but people, and prune_baseline keeps it.
_ENTRY_KEYS = ("path", "code", "message", "text", "reason")


# --- comparing ---------------------------------------------------------------------------------


def _beyond(
    a: List[Violation],
    b: List[Violation],
    key: Callable[[Violation], Tuple[str, ...]] = Violation.fingerprint,
) -> List[bool]:
    """For each violation of a: True if b does not account for it. b accounts for as many
    violations of a key (the fingerprint unless given) as it holds, the first ones in the order
    of a."""
    budget = Counter(key(v) for v in b)
    flags: List[bool] = []
    for v in a:
        fingerprint = key(v)
        if budget[fingerprint] > 0:
            budget[fingerprint] -= 1
            flags.append(False)
        else:
            flags.append(True)
    return flags


def multiset_diff(a: List[Violation], b: List[Violation]) -> List[Violation]:
    """What a has that b does not: for each fingerprint, as many violations of a as it has more
    than b. They come in the order of a."""
    return [v for v, beyond in zip(a, _beyond(a, b)) if beyond]


def _without_path(v: Violation) -> Tuple[str, ...]:
    return dataclasses.replace(v, path="").fingerprint()


def new_and_moved(
    a: List[Violation], b: List[Violation]
) -> Tuple[List[Violation], List[Violation]]:
    """What a has that b does not (multiset_diff), as two lists: the new violations, and those
    that moved from another file. One moved if b has it at another path, in the same code,
    message and line text, and a no longer has it there. One with no line text never moved."""
    extra = multiset_diff(a, b)
    lost = [v for v in multiset_diff(b, a) if v.text.strip()]
    flags = _beyond(extra, lost, _without_path)
    new = [v for v, beyond in zip(extra, flags) if beyond]
    moved = [v for v, beyond in zip(extra, flags) if not beyond]
    return new, moved


def _write_json(path: Path, data: Any) -> None:
    """Replace path with data as JSON in one step, so a reader sees the old file or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


# --- baseline ----------------------------------------------------------------------------------


def _read_baseline(path: Path) -> Optional[Dict[str, Any]]:
    """The parsed baseline file, or None if there is none. A file that is not a baseline raises
    ValueError."""

    def unreadable(why: str) -> ValueError:
        return ValueError(f"기준선 파일을 읽지 못했다: {path}: {why}")

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        data = json.loads(text)
    except ValueError as error:
        raise unreadable(str(error)) from error
    if not isinstance(data, dict) or data.get("version") != BASELINE_VERSION:
        raise unreadable(f"version {BASELINE_VERSION}인 JSON 객체가 아니다")
    stages = data.get("stages")
    if not isinstance(stages, dict):
        raise unreadable("stages가 객체가 아니다")
    for stage, entries in stages.items():
        if not isinstance(entries, list):
            raise unreadable(f"{stage}의 항목이 목록이 아니다")
        for item in entries:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(key), str) for key in _ENTRY_KEYS
            ):
                raise unreadable(f"{stage}의 항목에는 {', '.join(_ENTRY_KEYS)}가 문자열로 있어야 한다")
    return data


def _entry_violation(stage: str, item: Dict[str, str]) -> Violation:
    return Violation(stage, item["path"], item["code"], item["message"], item["text"])


def load_baseline(path: Path) -> Dict[str, List[Violation]]:
    """The violations the baseline file allows, by stage. No file means no baseline: {}."""
    data = _read_baseline(path)
    if data is None:
        return {}
    return {
        stage: [_entry_violation(stage, item) for item in entries]
        for stage, entries in data["stages"].items()
    }


def stale(head: List[Violation], baseline: List[Violation]) -> List[Violation]:
    """The baseline entries that the head no longer has. They are fixed and should be deleted."""
    return multiset_diff(baseline, head)


def _entry_violations(stage: str, entries: List[Dict[str, str]], pairs: bool) -> List[Violation]:
    """The violation each entry of one stage allows. With `pairs` (an import-linter stage) an entry
    written while violations were routes allows the pair it stands for."""
    found = [_entry_violation(stage, item) for item in entries]
    return [il_pair(v) for v in found] if pairs else found


def prune_baseline(path: Path, stage: str, head: List[Violation], pairs: bool = False) -> int:
    """Delete the stale entries of one stage from the baseline file and return how many there
    were. Every other entry, with its reason, and every other stage stay as they are written: the
    file only loses entries, which needs no approval. A file with nothing to delete is not
    written. `pairs` is for an import-linter stage (_entry_violations)."""
    data = _read_baseline(path)
    if data is None:
        return 0
    entries = data["stages"].get(stage, [])
    gone = _beyond(_entry_violations(stage, entries, pairs), head)
    removed = sum(gone)
    if removed:
        data["stages"][stage] = [item for item, drop in zip(entries, gone) if not drop]
        _write_json(path, data)
    return removed


def adopt_baseline(
    path: Path, stage: str, head: List[Violation], reason: str, pairs: bool = False
) -> List[Violation]:
    """Add the violations of `head` that the baseline file does not allow yet to one stage, each
    with `reason`, and return them. Every entry already there stays as it is written, with its own
    reason. `pairs` is for an import-linter stage (_entry_violations)."""
    data = _read_baseline(path) or {"version": 1, "stages": {}}
    entries = data["stages"].setdefault(stage, [])
    missing = multiset_diff(head, _entry_violations(stage, entries, pairs))
    for v in missing:
        entries.append(
            {"path": v.path, "code": v.code, "message": v.message, "text": v.text, "reason": reason}
        )
    if missing:
        _write_json(path, data)
    return missing


# --- cache of the reference run ----------------------------------------------------------------


def _file_digest(path: Path) -> Optional[str]:
    """sha256 of a file's content, or None if it cannot be read. Missing is not the same as empty."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


class ReferenceCache:
    """The violations of a reference run, kept under runs_dir/reference/<merge_base>/. An entry is
    named <stage>-<key>.json; key() says which runs give the same answer."""

    def __init__(self, runs_dir: Path) -> None:
        self._root = Path(runs_dir) / "reference"

    @staticmethod
    def key(
        stage: Stage, expanded_cmd: List[str], config_files: List[Path], paths: List[str]
    ) -> str:
        """sha256 of everything that decides what the tool prints on one tree: the stage as
        written, the command that is run, the content of the config files it reads, and the paths
        it is given."""
        payload = {
            "stage": dataclasses.asdict(stage),
            "cmd": list(expanded_cmd),
            "config": [_file_digest(p) for p in config_files],
            "paths": list(paths),
        }
        # ensure_ascii (the default) keeps a path with undecodable bytes from failing the encode.
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _file(self, merge_base: str, stage: str, key: str) -> Path:
        return self._root / merge_base / f"{stage}-{key}.json"

    def get(self, merge_base: str, stage: str, key: str) -> Optional[List[Violation]]:
        """What was stored, or None if there is nothing. [] is a stored run that found nothing.
        An entry that cannot be read counts as nothing: the run is done again."""
        try:
            data = json.loads(self._file(merge_base, stage, key).read_text(encoding="utf-8"))
            return [Violation(**item) for item in data["violations"]]
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def put(self, merge_base: str, stage: str, key: str, violations: List[Violation]) -> None:
        data = {"violations": [dataclasses.asdict(v) for v in violations]}
        _write_json(self._file(merge_base, stage, key), data)


# --- export ------------------------------------------------------------------------------------


@contextlib.contextmanager
def exported(repo: Path, rev: str, subdir: str) -> Iterator[Path]:
    """Export subdir of commit rev into a new temporary folder and hand out the folder. The files
    are at <folder>/<repo-relative path>, so subdir "server" gives <folder>/server/... The folder
    is deleted afterwards, whether the body or the export raised or not."""
    # Resolved, so that a tool that prints the path of its working directory (macOS gives the
    # /private/var form) and the caller agree on what the folder is called.
    root = Path(tempfile.mkdtemp(prefix="check-reference-")).resolve()
    try:
        yield export_tree(repo, rev, root, subdir)
    finally:
        shutil.rmtree(root, ignore_errors=True)
