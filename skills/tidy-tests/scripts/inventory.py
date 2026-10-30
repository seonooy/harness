#!/usr/bin/env python3
"""Inventory a test suite: one record per test with signals that point an auditor at weak spots.

Signals are investigation prompts, not verdicts. A test flagged `mock-only` may still be the
cheapest proof of a wire contract; a test with five strong asserts may still be redundant.

Usage:
  python3 inventory.py PATH... [--results FILE]... [--src DIR]... [--root DIR] [--out PREFIX]

  PATH       test files or directories (pytest test_*.py / *_test.py, *.test.ts(x) / *.spec.ts(x))
  --results  pytest --junitxml file or vitest/jest --reporter=json file (repeatable)
  --src      production source dir (repeatable): enables the test-only-code check — production
             symbols the tests import that nothing outside the tests uses
  --root     paths in the output are relative to this (default: common parent of PATHs)
  --out      write PREFIX.jsonl (one test per line) and PREFIX.md (summary); default: print summary

Flags (hints for reading, never verdicts): no-assert, implicit-only, mock-only (asserts only on mocked
modules/patches), callback-only (TS: asserts only on vi.fn callbacks — usually a component's output),
weak-only, status-only, broad-raises/broad-throws, conditional-assert, swallowed-assert, constant-assert,
mock-heavy, private-access, sleeps, skipped/xfail, duplicate-body, prefix-duplicate, and with --src:
covers-test-only-code, vacuous-negative (not-called on a test-only symbol), vacuous-negative-string.
The .md summary also lists unused test imports (often a deleted test's trace).

TypeScript parsing uses the `typescript` package from the nearest node_modules above the test
files (run from a project that has it installed). Python uses only the standard library.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY_TEST_FILE = re.compile(r"^(test_.*|.*_test)\.py$")
TS_TEST_FILE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")
SKIP_DIRS = {"node_modules", ".venv", "venv", ".git", "__pycache__", "dist", "build", ".tox"}

MOCK_ASSERT_METHODS = {
    "assert_called", "assert_called_once", "assert_called_with", "assert_called_once_with",
    "assert_any_call", "assert_has_calls", "assert_not_called", "assert_awaited",
    "assert_awaited_once", "assert_awaited_with", "assert_awaited_once_with",
    "assert_any_await", "assert_has_awaits", "assert_not_awaited",
}
MOCK_INSPECT_ATTRS = {"call_count", "call_args", "call_args_list", "mock_calls", "await_count",
                      "await_args", "await_args_list", "called", "calls"}
MOCK_FACTORIES = {"MagicMock", "AsyncMock", "Mock", "NonCallableMock", "create_autospec"}
HELPER_ASSERT = re.compile(r"^_?(assert|check|expect|verify|ensure|should)", re.I)


# ── Python ──────────────────────────────────────────────────────────────────────────────


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _parametrize_rows(decorators: list[ast.expr]) -> int | str:
    rows: int | str = 1
    for dec in decorators:
        if isinstance(dec, ast.Call) and _dotted(dec.func).endswith("mark.parametrize"):
            values = dec.args[1] if len(dec.args) > 1 else next(
                (k.value for k in dec.keywords if k.arg == "argvalues"), None)
            if isinstance(values, (ast.List, ast.Tuple)) and isinstance(rows, int):
                rows *= max(len(values.elts), 1)
            else:
                rows = "?"
    return rows


def _markers(decorators: list[ast.expr]) -> list[str]:
    out = []
    for dec in decorators:
        name = _dotted(dec)
        if ".mark." in name and not name.endswith("parametrize"):
            out.append(name.split(".mark.")[-1])
    return out


def _mentions_mock_inspection(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Attribute) and n.attr in MOCK_INSPECT_ATTRS for n in ast.walk(node))


def _classify_assert(node: ast.Assert) -> str:
    """strong | weak | mock — a coarse read of what one `assert` can detect."""
    test = node.test
    if _mentions_mock_inspection(test):
        return "mock"
    if isinstance(test, ast.Call) and _dotted(test.func) in {"isinstance", "hasattr", "callable"}:
        return "weak"
    if isinstance(test, (ast.Name, ast.Attribute, ast.Subscript)):
        return "weak"  # bare truthiness
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) and isinstance(
            test.operand, (ast.Name, ast.Attribute)):
        return "weak"
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        op, right, left = test.ops[0], test.comparators[0], test.left
        if isinstance(op, ast.IsNot) and isinstance(right, ast.Constant) and right.value is None:
            return "weak"
        is_len = isinstance(left, ast.Call) and _dotted(left.func) == "len"
        if is_len and isinstance(right, ast.Constant) and isinstance(right.value, int):
            if (isinstance(op, ast.Gt) and right.value == 0) or (
                    isinstance(op, ast.GtE) and right.value <= 1) or (
                    isinstance(op, ast.NotEq) and right.value == 0):
                return "weak"
    return "strong"


def _is_patch(name: str) -> bool:
    """unittest.mock.patch / patch.object / mocker.patch — not `client.patch(...)` (an HTTP PATCH)."""
    base = name.rsplit(".", 1)[0] if name.endswith((".object", ".dict", ".multiple")) else name
    return base in {"patch", "mock.patch", "unittest.mock.patch", "mocker.patch", "monkeypatch.setattr"}


def _classify_unittest(node: ast.Call, method: str) -> str:
    """self.assertX(...) → strong | weak | mock, mirroring _classify_assert."""
    if any(_mentions_mock_inspection(a) for a in node.args):
        return "mock"
    first = node.args[0] if node.args else None
    if method in {"assertIsNotNone", "assertIsInstance", "assertNotIsInstance"}:
        return "weak"
    if method in {"assertTrue", "assertFalse"} and not isinstance(first, ast.Compare):
        return "weak"
    if method in {"assertGreater", "assertGreaterEqual"} and len(node.args) > 1:
        left, right = node.args[0], node.args[1]
        if (isinstance(left, ast.Call) and _dotted(left.func) == "len"
                and isinstance(right, ast.Constant) and right.value in (0, 1)):
            return "weak"
    if method == "assertRaises" and first is not None and _dotted(first) in {"Exception", "BaseException"}:
        return "weak"
    return "strong"


class _TestBodyScan(ast.NodeVisitor):
    asserting_helpers: set[str] = set()  # same-file functions whose body asserts; set per file

    def __init__(self) -> None:
        self.c = Counter()
        self.flags: set[str] = set()
        self._if_depth = 0
        self._loop_depth = 0
        self._try_depth = 0
        self.negative_strings: list[str] = []

    def visit_If(self, node: ast.If) -> None:
        self._if_depth += 1
        self.generic_visit(node)
        self._if_depth -= 1

    def _loop(self, node: ast.AST) -> None:
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    visit_For = visit_AsyncFor = visit_While = _loop

    def visit_Try(self, node: ast.Try) -> None:
        self._try_depth += 1
        for stmt in node.body:
            self.visit(stmt)
        self._try_depth -= 1
        swallow = any(
            all(isinstance(s, (ast.Pass, ast.Expr)) for s in h.body) and not any(
                isinstance(n, ast.Raise) for s in h.body for n in ast.walk(s)) for h in node.handlers)
        for part in (*node.handlers, *node.orelse, *node.finalbody):
            self.visit(part)
        if swallow and self.c["asserts"]:
            self.flags.add("swallowed-assert")

    visit_TryStar = visit_Try

    def _count_assert(self, kind: str) -> None:
        self.c["asserts"] += 1
        self.c[kind] += 1
        if self._if_depth and not self._loop_depth:
            self.flags.add("conditional-assert")

    def visit_Assert(self, node: ast.Assert) -> None:
        if isinstance(node.test, ast.Constant):
            self.flags.add("constant-assert")
        test = node.test
        if isinstance(test, ast.Compare) and len(test.ops) == 1:
            sides = [test.left, test.comparators[0]]
            if any(isinstance(x, ast.Attribute) and x.attr in {"status_code", "status"} for x in sides):
                self.c["status"] += 1
            if isinstance(test.ops[0], ast.NotIn) and isinstance(test.left, ast.Constant) and isinstance(test.left.value, str):
                self.negative_strings.append(test.left.value)
        self._count_assert(_classify_assert(node))
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            expr = item.context_expr
            name = _dotted(expr)
            if name.endswith("raises") and not name.startswith("self.") and isinstance(expr, ast.Call):
                broad = bool(expr.args) and _dotted(expr.args[0]) in {"Exception", "BaseException"}
                has_match = any(k.arg == "match" for k in expr.keywords)
                if broad and not has_match:
                    self.flags.add("broad-raises")
                self._count_assert("weak" if broad and not has_match else "strong")
            elif _is_patch(name):
                self.c["mocks"] += 1
        self.generic_visit(node)

    visit_AsyncWith = visit_With

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted(node.func)
        last = name.rsplit(".", 1)[-1]
        if last in MOCK_ASSERT_METHODS:
            self._count_assert("mock")
        elif last in MOCK_FACTORIES or _is_patch(name):
            self.c["mocks"] += 1
        elif name.endswith("monkeypatch.setattr") or name.endswith("monkeypatch.setitem"):
            self.c["mocks"] += 1
        elif last in {"fail"} and name.startswith("pytest"):
            self.c["forced_fail"] += 1
        elif (HELPER_ASSERT.match(last) and not name.startswith(("self.", "unittest"))) or (
                last in self.asserting_helpers and name in {last, f"self.{last}"}):
            self._count_assert("helper")
        elif name.startswith("self.assert") or name.startswith("self.fail"):
            self._count_assert(_classify_unittest(node, last))
            first = node.args[0] if node.args else None
            if last == "assertNotIn" and isinstance(first, ast.Constant) and isinstance(first.value, str):
                self.negative_strings.append(first.value)
            if last == "assertEqual" and any(isinstance(a, ast.Attribute) and a.attr in {"status_code", "status"}
                                               for a in node.args[:2]):
                self.c["status"] += 1
        elif name == "self.subTest":
            self.c["subtests"] += 1
        if name in {"time.sleep", "asyncio.sleep", "sleep"} and node.args:
            arg = node.args[0]
            if not (isinstance(arg, ast.Constant) and arg.value == 0):
                self.flags.add("sleeps")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        own = isinstance(node.value, ast.Name) and node.value.id in {"self", "cls"}
        if node.attr.startswith("_") and not node.attr.startswith("__") and not own:
            self.c["private_access"] += 1
        self.generic_visit(node)


def _body_hash(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    dump = "".join(ast.dump(s, annotate_fields=False) for s in body)
    return hashlib.sha1(dump.encode()).hexdigest()[:10]


def _stmt_hashes(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return [hashlib.sha1(ast.dump(st, annotate_fields=False).encode()).hexdigest()[:8] for st in body]


def _unused_imports(tree: ast.Module, fixture_names: set[str]) -> tuple[list[str], dict[str, str]]:
    """Module-level imports never referenced in the file — often the trace of a deleted test.
    Returns (unused 'module.name' list, {local name: imported name} for from-imports)."""
    imported: dict[str, str] = {}
    from_names: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module != "__future__":
            for a in node.names:
                if a.name != "*":
                    local = a.asname or a.name
                    imported[local] = f"{node.module}.{a.name}"
                    from_names[local] = a.name
        elif isinstance(node, ast.Import):
            for a in node.names:
                local = a.asname or a.name.split(".")[0]
                imported[local] = a.name
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= fixture_names
    for node in ast.walk(tree):  # names listed in __all__ or pytest_plugins strings
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in imported:
            used.add(node.value)
    unused = [full for local, full in imported.items() if local not in used]
    return unused, from_names


def _is_test_class(node: ast.ClassDef) -> bool:
    if node.name.startswith("Test"):
        return True
    return any(_dotted(b).rsplit(".", 1)[-1].endswith("TestCase") for b in node.bases)


def scan_python(path: Path, rel: str) -> tuple[list[dict], dict]:
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [], {"file": rel, "error": f"SyntaxError: {exc}"}
    lines = src.count("\n") + 1
    imports, private_imports = [], []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
            private_imports += [f"{node.module}.{a.name}" for a in node.names
                                if a.name.startswith("_") and not a.name.startswith("__")]
        elif isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
    tests: list[dict] = []
    _TestBodyScan.asserting_helpers = {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("test")
        and any(isinstance(x, ast.Assert) or (isinstance(x, ast.Call) and _dotted(x.func).endswith(("raises", "fail")))
                for x in ast.walk(n))
    }

    def visit_fn(fn, suite: str, class_markers: list[str]) -> None:
        scan = _TestBodyScan()
        for stmt in fn.body:
            scan.visit(stmt)
        for dec in fn.decorator_list:
            if _is_patch(_dotted(dec)):
                scan.c["mocks"] += 1
        c = scan.c
        flags = set(scan.flags)
        markers = class_markers + _markers(fn.decorator_list)
        markers += [_dotted(d).rsplit(".", 1)[-1] for d in fn.decorator_list
                    if _dotted(d).startswith("unittest.skip") or _dotted(d) in {"skip", "skipIf", "skipUnless"}]
        if any(m.startswith("skip") and m not in {"skipif", "skipIf", "skipUnless"} for m in markers):
            flags.add("skipped")
        if "xfail" in markers:
            flags.add("xfail")
        if c["asserts"] == 0 and not c["forced_fail"]:
            flags.add("no-assert")
        elif c["mock"] and c["mock"] == c["asserts"]:
            flags.add("mock-only")
        elif c["weak"] and c["weak"] == c["asserts"]:
            flags.add("weak-only")
        if c["mocks"] >= 3:
            flags.add("mock-heavy")
        if c["status"] and c["status"] == c["asserts"]:
            flags.add("status-only")
        if c["private_access"]:
            flags.add("private-access")
        name = fn.name
        tests.append({
            "kind": "py", "file": rel, "suite": suite, "name": name,
            "id": f"{rel}::{suite + '::' if suite else ''}{name}",
            "line": fn.lineno, "end_line": fn.end_lineno,
            "loc": (fn.end_lineno or fn.lineno) - fn.lineno + 1,
            "rows": "?" if c["subtests"] else _parametrize_rows(fn.decorator_list), "markers": markers,
            "asserts": c["asserts"], "strong": c["strong"], "weak": c["weak"],
            "mock_asserts": c["mock"], "helper_asserts": c["helper"], "mocks": c["mocks"],
            "fixtures": [a.arg for a in fn.args.args if a.arg not in {"self", "cls"}],
            "flags": sorted(flags), "hash": _body_hash(fn), "steps": _stmt_hashes(fn),
            "negative_mock_subjects": [], "negative_strings": scan.negative_strings,
        })

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            visit_fn(node, "", [])
        elif isinstance(node, ast.ClassDef) and _is_test_class(node):
            cls_markers = _markers(node.decorator_list)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test"):
                    visit_fn(item, node.name, cls_markers)
    test_lines = sum(t["loc"] for t in tests)
    fixture_names = {f for t in tests for f in t["fixtures"]}
    fixture_names |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    unused, from_names = _unused_imports(tree, fixture_names)
    return tests, {
        "file": rel, "kind": "py", "lines": lines, "tests": len(tests),
        "support_lines": lines - test_lines, "imports": imports, "private_imports": private_imports,
        "unused_imports": unused,
        "symbols": sorted({name for local, name in from_names.items()}),
    }


# ── TypeScript / JavaScript (delegated to inventory_ts.mjs) ────────────────────────────────


def scan_ts(paths: list[Path], root: Path) -> tuple[list[dict], list[dict]]:
    if not paths:
        return [], []
    script = HERE / "inventory_ts.mjs"
    proc = subprocess.run(
        ["node", str(script), str(root), *map(str, paths)],
        capture_output=True, text=True, cwd=paths[0].parent,
    )
    if proc.returncode != 0:
        sys.exit(f"inventory_ts.mjs failed:\n{proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    return data["tests"], data["files"]


# ── Results (junit xml / vitest-jest json) ─────────────────────────────────────────────


def _base(name: str) -> str:
    return name.split("[", 1)[0]


def load_results(paths: list[Path], root: Path) -> dict:
    """Map a test key to {status, duration_ms, runs}. Keys: (rel_file, suite, name) for pytest,
    (rel_file, 'A > B > title') for vitest/jest."""
    out: dict = {}

    def add(key, status: str, ms: float) -> None:
        slot = out.setdefault(key, {"status": "passed", "duration_ms": 0.0, "runs": 0})
        rank = {"passed": 0, "skipped": 1, "xfailed": 1, "failed": 3, "error": 4}
        if rank.get(status, 2) > rank.get(slot["status"], 0):
            slot["status"] = status
        slot["duration_ms"] += ms
        slot["runs"] += 1

    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if text.lstrip().startswith("<"):
            for case in ET.fromstring(text).iter("testcase"):
                status = "passed"
                for child in case:
                    if child.tag in {"failure", "error"}:
                        status = "failed" if child.tag == "failure" else "error"
                    elif child.tag == "skipped":
                        status = "xfailed" if "xfail" in (child.get("type") or "") else "skipped"
                cls = case.get("classname", "")
                add(("junit", cls, _base(case.get("name", ""))), status,
                    float(case.get("time") or 0) * 1000)
        else:
            data = json.loads(text)
            for file_result in data.get("testResults", []):
                fpath = Path(file_result["name"])
                try:
                    fkey = str(fpath.resolve().relative_to(root))
                except ValueError:
                    fkey = fpath.name
                for a in file_result.get("assertionResults", []):
                    status = {"pending": "skipped", "todo": "skipped"}.get(a["status"], a["status"])
                    full = " > ".join([*a.get("ancestorTitles", []), a["title"]])
                    add(("json", fkey, full), status, float(a.get("duration") or 0))
    return out


def _title_pattern(title: str) -> re.Pattern:
    """Turn an it.each/test.each template ('adds %s', 'maps $input') into a regex."""
    parts = re.split(r"(%[sdifjoO#%]|\$[\w.]+|\{\{.*?\}\})", title)
    rx = "".join(".+?" if i % 2 else re.escape(p) for i, p in enumerate(parts))
    return re.compile(f"^{rx}$")


def attach_results(tests: list[dict], results: dict) -> None:
    if not results:
        return
    junit = defaultdict(list)
    for (src, cls, name), v in results.items():
        if src == "junit":
            junit[name].append((cls, v))
    json_by_file = defaultdict(dict)
    for key, v in results.items():
        if key[0] == "json":
            json_by_file[key[1]][key[2]] = v
    for t in tests:
        hit = None
        if t["kind"] == "py":
            module = t["file"][:-3].replace("/", ".")
            want = f"{module}.{t['suite']}" if t["suite"] else module
            for cls, v in junit.get(t["name"], []):
                if cls == want or cls.endswith("." + want) or want.endswith("." + cls) or cls.endswith(
                        t["file"].rsplit("/", 1)[-1][:-3] + (f".{t['suite']}" if t["suite"] else "")):
                    hit = v
                    break
        else:
            by_title = json_by_file.get(t["file"]) or json_by_file.get(Path(t["file"]).name, {})
            full = " > ".join([*t["suite_path"], t["name"]])
            hit = by_title.get(full)
            if hit is None and t.get("each"):
                rx = _title_pattern(full)
                matches = [v for k, v in by_title.items() if rx.match(k)]
                if matches:
                    hit = {"status": max((m["status"] for m in matches),
                                         key=lambda s: {"passed": 0, "skipped": 1}.get(s, 3)),
                           "duration_ms": sum(m["duration_ms"] for m in matches),
                           "runs": len(matches)}
        if hit:
            t.update(status=hit["status"], duration_ms=round(hit["duration_ms"], 1), runs=hit["runs"])
        else:
            t["status"] = "not-run"


# ── Cross-test signals ─────────────────────────────────────────────────────────────────


def mark_prefix_duplicates(tests: list[dict]) -> None:
    """Test A whose every statement is the start of test B: B already does all of A."""
    by_file = defaultdict(list)
    for t in tests:
        if len(t.get("steps", [])) >= 3:
            by_file[t["file"]].append(t)
    for members in by_file.values():
        for a in members:
            for b in members:
                if a is not b and len(a["steps"]) < len(b["steps"]) and b["steps"][: len(a["steps"])] == a["steps"]:
                    a["flags"] = sorted({*a["flags"], "prefix-duplicate"})
                    a.setdefault("prefix_of", []).append(b["id"])


SRC_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|__mocks__|e2e)(/|$)|(\.|_)(test|spec)\.[^/]+$|(^|/)test_[^/]+\.py$|(^|/)conftest\.py$")


def production_index(src_dirs: list[Path]) -> dict[Path, tuple[str, Path]]:
    """Non-test source files under the given dirs: path → (text, src dir it came from)."""
    files = {}
    for src in src_dirs:
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix in SRC_EXT and not TEST_PATH.search(str(path.relative_to(src.parent))):
                    try:
                        files[path] = (path.read_text(encoding="utf-8", errors="replace"), src)
                    except OSError:
                        pass
    return files


def _module_name(path: Path, src: Path) -> str:
    rel = path.relative_to(src.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def mark_test_only_code(tests: list[dict], metas: list[dict], prod: dict[Path, str], root: Path) -> None:
    """A symbol the tests import whose only uses are its own definition: tests keep it alive."""
    if not prod:
        return
    cache: dict[str, bool] = {}

    def used_in_production(name: str) -> bool:
        if name not in cache:
            word = re.compile(rf"\b{re.escape(name)}\b")
            define = re.compile(rf"(def|class|function|const|let|var|interface|type|enum)\s+{re.escape(name)}\b"
                                rf"|^{re.escape(name)}\s*[:=]", re.M)
            uses, homes = 0, []
            for path, (text, src) in prod.items():
                n = len(word.findall(text))
                if n:
                    found = list(define.finditer(text))
                    uses += n - len(found)
                    homes += [(path, src, text, m) for m in found]
            used = uses > 0 or not homes  # unknown names (third-party, renamed re-exports) count as used
            for path, src, text, m in homes:
                if used:
                    break
                before = text[: m.start()].rstrip().splitlines()
                if before and before[-1].lstrip().startswith("@"):
                    used = True  # registered by a decorator
                elif path.suffix == ".py":
                    module = _module_name(path, src)
                    parent, _, leaf = module.rpartition(".")
                    side_effect = re.compile(rf"^\s*import\s+{re.escape(module)}\b|^\s*from\s+{re.escape(parent)}\s+import\s+.*\b{re.escape(leaf)}\b", re.M)
                    used = any(side_effect.search(t) for q, (t, _) in prod.items() if q != path)
            cache[name] = used
        return cache[name]

    lines_cache: dict[str, list[str]] = {}
    for meta in metas:
        dead = [s for s in meta.get("symbols", []) if not used_in_production(s)]
        meta["test_only_symbols"] = dead
        if not dead:
            continue
        path = root / meta["file"]
        lines_cache[meta["file"]] = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for t in (t for t in tests if t["file"] == meta["file"]):
            body = "\n".join(lines_cache[meta["file"]][t["line"] - 1: t["end_line"]])
            hits = [s for s in dead if re.search(rf"\b{re.escape(s)}\b", body)]
            if hits:
                t["flags"] = sorted({*t["flags"], "covers-test-only-code"})
                t["test_only_symbols"] = hits
            if set(t.get("negative_mock_subjects", [])) & set(dead):
                t["flags"] = sorted({*t["flags"], "vacuous-negative"})


IDENTIFIER_LIKE = re.compile(r"^[A-Za-z_][\w\-:.]{2,}$")  # css classes, keys, flags — not prose or data


def _built_dynamically(lit: str, corpus: str) -> bool:
    """`height:80.0pt` can come from f"height:{h}pt": some prefix ending at a separator is followed
    by an interpolation in production code."""
    for i in range(len(lit) - 1, 2, -1):
        if lit[i - 1] in ":-_./=":
            if re.search(re.escape(lit[:i]) + r"""(\{|\$\{|["']\s*\+|%[sd])""", corpus):
                return True
    return False


def mark_vacuous_negative_strings(tests: list[dict], prod: dict[Path, tuple[str, Path]]) -> None:
    """`"x" not in out` where no production file can produce "x": it cannot fail unless code adds it."""
    if not prod:
        return
    corpus = "\n".join(text for text, _ in prod.values())
    for t in tests:
        absent = [lit for lit in t.get("negative_strings", [])
                  if IDENTIFIER_LIKE.match(lit) and lit not in corpus and not _built_dynamically(lit, corpus)]
        if absent:
            t["flags"] = sorted({*t["flags"], "vacuous-negative-string"})
            t["absent_strings"] = absent


def git_state(path: Path) -> dict:
    def git(*args: str) -> str:
        proc = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else ""
    status = git("status", "--porcelain")
    return {"head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
            "dirty_files": len(status.splitlines()), "status_hash": hashlib.sha1(status.encode()).hexdigest()[:12]}


# ── Report ─────────────────────────────────────────────────────────────────────────────


def mark_duplicates(tests: list[dict]) -> None:
    groups = defaultdict(list)
    for t in tests:
        if t["loc"] > 3:  # one-liners collide by accident
            groups[t["hash"]].append(t)
    for members in groups.values():
        if len(members) > 1:
            ids = [m["id"] for m in members]
            for m in members:
                m["flags"] = sorted({*m["flags"], "duplicate-body"})
                m["duplicates"] = [i for i in ids if i != m["id"]]


def summarize(tests: list[dict], files: list[dict], git: dict | None = None) -> str:
    by_file = defaultdict(list)
    for t in tests:
        by_file[t["file"]].append(t)
    flag_counts = Counter(f for t in tests for f in t["flags"])
    status_counts = Counter(t.get("status", "not-run") for t in tests)
    rows_total = sum(t["rows"] if isinstance(t["rows"], int) else 1 for t in tests)
    out = [
        f"# Test inventory — {len(tests)} test declarations ({rows_total} incl. parameter rows), "
        f"{len(files)} files",
        "",
        (f"repo: {git['branch']} @ {git['head'][:9]}, {git['dirty_files']} uncommitted files" if git and git.get("head") else "repo: (not a git checkout)"),
        "status: " + ", ".join(f"{k} {v}" for k, v in status_counts.most_common()),
        "flags: " + (", ".join(f"{k} {v}" for k, v in flag_counts.most_common()) or "none"),
        "",
        "| file | tests | lines (support) | asserts/test | mock-only | weak-only | no-assert | dup | not passing |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    meta = {f["file"]: f for f in files}
    for file in sorted(by_file, key=lambda f: -len(by_file[f])):
        ts = by_file[file]
        m = meta.get(file, {})
        cnt = Counter(f for t in ts for f in t["flags"])
        bad = sum(1 for t in ts if t.get("status") not in {"passed", None, "not-run"})
        out.append(
            f"| {file} | {len(ts)} | {m.get('lines', '?')} ({m.get('support_lines', '?')}) | "
            f"{sum(t['asserts'] for t in ts) / len(ts):.1f} | {cnt['mock-only']} | {cnt['weak-only']} | "
            f"{cnt['no-assert']} | {cnt['duplicate-body']} | {bad} |")
    slow = sorted((t for t in tests if t.get("duration_ms")), key=lambda t: -t["duration_ms"])[:10]
    if slow:
        out += ["", "slowest: " + "; ".join(f"{t['id']} {t['duration_ms']:.0f}ms" for t in slow)]
    failing = [t for t in tests if t.get("status") in {"failed", "error"}]
    if failing:
        out += ["", "not passing:"] + [f"- {t['id']} ({t['status']})" for t in failing[:40]]
    dead = [(f["file"], f["test_only_symbols"]) for f in files if f.get("test_only_symbols")]
    if dead:
        out += ["", "production symbols only the tests use (check callers; tests may be keeping dead code alive):"]
        out += [f"- {file}: {', '.join(names)}" for file, names in dead]
    unused = [(f["file"], f["unused_imports"]) for f in files if f.get("unused_imports")]
    if unused:
        out += ["", "imports never used in the test file (often a deleted test's trace):"]
        out += [f"- {file}: {', '.join(names)}" for file, names in unused]
    prefix = [t for t in tests if t.get("prefix_of")]
    if prefix:
        out += ["", "tests whose whole body is the opening of another test:"]
        out += [f"- {t['id']} ⊂ {t['prefix_of'][0]}" for t in prefix[:40]]
    return "\n".join(out) + "\n"


def collect(paths: list[str]) -> list[Path]:
    found = []
    for p in map(Path, paths):
        if p.is_file():
            found.append(p.resolve())
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                if PY_TEST_FILE.match(name) or TS_TEST_FILE.search(name):
                    found.append((Path(dirpath) / name).resolve())
    return sorted(set(found))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--results", action="append", default=[])
    ap.add_argument("--src", action="append", default=[])
    ap.add_argument("--root")
    ap.add_argument("--out")
    args = ap.parse_args()
    files = collect(args.paths)
    if not files:
        sys.exit("no test files found")
    root = Path(args.root).resolve() if args.root else Path(os.path.commonpath(
        [str(f.parent) for f in files]))
    tests, metas = [], []
    root = root.resolve()
    for f in (f for f in files if f.suffix == ".py"):
        t, m = scan_python(f, str(f.relative_to(root)))
        tests += t
        metas.append(m)
    t, m = scan_ts([f for f in files if f.suffix != ".py"], root)
    tests += t
    metas += m
    mark_duplicates(tests)
    mark_prefix_duplicates(tests)
    prod = production_index([Path(d).resolve() for d in args.src])
    mark_test_only_code(tests, metas, prod, root)
    mark_vacuous_negative_strings(tests, prod)
    attach_results(tests, load_results([Path(r) for r in args.results], root))
    git = git_state(root)
    report = summarize(tests, metas, git)
    if args.out:
        Path(args.out + ".jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in tests))
        Path(args.out + ".files.json").write_text(json.dumps(metas, ensure_ascii=False, indent=1))
        Path(args.out + ".meta.json").write_text(json.dumps({"root": str(root), **git}, indent=1))
        Path(args.out + ".md").write_text(report)
        print(f"wrote {args.out}.jsonl ({len(tests)} tests), {args.out}.md, {args.out}.files.json")
    else:
        print(report)


if __name__ == "__main__":
    main()
