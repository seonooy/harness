#!/usr/bin/env python3
r"""Break production code on purpose, run the tests, restore — and say what that proves.

One mutant:
    python3 falsify.py --repo REPO --file app/x.py --find 'if not ok:' --replace 'if False:' \
        --cwd server -- .venv/bin/pytest -q tests/test_x.py

A set of mutants (one or more per contract), e.g. before and after rewriting a feature's tests:
    python3 falsify.py --repo REPO --mutants $S/mutants.jsonl --out $S/kills-before.json \
        --cwd web -- ./node_modules/.bin/vitest run src/lib
    python3 falsify.py --compare $S/kills-before.json $S/kills-after.json

mutants.jsonl — one per line:
    {"id": "M1", "contract": "C1", "file": "web/src/lib/x.ts", "find": "if (a) b();", "replace": "",
     "note": "가드 삭제"}            (optional: "regex": true, "nth": 2, "all": true)

Everything runs in a scratch copy of REPO (rsync'd each time; node_modules/.venv symlinked back),
never in REPO itself. Steps:
  green  — the command passes on the unmodified copy (otherwise nothing can be concluded)
  sanity — per file, a deliberate error at its top must turn the command red; if it doesn't, the
           command never loads that file (wrong cwd, editable install importing the original, tests
           that don't reach it) and that file's mutants are INCONCLUSIVE
  mutant — apply find → replace (must match exactly once unless nth/all), run, restore the exact
           bytes and verify the hash
KILLED = some test went red (read the failure: right reason?). SURVIVED = nothing in the command
protects that code. --compare lists mutants killed before but not after (lost protection).

Options: --skip-green, --skip-sanity, --scratch DIR (default $FALSIFY_SCRATCH or the system temp
dir), --exclude PATTERN (extra rsync exclude), --timeout SECONDS, --tail LINES.
Exit: 0 all killed · 1 some survived · 3 inconclusive/invalid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

HEAVY = ("node_modules", ".venv", "venv")
EXCLUDE = (*HEAVY, ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", ".next")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sync_copy(repo: Path, scratch: Path, extra_excludes: list[str]) -> Path:
    dest = scratch / f"falsify-{repo.name}-{sha(str(repo).encode())[:8]}"
    dest.mkdir(parents=True, exist_ok=True)
    excludes = [*EXCLUDE, *extra_excludes]
    cmd = ["rsync", "-a", "--delete", *[f"--exclude={e}" for e in excludes], f"{repo}/", f"{dest}/"]
    subprocess.run(cmd, check=True)
    for heavy in HEAVY:  # link dependency dirs back, up to three levels deep
        for pattern in (heavy, f"*/{heavy}", f"*/*/{heavy}", f"*/*/*/{heavy}"):
            for src in repo.glob(pattern):
                if not any(part in excludes for part in src.relative_to(repo).parts[:-1]):
                    _link(src, dest / src.relative_to(repo))
    return dest


def _link(src: Path, dst: Path) -> None:
    if dst.is_symlink() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.symlink_to(src)


def run(cmd: list[str], cwd: Path, timeout: float) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, f"timeout after {timeout}s\n{exc.stdout or ''}{exc.stderr or ''}"


def sanity_break(path: Path, text: str) -> str:
    if path.suffix == ".py":
        return 'raise RuntimeError("falsify-sanity")\n' + text
    return 'throw new Error("falsify-sanity");\n' + text


def mutate(text: str, m: dict) -> str:
    find, replace = m["find"], m.get("replace", "")
    pattern = re.compile(find if m.get("regex") else re.escape(find), re.M)
    matches = list(pattern.finditer(text))
    if not matches:
        raise ValueError(f"find not found: {find!r}")
    if m.get("all"):
        return pattern.sub(replace if m.get("regex") else replace.replace("\\", "\\\\"), text)
    if m.get("nth") is None and len(matches) > 1:
        raise ValueError(f"find matches {len(matches)} times; set nth (1-based) or all")
    hit = matches[(m.get("nth") or 1) - 1]
    new = hit.expand(replace) if m.get("regex") else replace
    return text[: hit.start()] + new + text[hit.end():]


class Runner:
    def __init__(self, copy: Path, cmd: list[str], cwd: Path, timeout: float, tail: int) -> None:
        self.copy, self.cmd, self.cwd, self.timeout, self.tail = copy, cmd, cwd, timeout, tail

    def attempt(self, target: Path | None, content: str | None) -> tuple[int, str]:
        """Run the command, with `target` temporarily holding `content`; restore and verify after."""
        original = target.read_bytes() if target else b""
        if target and content is not None:
            target.write_text(content, encoding="utf-8")
        try:
            return run(self.cmd, self.cwd, self.timeout)
        finally:
            if target and content is not None:
                if sha(target.read_bytes()) != sha(content.encode("utf-8")):
                    backup = target.with_name(target.name + ".falsify-orig")
                    backup.write_bytes(original)
                    sys.exit(f"{target}: changed during the run; original saved to {backup}")
                target.write_bytes(original)
                if sha(target.read_bytes()) != sha(original):
                    sys.exit(f"restore failed for {target}")

    def tail_of(self, out: str) -> str:
        return "\n".join(out.strip().splitlines()[-self.tail:])


def run_mutants(runner: Runner, mutants: list[dict], skip_green: bool, skip_sanity: bool,
                verbose: bool) -> dict:
    results: dict[str, dict] = {}
    if not skip_green:
        code, out = runner.attempt(None, None)
        print(f"[green] exit {code}")
        if code != 0:
            print(runner.tail_of(out))
            print("INCONCLUSIVE — the command is not green on the unmodified copy")
            sys.exit(3)
    loaded: dict[str, bool] = {}
    for m in mutants:
        rel = m["file"]
        target = runner.copy / rel
        base = {"contract": m.get("contract", ""), "file": rel, "note": m.get("note", "")}
        if not target.is_file():
            results[m["id"]] = {**base, "status": "invalid", "detail": "no such file"}
            continue
        text = target.read_bytes().decode("utf-8")
        if not skip_sanity and rel not in loaded:
            code, _ = runner.attempt(target, sanity_break(target, text))
            loaded[rel] = code != 0
            print(f"[sanity] {rel}: {'loaded' if loaded[rel] else 'NOT LOADED by the command'}")
        if not skip_sanity and not loaded[rel]:
            results[m["id"]] = {**base, "status": "inconclusive", "detail": "file not loaded by the command"}
            continue
        try:
            mutant_text = mutate(text, m)
        except ValueError as exc:
            results[m["id"]] = {**base, "status": "invalid", "detail": str(exc)}
            continue
        code, out = runner.attempt(target, mutant_text)
        status = "survived" if code == 0 else "killed"
        results[m["id"]] = {**base, "status": status, "exit": code}
        print(f"[{m['id']}] {status.upper()}  {m.get('contract', '')} {m.get('note', '')}")
        if verbose and status == "killed":
            print(runner.tail_of(out))
    return results


def print_table(results: dict) -> None:
    by_contract: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for mid, r in results.items():
        by_contract[r.get("contract") or "-"].append((mid, r))
    print("\n| 계약 | 잡힘 | 안 잡힘(살아남음) | 판단 불가 |\n|---|---|---|---|")
    for contract, rows in sorted(by_contract.items()):
        killed = [m for m, r in rows if r["status"] == "killed"]
        survived = [m for m, r in rows if r["status"] == "survived"]
        other = [f"{m}({r['status']})" for m, r in rows if r["status"] not in {"killed", "survived"}]
        print(f"| {contract} | {len(killed)}/{len(rows)} | {', '.join(survived) or '-'} | {', '.join(other) or '-'} |")


def compare(before_path: str, after_path: str) -> None:
    before = json.loads(Path(before_path).read_text())["results"]
    after = json.loads(Path(after_path).read_text())["results"]
    lost = [m for m, r in before.items() if r["status"] == "killed" and after.get(m, {}).get("status") != "killed"]
    gained = [m for m, r in after.items() if r["status"] == "killed" and before.get(m, {}).get("status") != "killed"]
    still = [m for m, r in after.items() if r["status"] == "survived"]
    print(f"전에 잡히던 변이 중 이제 안 잡히는 것 (보호 손실): {', '.join(lost) or '없음'}")
    print(f"새로 잡히는 변이: {', '.join(gained) or '없음'}")
    print(f"여전히 아무도 못 잡는 변이: {', '.join(still) or '없음'}")
    sys.exit(1 if lost else 0)


def main() -> None:
    argv = sys.argv[1:]
    if argv[:1] == ["--compare"]:
        if len(argv) != 3:
            sys.exit("usage: falsify.py --compare BEFORE.json AFTER.json")
        compare(argv[1], argv[2])
    if "--" not in argv:
        if {"-h", "--help"} & set(argv):
            print(__doc__)
            sys.exit(0)
        sys.exit("usage: falsify.py --repo REPO (--file F --find TEXT [--replace TEXT] | --mutants FILE --out FILE) "
                 "[--cwd DIR] -- COMMAND...   (see --help)")
    split = argv.index("--")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="project root to copy (the real checkout; never modified)")
    ap.add_argument("--file", help="production file, relative to --repo (single-mutant mode)")
    ap.add_argument("--find")
    ap.add_argument("--replace", default="")
    ap.add_argument("--regex", action="store_true")
    ap.add_argument("--nth", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--mutants", help="JSONL of mutants (batch mode)")
    ap.add_argument("--out", help="write batch results JSON here (input for --compare)")
    ap.add_argument("--cwd", default=".", help="where to run COMMAND, relative to --repo")
    ap.add_argument("--scratch", default=os.environ.get("FALSIFY_SCRATCH", tempfile.gettempdir()))
    ap.add_argument("--skip-green", action="store_true")
    ap.add_argument("--skip-sanity", action="store_true")
    ap.add_argument("--exclude", action="append", default=[], help="extra rsync exclude (big data dirs)")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--tail", type=int, default=15)
    args = ap.parse_args(argv[:split])
    cmd = argv[split + 1:]
    if bool(args.mutants) == bool(args.file):
        sys.exit("give either --file/--find (one mutant) or --mutants (a set)")
    if args.file and not args.find:
        sys.exit("--find is required with --file")

    repo = Path(args.repo).resolve()
    copy = sync_copy(repo, Path(args.scratch).resolve(), args.exclude)
    runner = Runner(copy, cmd, copy / args.cwd, args.timeout, args.tail)
    print(f"copy: {copy}\ncommand: {' '.join(cmd)} (cwd {args.cwd})")

    if args.mutants:
        mutants = [json.loads(line) for line in Path(args.mutants).read_text(encoding="utf-8").splitlines() if line.strip()]
        ids = [m.get("id") for m in mutants]
        if None in ids or len(set(ids)) != len(ids):
            sys.exit("every mutant needs a unique id")
        results = run_mutants(runner, mutants, args.skip_green, args.skip_sanity, verbose=False)
        print_table(results)
        if args.out:
            Path(args.out).write_text(json.dumps({"command": cmd, "cwd": args.cwd, "results": results},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"\nwrote {args.out}")
        statuses = {r["status"] for r in results.values()}
        sys.exit(3 if statuses & {"inconclusive", "invalid"} else 1 if "survived" in statuses else 0)

    single = {"id": "mutant", "file": args.file, "find": args.find, "replace": args.replace,
              "regex": args.regex, "nth": args.nth, "all": args.all}
    results = run_mutants(runner, [single], args.skip_green, args.skip_sanity, verbose=True)
    r = results["mutant"]
    print("restored, hash verified")
    if r["status"] == "survived":
        print("SURVIVED — nothing in this command fails when that code is changed")
        sys.exit(1)
    if r["status"] == "killed":
        print("KILLED — the command goes red when that code is changed (read the failure: right reason?)")
        sys.exit(0)
    print(f"INCONCLUSIVE — {r.get('detail', '')}")
    sys.exit(3)


if __name__ == "__main__":
    main()
