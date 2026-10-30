#!/usr/bin/env python3
"""Collect the contract headers of test files into one map, and check them against the tests.

A contract header sits at the top of a test file (module docstring or leading comments):

    문서 업로드 API (POST /documents)

    계약:
    - PDF를 올리면 문서와 처리 run이 생긴다 → test_upload_creates_document_and_run
    - 50MB를 넘으면 413으로 거절한다 → test_upload_rejects_oversized_file

`Contracts:` works as well as `계약:`. After the arrow come the tests that prove the contract:
Python test names (`test_x` or `Class.test_x`), or for vitest/jest a quoted prefix of the test
title (`"stopping uploads"`). A contract line without an arrow is allowed: it records a contract
that no test proves yet (a known gap).

Usage:
  python3 contract_map.py PATH... [--check] [--strict] [--out FILE]

  default   print the map as markdown (contract → tests, per file) plus problems
  --check   exit 1 on stale references (named test not found) or test files without a header
  --strict  with --check, also fail when a test belongs to no contract
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

PY_TEST_FILE = re.compile(r"^(test_.*|.*_test)\.py$")
TS_TEST_FILE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")
SKIP_DIRS = {"node_modules", ".venv", "venv", ".git", "__pycache__", "dist", "build"}
HEADER_MARK = re.compile(r"^\s*(계약|contracts?)\s*:\s*$", re.I)
ARROW = re.compile(r"\s*(?:→|->)\s*")
TS_TEST = re.compile(r"""^\s*(?:it|test)(?:\.\w+)*(?:\([^)]*\))?\s*\(\s*(['"`])((?:\\.|(?!\1).)*)\1""", re.M)
PY_TEST = re.compile(r"^(\s*)(?:async\s+)?def\s+(test\w*)\s*\(", re.M)
PY_CLASS = re.compile(r"^class\s+(\w+)", re.M)


def leading_block(path: Path, text: str) -> list[str]:
    """The header lines: a Python module docstring or the comment lines before the first code."""
    if path.suffix == ".py":
        try:
            doc = ast.get_docstring(ast.parse(text), clean=True)
        except SyntaxError:
            doc = None
        if doc:
            return doc.splitlines()
        prefix = "#"
    else:
        prefix = "//"
    lines, in_block = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if in_block:
            end = "*/" in line
            lines.append(line.split("*/")[0].lstrip("*").strip())
            in_block = not end
        elif line.startswith("/*") and path.suffix != ".py":
            body = line[2:]
            in_block = "*/" not in body
            lines.append(body.split("*/")[0].lstrip("*").strip())
        elif line.startswith(prefix):
            lines.append(line[len(prefix):].strip())
        elif line == "" or line.startswith("#!"):
            lines.append("")
        else:
            break
    return lines


def parse_header(lines: list[str]) -> tuple[str, list[dict]] | None:
    try:
        start = next(i for i, ln in enumerate(lines) if HEADER_MARK.match(ln))
    except StopIteration:
        return None
    title = next((ln for ln in lines[:start] if ln.strip()), "")
    contracts: list[dict] = []
    for ln in lines[start + 1:]:
        if ln.startswith("- "):
            contracts.append({"text": ln[2:].strip()})
        elif ln.strip() and contracts and not HEADER_MARK.match(ln):
            contracts[-1]["text"] += " " + ln.strip()  # wrapped line
        elif not ln.strip() and contracts:
            break
    for c in contracts:
        parts = ARROW.split(c["text"], maxsplit=1)
        c["text"] = parts[0].strip()
        refs = parts[1] if len(parts) > 1 else ""
        quoted = re.findall(r"""["'`]([^"'`]+)["'`]""", refs)
        c["refs"] = quoted or [r.strip() for r in refs.split(",") if r.strip()]
    return title, contracts


def tests_in(path: Path, text: str) -> list[str]:
    if path.suffix == ".py":
        names, current_class = [], None
        for line in text.splitlines():
            if m := PY_CLASS.match(line):
                current_class = m.group(1)
            elif m := PY_TEST.match(line):
                indent, name = m.groups()
                names.append(f"{current_class}.{name}" if indent and current_class else name)
        return names
    return [m.group(2) for m in TS_TEST.finditer(text)]


def resolve(ref: str, tests: list[str], is_py: bool) -> list[str]:
    if is_py:
        return [t for t in tests if t == ref or t.endswith("." + ref)]
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    return [t for t in tests if norm(t).startswith(norm(ref))]


def collect(paths: list[str]) -> list[Path]:
    found = []
    for p in map(Path, paths):
        if p.is_file():
            found.append(p)
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            found += [Path(dirpath) / n for n in filenames if PY_TEST_FILE.match(n) or TS_TEST_FILE.search(n)]
    return sorted(set(found))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    files = collect(args.paths)
    root = Path(os.path.commonpath([str(f.parent.resolve()) for f in files])) if files else Path(".")
    out, problems = [], {"stale": [], "no_header": [], "unowned": [], "ambiguous": []}
    n_contracts = n_owned = n_tests = 0
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        rel = os.path.relpath(f.resolve(), root)
        tests = tests_in(f, text)
        n_tests += len(tests)
        header = parse_header(leading_block(f, text))
        if header is None:
            problems["no_header"].append(f"{rel} ({len(tests)} tests)")
            continue
        title, contracts = header
        owned: set[str] = set()
        out.append(f"### {rel}" + (f" — {title}" if title else ""))
        for c in contracts:
            n_contracts += 1
            shown = []
            for ref in c["refs"]:
                hits = resolve(ref, tests, f.suffix == ".py")
                if not hits:
                    problems["stale"].append(f"{rel}: '{ref}' (계약: {c['text']})")
                    shown.append(f"~~{ref}~~ (없음)")
                elif len(hits) > 1 and f.suffix != ".py":
                    problems["ambiguous"].append(f"{rel}: '{ref}' matches {len(hits)} tests")
                owned.update(hits)
                shown += [f"`{h}`" for h in hits]
            out.append(f"- {c['text']} → " + (", ".join(shown) if shown else "**(테스트 없음)**"))
        unowned = [t for t in tests if t not in owned]
        n_owned += len(tests) - len(unowned)
        problems["unowned"] += [f"{rel}: {t}" for t in unowned]
        out.append("")
    headed = len(files) - len(problems["no_header"])
    summary = (f"# 계약 지도 — 머리말 있는 파일 {headed}/{len(files)}, 계약 {n_contracts}개, "
               f"계약에 묶인 테스트 {n_owned}/{n_tests}\n")
    report = [summary, *out]
    labels = {"stale": "머리말에 있지만 없는 테스트", "no_header": "머리말 없는 테스트 파일",
              "unowned": "어느 계약에도 안 묶인 테스트", "ambiguous": "여러 테스트에 걸리는 제목 접두어"}
    for key, items in problems.items():
        if items:
            report += [f"## {labels[key]} ({len(items)})", *[f"- {i}" for i in items], ""]
    text = "\n".join(report) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    if args.check:
        failed = problems["stale"] or problems["no_header"] or (args.strict and problems["unowned"])
        sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
