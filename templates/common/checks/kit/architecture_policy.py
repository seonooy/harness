from __future__ import annotations

import configparser
from typing import List, Tuple

# What doctor reads out of the package table of architecture.md (`## 패키지`) and the import
# contracts. The table names each package and its style; every package needs contracts whose ids
# start with its short name, and every module has to sit in some layer, so a new module cannot slip
# past the architecture.

STYLES = ("layered", "hexagonal")
# Patterns sit on one module inside a package's style (`## 패턴`, columns: module, pattern).
PATTERNS = ("pipeline", "plugin", "task-queue")
_HEADING = "## 패키지"
_PATTERN_HEADING = "## 패턴"
_FILL = "<<FILL:"


def short_name(package: str) -> str:
    """The last dotted part of a package name: app.notes -> notes, app -> app."""
    return package.rsplit(".", 1)[-1]


def package_rows(markdown: str) -> List[Tuple[str, str]]:
    """(package, style) of each row of the table under the `## 패키지` heading. The heading must
    be exactly that line, so `## 패키지 사이` is another section. Backticks around a cell are
    dropped, and a row still holding a fill marker is left to the fill-marker check."""
    return _table_rows(markdown, _HEADING)


def pattern_rows(markdown: str) -> List[Tuple[str, str]]:
    """(module, pattern) of each row of the table under the `## 패턴` heading, read like the
    package table."""
    return _table_rows(markdown, _PATTERN_HEADING)


def _table_rows(markdown: str, heading: str) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    inside = False
    seen_header = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            inside = stripped == heading
            seen_header = False
            continue
        if not inside or not stripped.startswith("|"):
            continue
        cells = [cell.strip().strip("`").strip() for cell in stripped.strip("|").split("|")]
        if not seen_header:  # the first row names the columns
            seen_header = True
            continue
        if all(set(cell) <= set("-: ") for cell in cells):  # the separator row
            continue
        if len(cells) < 2 or not cells[0] or _FILL in cells[0]:
            continue
        rows.append((cells[0], cells[1]))
    return rows


def inventory_problems(ini_text: str) -> List[str]:
    """Every layers contract is exhaustive, and every root package is the container of one, so
    that each module is registered in some layer."""
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(ini_text)
    roots = config.get("importlinter", "root_packages", fallback="").split()
    roots += config.get("importlinter", "root_package", fallback="").split()
    containers: List[str] = []
    problems: List[str] = []
    for section in config.sections():
        if not section.startswith("importlinter:contract:"):
            continue
        if config.get(section, "type", fallback="") != "layers":
            continue
        names = config.get(section, "containers", fallback="").split()
        if not names:
            continue
        if not config.getboolean(section, "exhaustive", fallback=False):
            problems.append(f"{section}: 새 모듈 누락 검사를 위해 exhaustive = True가 필요하다")
        else:
            containers.extend(names)
    for root in roots:
        if root not in containers:
            problems.append(f"{root}: 루트 이름을 정확히 지정한 exhaustive layers containers가 없다")
    if not roots:
        problems.append("importlinter: root_package 또는 root_packages가 필요하다")
    return problems
