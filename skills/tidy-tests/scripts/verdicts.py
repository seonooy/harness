#!/usr/bin/env python3
"""Check a verdict file against the inventory and print the decision table for approval.

Usage:
  python3 verdicts.py INVENTORY.jsonl VERDICTS.jsonl [--batches]

INVENTORY.jsonl comes from inventory.py. VERDICTS.jsonl has one object per line:
  {"ids": [...], "verdict": "keep|repair|combine|remove|open", "contract": "...",
   "detects": "...", "evidence": "file:line ...", "action": "...", "batch": "optional label"}

Exits 1 when an inventory id has no verdict, appears twice, or a verdict names an unknown id —
every test needs exactly one evidence-backed decision before anything is changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

VERDICTS = ("keep", "repair", "combine", "remove", "open")
LABEL = {"keep": "Keep", "repair": "Repair", "combine": "Combine", "remove": "Remove", "open": "미결"}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                sys.exit(f"{path}:{n}: bad JSON ({exc})")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inventory")
    ap.add_argument("verdicts")
    ap.add_argument("--batches", action="store_true", help="group remove/combine/repair by batch label")
    args = ap.parse_args()
    inventory = {t["id"]: t for t in load_jsonl(Path(args.inventory))}
    records = load_jsonl(Path(args.verdicts))

    seen: Counter = Counter()
    unknown, bad_verdict = [], []
    by_verdict: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for rec in records:
        verdict = str(rec.get("verdict", "")).lower()
        if verdict not in VERDICTS:
            bad_verdict.append(rec)
            continue
        for test_id in rec.get("ids", []):
            seen[test_id] += 1
            if test_id not in inventory:
                unknown.append(test_id)
            by_verdict[verdict].append((test_id, rec))

    missing = [i for i in inventory if seen[i] == 0]
    dupes = [i for i, n in seen.items() if n > 1]
    total = len(inventory)
    counts = {v: len({i for i, _ in by_verdict[v]}) for v in VERDICTS}
    loc = {v: sum(inventory[i]["loc"] for i, _ in by_verdict[v] if i in inventory) for v in VERDICTS}

    print(f"# 판정표 — 테스트 {total}개")
    print(" · ".join(f"{LABEL[v]} {counts[v]}" for v in VERDICTS) + f" · 판정 없음 {len(missing)}")
    print(f"제거 예정 LOC {loc['remove']} · 합치기 대상 LOC {loc['combine']} · 수정 대상 LOC {loc['repair']}\n")

    for verdict in ("remove", "combine", "repair", "open"):
        rows = by_verdict[verdict]
        if not rows:
            continue
        print(f"## {LABEL[verdict]} ({counts[verdict]})")
        groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for test_id, rec in rows:
            groups[rec.get("batch", "") if args.batches else ""].append((test_id, rec))
        for batch, items in groups.items():
            if batch:
                print(f"### 묶음: {batch}")
            printed = set()
            for test_id, rec in items:
                key = id(rec)
                if key in printed:
                    continue
                printed.add(key)
                ids = [i for i in rec["ids"]]
                head = ids[0] + (f" 외 {len(ids) - 1}개" if len(ids) > 1 else "")
                print(f"- `{head}` — {rec.get('action', '')}  \n  근거: {rec.get('evidence', '')}")
        print()

    problems = False
    for label, items in (("판정 없는 테스트", missing), ("두 번 판정된 테스트", dupes),
                         ("인벤토리에 없는 id", unknown)):
        if items:
            problems = True
            print(f"## {label} ({len(items)})")
            print("\n".join(f"- {i}" for i in items[:50]) + ("\n- …" if len(items) > 50 else ""))
    if bad_verdict:
        problems = True
        print(f"## verdict 값이 잘못된 줄 ({len(bad_verdict)})")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
