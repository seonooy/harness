from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .gitio import (
    GitError,
    common_dir,
    config_value,
    head,
    is_ignored,
    is_tracked,
    toplevel,
)

# Putting the kit into a repository, and the hooks that make it run.
#
# A template has pieces: common, stacks/<stack>, arch/<arch> and project, each a folder under
# templates/ with a manifest.json:
#
#   {"files": [{"src": "checks/check.py", "dest": ".ai/checks/check.py", "owner": "kit"}, ...],
#    "private": ["/.ai", ...], "links": [".ai", ...]}
#
# `src` is a file or a folder of the piece. `dest` is one path, or {"personal": ..., "shared": ...}
# when the placements put the file in different places. A file the kit owns is replaced by every
# install; a file the project owns (filled in for the project) is written only when it is not there
# yet. `private` are the .git/info/exclude entries of the personal placement, and `links` the
# paths a linked worktree gets from the main checkout (link.py).
#
# install writes .ai/checks/install.json: where the kit came from, the pieces, the placement, each
# file with its owner and sha256, the private paths and the links. doctor reads it.

EXCLUDE_HEADER = "# agent-harness-template check kit"
PLACEMENTS = ("personal", "shared")
PROJECT_KINDS = ("existing", "new")
OWNERS = ("kit", "project")
INSTALL_RECORD = Path(".ai") / "checks" / "install.json"
# Run output is never committed, whatever the placement.
RUNS_EXCLUDE = "/.ai/runs"
# The stack's two stage lists: one for a project that exists, one for a new one. Either becomes
# the one name the runner reads.
_STAGE_LIST = re.compile(r"stages\.(existing|new)\.json")
STAGES_DEST = ".ai/checks/stages.json"



class InstallError(Exception):
    """The kit cannot be installed as asked. The message says what is in the way."""


@dataclass
class ManifestEntry:
    """One file or folder of a piece. `dest` has a path for each placement."""

    src: str
    dest: Dict[str, str]
    owner: str


@dataclass
class Manifest:
    piece: str
    files: List[ManifestEntry]
    private: List[str]
    links: List[str]


# --- manifest ------------------------------------------------------------------------------------


def _relative(value: Any, label: str) -> str:
    """A path inside the repository: relative, with "/", and no "..". Anything else could write
    outside the target."""
    if not isinstance(value, str) or not value.strip("/"):
        raise InstallError(f"{label}는 비어 있지 않은 문자열이어야 한다: {value!r}")
    if posixpath.isabs(value) or ".." in value.split("/"):
        raise InstallError(f"{label}는 저장소 안의 상대 경로여야 한다: {value!r}")
    return value


def _strings(value: Any, label: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InstallError(f"{label}는 문자열 목록이어야 한다")
    return list(value)


def _entry(raw: Any, label: str) -> ManifestEntry:
    known = ("src", "dest", "owner")
    if not isinstance(raw, dict):
        raise InstallError(f"{label}는 객체여야 한다")
    unknown = [key for key in raw if key not in known and not key.startswith("_")]
    if unknown:
        raise InstallError(f"{label}에 모르는 키가 있다: {', '.join(unknown)}")
    dest = raw.get("dest")
    if isinstance(dest, str):
        dest = {placement: dest for placement in PLACEMENTS}
    if not isinstance(dest, dict) or sorted(dest) != sorted(PLACEMENTS):
        raise InstallError(f"{label}.dest는 경로 하나이거나 personal·shared 경로여야 한다")
    if raw.get("owner") not in OWNERS:
        raise InstallError(f"{label}.owner는 kit이나 project여야 한다: {raw.get('owner')!r}")
    return ManifestEntry(
        src=_relative(raw.get("src"), f"{label}.src"),
        dest={key: _relative(path, f"{label}.dest.{key}") for key, path in dest.items()},
        owner=raw["owner"],
    )


def load_manifest(piece_dir: Path) -> Manifest:
    """The manifest.json of a piece. Raises InstallError, naming the file, when it is missing or
    does not follow the format."""
    path = Path(piece_dir) / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise InstallError("JSON 객체가 아니다")
        files = data.get("files", [])
        if not isinstance(files, list):
            raise InstallError("files는 목록이어야 한다")
        return Manifest(
            piece=str(data.get("piece", Path(piece_dir).name)),
            files=[_entry(raw, f"files[{index}]") for index, raw in enumerate(files)],
            private=_strings(data.get("private", []), "private"),
            links=_strings(data.get("links", []), "links"),
        )
    except (OSError, ValueError, InstallError) as exc:
        raise InstallError(f"조각 manifest를 읽지 못했다: {path}: {exc}") from None


# --- small helpers -------------------------------------------------------------------------------


def _write_json(path: Path, data: Any) -> None:
    """Replace path with data as JSON in one step, so a reader sees the old file or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _read_json_object(path: Path) -> Dict[str, Any]:
    """The JSON object in path, or {} when there is no file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        raise InstallError(f"JSON으로 읽지 못했다: {path}: {exc}") from None
    if not isinstance(data, dict):
        raise InstallError(f"JSON 객체가 아니다: {path}")
    return data


def _unique(items: List[str]) -> List[str]:
    return list(dict.fromkeys(items))


def _listed(record: Dict[str, Any], key: str) -> List[str]:
    """The strings of a list in an earlier install record. Anything else there counts as none."""
    value = record.get(key)
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files_of(src: Path, dest: str) -> Iterator[Tuple[Path, str]]:
    """(file to copy, where it goes) for a manifest source: the file itself, or every file below a
    folder. Caches and hidden files below a folder (__pycache__, .mypy_cache, .DS_Store) are left
    out."""
    if src.is_file():
        yield src, dest
        return
    if not src.is_dir():
        raise InstallError(f"manifest가 가리키는 파일이 템플릿에 없다: {src}")
    for folder, subfolders, names in os.walk(str(src)):
        subfolders[:] = sorted(
            n for n in subfolders if n != "__pycache__" and not n.startswith(".")
        )
        for name in sorted(names):
            if name.startswith(".") or name.endswith(".pyc"):
                continue
            path = Path(folder, name)
            yield path, posixpath.join(dest, path.relative_to(src).as_posix())


# --- exclude -------------------------------------------------------------------------------------


def append_exclude(repo: Path, entries: List[str]) -> List[str]:
    """Add entries to .git/info/exclude, the one every worktree shares, under the kit's header, and
    return the ones that were not there yet.

    An entry is written as "/<path>": anchored at the root, and with no trailing "/". A folder-only
    pattern would not match the links a linked worktree has in place of the folders."""
    wanted = _unique(["/" + entry.strip("/") for entry in entries if entry.strip("/")])
    path = common_dir(repo) / "info" / "exclude"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    present = {line.strip() for line in text.splitlines()}
    new = [entry for entry in wanted if entry not in present]
    if not new:
        return []
    if text and not text.endswith("\n"):
        text += "\n"
    if EXCLUDE_HEADER not in present:
        text += EXCLUDE_HEADER + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "".join(entry + "\n" for entry in new), encoding="utf-8")
    return new


# --- install -------------------------------------------------------------------------------------


def _template_commit(template: Path) -> Optional[str]:
    """The commit the template is at, or None if the template is not a git repository of its own."""
    try:
        return head(template) if toplevel(template) == template else None
    except GitError:
        return None


def _make_link(link: Path, dest: Path) -> None:
    """A relative symlink at `link` to `dest`, in place of a link that was there."""
    if link.is_symlink():
        link.unlink()
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(str(dest), str(link.parent)), str(link))


def _within(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder + "/")


def _project_folders(
    top: Path, manifests: Dict[str, Manifest], copies: List[Tuple[Path, str, str]]
) -> List[str]:
    """The manifests' private folders the project already keeps in git: every file the install
    would put there is the project's, and git tracks files there."""
    found: List[str] = []
    for manifest in manifests.values():
        for entry in manifest.private:
            folder = entry.strip("/")
            owners = {owner for _, rel, owner in copies if _within(rel, folder)}
            if owners == {"project"} and is_tracked(top, folder):
                found.append(folder)
    return found


def install(
    template: Path, target: Path, stack: str, arch: str, placement: str, project_kind: str
) -> Path:
    """Install the pieces common, stacks/<stack>, arch/<arch> and project of `template` into the
    repository that holds `target`, and return the path of the install record it writes.

    Nothing is written when a destination is tracked by git. The personal placement adds the
    manifests' private paths to .git/info/exclude, and copies nothing when a destination would
    still not be ignored; both placements add the run folder. A private folder that holds only
    the project's files and that git already tracks files in (a team's docs/adr) is the
    project's: nothing is copied into it, and it is neither excluded nor linked. A second install
    replaces the kit's files, keeps the project's, and keeps the private paths and links of the
    earlier record.
    """
    if placement not in PLACEMENTS:
        raise InstallError(f"배치는 {', '.join(PLACEMENTS)} 중 하나다: {placement!r}")
    if project_kind not in PROJECT_KINDS:
        raise InstallError(
            f"프로젝트 종류는 {', '.join(PROJECT_KINDS)} 중 하나다: {project_kind!r}"
        )
    template = Path(template).resolve()
    if not (template / "templates" / "common" / "manifest.json").is_file():
        raise InstallError(
            f"템플릿 저장소가 아니다(templates/common/manifest.json이 없다): {template}"
        )
    try:
        top = toplevel(Path(target))
    except GitError as exc:
        raise InstallError(f"대상이 git 작업 트리가 아니다: {target}: {exc}") from None

    pieces = ["common", f"stacks/{stack}", f"arch/{arch}", "project"]
    manifests = {piece: load_manifest(template / "templates" / piece) for piece in pieces}
    copies: List[Tuple[Path, str, str]] = []  # (source file, destination, owner)
    links: List[Tuple[str, str]] = []  # (link, what it points at)
    for piece, manifest in manifests.items():
        for entry in manifest.files:
            dest = entry.dest[placement]
            kind = _STAGE_LIST.fullmatch(posixpath.basename(entry.src))
            if kind is not None:
                if kind.group(1) != project_kind:
                    continue
                dest = STAGES_DEST
            source = template / "templates" / piece / entry.src
            copies.extend((src, rel, entry.owner) for src, rel in _files_of(source, dest))

    theirs = _project_folders(top, manifests, copies) if placement == "personal" else []
    copies = [c for c in copies if not any(_within(c[1], folder) for folder in theirs)]
    planned = [rel for _, rel, _ in copies] + [link for link, _ in links]
    tracked = [rel for rel in planned if is_tracked(top, rel)]
    if tracked:
        raise InstallError(f"git이 추적하는 파일은 덮어쓰지 않는다: {', '.join(tracked)}")
    in_the_way = [
        link for link, _ in links if (top / link).exists() and not (top / link).is_symlink()
    ]
    if in_the_way:
        raise InstallError(f"링크를 만들 자리에 파일이나 폴더가 있다: {', '.join(in_the_way)}")

    earlier = _read_json_object(top / INSTALL_RECORD)
    private = [RUNS_EXCLUDE]
    if placement == "personal":
        private = [
            entry
            for manifest in manifests.values()
            for entry in manifest.private
            if entry.strip("/") not in theirs
        ] + private
    private = _unique(["/" + p.strip("/") for p in private] + _listed(earlier, "private_paths"))
    append_exclude(top, private)
    if placement == "personal":
        shown = [rel for rel in planned if not is_ignored(top, rel)]
        if shown:
            raise InstallError(
                "개인 배치인데 git 무시 목록에 없는 파일이 있다. manifest의 private에 넣는다: "
                + ", ".join(shown)
            )

    files: List[Dict[str, str]] = []
    for src, rel, owner in copies:
        path = top / rel
        if owner == "kit" or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(path))
        files.append({"path": rel, "owner": owner, "sha256": _sha256(path)})
    for link, dest in links:
        _make_link(top / link, top / dest)

    manifest_links = [
        link
        for manifest in manifests.values()
        for link in manifest.links
        if not any(_within(link, folder) for folder in theirs)
    ]
    if placement != "personal":  # a worktree checks the committed kit out like any other file
        manifest_links = []
    record: Dict[str, Any] = {
        "kit": {
            "template": str(template),
            "commit": _template_commit(template),
            "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "pieces": pieces,
        "placement": placement,
        "files": files,
        "private_paths": private,
        "links": _unique(manifest_links + _listed(earlier, "links")),
    }
    _write_json(top / INSTALL_RECORD, record)
    return top / INSTALL_RECORD


def record_private_links(repo: Path, paths: List[str]) -> bool:
    """Add files the kit made after install (the CLIs' settings) to the install record: to
    private_paths, so doctor keeps them out of git, and to links, so a linked worktree gets them
    too. Return whether the record changed: it is a protected file, so the user approves again
    afterwards. A repository without a record is left alone."""
    path = toplevel(Path(repo)) / INSTALL_RECORD
    record = _read_json_object(path)
    if not record:
        return False
    rels = [entry.strip("/") for entry in paths if entry.strip("/")]
    private = _unique(_listed(record, "private_paths") + ["/" + rel for rel in rels])
    links = _unique(_listed(record, "links") + rels)
    if (private, links) == (record.get("private_paths"), record.get("links")):
        return False
    record["private_paths"], record["links"] = private, links
    _write_json(path, record)
    return True


