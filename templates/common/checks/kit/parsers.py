from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Reading what the check tools print.
#
# The runner starts a tool and hands its exit code and output to parse(). parse says one of three
# things: "ok", "violations" (with the list of them) or "error", for output that cannot be trusted.
# The runner turns "error" into an incomplete check, which keeps the whole run from passing. So
# everything that is not positively understood has to land there: an exit code the tool is not
# known to use, output in another format, counts that contradict each other. This module must
# never call a run "ok" or "violations" on a guess.
#
# A violation is compared between two trees (the work tree and an export of the merge-base), so it
# is identified by its fingerprint: path, code, message and the text of the source line. The line
# number is kept for display only, because it moves whenever someone edits above it.
#
# Every path is relative to ctx.tree and written with "/". A file outside the tree keeps its
# absolute path. On macOS names are made NFC, the form git lists them in.
#
# What each tool prints was captured once into tests/fixtures/tools (the README next to it has the
# findings). The formats below are those captures, not guesses; the notes above each parser say
# which facts it leans on.

OK = "ok"
VIOLATIONS = "violations"
ERROR = "error"


# A message can name a line of its own: Ruff F811 says "from line 1", mypy no-redef says "already
# defined on line 1". That number moves with every edit above it, so it must not be part of a
# fingerprint, or an edit above a teammate's old violation would make it look new.
_LINE_MENTION = re.compile(r"\bline \d+\b")
_LINES_MENTION = re.compile(r"\blines \d+(?:-\d+)?\b")


def normalize(message: str) -> str:
    """Trim the ends, shrink each run of whitespace to one space, and mask the line numbers the
    message mentions: "line 12" becomes "line N" and "lines 3-5" becomes "lines N".

    This is what a fingerprint holds of a message. The message of a Violation itself stays as the
    tool wrote it, for the person who reads it."""
    return _LINES_MENTION.sub("lines N", _LINE_MENTION.sub("line N", " ".join(message.split())))


@dataclass
class Violation:
    """One thing a tool flagged. `line` is for display; it is not part of the fingerprint."""

    stage: str
    path: str
    code: str
    message: str
    text: str
    line: Optional[int] = None

    def fingerprint(self) -> Tuple[str, str, str, str]:
        """What makes two violations the same one in two trees. Compare them as multisets: a
        line can be flagged twice in the same words."""
        return (self.path, self.code, normalize(self.message), self.text.strip())


@dataclass
class TestCounts:
    """What a junit file says. `skip_messages` holds the reason of every skip, allowed or not."""

    tests: int
    failures: int
    errors: int
    skipped: int
    skip_messages: List[str]


@dataclass
class ParseResult:
    """`status` is "ok", "violations" or "error". `violations` is empty unless the status is
    "violations". `detail` says what went wrong for "error" and is empty otherwise. `tests` is
    set by the pytest-junit parser once it has read the junit file."""

    status: str
    violations: List[Violation]
    detail: str
    tests: Optional[TestCounts] = None


@dataclass
class ParseContext:
    """Where an output came from. `tree` is the folder paths are made relative to. `cwd` is the
    folder the tool ran in; mypy prints its paths relative to it. `junit_path` is the file pytest
    wrote. `allow_skip` holds regular expressions; a skip is allowed when its reason matches one
    of them anywhere (re.search)."""

    stage: str
    tree: Path
    cwd: Path
    junit_path: Optional[Path] = None
    allow_skip: List[str] = field(default_factory=list)


# --- helpers ------------------------------------------------------------------------------------


class _Unparseable(Exception):
    """Output that cannot be trusted. parse turns it into an "error" result with this message."""


def _ok(tests: Optional[TestCounts] = None) -> ParseResult:
    return ParseResult(OK, [], "", tests)


def _violations(found: List[Violation], tests: Optional[TestCounts] = None) -> ParseResult:
    return ParseResult(VIOLATIONS, found, "", tests)


def _error(detail: str, tests: Optional[TestCounts] = None) -> ParseResult:
    return ParseResult(ERROR, [], detail, tests)


def _cannot_read(tool: str, why: str) -> _Unparseable:
    return _Unparseable(f"{tool} 출력을 해석하지 못했다: {why}")


_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def _lines(text: str) -> List[str]:
    """Split the way a tool counts lines: only \\n, \\r\\n and \\r end one. str.splitlines() also
    splits at a form feed and at U+2028, which would shift every row after them."""
    return _LINE_BREAK.split(text)


# Colour codes, as a tool prints them when the environment forces colour (FORCE_COLOR): a CSI
# sequence, a character-set switch such as ESC ( B, or another two-byte escape.
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\([A-Za-z0-9]|[@-Z\\-_])")


def _plain(text: str) -> str:
    """The text without colour codes, which can land in the middle of the lines parsed below."""
    return _ANSI.sub("", text)


def _tail(*texts: str) -> str:
    """The end of the first text that has any words in it, on one line: its last two non-empty
    lines. A tool states its reason last, and this is what follows "exit 2" in an error."""
    for text in texts:
        kept = [line.strip() for line in _lines(_plain(text)) if line.strip()]
        if kept:
            tail = " / ".join(kept[-2:])
            return tail if len(tail) <= 300 else "…" + tail[-300:]
    return ""


def _with_cause(message: str, cause: str) -> str:
    return f"{message}: {cause}" if cause else message


def _bad_exit(
    tool: str, exit_code: int, stderr: str, stdout: str, meaning: str = ""
) -> ParseResult:
    """An exit code the tool is not known to use for "clean" or "violations": its output, whatever
    it looks like, is not to be trusted."""
    what = f"{tool} 종료 코드 {exit_code}" + (f" ({meaning})" if meaning else "")
    return _error(_with_cause(what, _tail(stderr, stdout)))


def _number(digits: str) -> Optional[int]:
    """A count or a line number out of a tool's output. More than nine digits is not one: int()
    would take it (Python 3.11 and later refuse past 4300 digits) but nothing real is that big."""
    return int(digits) if len(digits) <= 9 else None


def _nfc(path: str) -> str:
    # git on macOS lists names precomposed (NFC), while the file system and the tools can hand
    # out the decomposed form (NFD). Elsewhere git lists a name as it was committed.
    return unicodedata.normalize("NFC", path) if sys.platform == "darwin" else path


def _tree_path(raw: str, base: Path, tree: Path) -> str:
    """`raw`, a path as a tool printed it, as the path a violation carries.

    A relative `raw` is relative to `base`, the folder the tool ran in. The result is relative to
    `tree`, with "/" separators. A file outside the tree keeps its absolute path: "../.." would
    differ between the work tree and the export it is compared with, the path of a library does
    not. The tree is tried as given and with its links resolved, because a tool reports the real
    path of its folder (on macOS /private/var) where the runner may hold the linked one."""
    absolute = os.path.abspath(os.path.join(str(base), raw))
    for root in (str(tree), os.path.realpath(str(tree))):
        prefix = os.path.abspath(root).rstrip(os.sep) + os.sep
        if absolute.startswith(prefix):
            return _nfc(absolute[len(prefix) :].replace(os.sep, "/"))
    return _nfc(absolute.replace(os.sep, "/"))


class _Sources:
    """The source lines a violation's `text` comes from. Each file is read once, however many of
    its lines were flagged."""

    def __init__(self, tree: Path) -> None:
        self._tree = tree
        self._files: Dict[str, Optional[List[str]]] = {}

    def line(self, path: str, row: Optional[int]) -> str:
        """Line `row` (1-based) of `path`, stripped. "" when there is no such line or the file
        cannot be read: the text is then missing from the fingerprint, which only makes it
        coarser."""
        if row is None or row < 1:
            return ""
        lines = self._read(path)
        if lines is None or row > len(lines):
            return ""
        return lines[row - 1].strip()

    def _read(self, path: str) -> Optional[List[str]]:
        if path not in self._files:
            try:
                data = (self._tree / path).read_bytes()  # an absolute path stays as it is
            except (OSError, ValueError):  # missing, a folder, no access; ValueError: NUL in name
                self._files[path] = None
            else:
                self._files[path] = _lines(data.decode("utf-8", errors="replace"))
        return self._files[path]


def _json_list(tool: str, stdout: str) -> List[Any]:
    try:
        data = json.loads(stdout)
    except (ValueError, RecursionError):  # RecursionError: "[[[[[..." nested too deep
        raise _cannot_read(tool, "JSON이 아니다") from None
    if not isinstance(data, list):
        raise _cannot_read(tool, "JSON 목록이 아니다")
    return data


def _valid_row(value: object) -> Optional[int]:
    """A 1-based line number a tool printed. 0 is what some tools write for "no line", and a
    negative number or a bool is not a line either."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _row(entry: Dict[str, Any]) -> Optional[int]:
    location = entry.get("location")
    return _valid_row(location.get("row") if isinstance(location, dict) else None)


# --- ruff and ruff format -----------------------------------------------------------------------

# `ruff check --output-format json` and `ruff format --check --output-format json` print a JSON
# array. Each entry has an absolute `filename` and a `location` with the 1-based `row`; check
# entries also have `code` and `message`. A syntax error is an ordinary entry. Exit codes: 0 clean,
# 1 something found, 2 error (bad config, unknown rule, and for format also a syntax error).
# Ruff 0.16.8 prints no "Would reformat: <path>" line in any output format, so the format stage
# must run with --output-format json, and the default and concise outputs are errors here.


def _ruff_entries(tool: str, stdout: str) -> List[Dict[str, Any]]:
    """The entries of the JSON list. Exit 1 says something was found, so an empty list or an entry
    that cannot be placed in a file is not believed."""
    entries = _json_list(tool, stdout)
    if not entries:
        raise _cannot_read(tool, "종료 코드 1인데 진단이 하나도 없다")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
            raise _cannot_read(tool, "항목에 filename이 없다")
        if not entry["filename"]:
            raise _cannot_read(tool, "항목의 filename이 비었다")
    return entries


def _parse_ruff(exit_code: int, stdout: str, stderr: str, ctx: ParseContext) -> ParseResult:
    if exit_code == 0:
        return _ok()
    if exit_code != 1:
        return _bad_exit("ruff", exit_code, stderr, stdout)
    sources = _Sources(ctx.tree)
    found = []
    for entry in _ruff_entries("ruff", stdout):
        message = entry.get("message")
        if not isinstance(message, str):
            raise _cannot_read("ruff", "항목에 message가 없다")
        code = entry.get("code")
        path = _tree_path(entry["filename"], ctx.cwd, ctx.tree)
        row = _row(entry)
        found.append(
            Violation(
                ctx.stage,
                path,
                code if isinstance(code, str) and code else "ruff",
                message,
                sources.line(path, row),
                row,
            )
        )
    return _violations(found)


def _parse_ruff_format(exit_code: int, stdout: str, stderr: str, ctx: ParseContext) -> ParseResult:
    if exit_code == 0:
        return _ok()
    if exit_code != 1:
        return _bad_exit("ruff format", exit_code, stderr, stdout)
    # One violation per file. What would change is not in the fingerprint: the file is either
    # formatted or it is not, and the text of its first changed line says nothing more.
    found = [
        Violation(
            ctx.stage,
            _tree_path(entry["filename"], ctx.cwd, ctx.tree),
            "format",
            "needs formatting",
            "",
            _row(entry),
        )
        for entry in _ruff_entries("ruff format", stdout)
    ]
    return _violations(found)


# --- mypy ---------------------------------------------------------------------------------------

# One error is `path:line: error: message  [code]`, with two spaces before the code. --show-column-
# numbers adds `:col` and --show-error-end adds `:col:endline:endcol`. The code is anchored at the
# end of the line because a message can hold brackets itself ("type: ignore[no-any-return]"). A
# few errors have no code, and a blocking one can have no line. `note:` lines are not errors and
# can sit apart from the error they belong to. The last line is `Found N errors in M files (...)`
# or `Success: ...`. Exit codes: 0 clean, 1 errors, 2 mypy could not do its job (bad option,
# unloadable plugin, a syntax error in a checked file: the stdout of that last one looks like a
# normal run, with `[syntax]` errors).
#
# The count in the summary must equal the number of error lines read. A line that fails to match
# (a path with a colon in it, a format change) would otherwise be a violation that nobody sees.

_MYPY_ERROR = re.compile(r"(?P<path>[^:]+):(?:(?P<line>\d+)(?::\d+)*:)? error: (?P<rest>.*)")
_MYPY_CODE = re.compile(r"(?P<message>.*?)  \[(?P<code>[\w.-]+)\]")
_MYPY_SUMMARY = re.compile(r"Found (?P<count>\d+) errors? in \d+ files?\b.*")


def _parse_mypy(exit_code: int, stdout: str, stderr: str, ctx: ParseContext) -> ParseResult:
    if exit_code == 0:
        return _ok()
    if exit_code != 1:
        return _bad_exit("mypy", exit_code, stderr, stdout)
    sources = _Sources(ctx.tree)
    found = []
    reported: Optional[int] = None
    for text in _lines(_plain(stdout)):
        error = _MYPY_ERROR.fullmatch(text)
        if error is None:
            summary = _MYPY_SUMMARY.fullmatch(text)
            if summary is not None:
                reported = _number(summary.group("count"))
                if reported is None:
                    raise _cannot_read("mypy", "요약의 오류 개수를 읽지 못했다")
            continue
        rest = error.group("rest")
        with_code = _MYPY_CODE.fullmatch(rest)
        message, code = (
            (with_code.group("message"), with_code.group("code")) if with_code else (rest, "mypy")
        )
        path = _tree_path(error.group("path"), ctx.cwd, ctx.tree)
        digits = error.group("line")
        row = _valid_row(_number(digits)) if digits else None
        found.append(Violation(ctx.stage, path, code, message, sources.line(path, row), row))
    if not found:
        raise _cannot_read("mypy", "종료 코드 1인데 오류 줄을 하나도 읽지 못했다")
    if reported is not None and reported != len(found):
        raise _cannot_read("mypy", f"요약은 오류 {reported}개인데 {len(found)}줄을 읽었다")
    return _violations(found)


# --- import-linter ------------------------------------------------------------------------------

# lint-imports 2.15, as captured. Exit codes: 0 all contracts kept; 1 a contract is broken, and
# also every configuration or usage error (a missing config, module or layer, an unknown contract
# type). Only a broken contract prints a "Broken contracts" heading, so exit 1 without that heading
# is an error and never "violations".
#
# Under that heading each broken contract has a block: its *name* (never its id) with a line of
# dashes of the same length under it, then paragraphs separated by blank lines:
#
#   app.engines is not allowed to import app.clients:      <- a group header, not a violation
#
#   -   app.engines.summary -> app.services.report (l.1)   <- one chain: a bullet and its hops
#       app.services.report -> app.clients.http_client (l.1)
#
#   The following modules are not listed as layers:       <- layers contract with exhaustive = True
#
#   - app.core                                             <- a module in the complaint
#
#   (Since this contract is marked as 'exhaustive', ...)   <- explanation
#
#   Move shared code down into core.                       <- broken_contract_guidance, last
#
# Chains and the "not listed" complaint can be in one block. The order of the groups in a layers
# contract changes from run to run (hash order), so the violations are an unordered collection.
#
# The text is read in paragraphs, never line by line. Without a terminal rich wraps at 80 columns,
# so a long chain is on two lines and the second one has no indent; a line-by-line reader would
# lose that chain without a word. A route that shares modules is printed as one bullet:
#
#   - app2.core.a1 (l.1)                      <- importers: the first has no "->" ...
#     & app2.core.a2 -> app2.shared (l.1)     <- ... the last of them carries the first hop
#     app2.shared -> app2.api.r1 (l.1)
#                    & app2.api.r2 (l.1)      <- more modules at the far end
#
# which is every importer times every imported module through the same middle: four chains, and
# each is a violation.
#
# What counts as a violation: each chain; each module of a "not listed as layers" complaint; and,
# only when a block gave nothing, one violation for the block, whose text is a hash of what was
# printed (line numbers and wrapping left out). The guidance is free text the project edits at
# will, so it is never a violation. A paragraph that looks like a chain or like the complaint but
# cannot be taken apart is one violation of its own, so that it is not dropped.
#
# The number of blocks must equal the "broken" count of the summary line, which catches a block
# whose heading was not recognised.

_IL_HEADING = "Broken contracts"
_IL_SUMMARY = re.compile(r"Contracts: \d+ kept, (?P<broken>\d+) broken\.")
_IL_UNLISTED = "The following modules are not listed as layers:"
_LINE_NUMBERS = re.compile(r"\(l\.[^()]*\)")
_IL_HOP = re.compile(r"(?:(?P<more>&) )?(?P<importer>\S+)(?: -> (?P<imported>\S+))?")
_IL_BULLET = re.compile(r"-\s+(?P<module>\S+)")
# An acyclic_siblings contract prints this per package with cycles, then at most five imports to cut
# and "(and N more).". That list cannot name a cycle, so the package is the violation and the list
# is left to the log: cutting some of the imports is progress, not a new violation.
_IL_CYCLES = re.compile(r"No cycles are allowed in (?P<package>\S+?)\.(?:\s|$)")
# The logo is made of box-drawing and block characters, U+2500 to U+259F.
_BOX_DRAWING = re.compile(r"[\u2500-\u259f]")


def _il_heading_index(lines: List[str]) -> Optional[int]:
    rule = "-" * len(_IL_HEADING)
    for i in range(1, len(lines) - 1):
        if (
            lines[i].strip() == _IL_HEADING
            and lines[i - 1].strip() == rule
            and lines[i + 1].strip() == rule
        ):
            return i
    return None


def _il_blocks(details: List[str]) -> List[Tuple[str, List[str]]]:
    """(contract name, lines of its block). A block starts at a name with a line of dashes as long
    as the name under it and runs to the next such pair."""
    starts = []
    for i in range(len(details) - 1):
        name = details[i].rstrip()
        if name and details[i + 1].rstrip() == "-" * len(name):
            starts.append(i)
    blocks = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(details)
        blocks.append((details[start].rstrip(), details[start + 2 : end]))
    return blocks


def _paragraphs(lines: List[str]) -> List[List[str]]:
    paragraphs: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    return paragraphs


def _il_split_chains(bullet: str) -> Optional[List[List[str]]]:
    """The chains (each a list of modules, importer first) that one bullet stands for, or None
    when it is not in a shape lint-imports is known to print. `bullet` is the whole paragraph on
    one line, without its leading "- "."""
    pieces = _LINE_NUMBERS.split(bullet)
    if pieces.pop().strip():  # words after the last "(l.N)"
        return None
    importers: List[str] = []  # the first is printed without "->", the last carries the first hop
    route: List[str] = []  # from the last importer to the first imported module
    farther: List[str] = []  # more imported modules, each printed as "& module"
    for piece in pieces:
        hop = _IL_HOP.fullmatch(piece.strip())
        if hop is None:
            return None
        more, importer, imported = (
            bool(hop.group("more")),
            hop.group("importer"),
            hop.group("imported"),
        )
        if not route:
            if more != bool(importers):
                return None
            importers.append(importer)
            if imported is not None:
                route = [importer, imported]
        elif farther or imported is None:
            if imported is not None or not more:
                return None
            farther.append(importer)
        else:
            if more or importer != route[-1]:
                return None
            route.append(imported)
    if not route:
        return None
    middle = route[1:-1]
    return [[head, *middle, tail] for head in importers for tail in [route[-1], *farther]]


def _il_chains(contract: str, bullet: str, ctx: ParseContext) -> List[Violation]:
    chains = _il_split_chains(bullet[2:])
    if chains is None:
        plain = normalize(_LINE_NUMBERS.sub("", bullet[2:]))
        importer = plain.split()[0] if plain else ctx.stage
        return [Violation(ctx.stage, importer, contract, "unreadable import chain", plain)]
    # A violation is the pair a chain breaks, not the route: lint-imports picks one route among
    # several, and which one moves when unrelated imports change. The route stays in the log.
    return [
        Violation(ctx.stage, nodes[0], contract, f"{nodes[0]} -> {nodes[-1]}", "")
        for nodes in chains
    ]


def _il_unlisted(contract: str, paragraph: List[str], ctx: ParseContext) -> List[Violation]:
    """The modules listed after "The following modules are not listed as layers:"."""
    modules = [_IL_BULLET.fullmatch(line.strip()) for line in paragraph]
    if paragraph and all(modules):
        return [
            Violation(ctx.stage, match.group("module"), contract, "not listed as a layer", "")
            for match in modules
            if match is not None
        ]
    return [
        Violation(
            ctx.stage,
            ctx.stage,
            contract,
            "modules not listed as layers could not be read",
            normalize(" ".join(paragraph)),
        )
    ]


def _unique(found: List[Violation]) -> List[Violation]:
    """Each violation once, in the order first seen: two routes of one pair are one violation."""
    seen = set()
    kept = []
    for violation in found:
        if violation.fingerprint() not in seen:
            seen.add(violation.fingerprint())
            kept.append(violation)
    return kept


def il_pair(v: Violation) -> Violation:
    """An import-linter violation as its pair. An entry written while a violation was its route
    (text "a -> b -> c" under message "a -> c") becomes the pair; any other is kept as it is."""
    route = v.text.split(" -> ")
    if len(route) > 1 and v.message == f"{route[0]} -> {route[-1]}":
        return replace(v, text="")
    return v


def il_pairs(violations: List[Violation]) -> List[Violation]:
    """Import-linter violations as pairs (il_pair), each once."""
    return _unique([il_pair(v) for v in violations])


def _il_block(contract: str, body: List[str], ctx: ParseContext) -> List[Violation]:
    found: List[Violation] = []
    expecting_modules = False
    cut_list = False  # the imports to cut that follow "No cycles are allowed in <package>."
    for paragraph in _paragraphs(body):
        text = normalize(" ".join(paragraph))
        cycles = _IL_CYCLES.match(text)
        if expecting_modules:
            expecting_modules = False
            found.extend(_il_unlisted(contract, paragraph, ctx))
        elif cycles is not None:
            package = cycles.group("package")
            found.append(Violation(ctx.stage, package, contract, f"cycles in {package}", ""))
            cut_list = True
        elif cut_list and text.startswith("- "):
            cut_list = False
        elif text == _IL_UNLISTED:
            expecting_modules = True
        elif text.startswith("- ") and " -> " in text:
            found.extend(_il_chains(contract, text, ctx))
    if expecting_modules:  # the complaint ended the block
        found.extend(_il_unlisted(contract, [], ctx))
    found = _unique(found)
    if not found:
        printed = normalize(_LINE_NUMBERS.sub("", " ".join(body)))
        digest = hashlib.sha1(printed.encode("utf-8"), usedforsecurity=False).hexdigest()
        found.append(
            Violation(
                ctx.stage, ctx.stage, contract, "contract is broken, details not read", digest
            )
        )
    return found


def _parse_import_linter(
    exit_code: int, stdout: str, stderr: str, ctx: ParseContext
) -> ParseResult:
    if exit_code == 0:
        return _ok()
    if exit_code != 1:
        return _bad_exit("import-linter", exit_code, stderr, stdout)
    lines = _lines(_plain(stdout))
    heading = _il_heading_index(lines)
    if heading is None:
        words = "\n".join(line for line in lines if not _BOX_DRAWING.search(line))
        what = "import-linter 종료 코드 1이지만 깨진 계약 목록이 없다 (설정이나 사용 오류)"
        raise _Unparseable(_with_cause(what, _tail(stderr, words)))
    blocks = _il_blocks(lines[heading + 2 :])
    if not blocks:
        raise _cannot_read("import-linter", "Broken contracts 아래에서 계약을 하나도 찾지 못했다")
    summaries = [_IL_SUMMARY.fullmatch(line.strip()) for line in lines[:heading]]
    reported = [_number(m.group("broken")) for m in summaries if m is not None]
    if reported and reported[-1] != len(blocks):
        raise _cannot_read(
            "import-linter", f"깨진 계약이 {reported[-1]}개라고 했는데 {len(blocks)}개만 읽었다"
        )
    found = []
    for contract, body in blocks:
        found.extend(_il_block(contract, body, ctx))
    return _violations(found)


# --- pytest -------------------------------------------------------------------------------------

# pytest's own output is not read; the junit XML is (--junitxml). Exit codes: 0 all passed, 1 some
# test failed, 2 collection error or interrupted, 3 internal error, 4 usage error, 5 no tests
# collected. Only 0 and 1 mean the tests ran, so only they get their junit file read.
#
# Counts come from the elements: a <testcase> per test (a test with a failure in the call and an
# error in the teardown is one <testcase> with a <failure> and an <error>), a <failure> or <error>
# inside it for each thing that went wrong, and a <skipped> for each skip. skip, skipif,
# pytest.skip and importorskip all give <skipped message="REASON">, and so does xfail, which is
# therefore a skip that needs allowing as well. A fixture error is an <error> and counts as a
# failure here. The attributes of <testsuite> are not used, so a count cannot disagree with the
# elements it is made of.
#
# What decides, in this order: an exit code other than 0 or 1; a junit file that cannot be read;
# any failure or error, which makes violations; exit 1 without any (the exit code cannot be
# explained); no tests at all; a skip whose reason matches none of allow_skip. A failing test is
# reported before a refused skip because failing is the stronger answer, and the refused skip
# shows up once the failure is fixed; the check cannot pass while it is there.
#
# A violation is a test, identified by where it is and its name, not by what it said: a failure
# message can hold object addresses, timings or temporary folders, which would make the same
# failing test look new on every run.

_PYTEST_EXIT_MEANING = {
    2: "수집 오류이거나 중단됐다",
    3: "pytest 내부 오류",
    4: "pytest 사용법 오류",
    5: "수집된 테스트 0개",
}


def _read_junit(path: Optional[Path]) -> ET.Element:
    if path is None:
        raise _cannot_read("pytest", "junit 파일 경로가 설정되지 않았다")
    try:
        return ET.parse(str(path)).getroot()
    except OSError as exc:
        raise _cannot_read("pytest", f"junit 파일을 읽을 수 없다 ({exc.strerror or exc})") from None
    except (ET.ParseError, ValueError) as exc:
        raise _cannot_read("pytest", f"junit 파일이 올바른 XML이 아니다 ({exc})") from None


def _test_file(ctx: ParseContext, classname: str) -> Tuple[str, List[str]]:
    """pytest writes the place of a test as dots: "tests.test_a.TestX" is class TestX in
    tests/test_a.py. The longest prefix that is a .py file under the cwd or the tree is the
    module and the rest are classes. With no such file the dotted name stands in for the path."""
    parts = [part for part in classname.split(".") if part]
    for size in range(len(parts), 0, -1):
        relative = "/".join(parts[:size]) + ".py"
        for base in (ctx.cwd, ctx.tree):
            if (base / relative).is_file():
                return _tree_path(str(base / relative), ctx.cwd, ctx.tree), parts[size:]
    return ".".join(parts), []


def _junit_violation(
    ctx: ParseContext, element: ET.Element, parents: Dict[ET.Element, ET.Element]
) -> Violation:
    # pytest puts these inside a <testcase>. One placed anywhere else is named after what holds it
    # (the suite), or after itself, so that it is not dropped.
    owner = parents.get(element, element)
    name = owner.get("name") or ""
    path, classes = _test_file(ctx, owner.get("classname") or "")
    return Violation(
        ctx.stage, path or name or ctx.stage, "test-failure", "::".join([*classes, name]), ""
    )


def _parse_pytest_junit(exit_code: int, stdout: str, stderr: str, ctx: ParseContext) -> ParseResult:
    if exit_code not in (0, 1):
        return _bad_exit(
            "pytest", exit_code, stderr, stdout, _PYTEST_EXIT_MEANING.get(exit_code, "")
        )
    try:
        allowed = [re.compile(pattern) for pattern in ctx.allow_skip]
    except re.error as exc:
        return _error(f"allow_skip의 정규식이 올바르지 않다: {exc}")
    root = _read_junit(ctx.junit_path)

    parents = {child: parent for parent in root.iter() for child in parent}
    cases = list(root.iter("testcase"))
    failed = [element for element in root.iter() if element.tag in ("failure", "error")]
    skips = [
        element.get("message") or (element.text or "").strip() for element in root.iter("skipped")
    ]
    counts = TestCounts(
        tests=len(cases),
        failures=sum(1 for element in failed if element.tag == "failure"),
        errors=sum(1 for element in failed if element.tag == "error"),
        skipped=len(skips),
        skip_messages=skips,
    )

    if failed:
        return _violations([_junit_violation(ctx, element, parents) for element in failed], counts)
    if exit_code == 1:
        return _error("pytest 종료 코드 1인데 junit에는 실패가 없다", counts)
    if not cases:
        return _error("수집된 테스트 0개", counts)
    refused = [reason for reason in skips if not any(p.search(reason) for p in allowed)]
    if refused:
        shown = ", ".join(repr(reason) for reason in refused[:3])
        more = f" 외 {len(refused) - 3}개" if len(refused) > 3 else ""
        return _error(f"allow_skip에 없는 skip {len(refused)}개: {shown}{more}", counts)
    return _ok(counts)


# --- command ------------------------------------------------------------------------------------


def _parse_command(exit_code: int, stdout: str, stderr: str, ctx: ParseContext) -> ParseResult:
    """Any command: 0 passes and 1 fails, and there is nothing in its output to compare, so it is
    one violation. Any other code is a command that did not do its job, as for the tools above:
    2 is most tools' usage error, 126 and 127 a program that could not run, a negative code a
    signal."""
    if exit_code == 0:
        return _ok()
    if exit_code != 1:
        return _bad_exit("명령", exit_code, stderr, stdout)
    return _violations([Violation(ctx.stage, ctx.stage, "exit", "exit 1", "")])


# --- parse --------------------------------------------------------------------------------------

# Keys are the kinds of config.KINDS. "weakening" is not here: it reads the diff, not the output
# of a tool, so the runner never calls parse for it.
PARSERS: Dict[str, Callable[[int, str, str, ParseContext], ParseResult]] = {
    "ruff": _parse_ruff,
    "ruff-format": _parse_ruff_format,
    "mypy": _parse_mypy,
    "import-linter": _parse_import_linter,
    "pytest-junit": _parse_pytest_junit,
    "command": _parse_command,
}


def parse(kind: str, exit_code: int, stdout: str, stderr: str, ctx: ParseContext) -> ParseResult:
    """Turn what a tool of this `kind` printed into a ParseResult.

    The exit code is read first and decides whether the output is read at all. A kind this module
    does not know and output that cannot be trusted are both an "error" result, not an exception
    and never "ok". An exception nobody expected (a bug in here) is not caught: it propagates to
    the runner, which reports the stage as incomplete."""
    parser = PARSERS.get(kind)
    if parser is None:
        return _error(f"해석할 수 없는 종류: {kind!r}")
    try:
        return parser(exit_code, stdout, stderr, ctx)
    except _Unparseable as exc:
        return _error(str(exc))
