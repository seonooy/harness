from __future__ import annotations

import json
import os
import re
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# The check kit's stage list.
#
# `.ai/checks/stages.json` says which tools run, in which folder and with which arguments. The
# runner knows no language, so all of that comes from this file. load_config reads and checks it.
# expand turns one stage's command template into the argument list to start.
#
# The keys of the file are the field names of Config and, inside "stages", of Stage. A key may be
# left out when its field has a default, except version, project, placement, base_ref and stages
# in the file, and name, kind and profiles in a stage.
#
# Only types, fixed choices (version, placement, kind, scope), the form of stage and profile names,
# that a command is not empty, that every stage but weakening has a cmd, that a timeout is
# positive and that suffixes, when given, are not empty are checked. A stage name is
# lowercase letters, digits and hyphens because it goes into ERROR lines and into log and cache
# file names; a profile name too, because it goes into the name of the run folder. Other free text
# such as a project name, a path or a fix hint
# is not checked, so a template that still holds `<<FILL: ...>>` markers loads, and
# `check doctor` is what reports the markers.
#
# A key that starts with "_" is a note for the people who edit the file and is ignored. Any other
# key the schema does not know is an error: a mistyped `env_remov` would otherwise leave
# DATABASE_URL in the environment of a test run without a word.

KINDS = ("ruff", "ruff-format", "mypy", "import-linter", "pytest-junit", "command", "weakening")
SCOPES = ("all", "paths", "changed")
PLACEMENTS = ("personal", "shared")

# Whole elements of a command template that expand handles itself. A command cannot take these
# names, or its @name could never be reached.
_PATHS = "@paths"
_PATHS_OR_DOT = "@paths_or_dot"
_RUFF_OVERRIDES = "@ruff_overrides"
_BUILTIN_TOKENS = (_PATHS, _PATHS_OR_DOT, _RUFF_OVERRIDES)


class ConfigError(Exception):
    """A stage list, a Ruff rule set or a command template that cannot be used. The message says
    what is wrong and where."""


@dataclass
class Stage:
    """One check. `cmd` is a template: expand turns it into the argument list to run. `name` is
    lowercase letters, digits and hyphens, because it appears in ERROR lines and in log and cache
    file names; load_config enforces that."""

    name: str
    kind: str
    profiles: List[str]
    cmd: List[str] = field(default_factory=list)
    cwd: str = "."
    scope: str = "all"
    compare: bool = False
    fix_hint: str = ""
    timeout: int = 300  # seconds
    env: Dict[str, str] = field(default_factory=dict)
    junit: Optional[str] = None
    ruff_rules: Optional[str] = None  # the rule set that `@ruff_overrides` turns into arguments
    allow_skip: List[str] = field(default_factory=list)
    # The file name endings a stage that is given files keeps: a formatter handed a README or a
    # JSON file rewrites it. None keeps every file, except in the ruff and ruff-format kinds,
    # which keep .py and .pyi (runner.py). Folders are always kept.
    suffixes: Optional[List[str]] = None


@dataclass
class Config:
    """The whole stage list. `commands` maps a name to the start of a command line: a stage
    writes `@py` where the project's Python goes."""

    version: int
    project: str
    placement: str
    base_ref: str
    commands: Dict[str, List[str]] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)
    env_remove: List[str] = field(default_factory=list)
    protected: List[str] = field(default_factory=list)
    venvs: List[str] = field(default_factory=list)
    import_check: Optional[Dict[str, str]] = None  # {"cwd": ..., "module": ...}
    baseline: Optional[str] = None
    stages: List[Stage] = field(default_factory=list)


# --- checking the file -------------------------------------------------------------------------

# A check takes a value from the file and the name to use in a message. It returns the value in
# the form the dataclass wants, or raises ConfigError.
_Check = Callable[[Any, str], Any]


def _object(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be an object, got {type(value).__name__}")
    return value


def _str(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{label} must be a string, got {type(value).__name__}")
    return value


def _opt_str(value: Any, label: str) -> Optional[str]:
    return None if value is None else _str(value, label)


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{label} must be true or false, got {type(value).__name__}")
    return value


def _int(value: Any, label: str) -> int:
    # bool is an int in Python, but `"timeout": true` is a mistake, not one second.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{label} must be an integer, got {type(value).__name__}")
    return value


def _str_list(value: Any, label: str) -> List[str]:
    if not isinstance(value, list):
        raise ConfigError(f"{label} must be a list, got {type(value).__name__}")
    for index, item in enumerate(value):
        _str(item, f"{label}[{index}]")
    return list(value)


def _str_dict(value: Any, label: str) -> Dict[str, str]:
    obj = _object(value, label)
    for key, item in obj.items():
        _str(item, f"{label}.{key}")
    return dict(obj)


def _choice(choices: Sequence[str]) -> _Check:
    def check(value: Any, label: str) -> str:
        if not isinstance(value, str) or value not in choices:
            raise ConfigError(f"{label} must be one of {', '.join(choices)}, got {value!r}")
        return value

    return check


# A stage name goes into ERROR lines and into the names of log and cache files, so it is not free
# text. fullmatch anchors at the very end; "$" would also match before a trailing newline.
_STAGE_NAME = re.compile(r"[a-z][a-z0-9-]*")


def _stage_name(value: Any, label: str) -> str:
    name = _str(value, label)
    if not _STAGE_NAME.fullmatch(name):
        raise ConfigError(
            f"{label} must be lowercase letters, digits and hyphens, starting with a letter "
            f"(like 'fix-lint'), got {name!r}"
        )
    return name


def _profiles(value: Any, label: str) -> List[str]:
    """Profile names follow the rule of stage names: the runner puts one into a folder name."""
    profiles = _str_list(value, label)
    if not profiles:
        raise ConfigError(f"{label} must not be empty: a stage with no profile never runs")
    for index, profile in enumerate(profiles):
        _stage_name(profile, f"{label}[{index}]")
    return profiles


def _suffixes(value: Any, label: str) -> Optional[List[str]]:
    if value is None:
        return None
    suffixes = _str_list(value, label)
    # An empty list or an empty ending would keep no file, or every one, without a word.
    if not suffixes or not all(suffixes):
        raise ConfigError(f"{label} must be a list of file name endings like '.py', got {value!r}")
    return suffixes


def _timeout(value: Any, label: str) -> int:
    seconds = _int(value, label)
    if seconds <= 0:
        raise ConfigError(f"{label} must be a positive number of seconds, got {seconds}")
    return seconds


def _version(value: Any, label: str) -> int:
    version = _int(value, label)
    if version != 1:
        raise ConfigError(f"{label} must be 1, got {version}")
    return version


def _commands(value: Any, label: str) -> Dict[str, List[str]]:
    commands = _object(value, label)
    for name in commands:
        if "@" + name in _BUILTIN_TOKENS:
            raise ConfigError(f"{label}.{name} cannot be a command name: @{name} is built in")
    checked = {name: _str_list(argv, f"{label}.{name}") for name, argv in commands.items()}
    for name, argv in checked.items():
        if not argv:
            raise ConfigError(f"{label}.{name} must not be empty: it needs at least a program")
    return checked


def _reject_unknown_keys(obj: Dict[str, Any], known: Sequence[str]) -> None:
    for key in obj:
        if key not in known and not key.startswith("_"):
            raise ConfigError(f"unknown key {key!r} (known keys: {', '.join(known)})")


def _build(
    obj: Dict[str, Any], fields: Dict[str, _Check], required: Sequence[str]
) -> Dict[str, Any]:
    """Check obj against a table of fields. Returns the keyword arguments for the dataclass: a
    field the file leaves out is left out here too, so its default comes from the dataclass."""
    _reject_unknown_keys(obj, list(fields))
    for key in required:
        if key not in obj:
            raise ConfigError(f"missing required key {key!r}")
    return {key: check(obj[key], key) for key, check in fields.items() if key in obj}


def _import_check(value: Any, label: str) -> Optional[Dict[str, str]]:
    if value is None:
        return None
    obj = _object(value, label)
    try:
        return _build(obj, {"cwd": _str, "module": _str}, ("cwd", "module"))
    except ConfigError as exc:
        raise ConfigError(f"{label}: {exc}") from None


def _stage(raw: Any, index: int) -> Stage:
    where = f"stages[{index}]"
    name = raw.get("name") if isinstance(raw, dict) else None
    # Only a valid name is put in front of the message: the name check shows a bad one itself.
    if isinstance(name, str) and _STAGE_NAME.fullmatch(name):
        where += f" ({name})"
    try:
        stage = Stage(**_build(_object(raw, "stage"), _STAGE_FIELDS, ("name", "kind", "profiles")))
        # A tool stage with no command would start nothing and could never fail. Weakening reads
        # the diff itself.
        if stage.kind != "weakening" and not stage.cmd:
            raise ConfigError(f"cmd must not be empty: a {stage.kind} stage runs a command")
        return stage
    except ConfigError as exc:
        raise ConfigError(f"{where}: {exc}") from None


def _stages(value: Any, label: str) -> List[Stage]:
    if not isinstance(value, list):
        raise ConfigError(f"{label} must be a list, got {type(value).__name__}")
    stages = [_stage(item, index) for index, item in enumerate(value)]
    first_seen: Dict[str, int] = {}
    for index, stage in enumerate(stages):
        if stage.name in first_seen:
            raise ConfigError(
                f"stage name {stage.name!r} is used twice "
                f"(stages[{first_seen[stage.name]}] and stages[{index}])"
            )
        first_seen[stage.name] = index
    return stages


_STAGE_FIELDS: Dict[str, _Check] = {
    "name": _stage_name,
    "kind": _choice(KINDS),
    "profiles": _profiles,
    "cmd": _str_list,
    "cwd": _str,
    "scope": _choice(SCOPES),
    "compare": _bool,
    "fix_hint": _str,
    "timeout": _timeout,
    "env": _str_dict,
    "junit": _opt_str,
    "ruff_rules": _opt_str,
    "allow_skip": _str_list,
    "suffixes": _suffixes,
}

_CONFIG_FIELDS: Dict[str, _Check] = {
    "version": _version,
    "project": _str,
    "placement": _choice(PLACEMENTS),
    "base_ref": _str,
    "commands": _commands,
    "env": _str_dict,
    "env_remove": _str_list,
    "protected": _str_list,
    "venvs": _str_list,
    "import_check": _import_check,
    "baseline": _opt_str,
    "stages": _stages,
}
_CONFIG_REQUIRED = ("version", "project", "placement", "base_ref", "stages")


def _read_json(path: Path) -> Any:
    # The encoding is named because the default follows the locale, and a git hook can run under
    # the C locale, where Korean text in a fix_hint would not decode.
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read: {exc.strerror or exc}") from None
    except ValueError as exc:  # not UTF-8, or not JSON
        raise ConfigError(f"not valid JSON: {exc}") from None


def load_config(path: Path) -> Config:
    """Read and check the stage list at `path`.

    Raises ConfigError, with the file name in its message, when the file cannot be read, is not
    JSON, or does not follow the schema.
    """
    path = Path(path)
    try:
        obj = _object(_read_json(path), "the stage list")
        return Config(**_build(obj, _CONFIG_FIELDS, _CONFIG_REQUIRED))
    except ConfigError as exc:
        raise ConfigError(f"{path}: {exc}") from None


def stages_for(config: Config, profile: str) -> List[Stage]:
    """The stages that run in `profile`, in the order of the file. A profile no stage names gives
    an empty list: whether that is a mistake is for the caller to say."""
    return [stage for stage in config.stages if profile in stage.profiles]


# --- expanding a command template --------------------------------------------------------------

_FORMATTER = string.Formatter()


def substitute(text: str, variables: Dict[str, str]) -> str:
    """Replace each {name} in `text` with variables[name]. {{ and }} stand for a literal brace.

    expand uses this for every command element. The runner uses it for the other strings that
    may hold variables, such as the values of `env`.

    Only a plain name is a variable. A name that `variables` does not have raises ConfigError, and
    so does anything str.format would read as more ({0}, {}, {a.b}, {a[0]}, {a!r}, {a:>9}) and a
    brace that is left open. In a file that people edit, those are mistakes to point at.
    """
    parts: List[str] = []
    try:
        for literal, name, spec, conversion in _FORMATTER.parse(text):
            parts.append(literal)
            if name is None:
                continue
            if name not in variables:
                known = ", ".join(sorted(variables)) or "none"
                raise ConfigError(f"unknown variable {{{name}}} in {text!r} (variables: {known})")
            if spec or conversion:
                raise ConfigError(
                    f"{{{name}}} in {text!r} cannot have a format spec or a conversion"
                )
            parts.append(variables[name])
    except ValueError as exc:
        raise ConfigError(
            f"{text!r} has a brace that is not part of a {{name}} ({exc}); "
            "write {{ or }} for a literal brace"
        ) from None
    return "".join(parts)


def _live(variables: Dict[str, str]) -> Path:
    if "live" not in variables:
        raise ConfigError("a relative path needs the variable {live}, which is not set")
    return Path(variables["live"])


def _is_relative_path(text: str) -> bool:
    """True for "server/.venv/bin/python". False for "uv", a bare name that is looked up on PATH,
    and for an absolute path."""
    return ("/" in text or os.sep in text) and not os.path.isabs(text)


def _command(name: str, config: Config, variables: Dict[str, str]) -> List[str]:
    if name not in config.commands:
        known = ", ".join(sorted(config.commands)) or "none"
        raise ConfigError(f"unknown command @{name} (commands: {known})")
    argv = [substitute(part, variables) for part in config.commands[name]]
    # Only the program is made absolute. Making `-m` or `tests/contract` absolute would break the
    # command, and `uv run --locked python` has to stay a name that PATH finds.
    if argv and _is_relative_path(argv[0]):
        argv[0] = str(_live(variables) / argv[0])
    return argv


def _rules_from_file(stage: Stage, variables: Dict[str, str]) -> List[str]:
    if not stage.ruff_rules:
        raise ConfigError("@ruff_overrides needs the stage to set ruff_rules")
    rules_path = Path(substitute(stage.ruff_rules, variables))
    if not rules_path.is_absolute():
        rules_path = _live(variables) / rules_path
    try:
        return ruff_overrides(_read_json(rules_path))
    except ConfigError as exc:
        raise ConfigError(f"{rules_path}: {exc}") from None


def expand(stage: Stage, config: Config, variables: Dict[str, str], paths: List[str]) -> List[str]:
    """Turn `stage.cmd` into the argument list to start. Each element of the template is one of:

    - `@paths`: the elements of `paths`, as they are.
    - `@paths_or_dot`: the same, or "." when `paths` is empty.
    - `@ruff_overrides`: the `--config` arguments for the Ruff rule set in `stage.ruff_rules`.
      That path gets the same {variable} replacement as a command, and a relative result is
      relative to variables["live"].
    - `@name`: the command `config.commands[name]`. Its elements get {variable} replacement. The
      first one is made an absolute path under variables["live"] when it is a relative path with
      a separator in it ("server/.venv/bin/python"); a bare name such as "uv" is left alone.
    - anything else: the element itself, with {variable} replacement.

    `variables` holds live, repo, cwd, checks_dir, run_dir and cache_dir. The list that comes back
    is new each time, and nothing that was passed in is changed.

    Raises ConfigError for an unknown @name or {variable}, a brace that is not a variable, and a
    rule set that cannot be read.
    """
    argv: List[str] = []
    try:
        for token in stage.cmd:
            if token == _PATHS:
                argv.extend(paths)
            elif token == _PATHS_OR_DOT:
                argv.extend(paths or ["."])
            elif token == _RUFF_OVERRIDES:
                argv.extend(_rules_from_file(stage, variables))
            elif token.startswith("@"):
                argv.extend(_command(token[1:], config, variables))
            else:
                argv.append(substitute(token, variables))
    except ConfigError as exc:
        raise ConfigError(f"stage {stage.name!r}: {exc}") from None
    return argv


# --- Ruff rule set -> command line -------------------------------------------------------------

_RULE_KEYS = (
    "select",
    "ignore",
    "project_ignore",
    "banned_api",
    "per_file_ignores",
    "allowed_confusables",
    "ban_relative_imports",
)


def _quote(text: str) -> str:
    """A TOML basic string. JSON quoting is TOML quoting, with one exception: TOML forbids a raw
    DEL character, which JSON leaves as it is, and Ruff then refuses the whole option."""
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")


def _array(items: Sequence[str]) -> str:
    return "[" + ", ".join(_quote(item) for item in items) + "]"


def _table(entries: Sequence[Tuple[str, str]]) -> str:
    """An inline table. An entry is a key and its value, which is already written as TOML."""
    return "{" + ", ".join(f"{_quote(key)} = {value}" for key, value in entries) + "}"


def ruff_overrides(rules: Dict[str, Any]) -> List[str]:
    """Turn a Ruff rule set (the parsed ruff-rules.json) into `--config "key = value"` arguments.

    Ruff reads each option as a TOML `key = value` pair, so the rules travel on the command line
    and no configuration file of the project is involved. The pairs come in a fixed order, ignore,
    select, banned_api, per_file_ignores, allowed_confusables, ban_relative_imports, whatever the
    order of the keys in `rules`.

    The ignore and per-file-ignores pairs are always there, `[]` and `{}` when the rule set has
    none: where the kit sets nothing, Ruff applies the project's own lists, and a project file
    that ignores F401 for app/x.py would silence it under the kit. The project's ignore and
    extend-ignore need no pair of their own, the kit's select starts the selection afresh. Its
    extend-per-file-ignores cannot be taken away here: Ruff 0.16.8 adds an override of that key
    to the project's table instead of replacing it, so the weakening stage watches that key, and
    `extend`, which pulls in another file's (toolconfig.CONFIG_KEYS). Any other key that is
    absent or empty gives no pair.

        select, ignore        lists of rule codes
        project_ignore        rule code -> why the team switches it off. Only the codes are
                              used: they go to the end of the ignore list.
        banned_api            module -> message (rule TID251)
        per_file_ignores      glob -> list of rule codes
        allowed_confusables   list of characters
        ban_relative_imports  "all" or "parents"

    A key that starts with "_" (`_reasons`) is a note and is skipped. Any other key raises
    ConfigError, as does a value of the wrong type.

    The ignore pair comes before the select pair, and per-file-ignores after it, on purpose; the
    comment where they are added says why.
    """
    obj = _object(rules, "the Ruff rule set")
    _reject_unknown_keys(obj, _RULE_KEYS)
    select = _str_list(obj.get("select", []), "select")
    ignore = _str_list(obj.get("ignore", []), "ignore")
    project_ignore = _str_dict(obj.get("project_ignore", {}), "project_ignore")
    banned_api = _str_dict(obj.get("banned_api", {}), "banned_api")
    per_file_object = _object(obj.get("per_file_ignores", {}), "per_file_ignores")
    per_file_ignores = {
        glob: _str_list(codes, f"per_file_ignores[{glob!r}]")
        for glob, codes in per_file_object.items()
    }
    confusables = _str_list(obj.get("allowed_confusables", []), "allowed_confusables")
    ban_relative_imports = _str(obj.get("ban_relative_imports", ""), "ban_relative_imports")

    argv: List[str] = []

    def add(option: str, value: str) -> None:
        argv.extend(["--config", f"{option} = {value}"])

    # ORDER MATTERS: lint.ignore must come before lint.select.
    # Ruff 0.16.8, verified: first --config wins for rule selection. So a lint.select that comes
    # first resets the selection and silently drops a lint.ignore written after it: E501 and F401
    # stay reported although the project ignores them. Do not reorder these two pairs.
    add("lint.ignore", _array(ignore + list(project_ignore)))
    if select:
        add("lint.select", _array(select))
    if banned_api:
        add(
            "lint.flake8-tidy-imports.banned-api",
            _table([(module, "{msg = " + _quote(msg) + "}") for module, msg in banned_api.items()]),
        )
    # ORDER MATTERS too: lint.select must not be the last pair. Ruff 0.16.8, verified: it reads the
    # --config pairs after the project's own settings, the last pair first, and a project that
    # writes `select = []` next to an ignore has that ignore carried over to the next thing it
    # reads. Were that lint.select, the project's F401 ignore would hold. per-file-ignores selects
    # no rule, is always there, and so always takes the carried-over ignore instead.
    add(
        "lint.per-file-ignores",
        _table([(glob, _array(codes)) for glob, codes in per_file_ignores.items()]),
    )
    if confusables:
        add("lint.allowed-confusables", _array(confusables))
    if ban_relative_imports:
        add("lint.flake8-tidy-imports.ban-relative-imports", _quote(ban_relative_imports))
    return argv
