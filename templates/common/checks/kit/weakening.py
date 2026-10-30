from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .gitio import (
    ChangedPath,
    GitError,
    Hunk,
    changed_hunks,
    changed_paths,
    is_tracked,
    lines_of_file,
    run_git,
)
from .parsers import Violation
from .toolconfig import CONFIG_FILES, entry_form, narrowing_lines, sets_listed_key

# Watching for checks that were made weaker instead of the code being made right.
#
# `scan` compares the work tree with the base (the merge-base, or HEAD) and reports violations of
# the stage "weakening":
#   suppression       a line added since base that switches a check off: noqa, type: ignore, ...
#   skip              a line added since base that skips or narrows tests: pytest.mark.skip, it.only
#   config-weakening  a line added since base to a tool config file (CONFIG_FILES) that sets a key
#                     which narrows what a check looks at (CONFIG_KEYS): exclude, addopts, ...,
#                     by its own words or by where it stands (toolconfig.py). A line caught by
#                     where it stands has the text "<key>: <line>", the key that opened its
#                     table, list or value: the same entry under two keys is two approvals. An
#                     entry that the same hunk removed, and added again with another comma,
#                     indent or comment, is not new
#   deleted-test      a test file that is gone since base, or renamed so that it is not one any more
#   protected         a tracked protected file (rules, stage list, hooks) that differs from base
# They are new by definition, so nothing is subtracted as for the other stages. What the user has
# allowed is in approvals.json and is left out. An approval matches exactly: the code, the path and
# the stripped text of the line (empty for deleted-test, and for protected unless it is bound to
# content, see below).
#
# A protected file that git does not track (the personal placement keeps the kit out of git) has no
# base to differ from. `write_protected_record` fingerprints those files and `protected_drift`
# compares them with that record. Only the user writes the record again (`harness.py approve`).
# The shared placement commits every protected file, so it has no record: there a protected
# violation is bound to content (`by_content`), its text is the sha256 of the file as it is now,
# and an approval allows that content and no later edit.
#
# The kit's own run output (.ai/runs) is never part of a change: its logs quote the lines a run
# reported, and read back as added lines they would fail every later run.
#
# git lists names precomposed (NFC) on macOS, while the file system may hand out the decomposed
# form. Every path is made NFC before it is compared or written down.

STAGE = "weakening"
RUNS = ".ai/runs"

SUPPRESSION_RE = r"(#|//|/\*)\s*(noqa\b|type:\s*ignore|pyright:\s*ignore|ruff:\s*(noqa|ignore|disable)|flake8:\s*noqa|mypy:|eslint-disable|@ts-(ignore|nocheck|expect-error))|@Suppress(Warnings)?\(|@(typing\.)?no_type_check\b"
SKIP_RE = r"pytest\.mark\.(skip|skipif|xfail)\b|pytest\.skip\(|unittest\.skip|@Disabled\b|(^|[^\w])(it|test|describe)\.(skip|only)\("
TEST_FILE_RE = r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|conftest\.py|[^/]*\.(test|spec)\.[jt]sx?|[^/]*Tests?\.(kt|java))$"

# Ruff and flake8 read `# NOQA` like `# noqa`, so a change of case must not get a line past.
_SUPPRESSION = re.compile(SUPPRESSION_RE, re.IGNORECASE)
_SKIP = re.compile(SKIP_RE)
_TEST_FILE = re.compile(TEST_FILE_RE)

_NEEDS_APPROVAL = "사용자 승인이 필요하다(harness.py approve는 사용자만 실행한다)."

# The message of each code. protected-drift is the same thing as protected, found in a file that
# git does not track.
MESSAGES = {
    "suppression": "무시 주석을 새로 넣었다. 주석을 지우고 원인을 고친다. 꼭 필요하면 사용자에게 승인을 요청한다.",
    "skip": "테스트를 건너뛰거나 일부만 돌리는 표시(skip·xfail·only)를 새로 넣었다. "
    "표시를 지우고 원인을 고친다. 꼭 필요하면 사용자에게 승인을 요청한다.",
    "config-weakening": "검사가 보는 범위를 줄이는 도구 설정(exclude·addopts 등)을 "
    "새로 넣었다. 설정을 되돌리고 원인을 고친다. 꼭 필요하면 사용자에게 승인을 요청한다.",
    "deleted-test": "테스트 파일을 없앴다. 파일을 되돌리고 원인을 고친다. "
    "꼭 필요하면 사용자에게 승인을 요청한다.",
    "protected": "보호 파일이 바뀌었다. " + _NEEDS_APPROVAL,
    "protected-drift": "보호 파일이 바뀌었다. " + _NEEDS_APPROVAL,
    "protected-record-missing": "보호 파일의 지문 기록이 없다. " + _NEEDS_APPROVAL,
}
# A protected violation bound to content: there is no record for approve to write.
PROTECTED_BY_CONTENT = (
    "보호 파일이 바뀌었다. 사용자 승인이 필요하다"
    "(지금 내용의 sha256을 approvals.json에 적는 것은 사용자만 한다)."
)

# Folders and files that appear and change by themselves: Python writes bytecode, Finder writes
# .DS_Store. Recording them would report drift nobody caused.
_SKIP_DIRS = frozenset((".git", "__pycache__"))
_SKIP_FILES = frozenset((".DS_Store",))


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text) if sys.platform == "darwin" else text


def _violation(code: str, path: str, text: str = "", message: Optional[str] = None) -> Violation:
    return Violation(STAGE, path, code, message or MESSAGES[code], text.strip())


def _run_output(path: str) -> bool:
    return path == RUNS or path.startswith(RUNS + "/")


# --- globs ---------------------------------------------------------------------------------------


def _match_segments(parts: List[str], patterns: List[str]) -> bool:
    if not patterns:
        return not parts
    if patterns[0] == "**":  # zero or more whole folders
        return any(_match_segments(parts[i:], patterns[1:]) for i in range(len(parts) + 1))
    return (
        bool(parts)
        and fnmatch.fnmatchcase(parts[0], patterns[0])
        and _match_segments(parts[1:], patterns[1:])
    )


def glob_match(path: str, pattern: str) -> bool:
    """True if the POSIX path, relative to the repository, matches the pattern. "**" stands for
    zero or more whole folders. "*", "?" and "[...]" work inside one name and never cross a "/"."""
    return _match_segments(_nfc(path).split("/"), _nfc(pattern).split("/"))


def _is_protected(path: str, patterns: List[str]) -> bool:
    return any(glob_match(path, pattern) for pattern in patterns)


# --- approvals -----------------------------------------------------------------------------------


@dataclass
class Approval:
    """Something the user allowed. `kind` is the code of the violation it covers, `text` the
    line it covers (empty for deleted-test; for protected empty, or the sha256 of the content it
    allows where protected violations are bound to content; `<key>: <line>` for a
    config-weakening line that narrows only by where it stands) and `reason` why it is allowed."""

    kind: str
    path: str
    text: str
    reason: str


_APPROVAL_FIELDS = ("kind", "path", "text", "reason")


def load_approvals(path: Path) -> List[Approval]:
    """The approvals in the file, `{"approvals": [{kind, path, text, reason}, ...]}`. No file means
    none. A file that is not like that raises ValueError."""

    def unreadable(why: str) -> ValueError:
        return ValueError(f"승인 파일을 읽지 못했다: {path}: {why}")

    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        data = json.loads(text)
    except ValueError as error:
        raise unreadable(str(error)) from error
    items = data.get("approvals") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise unreadable("approvals 목록이 없다")
    approvals: List[Approval] = []
    for item in items:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(field), str) for field in _APPROVAL_FIELDS
        ):
            raise unreadable(f"항목에는 {', '.join(_APPROVAL_FIELDS)}가 문자열로 있어야 한다")
        approvals.append(Approval(item["kind"], item["path"], item["text"], item["reason"]))
    return approvals


def add_content_approvals(path: Path, hashes: Dict[str, str], reason: str) -> None:
    """Approve the content each protected file has now, {path: sha256}, in the shared placement's
    approvals.json, which only the user writes (proposal apply, baseline adopt). An approval that is
    already there is not added again."""
    data: Dict[str, Any] = {"approvals": []}
    if Path(path).is_file():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.setdefault("approvals", [])
    for rel, sha in hashes.items():
        entry = {"kind": "protected", "path": rel, "text": sha, "reason": reason}
        if entry not in items:
            items.append(entry)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --- what a change added, removed or touched -----------------------------------------------------


def _marker_violations(added: Dict[str, List[str]]) -> List[Violation]:
    found: List[Violation] = []
    for path, lines in added.items():
        for line in lines:
            if _SUPPRESSION.search(line):
                found.append(_violation("suppression", path, line))
            if _SKIP.search(line):
                found.append(_violation("skip", path, line))
    return found


def _new_entries(name: str, hunks: List[Hunk]) -> List[Tuple[int, str]]:
    """The added lines of the hunks of a config file named `name` that the base did not have in
    another form. An entry that gained a comma when one was added after it, was indented
    otherwise or was given a comment is removed and added in the same hunk: it is not new. A
    removed line stands for one added line, so a second copy of it is."""
    new: List[Tuple[int, str]] = []
    for hunk in hunks:
        spare = Counter(entry_form(name, text) for text in hunk.removed)
        for number, text in hunk.added:
            form = entry_form(name, text)
            if spare[form] > 0:
                spare[form] -= 1
            else:
                new.append((number, text))
    return new


def _config_violations(repo: Path, changed: Dict[str, List[Hunk]]) -> List[Violation]:
    """The lines added to tool config files that narrow a check: by their own words, or by where
    they stand in the file as the work tree has it now.

    A line that sets a listed key keeps its text. A line that narrows only by where it stands gets
    the key that opened its table, list or value in front, as in `extend-exclude: "tests",`: an
    approval of the entry "tests" for testpaths must not let it into extend-exclude."""
    found: List[Violation] = []
    for path, hunks in changed.items():
        name = path.rsplit("/", 1)[-1]
        if name not in CONFIG_FILES:
            continue
        context = narrowing_lines(name, lines_of_file(Path(repo) / path))
        for number, text in _new_entries(name, hunks):
            if sets_listed_key(text):
                shown = text
            elif number in context:
                shown = f"{context[number]}: {text.strip()}"
            else:
                continue
            found.append(_violation("config-weakening", path, shown))
    return found


def _gone_test(change: ChangedPath) -> Optional[str]:
    """The path of the test file this change took away, if it did."""
    if change.status == "D" and _TEST_FILE.search(change.path):
        return change.path
    if (
        change.status == "R"
        and change.old_path is not None
        and _TEST_FILE.search(change.old_path)
        and not _TEST_FILE.search(change.path)
    ):
        return change.old_path
    return None


def _deleted_test_violations(changes: List[ChangedPath]) -> List[Violation]:
    gone = (_gone_test(change) for change in changes)
    return [_violation("deleted-test", path) for path in gone if path is not None]


def _protected_violations(
    repo: Path, changes: List[ChangedPath], patterns: List[str], by_content: bool
) -> List[Violation]:
    """A violation for each tracked protected file the change touched: both names of a rename,
    so that a protected file moved onto a name that is let through (approvals.json in the shared
    placement) is still reported by its old one. With by_content its text is the sha256 of the
    file as it is now ("" when it is gone): an approval names that."""
    found: List[Violation] = []
    for change in changes:
        if change.status == "?":
            continue  # untracked: protected_drift looks at it
        for path in (change.path, change.old_path):
            if path is not None and _is_protected(path, patterns):
                if by_content:
                    sha = _file_sha256(Path(repo) / path) or ""
                    found.append(_violation("protected", path, sha, PROTECTED_BY_CONTENT))
                else:
                    found.append(_violation("protected", path))
    return found


def _entry_counts(stages: Any) -> Optional[Dict[str, Counter[str]]]:
    """How many times each entry appears, per stage of a baseline's "stages". None if that is not
    an object of lists."""
    if not isinstance(stages, dict) or not all(isinstance(v, list) for v in stages.values()):
        return None
    return {
        stage: Counter(json.dumps(entry, sort_keys=True) for entry in entries)
        for stage, entries in stages.items()
    }


def _only_shrinks(repo: Path, base: str, path: str) -> bool:
    """True if the baseline file at `path` holds nothing it did not hold at base: entries were
    deleted and nothing else changed. A file that cannot be read either way is a change."""
    try:
        before = json.loads(run_git(repo, "show", f"{base}:{path}").decode("utf-8"))
        after = json.loads((Path(repo) / path).read_text(encoding="utf-8"))
    except (GitError, OSError, ValueError):
        return False
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    old, new = _entry_counts(before.pop("stages", None)), _entry_counts(after.pop("stages", None))
    if before != after or old is None or new is None:  # what is left besides the stages
        return False
    return all(not (counts - old.get(stage, Counter())) for stage, counts in new.items())


def weakenings(
    repo: Path,
    base: str,
    protected: List[str],
    baseline: Optional[str] = None,
    by_content: bool = False,
) -> List[Violation]:
    """What the work tree changed since `base` that makes the checks weaker, before any approval.
    Only the lines the work tree added are searched for markers. `protected` is a list of globs in
    the form `glob_match` takes. The run output under .ai/runs is never looked at.

    Protected files are not searched for markers: any change to one is reported as protected
    already, and the kit's own sources hold the marker words. `by_content` binds each protected
    violation to the content of the file (the shared placement, which has no record).

    `baseline` is the repository path of the shared placement's baseline file. A change that only
    deletes entries from it is what `harness.py prune` does. The baseline may only shrink, so that
    is not reported."""
    changes = [change for change in changed_paths(repo, base) if not _run_output(change.path)]
    hunks = changed_hunks(repo, base, changes)
    watched = {path: hs for path, hs in hunks.items() if not _is_protected(path, protected)}
    # Markers are looked for on every added line. Only a config entry is the same one with
    # another comma or comment: "# noqa" after "x = f()" is a new suppression on an old line.
    texts = {path: [text for h in hs for _, text in h.added] for path, hs in watched.items()}
    found = _marker_violations(texts) + _config_violations(repo, watched)
    found += _deleted_test_violations(changes)
    touched = _protected_violations(repo, changes, protected, by_content)
    if baseline is not None:
        pruned = _nfc(baseline)
        if any(v.path == pruned for v in touched) and _only_shrinks(repo, base, pruned):
            touched = [v for v in touched if v.path != pruned]
    return found + touched


def apply_approvals(
    found: List[Violation], approvals: List[Approval]
) -> Tuple[List[Violation], List[Approval]]:
    """The violations no approval covers, and the approvals that covered at least one, each once
    and in the order of the file. An approval matches exactly: the code, the path and the stripped
    text."""

    def key(code: str, path: str, text: str) -> Tuple[str, str, str]:
        return (code, _nfc(path), text.strip())

    allowed = {key(a.kind, a.path, a.text) for a in approvals}
    left = [v for v in found if key(v.code, v.path, v.text) not in allowed]
    covered = {key(v.code, v.path, v.text) for v in found} & allowed
    used: List[Approval] = []
    for approval in approvals:
        matched = key(approval.kind, approval.path, approval.text)
        if matched in covered:
            covered.discard(matched)
            used.append(approval)
    return left, used


def scan(
    repo: Path,
    base: str,
    protected: List[str],
    approvals: List[Approval],
    baseline: Optional[str] = None,
    by_content: bool = False,
) -> List[Violation]:
    """`weakenings` less what the user approved."""
    found = weakenings(repo, base, protected, baseline, by_content)
    return apply_approvals(found, approvals)[0]


# --- protected files that git does not track -----------------------------------------------------


def _write_json(path: Path, data: Any) -> None:
    """Replace path with data as JSON in one step, so a reader sees the old file or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _file_sha256(path: Path) -> Optional[str]:
    """sha256 of the file's content, or None if it is not a file (or not any more)."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files_matching(repo: Path, pattern: str) -> Dict[str, Path]:
    """The files in the work tree that one pattern names, ignored by git or not. The keys are
    their repo-relative paths with "/" and in NFC, the values the paths to read them from."""
    pattern = _nfc(pattern)
    segments = pattern.split("/")
    fixed = 0  # how many segments from the start are plain names
    while fixed < len(segments) and not any(ch in segments[fixed] for ch in "*?["):
        fixed += 1
    if fixed == len(segments):  # no wildcard: the pattern is the path of one file
        path = repo.joinpath(*segments)
        return {pattern: path} if path.is_file() else {}

    # Walk only below the plain start of the pattern, and for a pattern without "**" only as deep
    # as the pattern goes: ".ai/checks/*.json" must not wander into ".ai/checks/tools/venv".
    # Folders that are links are not followed, except the ones that make up the start itself
    # (in a linked worktree ".ai" is a link to the main checkout's).
    top = repo.joinpath(*segments[:fixed])
    deepest = None if "**" in segments[fixed:] else len(segments) - fixed
    top_depth = len(top.parts)
    found: Dict[str, Path] = {}
    for folder, subfolders, names in os.walk(str(top)):
        subfolders[:] = [name for name in subfolders if name not in _SKIP_DIRS]
        if deepest is not None and len(Path(folder).parts) - top_depth + 1 >= deepest:
            subfolders[:] = []
        for name in names:
            path = Path(folder, name)
            rel = _nfc(path.relative_to(repo).as_posix())
            if name not in _SKIP_FILES and glob_match(rel, pattern) and path.is_file():
                found[rel] = path
    return found


def _untracked_hashes(repo: Path, record: Path, patterns: List[str]) -> Dict[str, str]:
    """sha256 of each protected file git does not track, by path. Not the record itself."""
    files: Dict[str, Path] = {}
    for pattern in patterns:
        files.update(_files_matching(repo, pattern))
    record_real = os.path.realpath(record)
    hashes: Dict[str, str] = {}
    for rel, path in sorted(files.items()):
        if os.path.realpath(path) == record_real or is_tracked(repo, rel):
            continue
        sha = _file_sha256(path)
        if sha is not None:
            hashes[rel] = sha
    return hashes


def write_protected_record(repo: Path, record: Path, protected: List[str]) -> Dict[str, str]:
    """Write down the sha256 of every protected file that git does not track, as
    {path: sha256}, and return it. Tracked files are not in it: the diff against base covers
    them. The record itself is left out."""
    hashes = _untracked_hashes(Path(repo), Path(record), protected)
    _write_json(Path(record), hashes)
    return hashes


def _read_record(record: Path) -> Optional[Dict[str, str]]:
    """The record, or None if there is none. A file that is not a record raises ValueError."""
    try:
        text = record.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ValueError(f"보호 파일 기록을 읽지 못했다: {record}: {error}") from error
    if not isinstance(data, dict) or not all(
        isinstance(path, str) and isinstance(sha, str) for path, sha in data.items()
    ):
        raise ValueError(f"보호 파일 기록을 읽지 못했다: {record}: 경로와 sha256을 짝지은 객체가 아니다")
    return data


def _shown(repo: Path, path: Path) -> str:
    """The path as the repository's own, if it is inside it."""
    try:
        return _nfc(path.relative_to(repo).as_posix())
    except ValueError:
        return path.as_posix()


def protected_drift(repo: Path, record: Path, protected: List[str]) -> List[Violation]:
    """The protected files git does not track that differ from the record: changed, new or gone.
    Without a record the answer is one violation, protected-record-missing."""
    repo, record = Path(repo), Path(record)
    recorded = _read_record(record)
    if recorded is None:
        return [_violation("protected-record-missing", _shown(repo, record))]
    current = _untracked_hashes(repo, record, protected)
    drifted: List[str] = []
    for rel in sorted(set(recorded) | set(current)):
        if rel not in recorded:
            drifted.append(rel)
            continue
        # A recorded file that is not among the current ones is gone, or git tracks it now. If
        # it is there, it still has to be what was recorded.
        sha = current.get(rel) or _file_sha256(repo / rel)
        if sha != recorded[rel]:
            drifted.append(rel)
    return [_violation("protected-drift", rel) for rel in drifted]
