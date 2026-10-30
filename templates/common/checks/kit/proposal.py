from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO, Tuple

from .config import ConfigError, substitute
from .gitio import is_tracked, toplevel
from .weakening import add_content_approvals, glob_match, load_approvals, protected_drift

# `harness.py proposal apply NAME`, which only the user runs. An agent may not edit the protected
# files (the deny rules, the Codex guard and the Checks section stop it), so a change to them, such
# as a new import contract when a package changes style, is written down as a proposal:
#
#   .ai/proposals/<name>/README.md    the first line that is not empty is the reason (an ADR number)
#   .ai/proposals/<name>/files/<path> the whole new content of each protected file it changes
#
# Applying writes the files and approves them, and only them, in the same step: the personal
# placement records their fingerprints, the shared placement adds an approval of the new content to
# approvals.json. It stops before writing anything when another protected file differs from what
# the user approved, when a target is one of the kit's own records or code, or when the proposal or
# its targets changed since it was applied. The replaced content is kept in before/ and the proposal
# stays, with applied.json beside it, as the record.

PROPOSALS = Path(".ai") / "proposals"
CHECKS = Path(".ai") / "checks"
EXIT_PASS, EXIT_INCOMPLETE = 0, 2
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# The kit's records and code: written by install, approve and adopt, never by a proposal.
_RECORDS = (".ai/checks/protected.json", ".ai/checks/approvals.json", ".ai/checks/install.json")


class _Stop(ValueError):
    """Applying stops here, before anything is written."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reason(readme: Path) -> str:
    for line in readme.read_text(encoding="utf-8").splitlines():
        if line.strip():
            return line.strip().lstrip("#").strip()
    return ""


def stage_list(top: Path) -> Tuple[str, List[str], Optional[str]]:
    """The placement, the protected globs and the repository path of the baseline file of
    stages.json, read without checking its stages: a stage list of another kit, with kinds this
    one does not know, is what a proposal may come to fix."""
    data = json.loads((top / CHECKS / "stages.json").read_text(encoding="utf-8"))
    placement, protected = data.get("placement"), data.get("protected")
    if placement not in ("personal", "shared"):
        raise _Stop(f"stages.json의 placement를 읽지 못했다: {placement!r}")
    if not isinstance(protected, list) or not all(isinstance(g, str) for g in protected):
        raise _Stop("stages.json의 protected가 문자열 목록이 아니다")
    baseline = data.get("baseline")
    return placement, protected, _in_repo(top, baseline) if isinstance(baseline, str) else None


def _in_repo(top: Path, named: str) -> Optional[str]:
    """The repository path of a file stages.json names, read as the runner reads it: its
    variables filled in, relative to the repository. None when it lies outside."""
    variables = {"live": str(top), "repo": str(top), "cwd": str(top), "checks_dir": str(top / CHECKS)}
    try:
        text = substitute(named, variables)
    except ConfigError:
        return None
    try:
        return Path(os.path.normpath(str(top / text))).relative_to(top).as_posix()
    except ValueError:
        return None


def _proposed(files: Path) -> Tuple[Dict[str, bytes], List[str]]:
    """The new content of each file under `files`, by repository path, and the paths that are
    links. A linked folder is not entered."""
    found: Dict[str, bytes] = {}
    links: List[str] = []
    for folder, dirs, names in os.walk(str(files), followlinks=False):
        here = Path(folder)
        for name in sorted(dirs):
            if (here / name).is_symlink():
                links.append((here / name).relative_to(files).as_posix())
        for name in sorted(names):
            path = here / name
            rel = path.relative_to(files).as_posix()
            if path.is_symlink():
                links.append(rel)
            else:
                found[rel] = path.read_bytes()
    return found, links


def _kit_owned(rel: str, baseline: Optional[str]) -> bool:
    if rel in _RECORDS or rel == baseline:
        return True
    if rel.startswith(".ai/checks/kit/"):
        return True
    return rel.startswith(".ai/checks/") and rel.endswith(".py")


def _now(top: Path, rels: List[str]) -> Dict[str, Optional[str]]:
    return {rel: _sha256((top / rel).read_bytes()) if (top / rel).is_file() else None for rel in rels}


def _write(target: Path, data: bytes) -> None:
    """Replace the file in one step: a crash leaves the old content or the new, never half."""
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    with os.fdopen(handle, "wb") as out:
        out.write(data)
    os.replace(temp, str(target))


def apply_proposal(repo: Path, name: str, out: TextIO) -> int:
    """Apply the proposal `name` of the repository that holds `repo`: 0 when applied (or applied
    already), 2 when it stops, in which case nothing was written."""
    try:
        return _apply(toplevel(Path(repo)), name, out)
    except _Stop as stop:
        out.write(f"INCOMPLETE proposal: {stop}\n")
    except Exception as exc:  # an unreadable file of the kit: stop like prune and adopt do
        out.write(f"INCOMPLETE proposal: {type(exc).__name__}: {exc}\n")
    return EXIT_INCOMPLETE


def _apply(top: Path, name: str, out: TextIO) -> int:
    if not _NAME.fullmatch(name):
        raise _Stop(f"제안 이름은 영문·숫자·.-_만 쓴다: {name!r}")
    folder = top / PROPOSALS / name
    readme, files = folder / "README.md", folder / "files"
    if not folder.is_dir():
        raise _Stop(f"없는 제안이다: {folder}")
    if not readme.is_file() or not _reason(readme):
        raise _Stop(f"제안의 이유가 없다. {readme}의 첫 줄에 이유(ADR 번호)를 적는다")
    if not files.is_dir():
        raise _Stop(f"바꿀 파일이 없다. {files} 아래에 저장소 경로 그대로 새 내용을 둔다")
    placement, protected, baseline = stage_list(top)
    proposed, links = _proposed(files)
    if links:
        raise _Stop(f"제안 안에 링크가 있다: {', '.join(links)}")
    if not proposed:
        raise _Stop(f"바꿀 파일이 없다: {files}")
    kit = [rel for rel in proposed if _kit_owned(rel, baseline)]
    if kit:
        raise _Stop(f"키트의 기록과 코드는 제안으로 바꾸지 않는다: {', '.join(kit)}")
    outside = [rel for rel in proposed if not any(glob_match(rel, g) for g in protected)]
    if outside:
        raise _Stop(f"보호 파일만 제안으로 바꾼다. 보호 파일이 아닌 것: {', '.join(outside)}")
    linked = [rel for rel in proposed if (top / rel).is_symlink()]
    if linked:
        raise _Stop(f"링크인 파일에는 쓰지 않는다: {', '.join(linked)}")

    rels = sorted(proposed)
    hashes = {rel: _sha256(proposed[rel]) for rel in rels}
    applied = folder / "applied.json"
    if applied.is_file():
        recorded = json.loads(applied.read_text(encoding="utf-8")).get("files")
        now = _now(top, rels)
        if recorded == hashes and now == hashes:
            out.write(f"INFO proposal: 이미 적용했다: {name}\n")
            return EXIT_PASS
        changed = [rel for rel in rels if now.get(rel) != (recorded or {}).get(rel)]
        changed += [rel for rel in rels if (recorded or {}).get(rel) != hashes[rel] and rel not in changed]
        raise _Stop(
            f"적용한 뒤 바뀌었다: {', '.join(changed) or name}. 되돌리지 않는다. 다시 바꾸려면 새 제안을 만든다"
        )

    record_path = top / CHECKS / "protected.json"
    record: Dict[str, Any] = {}
    if placement == "personal":
        if not record_path.is_file():
            raise _Stop("보호 파일 기록이 없다. 사용자가 먼저 harness.py approve를 돌린다")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        drift = sorted({v.path for v in protected_drift(top, record_path, protected)} - set(rels))
        if drift:
            raise _Stop(
                f"제안 밖의 보호 파일이 승인한 내용과 다르다: {', '.join(drift)}. "
                "사용자가 그 차이를 보고 harness.py approve로 따로 확인한 뒤 다시 적용한다"
            )
    else:
        load_approvals(top / CHECKS / "approvals.json")  # a file it cannot read stops it here

    for rel in rels:
        old = (top / rel).read_text(encoding="utf-8", errors="replace") if (top / rel).is_file() else ""
        new = proposed[rel].decode("utf-8", errors="replace")
        out.writelines(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )
    for rel in rels:
        if (top / rel).is_file():
            _write(folder / "before" / rel, (top / rel).read_bytes())
    for rel in rels:
        _write(top / rel, proposed[rel])

    reason = _reason(readme)
    if placement == "shared":
        add_content_approvals(top / CHECKS / "approvals.json", hashes, reason)
    else:
        for rel in rels:
            if not is_tracked(top, rel):  # the record holds the protected files git does not track
                record[rel] = hashes[rel]
        _write(record_path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write(
        applied,
        (json.dumps({"applied_at": stamp, "files": hashes}, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
    )
    out.write(f"INFO proposal: {name}를 적용하고 그 파일만 승인했다({len(rels)}개). 이유: {reason}\n")
    return EXIT_PASS
