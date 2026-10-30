#!/usr/bin/env python3
"""handoff 상태 파일(작업 폴더의 .handoff/<이름>.json) 관리.

  state.py list           저장된 작업 목록(최근 순, 7일 넘은 것 표시)
  state.py check <이름>   칸과 길이 검사. 문제가 없으면 ok
  state.py path <이름>    파일 경로
  state.py done <이름>    작업을 끝내고 파일과 <cwd>/tmp/handoff/<이름>/ 폴더를 지운다
"""
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TEXT = {"name": 40, "title": 80, "updated_at": 40, "by": 40, "cwd": 300, "goal": 400, "now": 400, "next": 400}
OPTIONAL_TEXT = {"session": 80}
LISTS = {"rules": 8, "decisions": 8, "done": 8, "waiting": 6, "corrections": 6, "refs": 10, "running": 5}
ITEM = 300
MAX_BYTES = 8000
STALE_DAYS = 7


def home():
    return Path(os.environ.get("HANDOFF_DIR", ".handoff"))


def path_of(name):
    return home() / f"{name}.json"


def check(name):
    if not NAME.match(name) or len(name) > TEXT["name"]:
        return [f"이름 '{name}': 영어 소문자·숫자와 -만, {TEXT['name']}자 이하"]
    path = path_of(name)
    if not path.exists():
        return [f"파일 없음: {path}"]
    if path.stat().st_size > MAX_BYTES:
        return [f"파일이 {path.stat().st_size}바이트: {MAX_BYTES} 이하로 줄인다(자세한 건 작업 로그로)"]
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"JSON 오류: {e}"]
    problems = []
    for key in data.keys() - TEXT.keys() - OPTIONAL_TEXT.keys() - LISTS.keys():
        problems.append(f"모르는 칸 '{key}': 있는 칸에 넣는다")
    for key, limit in {**TEXT, **OPTIONAL_TEXT}.items():
        value = data.get(key)
        if value is None and key in OPTIONAL_TEXT:
            continue
        if not isinstance(value, str) or not value.strip():
            problems.append(f"'{key}' 칸이 비었거나 글이 아님")
        elif len(value) > limit:
            problems.append(f"'{key}' {len(value)}자: {limit}자 이하")
    for key, limit in LISTS.items():
        items = data.get(key, [])
        if not isinstance(items, list) or not all(isinstance(i, str) and i.strip() for i in items):
            problems.append(f"'{key}'는 글 목록")
            continue
        if len(items) > limit:
            problems.append(f"'{key}' {len(items)}줄: {limit}줄 이하(끝난 것·덜 중요한 것을 뺀다)")
        problems += [f"'{key}'의 {i + 1}번째 줄 {len(t)}자: {ITEM}자 이하" for i, t in enumerate(items) if len(t) > ITEM]
    if data.get("name") != name:
        problems.append(f"'name' 칸이 파일 이름({name})과 다름")
    return problems


def listing():
    files = sorted(home().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "저장된 작업 없음"
    rows = []
    for p in files:
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError:
            data = {}
        age = int((time.time() - p.stat().st_mtime) // 86400)
        when = datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M")
        stale = f"  ← {STALE_DAYS}일 넘음" if age >= STALE_DAYS else ""
        rows.append(f"{p.stem}  {when} {data.get('by', '?')}  {data.get('title', '')}{stale}")
    return "\n".join(rows)


def work_dir(name):
    """작업 폴더의 tmp/handoff/<이름>/. 상태 파일의 cwd가 없거나 상대 경로면 None."""
    try:
        cwd = json.loads(path_of(name).read_text()).get("cwd")
    except (OSError, json.JSONDecodeError):
        return None
    return Path(cwd) / "tmp/handoff" / name if isinstance(cwd, str) and os.path.isabs(cwd) else None


def done(name):
    """상태 파일과 그 작업 폴더를 지운다. 지운 경로 목록을 돌려준다."""
    if not NAME.match(name):
        raise ValueError(f"이름 '{name}': 영어 소문자·숫자와 -만")
    removed = [path_of(name)]
    work = work_dir(name)
    if work and work.is_dir() and not work.is_symlink():
        shutil.rmtree(work)
        removed.append(work)
    path_of(name).unlink()
    return removed


def main(argv):
    if argv[:1] == ["list"]:
        print(listing())
        return 0
    if len(argv) == 2 and argv[0] in ("check", "path", "done"):
        cmd, name = argv
        if cmd == "path":
            print(path_of(name))
        elif cmd == "done":
            print("\n".join(f"지움: {p}" for p in done(name)))
        else:
            problems = check(name)
            print("\n".join(problems) if problems else "ok")
            return 1 if problems else 0
        return 0
    print(__doc__.split("\n\n", 1)[1].rstrip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
