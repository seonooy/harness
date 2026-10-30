from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from kit.gitio import is_tracked, toplevel
from kit.install import (
    INSTALL_RECORD,
    InstallError,
    _listed,
    _read_json_object,
    _write_json,
    append_exclude,
    record_private_links,
)

# Project skills that a project picks for itself (docs/skill-guide.md of the template), beside the
# kit's own kit-change and kit-verify. A skill is a folder with SKILL.md. It goes to
# .agents/skills/<name>, where Codex reads a repository's skills. In the personal placement that
# path is excluded from git and becomes private paths and links of install.json, so a linked worktree gets them too; that
# record is protected, so the user approves again after a change.

SKILLS = ".agents/skills"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_COPY_IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".DS_Store")


def _paths(name: str) -> List[str]:
    if not _NAME.fullmatch(name):
        raise InstallError(f"스킬 이름은 영문·숫자·.-_만 쓴다: {name!r}")
    return [f"{SKILLS}/{name}"]


def kit_skills(repo: Path) -> List[str]:
    """The skills the kit installed itself, by the files install.json records as the kit's."""
    record = _read_json_object(toplevel(Path(repo)) / INSTALL_RECORD)
    files = record.get("files")
    names = set()
    for entry in files if isinstance(files, list) else []:
        parts = str(entry.get("path", "")).split("/") if isinstance(entry, dict) else []
        if len(parts) > 3 and parts[:2] == [".agents", "skills"] and entry.get("owner") == "kit":
            names.add(parts[2])
    return sorted(names)


def add_skill(
    repo: Path, source: Path, placement: str, name: Optional[str] = None
) -> Tuple[List[str], bool]:
    """Copy the skill folder `source` into the repository, or take it as it is when it already
    sits at .agents/skills/<name> (a personal skill from before the kit). Return the paths and
    whether install.json changed (the personal placement records them)."""
    top = toplevel(Path(repo))
    src = Path(source).expanduser().resolve()
    if not (src / "SKILL.md").is_file():
        raise InstallError(f"SKILL.md가 든 스킬 폴더가 아니다: {src}")
    rels = _paths(name or src.name)
    dest = top / rels[0]
    tracked = [rel for rel in rels if is_tracked(top, rel)]
    if tracked:
        raise InstallError(f"git이 추적하는 자리다: {', '.join(tracked)}")
    in_place = dest.is_dir() and not dest.is_symlink() and dest.resolve() == src
    if os.path.lexists(str(dest)) and not in_place:
        raise InstallError(f"이미 있다: {rels[0]}. 바꾸려면 remove 뒤 다시 add한다")
    personal = placement == "personal"
    if personal:  # excluded before anything is written, so git never shows the files
        append_exclude(top, ["/" + rel for rel in rels])
    if not in_place:
        shutil.copytree(str(src), str(dest), ignore=_COPY_IGNORE)
    return rels, record_private_links(top, rels) if personal else False


def remove_skill(repo: Path, name: str, placement: str) -> bool:
    """Delete a skill that add_skill put in. Return whether install.json
    changed. The kit's own skills and skills the team committed are left alone."""
    top = toplevel(Path(repo))
    rels = _paths(name)
    if name in kit_skills(top):
        raise InstallError(f"키트가 설치한 스킬이라 빼지 않는다: {name}")
    tracked = [rel for rel in rels if is_tracked(top, rel)]
    if tracked:
        raise InstallError(f"git이 추적하는 스킬이라 빼지 않는다: {', '.join(tracked)}")
    dest = top / rels[0]
    if not dest.is_dir():
        raise InstallError(f"없는 스킬이다: {rels[0]}")
    shutil.rmtree(str(dest))
    if placement != "personal":
        return False
    path = top / INSTALL_RECORD
    record = _read_json_object(path)
    if not record:
        return False
    private = [p for p in _listed(record, "private_paths") if p.strip("/") not in rels]
    links = [p for p in _listed(record, "links") if p.strip("/") not in rels]
    if (private, links) == (record.get("private_paths"), record.get("links")):
        return False
    record["private_paths"], record["links"] = private, links
    _write_json(path, record)
    return True


def _description(skill_md: Path) -> str:
    lines = skill_md.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("description:"):
            return line[len("description:") :].strip().strip("\"'")
    return ""


def list_skills(repo: Path) -> List[Tuple[str, str]]:
    """(name, description) of each skill in .agents/skills, the kit's included."""
    top = toplevel(Path(repo))
    folder = top / SKILLS
    found = []
    for skill_md in sorted(folder.glob("*/SKILL.md")) if folder.is_dir() else []:
        name = skill_md.parent.name
        found.append((name, _description(skill_md)))
    return found
