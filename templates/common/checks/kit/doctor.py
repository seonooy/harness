from __future__ import annotations

import configparser
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Set, TextIO, Tuple

from . import gitio
from .architecture_policy import PATTERNS, STYLES, inventory_problems, package_rows, pattern_rows, short_name
from .config import Config, ConfigError, Stage, expand, load_config
from .link import missing_links
from .runner import (
    _STATUS,
    CHECKS,
    EXIT_FAIL,
    EXIT_INCOMPLETE,
    EXIT_PASS,
    RUNS,
    _child_env,
    _flat,
    _not_installed,
    _stop,
    _text,
)
from .weakening import protected_drift

# `check.py doctor`: whether the work tree that holds the current directory is ready to be checked.
#
# It looks at what the runner takes for granted: the install record and the private paths it lists,
# the links of a linked worktree, the protected-file record, the commands and virtual environments
# of stages.json, where the project's module is imported from, base_ref, and whether
# architecture.md and importlinter.ini name the same contracts. Each check runs on its own, so one
# that trips does not hide the others. Exit codes are the runner's: 1 for what must be fixed by
# hand (privacy, protected drift), 2 for what is not ready yet.

_FILL = "<<FILL:"
_ARCH_TAG = re.compile(r"\[검사:\s*architecture/([A-Za-z0-9_.-]+)\s*\]")
_CONTRACT = "importlinter:contract:"
_IMPORT = "import importlib, sys; print(importlib.import_module(sys.argv[1]).__file__)"


def architecture_tags(markdown: str) -> Set[str]:
    """The ids of the `[검사: architecture/<id>]` marks in architecture.md."""
    return set(_ARCH_TAG.findall(markdown))


def importlinter_ids(ini_text: str) -> Set[str]:
    """The contract ids of an import-linter INI file: what follows "importlinter:contract:" in the
    section names."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(ini_text)
    return {name[len(_CONTRACT) :] for name in parser.sections() if name.startswith(_CONTRACT)}


_Problem = Tuple[int, str]  # (EXIT_FAIL or EXIT_INCOMPLETE, what is wrong)


def doctor(cwd: Path, out: TextIO = sys.stdout) -> int:
    """Whether the work tree that holds cwd is ready to be checked.

    1: a private path is tracked by git or not ignored, or a protected file differs from its
    record (personal placement). 2: no install record, a placeholder left in a project file, a
    worktree link missing, a command or virtual environment missing, the import_check module
    imported from outside the tree, base_ref not found (personal placement), or architecture.md
    and importlinter.ini naming different contracts. A failure outweighs an incomplete check, as
    in `run`.
    """
    try:
        return _doctor(Path(cwd), out)
    except Exception as exc:
        return _stop(out, "doctor", f"검사 실행기 오류: {type(exc).__name__}: {exc}")


def _doctor(cwd: Path, out: TextIO) -> int:
    try:
        live = gitio.toplevel(cwd)
    except gitio.GitError as exc:
        return _stop(out, "doctor", f"git 작업 트리 안에서 실행해야 한다: {exc}")
    checks_dir = live / CHECKS
    if not (checks_dir / "stages.json").is_file():
        return _stop(out, "doctor", _not_installed(live))
    problems: List[_Problem] = []
    checks: List[Callable[[], List[_Problem]]] = []
    try:
        install = json.loads((checks_dir / "install.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.append((EXIT_INCOMPLETE, f"설치 기록이 없다: {checks_dir / 'install.json'}"))
    except ValueError as exc:
        problems.append((EXIT_INCOMPLETE, f"설치 기록을 읽지 못했다: {exc}"))
    else:
        checks += [
            lambda: _privacy(live, install),
            lambda: _install_files(live, install),
            lambda: _links(live),
        ]
    try:
        config = load_config(checks_dir / "stages.json")
    except ConfigError as exc:
        problems.append((EXIT_INCOMPLETE, str(exc)))
    else:
        checks += [
            lambda: _protected(live, config),
            lambda: _tools(live, config),
            lambda: _import_check(live, config),
            lambda: _base_ref(live, config),
        ]
    checks.append(lambda: _architecture(live))
    for check in checks:
        try:
            problems += check()
        except Exception as exc:  # one check that trips does not hide the others
            problems.append((EXIT_INCOMPLETE, f"{type(exc).__name__}: {exc}"))
    for code, message in problems:
        label = "ERROR" if code == EXIT_FAIL else "INCOMPLETE"
        out.write(f"{label} doctor: {_flat(message)}\n")
    codes = {code for code, _ in problems}
    code = EXIT_FAIL if EXIT_FAIL in codes else EXIT_INCOMPLETE if codes else EXIT_PASS
    out.write(f"check doctor: {_STATUS[code]}\n")
    return code


def _privacy(live: Path, install: Dict[str, Any]) -> List[_Problem]:
    """A private path must be untracked and ignored. The path itself is asked about, never one
    below a link: in a linked worktree .ai is a link, git refuses to look below one, and the link
    is a private path of its own."""
    problems: List[_Problem] = []
    for entry in install.get("private_paths", []):
        rel = entry.lstrip("/")
        if not rel or any((live / up).is_symlink() for up in list(Path(rel).parents)[:-1]):
            continue
        if gitio.is_tracked(live, rel):
            problems.append((EXIT_FAIL, f"개인 파일이 git에 추적된다: {entry}"))
        elif not gitio.is_ignored(live, rel):
            problems.append(
                (
                    EXIT_FAIL,
                    f"개인 파일이 git 무시 목록에 없다: {entry}. .git/info/exclude에 넣는다",
                )
            )
    return problems


def _install_files(live: Path, install: Dict[str, Any]) -> List[_Problem]:
    problems: List[_Problem] = []
    for item in install.get("files", []):
        rel = item["path"].lstrip("/")
        path = live / rel
        if not path.is_file():
            problems.append((EXIT_INCOMPLETE, f"설치 기록에 있는 파일이 없다: {rel}"))
        elif item.get("owner") == "project" and _FILL in path.read_text(
            encoding="utf-8", errors="replace"
        ):
            problems.append(
                (
                    EXIT_INCOMPLETE,
                    f"자리표시 {_FILL} ...>>가 남아 있다: {rel}. 프로젝트의 값으로 채운다",
                )
            )
    return problems


def _links(live: Path) -> List[_Problem]:
    if not gitio.is_linked_worktree(live):
        return []
    missing = missing_links(live)
    if not missing:
        return []
    harness = gitio.main_checkout(live) / CHECKS / "harness.py"
    message = f"이 워크트리에 연결되지 않은 개인 파일: {', '.join(missing)}. "
    message += f'실행: python3 "{harness}" link'
    return [(EXIT_INCOMPLETE, message)]


def _protected(live: Path, config: Config) -> List[_Problem]:
    # The shared placement commits every protected file. The weakening stage compares them with
    # the base, and there is no record of untracked ones to keep.
    if config.placement == "shared":
        return []
    drift = protected_drift(live, live / CHECKS / "protected.json", config.protected)
    return [(EXIT_FAIL, f"{v.path}: {v.message}") for v in drift]


def _doctor_variables(live: Path) -> Dict[str, str]:
    runs = live / RUNS
    return {
        "live": str(live),
        "repo": str(live),
        "cwd": str(live),
        "checks_dir": str(live / CHECKS),
        "run_dir": str(runs / "doctor"),
        "cache_dir": str(runs / "cache"),
    }


def _command(name: str, config: Config, variables: Dict[str, str]) -> List[str]:
    """`@name` as a stage would start it."""
    probe = Stage(name="doctor", kind="command", profiles=["doctor"], cmd=["@" + name])
    return expand(probe, config, variables, [])


def _tools(live: Path, config: Config) -> List[_Problem]:
    variables = _doctor_variables(live)
    search = _child_env(config, {}, variables).get("PATH")
    problems: List[_Problem] = []
    for name in config.commands:
        program = _command(name, config, variables)[0]
        if os.sep in program:
            found = os.path.isfile(program) and os.access(program, os.X_OK)
        else:
            found = shutil.which(program, path=search) is not None
        if not found:
            problems.append((EXIT_INCOMPLETE, f"commands.{name}의 실행 파일이 없다: {program}"))
    for venv in config.venvs:
        if not (live / venv).is_dir():
            # check never installs: the environment is made once, by hand.
            how = "프로젝트의 설치 명령으로 만든다(예: uv sync --locked)"
            problems.append((EXIT_INCOMPLETE, f"가상환경이 없다: {venv}. {how}"))
    return problems


def _import_check(live: Path, config: Config) -> List[_Problem]:
    """The project's Python, started in import_check.cwd, must import the module from this tree.
    A copy installed elsewhere (the main checkout, a virtual environment) would be checked in the
    tree's place."""
    check = config.import_check
    if not check:
        return []
    if "py" not in config.commands:
        return [
            (EXIT_INCOMPLETE, "import_check는 commands.py로 import해 본다. commands에 py가 없다")
        ]
    variables = _doctor_variables(live)
    module = check["module"]
    done = subprocess.run(
        [*_command("py", config, variables), "-c", _IMPORT, module],
        cwd=str(live / check["cwd"]),
        env=_child_env(config, {}, variables),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=120,
    )
    if done.returncode != 0:
        why = _flat(_text(done.stderr))[-300:]
        return [(EXIT_INCOMPLETE, f"import_check: {module}를 import하지 못했다: {why}")]
    # The last line: an import may print lines of its own, and a path may hold spaces.
    printed = [line.strip() for line in _text(done.stdout).splitlines() if line.strip()]
    where = printed[-1] if printed else ""
    if not os.path.isabs(where) or not _inside(Path(where), live):
        message = (
            f"import_check: {module}가 검사 대상 트리 밖에서 import된다: {where} (트리: {live})"
        )
        return [(EXIT_INCOMPLETE, message)]
    return []


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _base_ref(live: Path, config: Config) -> List[_Problem]:
    if config.placement != "personal" or gitio.merge_base(live, config.base_ref) is not None:
        return []
    message = (
        f"기준 브랜치({config.base_ref})를 찾지 못했거나 HEAD와 공통 조상이 없다. "
        "git fetch로 받아 오거나 stages.json의 base_ref를 고친다"
    )
    return [(EXIT_INCOMPLETE, message)]


def _architecture(live: Path) -> List[_Problem]:
    doc = live / ".ai" / "project" / "architecture.md"
    ini = live / CHECKS / "importlinter.ini"
    if not doc.is_file() and not ini.is_file():
        return []
    markdown = doc.read_text(encoding="utf-8") if doc.is_file() else ""
    ini_text = ini.read_text(encoding="utf-8") if ini.is_file() else ""
    tags = architecture_tags(markdown)
    ids = importlinter_ids(ini_text) if ini_text else set()
    problems: List[_Problem] = []
    if tags != ids:
        only_doc = ", ".join(sorted(tags - ids)) or "없음"
        only_ini = ", ".join(sorted(ids - tags)) or "없음"
        problems.append(
            (
                EXIT_INCOMPLETE,
                "architecture.md의 [검사: architecture/<id>]와 importlinter.ini의 계약 id가 다르다 "
                f"(architecture.md에만: {only_doc}; importlinter.ini에만: {only_ini})",
            )
        )
    rows = package_rows(markdown)
    if not rows:  # an architecture.md from before the package table: checked as it always was
        return problems
    for package, style in rows:
        if style not in STYLES:
            problems.append(
                (
                    EXIT_INCOMPLETE,
                    f"패키지 표의 {package}: 모르는 스타일 {style}. "
                    f"{' 또는 '.join(STYLES)}을 쓴다",
                )
            )
        if not any(i.startswith(short_name(package) + "-") for i in ids):
            problems.append(
                (
                    EXIT_INCOMPLETE,
                    f"패키지 표의 {package}에 맞는 계약이 없다(id가 {short_name(package)}-로 "
                    "시작하는 것). kit-architecture로 제안을 만든다",
                )
            )
    for module, pattern in pattern_rows(markdown):
        if pattern not in PATTERNS:
            problems.append(
                (
                    EXIT_INCOMPLETE,
                    f"패턴 표의 {module}: 모르는 패턴 {pattern}. {', '.join(PATTERNS)} 가운데 하나를 쓴다",
                )
            )
        if not any(i.startswith(short_name(module) + "-") for i in ids):
            problems.append(
                (
                    EXIT_INCOMPLETE,
                    f"패턴 표의 {module}에 맞는 계약이 없다(id가 {short_name(module)}-로 "
                    "시작하는 것). kit-architecture로 제안을 만든다",
                )
            )
    if ini_text:
        problems += [(EXIT_INCOMPLETE, message) for message in inventory_problems(ini_text)]
    return problems
