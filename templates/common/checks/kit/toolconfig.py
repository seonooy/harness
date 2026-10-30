from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

# The tool config files a project keeps, and the lines in them that narrow what a check looks at:
# a file excluded there passes every check without a suppression in sight. weakening.py reports
# such a line as config-weakening when a change added it.
#
# A line narrows a check when it sets one of CONFIG_KEYS in one of CONFIG_FILES (by name, in any
# folder):
#   any file   it starts with a listed key and its "=" or ":", maybe quoted and maybe after a
#              dotted table name: lint.extend-ignore = ..., "exclude" = ..., collect_ignore += ...
#   TOML       a [table] or [[table]] header whose last dotted key is listed; a line inside such a
#              table; a dotted key with a listed part (extend-per-file-ignores."x.py" = ...); a
#              line inside a value that spans lines (an array, a multi-line string) that a listed
#              key opened, so an entry added to an existing list counts
#   INI        a continuation line (it starts with a space or a tab) of a listed key's value
#   conftest   collect_ignore or collect_ignore_glob with .append(, .extend(, .insert( or +=, or
#              a line inside a list that a listed name opened
# A line that narrows only by where it stands is reported with the listed key that opened its table,
# list or value, so that weakening.py can tell the same words apart under two keys ("tests" in
# testpaths, "tests" in extend-exclude). A line that sets a listed key itself needs no such key.
# An added line is no new entry when the hunk removed the same entry written another way (a comma
# came after it, it was indented otherwise, a comment was added): entry_form is what compares.
# Blank lines, comments and lines that only close brackets add no entry. Brackets inside quoted
# strings and comments are not counted. Not read: an inline table (lint = { extend-exclude = [...]
# }), other tools' keys (deptry's ignore, coverage's omit), Ruff's include, values computed in
# Python, and files not in the list. Ruff merges the file that `extend` names into the settings,
# and a file of any name can hold extend-per-file-ignores: only the `extend` line is read, not
# that file.

CONFIG_FILES = frozenset(
    (
        "pyproject.toml",
        "ruff.toml",
        ".ruff.toml",
        "pytest.ini",
        "setup.cfg",
        "tox.ini",
        "conftest.py",
    )
)
CONFIG_KEYS = (
    # Ruff
    "extend",  # merges another file's settings in, whatever the file is called
    "exclude",
    "extend-exclude",
    "extend-per-file-ignores",
    "extend-ignore",
    # pytest
    "addopts",
    "deselect",
    "testpaths",
    "norecursedirs",
    "python_files",
    "python_classes",
    "python_functions",
    "collect_ignore",
    "collect_ignore_glob",
    # deptry
    "extend_exclude",
    "per_rule_ignores",
)
_LISTED = frozenset(CONFIG_KEYS)
_TOML = frozenset(("pyproject.toml", "ruff.toml", ".ruff.toml"))
_INI = frozenset(("pytest.ini", "setup.cfg", "tox.ini"))

# A key at the start of a line, maybe quoted and maybe after a dotted table name (lint.), then the
# "=" or ":" of an assignment in TOML, INI or Python ("+=" too). Longer keys are tried first.
_KEY_LINE = re.compile(
    r"""^\s*(?:[\w.-]+\.)?["']?(?:%s)["']?\s*(?:\+?=|:)"""
    % "|".join(map(re.escape, sorted(CONFIG_KEYS, key=len, reverse=True)))
)
_CONFTEST_CALL = re.compile(
    r"^\s*(collect_ignore(?:_glob)?)\s*(?:\.\s*(?:append|extend|insert)\s*\(|\+=)"
)
_PY_NAME = re.compile(r"\s*([A-Za-z_]\w*)")
_INI_KEY = re.compile(r"([^=:\s][^=:]*?)\s*[=:]")
# (what opens, what closes)
_TOML_BRACKETS = ("[{", "]}")
_PY_BRACKETS = ("([{", ")]}")


def sets_listed_key(line: str) -> bool:
    """Whether the line starts by setting a listed key, in any of the files."""
    return _KEY_LINE.match(line) is not None


def entry_form(name: str, line: str) -> str:
    """The line with only what the config file named `name` reads of it, so that an entry and the
    same entry written another way have one form: another indent, other spaces round the "=" or
    the brackets, a trailing comma, a comment after it.

    TOML and conftest.py: whitespace outside strings, a comment and a trailing comma are left
    out. A "#" or a space inside quotes is part of the entry. INI: only the whitespace round the
    line, for a "#" and a "," belong to a value there (norecursedirs = legacy # tests)."""
    if name in _TOML:
        return _code_form(line, '"')
    if name == "conftest.py":
        return _code_form(line, "\"'")
    return line.strip()


def narrowing_lines(name: str, lines: List[str]) -> Dict[int, str]:
    """The lines (numbered from 1) of a config file named `name` that narrow a check by where they
    stand: in a listed table, inside a listed key's value, as its continuation. Each comes with
    the listed key that opened that table, value or continuation. A line that sets a listed key
    itself may be among them (a table header names its key): sets_listed_key is what tells."""
    reader = _READERS.get(name)
    return reader(lines) if reader is not None else {}


# --- a line at a time ----------------------------------------------------------------------------


@dataclass
class _Open:
    """What a line leaves open for the next: brackets, and the multi-line string it ends inside
    (the quotes that close it)."""

    depth: int = 0
    string: Optional[str] = None

    def spans(self) -> bool:
        return self.depth > 0 or self.string is not None


def _string_end(text: str, start: int, escapes: bool) -> int:
    """Where the one-line string that starts at `start` ends: just past its closing quote, or the
    end of the line."""
    quote, i = text[start], start + 1
    while i < len(text):
        if escapes and text[i] == "\\":
            i += 2
        elif text[i] == quote:
            return i + 1
        else:
            i += 1
    return len(text)


def _scan(text: str, state: _Open, brackets: Tuple[str, str], escaped: str) -> None:
    """Move `state` over one line. `escaped` names the quotes whose strings take backslash
    escapes. A comment ends the line."""
    opening, closing = brackets
    i = 0
    while i < len(text):
        char = text[i]
        if state.string is not None:
            if char == "\\" and state.string[0] in escaped:
                i += 2
            elif text.startswith(state.string, i):
                i += len(state.string)
                state.string = None
            else:
                i += 1
        elif char == "#":
            return
        elif char in "\"'" and text.startswith(char * 3, i):
            state.string = char * 3
            i += 3
        elif char in "\"'":
            i = _string_end(text, i, char in escaped)
        else:
            if char in opening:
                state.depth += 1
            elif char in closing and state.depth:
                state.depth -= 1
            i += 1


def _code_form(text: str, escaped: str) -> str:
    """`text` without the whitespace outside its strings, without a comment and without a
    trailing comma. `escaped` names the quotes whose strings take backslash escapes. A line
    inside a multi-line string is read as code: this sees no line but its own."""
    kept: List[str] = []
    i = 0
    while i < len(text) and text[i] != "#":
        if text[i] in "\"'":
            end = _string_end(text, i, text[i] in escaped)
            kept.append(text[i:end])
            i = end
        else:
            if not text[i].isspace():
                kept.append(text[i])
            i += 1
    return "".join(kept).rstrip(",")


def _adds_entry(text: str, string: Optional[str]) -> bool:
    """Whether a line inside a value holds part of it: not blank, not only a comment, not only
    what closes the value."""
    if string is not None:  # inside a multi-line string, every word is part of the value
        return bool(text.replace(string, "").strip(" \t,)]}"))
    code = text.split("#", 1)[0]
    return bool(code.strip(" \t,)]}"))


# --- TOML ----------------------------------------------------------------------------------------


def _toml_key(text: str) -> Tuple[List[str], int]:
    """The parts of the dotted key that `text` starts with, quotes taken off, and where it ends:
    at the "=" of a key line or the "]" of a header."""
    parts: List[str] = []
    part, i = "", 0
    while i < len(text) and text[i] not in "=]":
        char = text[i]
        if char in "\"'":
            end = _string_end(text, i, char == '"')
            part += text[i + 1 : end - 1]
            i = end
        elif char == ".":
            parts.append(part.strip())
            part, i = "", i + 1
        else:
            part, i = part + char, i + 1
    parts.append(part.strip())
    return parts, i


def _toml(lines: List[str]) -> Dict[int, str]:
    found: Dict[int, str] = {}
    table: Optional[str] = None  # the listed key the header of the current table names last
    value = _Open()  # a value that spans lines
    value_key: Optional[str] = None  # and the listed key that opened it
    for number, text in enumerate(lines, 1):
        if value.spans():
            if value_key is not None and _adds_entry(text, value.string):
                found[number] = value_key
            _scan(text, value, _TOML_BRACKETS, '"')
            continue
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("["):  # [table] or [[array.of.tables]]
            parts, _ = _toml_key(stripped.lstrip("["))
            table = parts[-1] if parts[-1] in _LISTED else None
            if table is not None:
                found[number] = table
            continue
        parts, end = _toml_key(text)
        # A listed part of the line's own key, else the table the line stands in.
        value_key = next((part for part in parts if part in _LISTED), table)
        if value_key is not None:
            found[number] = value_key
        _scan(text[end + 1 :], value, _TOML_BRACKETS, '"')
    return found


# --- INI -----------------------------------------------------------------------------------------


def _ini(lines: List[str]) -> Dict[int, str]:
    found: Dict[int, str] = {}
    key: Optional[str] = None  # the key whose value an indented line continues
    for number, text in enumerate(lines, 1):
        stripped = text.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue  # neither a blank line nor a comment ends a value
        if text[0] in " \t":
            if key is not None and key in _LISTED:
                found[number] = key
        elif stripped.startswith("["):
            key = None
        else:
            match = _INI_KEY.match(text)
            key = match.group(1).strip() if match else None
    return found


# --- conftest.py ---------------------------------------------------------------------------------


def _conftest(lines: List[str]) -> Dict[int, str]:
    found: Dict[int, str] = {}
    value = _Open()
    value_key: Optional[str] = None  # the listed name that opened the value
    for number, text in enumerate(lines, 1):
        if value.spans():
            if value_key is not None and _adds_entry(text, value.string):
                found[number] = value_key
            _scan(text, value, _PY_BRACKETS, "\"'")
            continue
        call = _CONFTEST_CALL.match(text)
        if call is not None:
            found[number] = call.group(1)
        name = _PY_NAME.match(text)
        value_key = name.group(1) if name is not None and name.group(1) in _LISTED else None
        _scan(text, value, _PY_BRACKETS, "\"'")
    return found


_READERS: Dict[str, Callable[[List[str]], Dict[int, str]]] = {
    **{name: _toml for name in _TOML},
    **{name: _ini for name in _INI},
    "conftest.py": _conftest,
}
