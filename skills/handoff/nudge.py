#!/usr/bin/env python3
"""Codex UserPromptSubmit 훅. 컨텍스트가 창의 40%, 60%를 처음 넘을 때 한 번씩 handoff를 제안하라고 모델에게 알린다.

저장은 사용자가 handoff를 부를 때만 한다. 이 훅은 알림만 하고, 어떤 오류에도 아무것도 출력하지 않고 끝난다(프롬프트를 막지 않는다).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

LEVELS = (0.4, 0.6)
CHUNK = 1 << 20
MAX_SCAN = 64 << 20
KEEP_DAYS = 7


def mark_dir():
    return Path(os.environ.get("HANDOFF_NUDGE_DIR", Path.home() / ".local/state/handoff-nudge"))


def lines_from_end(path):
    """파일 끝에서부터 한 줄씩 돌려준다. 큰 기록(수십 MB)도 끝 부분만 읽는다."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        rest = b""
        scanned = 0
        while pos > 0 and scanned < MAX_SCAN:
            size = min(CHUNK, pos)
            pos -= size
            scanned += size
            f.seek(pos)
            parts = (f.read(size) + rest).split(b"\n")
            rest = parts[0]
            for raw in reversed(parts[1:]):
                if raw:
                    yield raw.decode("utf-8", "replace")
        if pos == 0 and rest:
            yield rest.decode("utf-8", "replace")


def latest_usage(path):
    """(쓴 토큰, 창 크기)를 돌려준다. 못 찾으면 None."""
    for line in lines_from_end(path):
        if '"token_count"' in line:
            payload = json.loads(line).get("payload") or {}
            info = payload.get("info") or {}
            last = info.get("last_token_usage") or {}
            used, window = last.get("total_tokens") or 0, info.get("model_context_window") or 0
            if payload.get("type") == "token_count" and used and window:
                return used, window
    return None


def prune(marks):
    cutoff = time.time() - KEEP_DAYS * 86400
    for mark in marks.iterdir():
        if mark.stat().st_mtime < cutoff:
            mark.unlink()


def thresholds(window):
    return tuple(round(window * level) for level in LEVELS)


def tokens_text(used):
    return f"{used / 10000:.1f}".rstrip("0").rstrip(".") + "만"


def message(used, window, level):
    cmd, clear = "$handoff", "/new"
    pct = round(used / window * 100)
    marks = thresholds(window)
    later = f"다음 알림은 {tokens_text(marks[level])} 토큰에서 온다." if level < len(marks) else "이것이 마지막 알림이다."
    return (
        f"[handoff 알림] 컨텍스트가 약 {tokens_text(used)} 토큰, 창의 {pct}%다. "
        f"이번 답 맨 끝에 한 줄로 이렇게 제안하라: \"컨텍스트가 {pct}% 찼어요. 상태 저장하고 비울까요? ({cmd} → {clear} → {cmd} 이어)\". "
        f"저장은 사용자가 {cmd}를 부를 때만 한다. 제안은 이번 한 번만 하고, {later}"
    )


def main(raw):
    try:
        data = json.loads(raw)
        if data.get("agent_id") or not data.get("transcript_path"):
            return None
        found = latest_usage(data["transcript_path"])
        if not found:
            return None
        used, window = found
        level = sum(used >= t for t in thresholds(window))
        marks = mark_dir()
        marks.mkdir(parents=True, exist_ok=True)
        prune(marks)
        mark = marks / re.sub(r"[^A-Za-z0-9_-]", "_", str(data.get("session_id") or data["transcript_path"]))
        if level == 0:
            mark.unlink(missing_ok=True)
            return None
        shown = int(mark.read_text() or 0) if mark.exists() else 0
        if level <= shown:
            return None
        mark.write_text(str(level))
        return json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": message(used, window, level)}}, ensure_ascii=False)
    except Exception:
        return None


if __name__ == "__main__":
    out = main(sys.stdin.read())
    if out:
        print(out)
