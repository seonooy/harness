from __future__ import annotations

import configparser
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

# The import contracts as they apply to one tree. One importlinter.ini serves every tree the kit
# checks: the work tree, the merge-base export that tells old violations from new ones, and the
# linked worktrees of other branches, which share the file. A tree may lack a module a contract
# names: a package new on the branch is not in the merge-base, a module of another branch is not
# here. lint-imports stops on a missing module, so the kit hands it the contracts cut to the modules
# the tree has. A contract left with nothing to check is left out: a package that is not there
# cannot break it. A layer the tree lacks becomes optional, which lint-imports takes as written.
# Expressions with a wildcard are left as written: lint-imports accepts one that matches nothing.

_TOKEN = re.compile(r"\(?[A-Za-z_][\w.]*\)?")
_CONTRACT = "importlinter:contract:"
# The fields of each contract type that name modules of the project, and how few must remain.
_FIELDS = {
    "forbidden": (("source_modules", 1), ("forbidden_modules", 1)),
    "protected": (("protected_modules", 1), ("allowed_importers", 0)),
    "independence": (("modules", 2),),
    "acyclic_siblings": (("ancestors", 1),),
}


@dataclass
class Cut:
    """The contracts cut for a tree. `missing` are the project modules the tree lacks, in order;
    `dropped` the contract ids left out; `missing_roots` the root packages the tree lacks; `total`
    how many contracts the file had and `kept` how many are left."""

    text: str
    missing: List[str] = field(default_factory=list)
    dropped: List[str] = field(default_factory=list)
    missing_roots: List[str] = field(default_factory=list)
    total: int = 0
    kept: int = 0


def _exists(folders: Sequence[Path], name: str) -> bool:
    relative = name.replace(".", "/")
    return any(
        (folder / relative).is_dir() or (folder / relative).with_suffix(".py").is_file()
        for folder in folders
    )


def contracts_for_tree(ini_text: str, tree: Path, source_dirs: Sequence[Path] = ()) -> Cut:
    """The import-linter file with every contract cut to the modules `tree` has. A module is there
    when it sits under `tree` or under one of `source_dirs`: in a src layout the stage puts those
    folders on PYTHONPATH, and lint-imports finds the root packages in them."""
    folders = [tree, *source_dirs]
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(ini_text)
    cut = Cut(text="")
    roots = _cut_roots(parser, folders, cut)
    every_root = roots + cut.missing_roots

    def absent(name: str) -> bool:
        if "*" in name or not any(name == r or name.startswith(r + ".") for r in every_root):
            return False
        if _exists(folders, name):
            return False
        if name not in cut.missing:
            cut.missing.append(name)
        return True

    for section in [s for s in parser.sections() if s.startswith(_CONTRACT)]:
        cut.total += 1
        contract = parser[section]
        found_before = len(cut.missing)
        kind = contract.get("type", "")
        if kind == "layers":
            ok = _layers(contract, absent)
        else:
            ok = True
            for name, least in _FIELDS.get(kind, ()):
                if name not in contract:
                    continue
                kept = [n for n in contract[name].split() if not absent(n)]
                contract[name] = "\n" + "\n".join(kept) if kept else ""
                # an expression with a wildcard may stand for any number of modules
                ok = ok and (len(kept) >= least or any("*" in n for n in kept))
        if not ok or not roots:
            parser.remove_section(section)
            cut.dropped.append(section[len(_CONTRACT) :])
            continue
        cut.kept += 1
        if len(cut.missing) > found_before and "ignore_imports" in contract:
            contract["unmatched_ignore_imports_alerting"] = "none"
    out = io.StringIO()
    parser.write(out)
    cut.text = out.getvalue()
    return cut


def _cut_roots(parser: configparser.ConfigParser, folders: Sequence[Path], cut: Cut) -> List[str]:
    """The root packages the tree has, written back without the others."""
    if not parser.has_section("importlinter"):
        return []
    roots: List[str] = []
    for key in ("root_package", "root_packages"):
        if key not in parser["importlinter"]:
            continue
        names = parser["importlinter"][key].split()
        here = [n for n in names if _exists(folders, n)]
        cut.missing_roots += [n for n in names if n not in here]
        roots += here
        if here:
            parser["importlinter"][key] = here[0] if key == "root_package" else "\n" + "\n".join(here)
        else:
            parser.remove_option("importlinter", key)
    return roots


def _layers(contract: configparser.SectionProxy, absent: Callable[[str], bool]) -> bool:
    """Cut a layers contract to the containers the tree has (False when none is left); each
    plain layer some remaining container lacks becomes optional."""
    named = contract.get("containers", "").split()
    containers = [c for c in named if not absent(c)]
    if named and not containers:
        return False
    if containers:
        contract["containers"] = "\n" + "\n".join(containers)

    def optional(match: "re.Match[str]") -> str:
        token = match.group(0)
        if token.startswith("("):
            return token
        lacks = [absent(f"{c}.{token}") for c in containers] if containers else [absent(token)]
        return f"({token})" if any(lacks) else token

    lines = contract.get("layers", "").split("\n")
    contract["layers"] = "\n".join(_TOKEN.sub(optional, line) for line in lines)
    return True


def first_config(argv: List[str]) -> Optional[int]:
    """The index of the value after "--config" in a lint-imports command, if there is one."""
    for i, arg in enumerate(argv[:-1]):
        if arg == "--config":
            return i + 1
    return None
