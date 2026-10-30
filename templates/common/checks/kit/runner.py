from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import posixpath
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, TextIO, Tuple

from . import gitio
from .config import Config, ConfigError, Stage, expand, load_config, stages_for, substitute
from .importcontracts import contracts_for_tree, first_config
from .parsers import ERROR, ParseContext, Violation, il_pairs, parse
from .reference import (
    ReferenceCache,
    adopt_baseline,
    exported,
    load_baseline,
    multiset_diff,
    new_and_moved,
    prune_baseline,
    stale,
)
from .weakening import (
    Approval,
    add_content_approvals,
    apply_approvals,
    load_approvals,
    protected_drift,
    weakenings,
)

# The runner behind `check.py <profile> [--staged] [paths...]`. `check.py doctor` is in doctor.py.
#
# The tree it checks is the git work tree that holds the current directory, never the one the
# script lies in: the main checkout's check.py run from a linked worktree checks the worktree.
# The stages come from .ai/checks/stages.json and run in the order of the file. What a tool prints
# is read into violations (parsers.py), and a stage that compares fails only on the violations its
# reference does not have:
#   personal placement  the same command run on an export of the merge-base with base_ref. The
#                       result is cached under .ai/runs/cache: the merge-base stays put while a
#                       branch is worked on.
#   shared placement    the baseline file, which may only shrink. An entry the tree no longer has
#                       fails the stage until it is deleted.
# A stage whose tool cannot start, runs out of time or prints what the parser cannot trust is
# incomplete, never passed, and so is a stage the runner itself trips over. Exit codes: 0 passed,
# 1 failed (a failure outweighs an incomplete stage), 2 incomplete. A run writes only under
# .ai/runs: a folder per run with a log per stage, and result.json.

EXIT_PASS, EXIT_FAIL, EXIT_INCOMPLETE = 0, 1, 2
PASSED, FAILED, INCOMPLETE, SKIPPED = "passed", "failed", "incomplete", "skipped"
_STATUS = {EXIT_PASS: PASSED, EXIT_FAIL: FAILED, EXIT_INCOMPLETE: INCOMPLETE}

CHECKS = Path(".ai") / "checks"
RUNS = Path(".ai") / "runs"
_APPROVALS = (CHECKS / "approvals.json").as_posix()

# What every tool gets on top of its environment. UTF-8, so Korean text decodes under the C locale
# of a git hook; a fixed hash seed, so lint-imports prints its groups in one order; a wide
# terminal, so rich does not fold long module paths; no colour codes in what the parsers read.
_CHILD_ENV = {"PYTHONUTF8": "1", "PYTHONHASHSEED": "0", "COLUMNS": "1000", "NO_COLOR": "1"}
# What a git hook exports so that git finds the repository and the index it runs for. The runner's
# own git calls keep them: `--staged` has to read the index of the commit being made. A tool must
# not see them, or a test suite that makes repositories of its own would act on this one.
_GIT_REPO_VARIABLES = frozenset(
    (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_PREFIX",
        "GIT_NAMESPACE",
    )
)
_RUFF_KINDS = ("ruff", "ruff-format")
_PYTHON = (".py", ".pyi")
_SHOWN = 5  # violations listed under an ERROR line


@dataclass
class StageOutcome:
    """What one stage came to. `new` holds the violations that fail it, `reference_count` how many
    of the tree's violations its reference accounted for, `moved_count` how many of those moved
    from another file (personal placement), and `stale` the baseline entries the tree no longer
    has (shared placement), which fail it too. `notes` are shown as INFO lines."""

    name: str
    status: str  # passed, failed, incomplete, skipped
    exit_code: Optional[int] = None
    new: List[Violation] = field(default_factory=list)
    reference_count: int = 0
    moved_count: int = 0
    detail: str = ""
    log_path: Optional[Path] = None
    duration_s: float = 0.0
    cmd: List[str] = field(default_factory=list)
    stale: List[Violation] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def overall(outcomes: List[StageOutcome]) -> int:
    """1 if any stage failed, else 2 if any is incomplete, else 0."""
    statuses = {outcome.status for outcome in outcomes}
    if FAILED in statuses:
        return EXIT_FAIL
    return EXIT_INCOMPLETE if INCOMPLETE in statuses else EXIT_PASS


# --- small helpers -------------------------------------------------------------------------------


class _Incomplete(Exception):
    """The stage cannot come to a verdict. The message says why."""


def _text(data: Optional[bytes]) -> str:
    return data.decode("utf-8", errors="replace") if data else ""


def _flat(text: str) -> str:
    """The text on one line, for an output line that starts with a fixed word."""
    return " ".join(text.split())


def _where(violation: Violation) -> str:
    # An import-linter violation names a module and has no line; a command's names its stage.
    return violation.path if violation.line is None else f"{violation.path}:{violation.line}"


def _child_env(
    config: Config, stage_env: Dict[str, str], variables: Dict[str, str]
) -> Dict[str, str]:
    """This environment without env_remove and the git hook's repository variables, then
    config.env and the stage's env with their {variables} filled in, then _CHILD_ENV, and the
    bin folder of each of config.venvs in front of PATH.

    `uv run` used to put the environment's bin first on PATH. The tools run by path now, and a
    program they start by name (a test that runs `alembic`) must still find the project's own.
    VIRTUAL_ENV stays as it is: nothing here activates an environment."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in config.env_remove and key not in _GIT_REPO_VARIABLES
    }
    for key, value in [*config.env.items(), *stage_env.items()]:
        env[key] = substitute(value, variables)
    env.update(_CHILD_ENV)
    if config.venvs:
        bins = [str(Path(variables["live"]) / venv / "bin") for venv in config.venvs]
        env["PATH"] = os.pathsep.join([*bins, env.get("PATH", os.defpath)])
    return env


def _source_dirs(stage: Stage, variables: Dict[str, str], cwd: Path) -> List[Path]:
    """The folders the stage's own env puts on PYTHONPATH, where lint-imports finds the root
    packages of a src layout. A relative entry is taken from `cwd`, as the tool takes it.
    PYTHONPATH from the calling shell is left out: it is the same for the work tree and the
    merge-base export, so it says nothing about what this tree has."""
    value = stage.env.get("PYTHONPATH")
    if not value:
        return []
    entries = [Path(p) for p in substitute(value, variables).split(os.pathsep) if p]
    return [p if p.is_absolute() else cwd / p for p in entries]


def _run_tool(
    argv: List[str], cwd: Path, env: Dict[str, str], timeout: int
) -> Tuple[int, bytes, bytes]:
    """Run argv in a session of its own and return its exit code, stdout and stderr.

    When the time runs out, or the run is interrupted (a group of its own does not get the
    terminal's Ctrl-C), the whole process group is killed: under `uv run` the tool is a
    grandchild, and killing only the direct child would leave pytest or mypy running. Raises
    subprocess.TimeoutExpired with what was printed until then, and OSError when argv cannot be
    started."""
    with subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(process)
            stdout, stderr = _printed(process)
            raise subprocess.TimeoutExpired(argv, timeout, stdout, stderr) from None
        except BaseException:
            _kill_group(process)
            raise
    return process.returncode, stdout, stderr


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:  # gone already (macOS answers EPERM for a group of zombies)
        process.kill()


def _printed(process: subprocess.Popen[bytes]) -> Tuple[bytes, bytes]:
    """What a killed group printed. A process that left the group may still hold the pipes: it is
    given a few seconds, not as long as it runs."""
    try:
        return process.communicate(timeout=5)
    except subprocess.TimeoutExpired as exc:
        return exc.stdout or b"", exc.stderr or b""


def _write_log(
    path: Path, argv: List[str], cwd: Path, exit_code: Optional[int], stdout: str, stderr: str
) -> None:
    text = f"$ {shlex.join(argv)}\ncwd: {cwd}\nexit: {exit_code}\n"
    text += f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n"
    path.write_text(text, encoding="utf-8", errors="replace")


def _given_paths(cwd: Path, live: Path, paths: List[str], staged: bool) -> Optional[List[str]]:
    """The paths the caller named (relative to cwd), or the staged ones, relative to the root of
    the repository. None when no path was named. A path outside the repository is dropped."""
    if staged:
        return gitio.staged_paths(live)
    if not paths:
        return None
    here = os.path.realpath(str(cwd))
    given: List[str] = []
    for raw in paths:
        rel = os.path.relpath(os.path.join(here, raw), str(live))
        if rel != os.pardir and not rel.startswith(os.pardir + os.sep):
            given.append(rel.replace(os.sep, "/"))
    return given


def _suffixes(stage: Stage) -> Tuple[str, ...]:
    """The file name endings the stage keeps, or () for every file. A Ruff stage keeps Python
    files unless it says otherwise: Ruff would report a README as a syntax error."""
    if stage.suffixes is not None:
        return tuple(stage.suffixes)
    return _PYTHON if stage.kind in _RUFF_KINDS else ()


def _for_stage(paths: List[str], stage: Stage, live: Path) -> List[str]:
    """The repository paths that lie in the stage's folder, relative to that folder. Files whose
    name does not end in one of the stage's suffixes are left out, folders never. A path that
    starts with "-" gets "./" in front, so that the tool does not take it for an option."""
    base = posixpath.normpath(stage.cwd)
    suffixes = _suffixes(stage)
    kept: List[str] = []
    for path in (posixpath.normpath(p) for p in paths):
        if base == ".":
            rel = path
        elif path.startswith(base + "/"):
            rel = path[len(base) + 1 :]
        elif path in (".", base) or base.startswith(path + "/"):
            rel = "."  # the stage's folder itself, or a folder that holds it
        else:
            continue
        if suffixes and not rel.endswith(suffixes) and not (live / path).is_dir():
            continue
        if rel.startswith("-"):
            rel = "./" + rel
        if rel not in kept:
            kept.append(rel)
    return kept


def _within(path: str, scanned: List[str]) -> bool:
    return any(s == "." or path == s or path.startswith(s + "/") for s in scanned)


# --- one run of a profile ------------------------------------------------------------------------


class _Run:
    """The tree a profile runs on, its git state, and the folder the run writes to."""

    def __init__(
        self,
        live: Path,
        config: Config,
        head: str,
        merge_base: Optional[str],
        run_dir: Path,
        given: Optional[List[str]],
    ) -> None:
        self.live, self.config, self.head, self.merge_base = live, config, head, merge_base
        self.run_dir, self.given = run_dir, given
        self.checks_dir = live / CHECKS
        self.cache_dir = live / RUNS / "cache"
        self._dirty: Optional[bool] = None

    def variables(self, repo: Path, cwd: str) -> Dict[str, str]:
        """{repo} and {cwd} are in the tree being run, the work tree or an export of the
        merge-base. {live}, {checks_dir} and the commands always belong to the work tree."""
        return {
            "live": str(self.live),
            "repo": str(repo),
            "cwd": str(repo / cwd),
            "checks_dir": str(self.checks_dir),
            "run_dir": str(self.run_dir),
            "cache_dir": str(self.cache_dir),
        }

    def stage(self, stage: Stage) -> StageOutcome:
        outcome = StageOutcome(stage.name, PASSED)
        started = time.monotonic()
        try:
            if stage.kind == "weakening":
                self._weakening(outcome)
            else:
                self._tool_stage(stage, outcome)
        except _Incomplete as exc:
            outcome.status, outcome.detail = INCOMPLETE, str(exc)
        except Exception as exc:  # whatever else trips this stage; the other stages still run
            outcome.status, outcome.detail = INCOMPLETE, f"{type(exc).__name__}: {exc}"
        outcome.duration_s = round(time.monotonic() - started, 3)
        return outcome

    def _tool_stage(self, stage: Stage, outcome: StageOutcome) -> None:
        paths, limited = self._paths(stage)
        if limited and not paths:
            outcome.status, outcome.detail = SKIPPED, "검사할 파일이 없다"
            return
        log = self.run_dir / f"{stage.name}.log"
        current = self._execute(stage, self.live, paths, log, outcome)
        if stage.compare and self.config.placement == "shared":
            reference = self._baseline().get(stage.name, [])
            if stage.kind == "import-linter":  # a baseline written while violations were routes
                reference = il_pairs(reference)
            if limited:  # entries of files that were not looked at say nothing either way
                scanned = [posixpath.normpath(posixpath.join(stage.cwd, p)) for p in paths]
                reference = [v for v in reference if _within(v.path, scanned)]
            outcome.stale = stale(current, reference)
            outcome.new = multiset_diff(current, reference)
        elif stage.compare:
            reference = self._merge_base_run(stage, outcome.cmd, paths, current)
            outcome.new, moved = new_and_moved(current, reference)
            outcome.moved_count = len(moved)
        else:
            outcome.new = current
        outcome.reference_count = len(current) - len(outcome.new)
        outcome.status = FAILED if outcome.new or outcome.stale else PASSED

    def _paths(self, stage: Stage) -> Tuple[List[str], bool]:
        """The paths the stage is given, relative to its folder, and whether they are a selection
        rather than everything. A selection that comes out empty skips the stage."""
        if stage.scope == "all":
            return [], False
        if self.given is not None:
            return _for_stage(self.given, stage, self.live), True
        if stage.scope == "paths":
            return ["."], False
        changed = gitio.changed_paths(self.live, self._base())
        return _for_stage([c.path for c in changed if c.status != "D"], stage, self.live), True

    def _execute(
        self,
        stage: Stage,
        repo: Path,
        paths: List[str],
        log: Path,
        outcome: Optional[StageOutcome] = None,
    ) -> List[Violation]:
        """Run the stage's command on the tree at `repo` and return what the tool found. With
        `outcome`, the command, its exit code and the log are noted there as soon as known."""
        variables = self.variables(repo, stage.cwd)
        argv = expand(stage, self.config, variables, paths)
        cwd = Path(variables["cwd"])
        # `argv` stays the command as configured: the merge-base cache keys on the files it names.
        # What runs is `run`, which may point lint-imports at the contracts cut for this tree.
        run = list(argv)
        if stage.kind == "import-linter" and not self._contracts_for_tree(
            run, cwd, _source_dirs(stage, variables, cwd), log, outcome, work_tree=repo == self.live
        ):
            if outcome is not None:
                outcome.cmd, outcome.log_path = argv, log
            _write_log(log, run, cwd, 0, "", "이 트리에는 계약이 가리키는 모듈이 없어 돌리지 않았다")
            return []
        junit = None
        if stage.junit:
            junit = Path(substitute(stage.junit, variables))
            junit = junit if junit.is_absolute() else cwd / junit
            junit.unlink(missing_ok=True)  # one left by an earlier run would be read as this one's
        if outcome is not None:
            outcome.cmd, outcome.log_path = argv, log
        env = _child_env(self.config, stage.env, variables)
        try:
            exit_code, out, err = _run_tool(run, cwd, env, stage.timeout)
        except subprocess.TimeoutExpired as exc:
            _write_log(log, run, cwd, None, _text(exc.stdout), _text(exc.stderr))
            raise _Incomplete(f"{stage.timeout}초 안에 끝나지 않았다") from None
        except OSError as exc:  # no such program, not executable, no such folder
            _write_log(log, run, cwd, None, "", str(exc))
            raise _Incomplete(f"실행하지 못했다: {exc}") from None
        stdout, stderr = _text(out), _text(err)
        _write_log(log, run, cwd, exit_code, stdout, stderr)
        if outcome is not None:
            outcome.exit_code = exit_code
        context = ParseContext(stage.name, repo, cwd, junit, list(stage.allow_skip))
        parsed = parse(stage.kind, exit_code, stdout, stderr, context)
        if parsed.status == ERROR:
            raise _Incomplete(parsed.detail)
        return parsed.violations

    def _contracts_for_tree(
        self,
        argv: List[str],
        cwd: Path,
        source_dirs: List[Path],
        log: Path,
        outcome: Optional[StageOutcome],
        work_tree: bool,
    ) -> int:
        """Point lint-imports at the contracts cut to the modules the tree at `cwd` has, written
        beside the log, and return how many contracts are left. Modules are looked for in `cwd`
        and in `source_dirs`. The merge-base export may lack modules and whole root packages the
        branch added. The work tree, which check, prune and adopt run on, may lack modules of
        another branch's worktree, but never a root package, and never every module of its
        contracts: that is a stage set up in the wrong folder or a misspelled name. What was left
        out is noted on `outcome`."""
        at = first_config(argv)
        if at is None:
            return 1
        config = Path(argv[at]) if Path(argv[at]).is_absolute() else cwd / argv[at]
        cut = contracts_for_tree(config.read_text(encoding="utf-8"), cwd, source_dirs)
        written = log.with_name(log.stem + ".importlinter.ini")
        written.write_text(cut.text, encoding="utf-8")
        argv[at] = str(written)
        if not work_tree:
            return cut.kept
        if cut.missing_roots:
            raise _Incomplete(
                f"최상위 패키지가 이 트리({cwd})에 없다: {', '.join(cut.missing_roots)}. "
                "stages.json의 이 단계 cwd를 최상위 패키지가 있는 폴더로 맞추거나, src 레이아웃이면 "
                "그 폴더를 이 단계 env의 PYTHONPATH에 넣는다"
            )
        if cut.total and not cut.kept:
            raise _Incomplete(
                f"계약({', '.join(cut.dropped)})이 가리키는 모듈이 이 트리에 하나도 없다: "
                f"{', '.join(cut.missing)}. 이름이 틀렸는지 본다"
            )
        if cut.missing and outcome is not None:
            note = f"이 트리에 없는 모듈은 계약에서 빼고 돌렸다: {', '.join(cut.missing)}"
            if cut.dropped:
                note += f" (그래서 뺀 계약 {', '.join(cut.dropped)})"
            outcome.notes.append(note)
        return cut.kept

    def _merge_base_run(
        self, stage: Stage, argv: List[str], paths: List[str], current: List[Violation]
    ) -> List[Violation]:
        """What the stage finds on the merge-base: from the cache, or by running it there."""
        base = self._base()
        if base == self.head and not self._dirty_tree():
            return current  # the merge-base is what is checked out
        key = ReferenceCache.key(
            # config.env reaches the tool too, and stages.json is not among the files below.
            dataclasses.replace(stage, env={**self.config.env, **stage.env}),
            # The command as the work tree runs it: an export lands in a new folder every time,
            # and so does a run, so the key holds neither.
            expand(
                stage,
                self.config,
                dict(self.variables(self.live, stage.cwd), run_dir="{run_dir}"),
                paths,
            ),
            self._config_files(stage, argv),
            paths,
        )
        cache = ReferenceCache(self.cache_dir)
        found = cache.get(base, stage.name, key)
        if found is not None:
            return found
        with exported(self.live, base, stage.cwd) as root:
            # A file the branch added is not in the export, and Ruff format stops on a missing one.
            there = [p for p in paths if os.path.lexists(root / stage.cwd / p)]
            if paths and not there:
                found = []
            else:
                log = self.run_dir / f"{stage.name}.base.log"
                try:
                    found = self._execute(stage, root, there, log)
                except _Incomplete as exc:
                    raise _Incomplete(f"기준 트리({base[:12]})에서: {exc} (로그: {log})") from None
        cache.put(base, stage.name, key, found)
        return found

    def _config_files(self, stage: Stage, argv: List[str]) -> List[Path]:
        """The files besides the tree whose content decides what the tool prints: those the
        command names under checks_dir, the Ruff rule set, the lock of the tools, and the kit's
        parser."""
        prefix = str(self.checks_dir) + os.sep
        files = [Path(arg[arg.index(prefix) :]) for arg in argv if prefix in arg]
        if stage.ruff_rules:
            variables = self.variables(self.live, stage.cwd)
            files.append(self._live_path(substitute(stage.ruff_rules, variables)))
        lock = self.checks_dir / "tools" / "requirements.lock"
        if lock.is_file():
            files.append(lock)
        files.append(Path(__file__).with_name("parsers.py"))
        files.append(Path(__file__).with_name("importcontracts.py"))
        return files

    def _weakening(self, outcome: StageOutcome) -> None:
        # The base is the merge-base with base_ref; a shared placement's "HEAD" gives HEAD itself.
        base = self._base()
        shared = self.config.placement == "shared"
        approvals = load_approvals(self.checks_dir / "approvals.json")
        # `harness.py prune` deletes entries from the baseline, which needs no approval.
        baseline = self.baseline_file()
        in_tree: Optional[str] = None
        if baseline is not None:
            try:
                in_tree = baseline.relative_to(self.live).as_posix()
            except ValueError:  # outside the repository, so git has no version of it to compare
                in_tree = None
        protected = self.config.protected
        # The shared placement commits every protected file, so an approval names the content it
        # allows and is committed with the change. approvals.json itself is then shown, by the
        # INFO lines below and in the diff, for whoever reviews the branch: approving an approval
        # would only ask for another. The personal placement keeps it in the record approve writes.
        found = weakenings(self.live, base, protected, baseline=in_tree, by_content=shared)
        if shared:
            found = [v for v in found if not (v.code == "protected" and v.path == _APPROVALS)]
        found, used = apply_approvals(found, approvals)
        if not shared:  # protected files that git does not track
            found += protected_drift(self.live, self.checks_dir / "protected.json", protected)
        outcome.notes = [_approved(approval) for approval in used]
        outcome.log_path = self.run_dir / f"{outcome.name}.log"
        lines = [f"base: {base}"] + [f"{_where(v)} {v.code} {v.message} | {v.text}" for v in found]
        lines += outcome.notes
        outcome.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8", errors="replace")
        outcome.new = found
        outcome.status = FAILED if found else PASSED

    def _base(self) -> str:
        if self.merge_base is None:
            raise _Incomplete(
                f"기준 브랜치({self.config.base_ref})와의 merge-base를 찾지 못했다. "
                "기준 브랜치를 git fetch로 받아 오거나 stages.json의 base_ref를 고친다"
            )
        return self.merge_base

    def baseline_file(self) -> Optional[Path]:
        """The file config.baseline names, or None when it names none."""
        if not self.config.baseline:
            return None
        variables = self.variables(self.live, ".")
        return self._live_path(substitute(self.config.baseline, variables))

    def _baseline(self) -> Dict[str, List[Violation]]:
        path = self.baseline_file()
        return {} if path is None else load_baseline(path)

    def _live_path(self, text: str) -> Path:
        path = Path(text)
        return path if path.is_absolute() else self.live / path

    def _dirty_tree(self) -> bool:
        if self._dirty is None:
            self._dirty = gitio.working_tree_dirty(self.live)
        return self._dirty


def _report(out: TextIO, outcome: StageOutcome, stage: Stage, run: _Run) -> None:
    name, log = outcome.name, outcome.log_path
    if outcome.status == INCOMPLETE:
        where = f" (전체 로그: {log})" if log is not None and log.exists() else ""
        out.write(f"INCOMPLETE {name}: {_flat(outcome.detail)}{where}\n")
    elif outcome.status == SKIPPED:
        out.write(f"INFO {name}: {outcome.detail}. 건너뛰었다\n")
    if outcome.new:
        hint = _flat(stage.fix_hint) or "새 위반을 고친다"
        out.write(f"ERROR {name}: {hint} (새 위반 {len(outcome.new)}개, 전체 로그: {log})\n")
        _list(out, outcome.new)
    if outcome.stale:
        prune = f'python3 "{run.checks_dir / "harness.py"}" prune --stage {name}'
        count = len(outcome.stale)
        out.write(
            f"ERROR {name}: 기준선에 이제는 없는 위반 {count}개가 남아 있다. "
            f"지운다: {prune} (전체 로그: {log})\n"
        )
        _list(out, outcome.stale)
    if outcome.reference_count:
        what = "기준선에" if run.config.placement == "shared" else "기준 브랜치에 이미"
        out.write(f"INFO {name}: {what} 있던 위반 {outcome.reference_count}개는 판정에서 뺐다\n")
        if outcome.moved_count:
            out.write(
                f"INFO {name}: 그중 {outcome.moved_count}개는 다른 파일에서 옮겨 온 위반이다\n"
            )
    for note in outcome.notes:
        out.write(f"INFO {name}: {_flat(note)}\n")


def _list(out: TextIO, violations: List[Violation]) -> None:
    for violation in violations[:_SHOWN]:
        out.write(f"  {_where(violation)} {violation.code} {_flat(violation.message)}\n")


def _approved(approval: Approval) -> str:
    """The note that an approval let a change through: what it allows, and why."""
    text = f" | {approval.text.strip()}" if approval.text.strip() else ""
    return f"승인으로 넘어갔다: {approval.kind} {approval.path}{text} (이유: {approval.reason})"


def _write_result(
    path: Path,
    profile: str,
    run: _Run,
    diff: str,
    started: datetime,
    outcomes: List[StageOutcome],
    code: int,
) -> None:
    stages = [
        {
            "name": o.name,
            "cmd": o.cmd,
            "exit_code": o.exit_code,
            "status": o.status,
            "new": [dataclasses.asdict(v) for v in o.new],
            "reference_count": o.reference_count,
            "duration_s": o.duration_s,
            "detail": o.detail,
            "log": str(o.log_path) if o.log_path is not None else None,
            "stale": [dataclasses.asdict(v) for v in o.stale],
        }
        for o in outcomes
    ]
    data = {
        "profile": profile,
        # Every stage looked at the whole tree: no paths were named and --staged was not given.
        "full": run.given is None,
        "repo": str(run.live),
        "head": run.head,
        "diff_sha256": diff,
        "base_ref": run.config.base_ref,
        "merge_base": run.merge_base,
        "placement": run.config.placement,
        "started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stages": stages,
        "status": _STATUS[code],
        "exit_code": code,
    }
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", errors="replace")


def _stop(out: TextIO, profile: str, reason: str) -> int:
    out.write(f"INCOMPLETE harness: {_flat(reason)}\ncheck {profile}: {INCOMPLETE}\n")
    return EXIT_INCOMPLETE


def _not_installed(live: Path) -> str:
    """Why a tree without stages.json cannot be checked, and what to run."""
    main = gitio.main_checkout(live)
    if main != live and (main / CHECKS / "stages.json").is_file():
        harness = main / CHECKS / "harness.py"
        return f'이 워크트리에 개인 하네스가 연결되지 않았다. 실행: python3 "{harness}" link'
    return f"검사 키트가 설치되지 않았다: {live / CHECKS / 'stages.json'}가 없다"


def run(
    cwd: Path, profile: str, paths: List[str], staged: bool = False, out: TextIO = sys.stdout
) -> int:
    """Run the stages of `profile` on the work tree that holds cwd and return the exit code.

    `paths` (relative to cwd) or, with `staged`, the staged files narrow the stages whose scope is
    not "all". The output has an ERROR, INFO or INCOMPLETE line per finding, and a last line
    `check <profile>: <status> (<run folder>/result.json)`.
    """
    try:
        return _run(Path(cwd), profile, paths, staged, out)
    except Exception as exc:  # a crash must not read as 1, which means violations
        return _stop(out, profile, f"검사 실행기 오류: {type(exc).__name__}: {exc}")


def _run(cwd: Path, profile: str, paths: List[str], staged: bool, out: TextIO) -> int:
    try:
        live = gitio.toplevel(cwd)
    except gitio.GitError as exc:
        return _stop(out, profile, f"git 작업 트리 안에서 실행해야 한다: {exc}")
    stages_file = live / CHECKS / "stages.json"
    if not stages_file.is_file():
        return _stop(out, profile, _not_installed(live))
    try:
        config = load_config(stages_file)
    except ConfigError as exc:
        return _stop(out, profile, str(exc))
    stages = stages_for(config, profile)
    if not stages:  # before any run folder exists: `check fats` is a typo, not a pass
        known = ", ".join(sorted({p for s in config.stages for p in s.profiles})) or "없음"
        return _stop(out, profile, f"프로필 {profile}에 실행할 단계가 없다 (있는 프로필: {known})")
    try:
        head = gitio.head(live)
        merge_base = gitio.merge_base(live, config.base_ref)
        diff = gitio.diff_sha256(live)
        given = _given_paths(cwd, live, paths, staged)
    except gitio.GitError as exc:
        return _stop(out, profile, f"git 상태를 읽지 못했다: {exc}")
    started = datetime.now(timezone.utc)
    run_dir = _new_run_dir(live, started, profile)
    state = _Run(live, config, head, merge_base, run_dir, given)
    outcomes: List[StageOutcome] = []
    for stage in stages:
        outcome = state.stage(stage)
        outcomes.append(outcome)
        _report(out, outcome, stage, state)
        out.flush()
    code = overall(outcomes)
    result = run_dir / "result.json"
    _write_result(result, profile, state, diff, started, outcomes, code)
    out.write(f"check {profile}: {_STATUS[code]} ({result})\n")
    return code


def _new_run_dir(live: Path, started: datetime, label: str) -> Path:
    """A new folder .ai/runs/<UTC time>-<label>-<unique> for one run's logs and result."""
    runs = live / RUNS
    runs.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"{started:%Y%m%dT%H%M%SZ}-{label}-", dir=str(runs)))


# --- harness.py prune ----------------------------------------------------------------------------


def prune(cwd: Path, stage_name: str, out: TextIO = sys.stdout) -> int:
    """Run one stage on the whole work tree that holds cwd and delete the baseline entries it no
    longer finds. Only a full run can say an entry is gone: a run on some files says nothing of
    the others. 0 when done (also with nothing to delete), 2 when the stage could not come to a
    verdict or there is no baseline to prune."""
    try:
        return _prune(Path(cwd), stage_name, out)
    except Exception as exc:
        return _prune_stop(out, f"검사 실행기 오류: {type(exc).__name__}: {exc}")


def _prune_stop(out: TextIO, reason: str) -> int:
    out.write(f"INCOMPLETE prune: {_flat(reason)}\n")
    return EXIT_INCOMPLETE


def _prune(cwd: Path, stage_name: str, out: TextIO) -> int:
    live = gitio.toplevel(cwd)
    stages_file = live / CHECKS / "stages.json"
    if not stages_file.is_file():
        return _prune_stop(out, _not_installed(live))
    config = load_config(stages_file)
    stage = next((s for s in config.stages if s.name == stage_name), None)
    if stage is None or not stage.compare:
        return _prune_stop(out, f"stages.json에 기준선과 비교하는 단계 {stage_name}가 없다")
    no_baseline = "기준선은 공유 배치에서 stages.json의 baseline이 가리키는 파일이다"
    if config.placement != "shared":
        return _prune_stop(out, no_baseline)
    run_dir = _new_run_dir(live, datetime.now(timezone.utc), "prune")
    state = _Run(live, config, gitio.head(live), None, run_dir, None)
    baseline = state.baseline_file()
    if baseline is None:
        return _prune_stop(out, no_baseline)
    log = run_dir / f"{stage.name}.log"
    try:
        current = state._execute(stage, live, [] if stage.scope == "all" else ["."], log)
    except _Incomplete as exc:
        return _prune_stop(out, f"{stage.name}: {exc} (전체 로그: {log})")
    removed = prune_baseline(baseline, stage.name, current, pairs=stage.kind == "import-linter")
    out.write(f"INFO prune: {stage.name}: 기준선에서 이제는 없는 위반 {removed}개를 지웠다\n")
    return EXIT_PASS


# --- harness.py baseline adopt -------------------------------------------------------------------


def adopt(cwd: Path, stage_name: str, reason: str, out: TextIO = sys.stdout) -> int:
    """Run one stage on the whole work tree that holds cwd, add the violations the baseline does
    not allow yet with `reason`, and approve the baseline's new content. Only the user runs it,
    right after a change of style brought new contracts that old code breaks. 0 when done, 2 when
    the stage could not come to a verdict or there is no baseline (the personal placement)."""
    try:
        return _adopt(Path(cwd), stage_name, reason, out)
    except Exception as exc:
        return _adopt_stop(out, f"검사 실행기 오류: {type(exc).__name__}: {exc}")


def _adopt_stop(out: TextIO, reason: str) -> int:
    out.write(f"INCOMPLETE baseline: {_flat(reason)}\n")
    return EXIT_INCOMPLETE


def _adopt(cwd: Path, stage_name: str, reason: str, out: TextIO) -> int:
    live = gitio.toplevel(cwd)
    stages_file = live / CHECKS / "stages.json"
    if not stages_file.is_file():
        return _adopt_stop(out, _not_installed(live))
    config = load_config(stages_file)
    stage = next((s for s in config.stages if s.name == stage_name), None)
    if stage is None or not stage.compare:
        return _adopt_stop(out, f"stages.json에 기준선과 비교하는 단계 {stage_name}가 없다")
    if not reason.strip():
        return _adopt_stop(out, "--reason에 이유(ADR 번호)를 적는다")
    personal = "기준선은 공유 배치의 파일이다. 개인 배치는 merge-base가 기존 위반을 뺀다"
    if config.placement != "shared":
        return _adopt_stop(out, personal)
    run_dir = _new_run_dir(live, datetime.now(timezone.utc), "adopt")
    state = _Run(live, config, gitio.head(live), None, run_dir, None)
    baseline = state.baseline_file()
    if baseline is None:
        return _adopt_stop(out, personal)
    log = run_dir / f"{stage.name}.log"
    try:
        current = state._execute(stage, live, [] if stage.scope == "all" else ["."], log)
    except _Incomplete as exc:
        return _adopt_stop(out, f"{stage.name}: {exc} (전체 로그: {log})")
    added = adopt_baseline(
        baseline, stage.name, current, reason.strip(), pairs=stage.kind == "import-linter"
    )
    if added:
        rel = baseline.relative_to(live).as_posix()
        digest = hashlib.sha256(baseline.read_bytes()).hexdigest()
        add_content_approvals(live / CHECKS / "approvals.json", {rel: digest}, reason.strip())
    out.write(
        f"INFO baseline: {stage.name}: 기존 위반 {len(added)}개를 기준선에 올리고 그 내용을 승인했다\n"
    )
    _list(out, added)  # what the user approved, entry by entry
    return EXIT_PASS
