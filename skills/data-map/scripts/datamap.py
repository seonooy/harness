#!/usr/bin/env python3
"""CSV·TSV 여러 개를 SQLite 파일 하나에 담고, 표마다 키와 표끼리의 관계를 값으로 잰다.

파이썬 표준 라이브러리만 쓴다. 파일을 줄 단위로 읽고 정렬은 SQLite가 디스크에서 하므로
데이터가 커져도 메모리는 거의 그대로다. 명령 목록은 -h로 본다.
"""
import argparse
import codecs
import csv
import hashlib
import io
import itertools
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path(".datamap")
DB = HOME / "data.sqlite"
LOG = HOME / "build.log"
LOCK = HOME / "build.lock"
PROGRESS = HOME / "progress.json"
PROFILE = Path("notes") / "data-profile.md"
SVG = Path("notes") / "data-map.svg"
_rel_script = os.path.relpath(os.path.abspath(__file__))
SCRIPT = os.path.abspath(__file__) if _rel_script.startswith("..") else _rel_script

DATA_EXT = {".csv", ".tsv"}
TEXTLIKE_EXT = {".txt", ".dat"}
DOC_EXT = {".md", ".pdf", ".docx", ".hwp", ".hwpx", ".html", ".pptx"}
OTHER_DATA_EXT = {".xlsx", ".xls", ".json", ".jsonl", ".parquet", ".feather", ".db",
                  ".sqlite", ".xml", ".h5", ".zip", ".gz", ".bz2", ".7z"}
SKIP_DIRS = {".git", ".agents", ".datamap", ".handoff", ".venv", "venv", "node_modules",
             "__pycache__", "notes"}
SKIP_DOCS = {"agents.md", "claude.md", "decisions.md"}
NULLS = frozenset(["", "NULL", "null", "Null", "NA", "N/A", "n/a", "NaN", "nan", "None",
                   "none", "#N/A", "\\N"])
SCHEMA_VERSION = 3
FIELD_LIMIT = 4 << 20
SWALLOW_LINES = 1000
RELATION_SECONDS = 300
HEAD_BYTES = 1 << 20
PROBE_BYTES = 1 << 18
LOWCARD = 30
SAMPLE_ROWS = 2000
COMBO_SAMPLE_ROWS = 20000
SAMPLE_VALUES = 300
BATCH = 5000
DRAW_INCLUSION = 0.95
# 거의 키: 빈 값이 행의 5%까지, 겹친 값이 0.1%까지면 그 칸들만 빼고 행마다 다른 열로 본다.
NEAR_KEY_NULLS = 0.05
NEAR_KEY_DUPS = 0.001
SHOW_INCLUSION = 0.5
COMPOSITE_SECONDS = 120
MAX_DETAIL_COLUMNS = 40

INT, FLOAT, DATE, DATETIME = 1, 2, 4, 8
ALL_TYPES = INT | FLOAT | DATE | DATETIME
TYPE_KO = {"int": "정수", "float": "실수", "date": "날짜", "datetime": "날짜시간",
           "text": "글자", "empty": "빈 열"}
DELIM_KO = {",": "쉼표", "\t": "탭", ";": "세미콜론", "|": "세로줄"}
FLOAT_RE = re.compile(r"[-+]?(\d+\.\d*|\.\d+|\d+(\.\d*)?[eE][-+]?\d+)$")
DATE_RE = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$")
DT_RE = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}[ T]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?"
                   r"(Z|[+-]\d{2}:?\d{2})?$")
VERDICT_KO = {
    "drawn": "지도에 그림",
    "checked": "직접 확인, 지도에 그림",
    "ambiguous": "모호: 점수가 같은 부모가 여럿",
    "weak": "약함: 이름이 다르고, 정수 키이거나 부모를 조금만 덮음",
    "other": "같은 열에 더 맞는 부모가 있음",
    "reverse": "1:1이라 반대 방향만 그림",
    "checked-low": "직접 확인, 포함률 95% 미만",
    "checked-nm": "직접 확인, 부모 쪽이 키가 아니라(N:M) 지도에 안 그림",
    "low": "포함률 95% 미만",
    "dropped": "판정으로 뺌",
    "samekey": "키끼리 값이 맞음",
}
VERDICT_ORDER = {k: i for i, k in enumerate(VERDICT_KO)}

_replaced = [0]


def _count_replace(err):
    _replaced[0] += 1
    return ("\ufffd", err.end)


codecs.register_error("datamap", _count_replace)


# 따옴표가 안 닫힌 칸은 파일 끝까지 삼키므로, 칸 크기에 한도를 둬서 메모리가 같이 커지지 않게 한다.
csv.field_size_limit(FIELD_LIMIT)


class Timeout(Exception):
    pass


class Swallow(Exception):
    """한 행이 너무 많은 줄을 삼켰다. 따옴표가 닫히지 않은 칸으로 본다."""


def die(msg):
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def q(name):
    return '"' + str(name).replace('"', '""') + '"'


def chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def first_distinct(values, n):
    """빈 값을 빼고, 처음 나온 순서대로 서로 다른 값 n개까지."""
    out = []
    for v in values:
        if v is not None and v not in out:
            out.append(v)
            if len(out) >= n:
                break
    return out


def norm(s):
    return re.sub(r"[^0-9a-z가-힣]", "", str(s).lower())


def singular(s):
    if len(s) > 4 and s.endswith("ies"):
        return s[:-3] + "y"
    if len(s) > 4 and s.endswith(("ses", "xes", "zes", "ches", "shes")):
        return s[:-2]
    if len(s) > 3 and s.endswith("s") and not s.endswith("ss"):
        return s[:-1]
    return s


def name_score(src_col, tgt_col, tgt_table, same_table=False, generic=frozenset(), own_key=False):
    """열 이름이 그 표의 키를 가리킨다는 근거의 세기. 낱말의 뜻은 보지 않고 글자 모양만 본다.

    3 같은 이름이거나 표 이름 + 키 이름(customer_id → customers.id), 2 뒤가 같음(parent_lot_id → lot_id), 0 근거 없음.
    generic은 이 데이터에서 여러 표가 키 이름으로 쓰는 이름이다(id, code). 그런 이름은 어느 표를 가리키는지 못 가른다.
    own_key는 자식 열이 자식 표 자신의 키라는 뜻이다. 두 표의 키 이름이 같다는 것만으로는 한쪽이 부모인지 모른다.
    """
    s, t, tbl = norm(src_col), norm(tgt_col), norm(tgt_table)
    one = singular(tbl)
    if not s or s == t and same_table:
        return 0
    plain = t not in generic
    if same_table:
        return 2 if len(t) >= 3 and plain and s.endswith(t) else 0
    if s in (one + t, tbl + t):
        return 3
    if s == t and (plain or not own_key or len(one) >= 3 and (s.startswith(one) or s.startswith(tbl))):
        return 3
    if len(t) >= 3 and plain and s.endswith(t):
        return 2
    return 0


def named_after(r):
    """자식 열 이름이 부모 표 이름으로 시작한다(film_id → film)."""
    c, tbl = norm(json.loads(r["child_cols"])[0]), norm(r["parent"])
    return len(singular(tbl)) >= 3 and (c.startswith(singular(tbl)) or c.startswith(tbl))


def fmt_size(b):
    for unit in ("B", "KB", "MB"):
        if b < 1024:
            return f"{b:.0f}{unit}" if unit == "B" else f"{b:.1f}{unit}"
        b /= 1024
    return f"{b:.1f}GB"


def fmt_n(n):
    return "-" if n is None else f"{int(n):,}"


def pct(x):
    if x is None:
        return "-"
    if x >= 1:
        return "100%"
    return f"{x * 100:.1f}%"


def rel(p):
    try:
        r = os.path.relpath(p)
    except ValueError:
        return str(p)
    return str(Path(p).resolve()) if r.startswith("..") else r


def short(v, n=24):
    s = str(v).replace("\n", " ").replace("\r", " ")
    return s if len(s) <= n else s[:n - 1] + "…"


def md_cell(v, n=60):
    return short(v, n).replace("|", "\\|")


def jcols(s):
    return ",".join(json.loads(s))


def peak_mb():
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return r / (1024 * 1024) if sys.platform == "darwin" else r / 1024
    except Exception:
        return None


# ---------------------------------------------------------------- 파일 찾기와 모양 보기

def default_roots():
    if Path("data").is_dir():
        return ["data"]
    if Path("/data").is_dir():
        return ["/data"]
    return ["."]


def find_files(roots):
    data, docs, others = [], [], []
    for root in roots:
        root = Path(root)
        if not root.exists():
            die(f"없는 경로: {root}")
        walker = [(str(root.parent), [], [root.name])] if root.is_file() else os.walk(root)
        for dirpath, dirnames, filenames in walker:
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                p = Path(dirpath) / name
                ext = p.suffix.lower()
                readme = name.lower().startswith("readme")
                if ext in DATA_EXT or (ext in TEXTLIKE_EXT and not readme and looks_tabular(p)):
                    data.append(p)
                elif (ext in DOC_EXT or ext == ".txt" or readme) and name.lower() not in SKIP_DOCS:
                    docs.append(p)
                elif ext in OTHER_DATA_EXT or ext in TEXTLIKE_EXT:
                    others.append(p)
    docs.sort(key=lambda p: (not p.name.lower().startswith("readme"), str(p)))
    return data, docs, others


def read_probes(path, size):
    with open(path, "rb") as f:
        head = f.read(HEAD_BYTES)
        probes = [head]
        if size > HEAD_BYTES + 2 * PROBE_BYTES:
            for pos in (size // 2, size - PROBE_BYTES):
                f.seek(pos)
                chunk = f.read(PROBE_BYTES)
                nl = chunk.find(b"\n")
                if nl >= 0:
                    probes.append(chunk[nl + 1:])
    return head, probes


def detect_encoding(probes):
    head = probes[0]
    if head.startswith(codecs.BOM_UTF8):
        return "utf-8-sig", ""
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16", ""
    pairs = head[:4000]
    if pairs.count(0) > len(pairs) // 4:
        if pairs[1::2].count(0) > len(pairs) // 5:
            return "utf-16-le", "BOM 없는 UTF-16으로 보고 읽었다"
        if pairs[0::2].count(0) > len(pairs) // 5:
            return "utf-16-be", "BOM 없는 UTF-16으로 보고 읽었다"
    for enc in ("utf-8", "cp949"):
        try:
            for p in probes:
                codecs.getincrementaldecoder(enc)().decode(p, final=False)
            return enc, ""
        except UnicodeDecodeError:
            continue
    return "latin-1", "utf-8도 cp949도 아니어서 latin-1로 읽었다. 글자가 깨졌을 수 있다"


def vclass(v):
    s = v.strip()
    if s.isdigit():
        ok = len(s) <= 18 and (len(s) == 1 or s[0] != "0")
        return INT | FLOAT if ok else 0
    if s[:1] == "-" and s[1:].isdigit():
        ok = len(s) <= 19 and (len(s) == 2 or s[1] != "0")
        return INT | FLOAT if ok else 0
    if FLOAT_RE.match(s):
        return FLOAT
    if DT_RE.match(s):
        return DATETIME
    if DATE_RE.match(s):
        return DATE | DATETIME
    return 0


def type_name(possible, has_values):
    if not has_values:
        return "empty"
    for bit, name in ((INT, "int"), (FLOAT, "float"), (DATE, "date"), (DATETIME, "datetime")):
        if possible & bit:
            return name
    return "text"


def looks_like_data(cells):
    vals = [c.strip() for c in cells if c.strip()]
    return bool(vals) and all(vclass(v) for v in vals)


def detect_delim(lines, prefer_tab):
    order = ["\t", ",", ";", "|"] if prefer_tab else [",", "\t", ";", "|"]
    sample = "\n".join(lines)
    best, best_score = order[0], (-1.0, -1)
    for d in order:
        widths = [len(r) for r in csv.reader(io.StringIO(sample), delimiter=d) if r]
        if not widths:
            continue
        mode = max(set(widths), key=widths.count)
        if mode < 2:
            continue
        score = (round(widths.count(mode) / len(widths), 2), mode)
        if score > best_score:
            best, best_score = d, score
    return best


def looks_tabular(path):
    """.txt·.dat 가운데 구분자로 나뉜 표(엑셀의 유니코드 텍스트 저장 등)를 고른다."""
    try:
        with open(path, "rb") as f:
            head = f.read(1 << 16)
    except OSError:
        return False
    enc, _ = detect_encoding([head])
    text = codecs.getincrementaldecoder(enc)(errors="replace").decode(head, final=False).lstrip("\ufeff")
    lines = [ln for ln in text.splitlines()[:51] if ln.strip()][:50]
    if len(lines) < 3:
        return False
    d = detect_delim(lines, prefer_tab=True)
    widths = [len(r) for r in csv.reader(io.StringIO("\n".join(lines)), delimiter=d)]
    mode = max(set(widths), key=widths.count)
    return mode >= 2 and widths.count(mode) / len(widths) >= 0.9


def eff_width(row):
    n = len(row)
    while n and not row[n - 1].strip():
        n -= 1
    return n


def make_names(header, ncol):
    names, seen = [], set()
    for i in range(ncol):
        raw = re.sub(r"\s+", " ", header[i].replace("\ufeff", "")).strip() if i < len(header) else ""
        base = raw or f"col_{i + 1}"
        name, k = base, 2
        while name.lower() in seen or name.lower() == "_dm_file":
            name, k = f"{base}_{k}", k + 1
        seen.add(name.lower())
        names.append(name)
    return names


def sniff(path):
    st = path.stat()
    head, probes = read_probes(path, st.st_size)
    if head.startswith((b"\x1f\x8b", b"PK\x03\x04", b"BZh", b"7z\xbc\xaf")):
        raise ValueError("압축 파일이다. 풀고 다시 돌린다")
    enc, note = detect_encoding(probes)
    if not enc.startswith("utf-16") and head.count(0) > len(head) // 100 + 10:
        raise ValueError("글자 파일이 아닌 것 같다 (NUL 바이트가 많다)")
    whole = len(head) >= st.st_size
    text = codecs.getincrementaldecoder(enc)(errors="replace").decode(head, final=whole)
    text = text.lstrip("\ufeff").replace("\0", "")
    lines = text.splitlines()
    if not whole and lines:
        lines = lines[:-1]
    delim = detect_delim(lines[:200], path.suffix.lower() == ".tsv")
    parse_text = text if whole else "\n".join(lines[:200])
    rows = [r for r in csv.reader(io.StringIO(parse_text, newline=""), delimiter=delim) if any(c.strip() for c in r)]
    effs = [eff_width(r) for r in rows[:200]]
    mode_eff = max(set(effs), key=effs.count) if effs else 0
    # 공공데이터처럼 표 위에 '자료명', '단위' 같은 좁은 설명 줄이 있으면 건너뛴다.
    skip = next((i for i, w in enumerate(effs) if w >= mode_eff), 0) if mode_eff >= 2 else 0
    first = rows[skip] if rows else []
    has_header = bool(first) and not looks_like_data(first)
    body = rows[skip + 1:] if has_header else rows[skip:]
    widths = [len(r) for r in body[:200]] or [len(first)]
    mode = max(set(widths), key=widths.count)
    ncol = max(len(first), mode) if rows else 0
    if whole:
        est = len(body)
    else:
        est = max(int(head.count(b"\n") / max(len(head), 1) * st.st_size) - (1 if has_header else 0) - skip, 0)
    return {
        "path": str(path), "rel": rel(path), "size": st.st_size, "mtime_ns": st.st_mtime_ns,
        "encoding": enc, "encoding_note": note, "delimiter": delim, "has_header": has_header,
        "columns": make_names(first if has_header else [], ncol), "est_rows": est,
        "skip": skip, "skipped": [short(",".join(r).strip(","), 40) for r in rows[:skip][:3]],
    }


def group_files(infos, split=False):
    """번호만 다른 파일은 한 표로 묶는다. 이름이 다른 파일도 머리 줄이 같고 20개 이상이면 묶는다. split이면 파일마다 따로 둔다."""
    groups = {}
    for info in infos:
        stem_path = os.path.splitext(info["rel"])[0]
        key = (stem_path if split else re.sub(r"\d+", "#", stem_path), tuple(c.lower() for c in info["columns"]))
        groups.setdefault(key, []).append(info)
    by_header = defaultdict(list)
    for key in groups:
        by_header[key[1]].append(key)
    merged = []
    for keys in by_header.values():
        total = sum(len(groups[k]) for k in keys)
        if len(keys) > 1 and total >= 20 and not split:
            merged.append(sorted((f for k in keys for f in groups[k]), key=lambda i: i["rel"]))
        else:
            merged.extend(sorted(groups[k], key=lambda i: i["rel"]) for k in keys)
    used, out = set(), []
    for files in sorted(merged, key=lambda fs: fs[0]["rel"]):
        name = table_name(files, used)
        used.add(name.lower())
        out.append((name, files))
    return out


def table_name(files, used):
    stems = [Path(f["rel"]).stem for f in files]
    if len(files) == 1:
        base = stems[0]
    else:
        pat = re.sub(r"\d+", "#", stems[0])
        base = re.sub(r"^[#_\-. ]+|[#_\-. ]+$", "", pat).replace("#", "_") or os.path.commonprefix(stems)
    base = re.sub(r"[^0-9A-Za-z가-힣_]+", "_", base).strip("_") or "table"
    if base.lower().startswith(("_dm_", "sqlite_")):
        base = "t_" + base
    name, k = base, 2
    while name.lower() in used:
        name, k = f"{base}_{k}", k + 1
    return name


def signature(files, limit):
    parts = [[f["rel"], f["size"], f["mtime_ns"], f["encoding"], f["delimiter"], f["has_header"],
              f["columns"], f["skip"]] for f in files]
    raw = json.dumps(parts + [limit or 0], ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------- SQLite

def connect(write):
    tmp = HOME / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    # 큰 정렬이 쓰는 임시 파일을 RAM일 수 있는 /tmp가 아니라 작업 폴더 디스크에 둔다.
    os.environ["SQLITE_TMPDIR"] = str(tmp.resolve())
    import sqlite3
    if write:
        conn = sqlite3.connect(str(DB))
        conn.execute("PRAGMA synchronous=OFF")
    else:
        if not DB.exists():
            die(f"아직 build를 돌리지 않았다. 먼저: python3 {SCRIPT} build <데이터 폴더>")
        conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA cache_size=-65536")
    conn.execute("PRAGMA temp_store=1")
    return conn


class Budget:
    """질의 하나가 정한 시간을 넘으면 SQLite 쪽에서 멈추게 한다."""

    def __init__(self, conn, seconds):
        self.conn, self.seconds, self.deadline = conn, seconds, None
        conn.set_progress_handler(self._tick, 100000)

    def _tick(self):
        return 1 if self.deadline is not None and time.monotonic() > self.deadline else 0

    def all(self, sql, params=(), seconds=None):
        import sqlite3
        self.deadline = time.monotonic() + (seconds or self.seconds)
        try:
            return self.conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as e:
            if "interrupt" in str(e).lower():
                raise Timeout(sql) from None
            raise
        finally:
            self.deadline = None

    def one(self, sql, params=(), seconds=None):
        rows = self.all(sql, params, seconds)
        return rows[0] if rows else None


def init_meta(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS _dm_files(id INTEGER PRIMARY KEY, tbl TEXT, path TEXT, size INTEGER,
        encoding TEXT, encoding_note TEXT, delimiter TEXT, has_header INTEGER, skip_rows INTEGER,
        skipped TEXT, rows INTEGER, bad_rows INTEGER, bad_lines TEXT, blank_rows INTEGER,
        replaced INTEGER, truncated INTEGER, merged_lines INTEGER, repeated_headers INTEGER,
        parse_note TEXT, error TEXT);
    CREATE TABLE IF NOT EXISTS _dm_tables(name TEXT PRIMARY KEY, rows INTEGER, limit_rows INTEGER,
        signature TEXT, loaded INTEGER DEFAULT 0, truncated INTEGER DEFAULT 0, key_cols TEXT,
        key_kind TEXT, key_note TEXT, dup_groups INTEGER);
    CREATE TABLE IF NOT EXISTS _dm_columns(tbl TEXT, pos INTEGER, name TEXT, type TEXT,
        nulls INTEGER, distinct_n INTEGER, minv TEXT, maxv TEXT, avg_len REAL, top_values TEXT,
        examples TEXT, is_key INTEGER DEFAULT 0, note TEXT, null_words TEXT, PRIMARY KEY (tbl, name));
    CREATE TABLE IF NOT EXISTS _dm_relations(child TEXT, child_cols TEXT, parent TEXT,
        parent_cols TEXT, origin TEXT, child_rows INTEGER, child_distinct INTEGER, matched INTEGER,
        parent_rows INTEGER, parent_distinct INTEGER, inclusion REAL, coverage REAL,
        avg_fanout REAL, max_fanout INTEGER, orphan_rows INTEGER, orphan_examples TEXT,
        join_rows INTEGER, name_score INTEGER, verdict TEXT, note TEXT,
        PRIMARY KEY (child, child_cols, parent, parent_cols));
    CREATE TABLE IF NOT EXISTS _dm_run(key TEXT PRIMARY KEY, value TEXT);
    """)


def get_run(conn):
    try:
        row = conn.execute("SELECT value FROM _dm_run WHERE key='run'").fetchone()
    except Exception:
        return {}
    return json.loads(row[0]) if row else {}


def ensure_index(b, t, cols):
    name = "ix_" + hashlib.md5(json.dumps([t] + list(cols), ensure_ascii=False).encode()).hexdigest()[:16]
    b.all(f"CREATE INDEX IF NOT EXISTS {q(name)} ON {q(t)} ({', '.join(q(c) for c in cols)})")


_rid_cache = {}


def rid(conn, t):
    """사용자 열 이름과 겹치지 않는 SQLite 행 번호 이름을 고른다(rowid라는 열이 있을 수 있다)."""
    if t not in _rid_cache:
        cols = {r[1].lower() for r in conn.execute(f"PRAGMA table_info({q(t)})")}
        _rid_cache[t] = next((a for a in ("rowid", "_rowid_", "oid") if a not in cols), "rowid")
    return _rid_cache[t]


def sample_rows(conn, t, names, n):
    sel = ", ".join(q(c) for c in names)
    top = conn.execute(f"SELECT MAX({rid(conn, t)}) FROM {q(t)}").fetchone()[0] or 0
    if top <= n:
        return conn.execute(f"SELECT {sel} FROM {q(t)}").fetchall()
    ids = sorted(random.Random(f"{t}:{n}").sample(range(1, top + 1), n))
    out = []
    for part in chunks(ids, 500):
        out += conn.execute(f"SELECT {sel} FROM {q(t)} WHERE {rid(conn, t)} IN ({','.join('?' * len(part))})", part).fetchall()
    return out


def drop_table(conn, name):
    _rid_cache.pop(name, None)
    conn.execute(f"DROP TABLE IF EXISTS {q(name)}")
    for sql in ("DELETE FROM _dm_tables WHERE name=?", "DELETE FROM _dm_columns WHERE tbl=?",
                "DELETE FROM _dm_files WHERE tbl=?",
                "DELETE FROM _dm_relations WHERE child=? OR parent=?"):
        conn.execute(sql, (name,) * sql.count("?"))
    conn.commit()


# ---------------------------------------------------------------- 적재

class Log:
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")

    def __call__(self, msg=""):
        print(msg, flush=True)
        self.f.write(msg + "\n")
        self.f.flush()


class Progress:
    def __init__(self, log, total_est):
        self.log, self.total_est = log, max(total_est, 1)
        self.done = self.table_done = self.table_est = 0
        self.table, self.phase, self.detail = "", "적재", ""
        self.t0 = time.monotonic()
        self.last_write = self.last_log = self.t0
        self.write()

    def start(self, table, est):
        self.table, self.table_done, self.table_est = table, 0, est
        self.write()

    def tick(self, n):
        self.done += n
        self.table_done += n
        now = time.monotonic()
        if now - self.last_write >= 2:
            self.write(now)
        if now - self.last_log >= 10:
            self.last_log = now
            self.log(f"  {self.table}: {self.table_done:,}행 · 전체 {self.done:,}/약 {self.total_est:,}행 · "
                     f"초당 {self.rate(now):,.0f}행")

    def rate(self, now=None):
        return self.done / max((now or time.monotonic()) - self.t0, 1e-9)

    def set_phase(self, phase, detail=""):
        self.phase, self.detail = phase, detail
        self.write()

    def write(self, now=None):
        now = now or time.monotonic()
        self.last_write = now
        data = {"phase": self.phase, "detail": self.detail, "table": self.table,
                "table_done": self.table_done, "table_est": self.table_est, "done": self.done,
                "total_est": self.total_est, "rate": self.rate(now), "elapsed": now - self.t0,
                "at": time.time()}
        tmp = PROGRESS.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, PROGRESS)


class Stats:
    def __init__(self, n):
        self.nulls = [0] * n
        self.possible = [ALL_TYPES] * n
        self.counters = [{} for _ in range(n)]
        self.null_words = [{} for _ in range(n)]   # 빈 값으로 읽은 글자(NA, null 같은)와 횟수

    def merge(self, o):
        for i in range(len(self.nulls)):
            self.nulls[i] += o.nulls[i]
            self.possible[i] &= o.possible[i]
            for w, n in o.null_words[i].items():
                self.null_words[i][w] = self.null_words[i].get(w, 0) + n
            a, b = self.counters[i], o.counters[i]
            if a is None or b is None:
                self.counters[i] = None
                continue
            for v, n in b.items():
                a[v] = a.get(v, 0) + n
            if len(a) > LOWCARD:
                self.counters[i] = None


def read_rows(conn, insert, reader, f, ncol, keep, limit, fid, st, res, prog):
    nulls, possible, counters, null_words = st.nulls, st.possible, st.counters, st.null_words
    to_skip = f["skip"] + (1 if f["has_header"] else 0)
    header, h0 = None, None
    delim = f["delimiter"]
    rng = range(keep)
    batch, rows, last_line = [], 0, 0
    for row in reader:
        span = reader.line_num - last_line
        last_line = reader.line_num
        if span > 1:
            res["merged"] += span - 1
            if span > SWALLOW_LINES:
                raise Swallow(last_line - span + 1)
        if to_skip:
            if any(c.strip() for c in row):
                to_skip -= 1
                if to_skip == 0 and f["has_header"]:
                    header, h0 = row, row[0]
            continue
        if header is not None and row and row[0] == h0 and row == header:
            res["repeated"] += 1
            continue
        n = len(row)
        if n != ncol:
            if n == 0 or (n == 1 and not row[0].strip()):
                res["blank"] += 1
                continue
            res["bad"] += 1
            if len(res["bad_lines"]) < 3:
                res["bad_lines"].append(reader.line_num)
            if n < ncol:
                row.extend([""] * (ncol - n))
            else:
                row[ncol - 1:] = [delim.join(row[ncol - 1:])]
        if keep < ncol:
            del row[keep:]
        if limit and rows >= limit:
            res["truncated"] = True
            break
        for i in rng:
            v = row[i]
            if v in NULLS or v.isspace():
                row[i] = None
                nulls[i] += 1
                if v and not v.isspace():
                    null_words[i][v] = null_words[i].get(v, 0) + 1
                continue
            c = counters[i]
            if c is not None:
                c[v] = c.get(v, 0) + 1
                if len(c) > LOWCARD:
                    counters[i] = None
            p = possible[i]
            if p:
                possible[i] = p & vclass(v)
        if fid is not None:
            row.append(fid)
        batch.append(row)
        rows += 1
        if len(batch) >= BATCH:
            conn.executemany(insert, batch)
            batch = []
            prog.tick(BATCH)
    if batch:
        conn.executemany(insert, batch)
        prog.tick(len(batch))
    res["rows"] = rows


def load_file(conn, insert, f, ncol, keep, limit, fid, prog):
    """보통 방식으로 읽고, NUL 문자면 지우고 다시, 따옴표가 깨졌으면 따옴표를 글자로 보고 다시 읽는다."""
    attempt, note = "plain", ""
    while True:
        st = Stats(keep)
        res = {"rows": 0, "bad": 0, "bad_lines": [], "blank": 0, "truncated": False, "merged": 0,
               "repeated": 0, "note": note}
        _replaced[0] = 0
        before = prog.done
        try:
            with open(f["path"], "r", encoding=f["encoding"], errors="datamap", newline="") as fh:
                src = fh if attempt == "plain" else (line.replace("\0", "") for line in fh)
                quoting = csv.QUOTE_NONE if attempt == "noquote" else csv.QUOTE_MINIMAL
                read_rows(conn, insert, csv.reader(src, delimiter=f["delimiter"], quoting=quoting), f, ncol, keep,
                          limit, fid, st, res, prog)
            res["replaced"] = _replaced[0]
            return st, res
        except (csv.Error, Swallow) as e:
            conn.rollback()
            prog.done = before
            if attempt == "plain" and isinstance(e, csv.Error) and "NUL" in str(e):
                attempt = "nul"
            elif attempt != "noquote":
                where = f"줄 {e.args[0]:,}부터 {SWALLOW_LINES:,}줄 넘게 한 칸에 들어갔다" if isinstance(e, Swallow) else str(e)[:120]
                attempt, note = "noquote", f"따옴표가 닫히지 않은 칸이 있어({where}) 따옴표를 글자로 보고 다시 읽었다"
            else:
                raise


def load_table(conn, name, files, limit, log, prog, problems):
    import sqlite3
    ncol = len(files[0]["columns"])
    multi = len(files) > 1
    max_cols = (1990 if sqlite3.sqlite_version_info >= (3, 32, 0) else 990) - int(multi)
    keep = min(ncol, max_cols)
    cols = files[0]["columns"][:keep]
    if keep < ncol:
        problems.append(f"{name}: 열이 {ncol:,}개라 SQLite 한도 때문에 앞 {keep:,}개만 담았다. "
                        f"나머지 열 이름: {', '.join(files[0]['columns'][keep:keep + 10])} …")
    drop_table(conn, name)
    names = cols + (["_dm_file"] if multi else [])
    try:
        conn.execute(f"CREATE TABLE {q(name)} ({', '.join(q(c) for c in names)})")
    except Exception as e:
        problems.append(f"{name}: 표를 만들 수 없다 ({e})")
        return
    conn.commit()
    insert = f"INSERT INTO {q(name)} VALUES ({', '.join(['?'] * len(names))})"
    prog.start(name, sum(min(f["est_rows"], limit) if limit else f["est_rows"] for f in files))
    log(f"{name}: 파일 {len(files)}개 읽는 중")
    total, rows_total, truncated = Stats(keep), 0, False
    for f in files:
        cur = conn.execute(
            "INSERT INTO _dm_files(tbl, path, size, encoding, encoding_note, delimiter, has_header, skip_rows, skipped)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (name, f["rel"], f["size"], f["encoding"], f["encoding_note"], f["delimiter"], int(f["has_header"]),
             f["skip"], json.dumps(f["skipped"], ensure_ascii=False)))
        fid = cur.lastrowid
        conn.commit()
        try:
            st, res = load_file(conn, insert, f, len(f["columns"]), keep, limit, fid if multi else None, prog)
            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.execute("UPDATE _dm_files SET error=? WHERE id=?", (str(e)[:300], fid))
            conn.commit()
            problems.append(f"{f['rel']}: 읽지 못했다 ({str(e)[:200]})")
            log(f"  {f['rel']}: 읽지 못했다 — {e}")
            continue
        total.merge(st)
        rows_total += res["rows"]
        truncated = truncated or res["truncated"]
        conn.execute(
            "UPDATE _dm_files SET rows=?, bad_rows=?, bad_lines=?, blank_rows=?, replaced=?, truncated=?, "
            "merged_lines=?, repeated_headers=?, parse_note=? WHERE id=?",
            (res["rows"], res["bad"], json.dumps(res["bad_lines"]), res["blank"], res["replaced"],
             int(res["truncated"]), res["merged"], res["repeated"], res["note"], fid))
    for i, c in enumerate(cols):
        top = total.counters[i]
        top_json = json.dumps(sorted(top.items(), key=lambda kv: (-kv[1], kv[0])), ensure_ascii=False) if top is not None else None
        conn.execute(
            "INSERT INTO _dm_columns(tbl, pos, name, type, nulls, distinct_n, top_values, null_words) VALUES (?,?,?,?,?,?,?,?)",
            (name, i, c, type_name(total.possible[i], total.nulls[i] < rows_total), total.nulls[i],
             len(top) if top is not None else None, top_json,
             json.dumps(total.null_words[i], ensure_ascii=False) if total.null_words[i] else None))
    conn.execute(
        "INSERT INTO _dm_tables(name, rows, limit_rows, signature, loaded, truncated) VALUES (?,?,?,?,1,?)",
        (name, rows_total, limit or 0, signature(files, limit), int(truncated)))
    conn.commit()
    log(f"{name}: {rows_total:,}행 읽음" + (" (앞부분만)" if truncated else ""))


# ---------------------------------------------------------------- 분석

def analyze_table(conn, b, t, problems, prog):
    prog.set_phase("분석", f"{t}: 열 범위")
    rows = conn.execute("SELECT rows FROM _dm_tables WHERE name=?", (t,)).fetchone()[0] or 0
    cols = [dict(r) for r in conn.execute(
        "SELECT pos, name, type, nulls, distinct_n, top_values, null_words FROM _dm_columns WHERE tbl=? ORDER BY pos", (t,))]
    for c in cols:
        c["top"] = json.loads(c["top_values"]) if c["top_values"] else None
        c.update(avg_len=None, minv=None, maxv=None, examples=[], is_key=0, note="")
    usable = [c for c in cols if c["type"] != "empty"]
    sample, kind, key_cols, key_note, dup_groups = {}, "none", [], "", None
    if rows and usable:
        for part in chunks(usable, 150):
            exprs = []
            for c in part:
                col = q(c["name"])
                cast = {"int": "INTEGER", "float": "REAL"}.get(c["type"])
                v = f"CAST({col} AS {cast})" if cast else col
                exprs += [f"MIN({v})", f"MAX({v})", f"AVG(LENGTH({col}))"]
            try:
                vals = b.one(f"SELECT {', '.join(exprs)} FROM {q(t)}")
            except Timeout:
                problems.append(f"{t}: 열 범위 재기 시간 초과")
                continue
            for i, c in enumerate(part):
                c["minv"], c["maxv"], c["avg_len"] = vals[3 * i], vals[3 * i + 1], vals[3 * i + 2]
        names = [c["name"] for c in usable]
        srows = sample_rows(conn, t, names, SAMPLE_ROWS)
        sample = {n: [r[i] for r in srows] for i, n in enumerate(names)}
        for c in usable:
            c["examples"] = first_distinct(sample[c["name"]], 3)
            if c["type"] == "int" and c["minv"] is not None and 19000101 <= c["minv"] and c["maxv"] <= 21001231:
                c["note"] = "YYYYMMDD 날짜일 수 있다"
        prog.set_phase("분석", f"{t}: 키")
        keys = find_single_keys(b, t, usable, rows, sample, problems)
        find_near_keys(b, t, usable, rows, sample, problems)
        # 처음에는 맨 왼쪽의 깨끗한 키를 고른다. 관계를 잰 뒤 rekey가 다른 표들이 가리키는 열로 바꾼다.
        pool = keys or [c for c in usable if c.get("near")]
        manual = conn.execute("SELECT key_cols, key_note FROM _dm_tables WHERE name=? AND key_kind='manual'", (t,)).fetchone()
        if manual and set(json.loads(manual[0])) <= {c["name"] for c in cols}:
            kind, key_cols, key_note = "manual", json.loads(manual[0]), manual[1]
        elif rows < 2:
            kind = "single-row"
        elif pool:
            best = min(pool, key=lambda c: (c["type"] not in ("int", "text"), c["pos"]))
            kind, key_cols = ("single" if best["is_key"] else "near"), [best["name"]]
            if not best["is_key"]:
                key_note = best["note"]
        else:
            combo, key_note = find_composite(conn, b, t, usable, rows, problems)
            if combo:
                kind, key_cols = "composite", combo
            else:
                try:
                    all_cols = ", ".join(q(c["name"]) for c in cols)
                    r = b.one(f"SELECT COUNT(*) FROM (SELECT 1 FROM {q(t)} GROUP BY {all_cols} HAVING COUNT(*) > 1)", seconds=60)
                    dup_groups = r[0]
                except Timeout:
                    problems.append(f"{t}: 완전히 같은 행 세기 시간 초과")
    for c in cols:
        conn.execute(
            "UPDATE _dm_columns SET distinct_n=?, minv=?, maxv=?, avg_len=?, examples=?, is_key=?, note=? WHERE tbl=? AND name=?",
            (rows if c["is_key"] else c["distinct_n"], None if c["minv"] is None else str(c["minv"]),
             None if c["maxv"] is None else str(c["maxv"]), c["avg_len"],
             json.dumps(c["examples"], ensure_ascii=False), c["is_key"], c["note"], t, c["name"]))
    conn.execute("UPDATE _dm_tables SET key_cols=?, key_kind=?, key_note=?, dup_groups=? WHERE name=?",
                 (json.dumps(key_cols, ensure_ascii=False), kind, key_note, dup_groups, t))
    conn.commit()
    return {"rows": rows, "cols": {c["name"]: c for c in cols}, "sample": sample,
            "keys": [c["name"] for c in cols if c["is_key"]], "key_cols": key_cols, "kind": kind,
            "near": [c["name"] for c in cols if c.get("near")]}


def find_single_keys(b, t, usable, rows, sample, problems):
    keys = []
    if rows < 2:
        return keys
    for c in usable:
        if c["type"] == "float" or c["nulls"] or (c["avg_len"] or 0) > 64:
            continue
        if c["top"] is not None:
            if len(c["top"]) != rows:
                continue
        else:
            vals = sample[c["name"]]
            if len(set(vals)) < len(vals):
                continue
        try:
            ensure_index(b, t, [c["name"]])
            dup = b.all(f"SELECT 1 FROM {q(t)} GROUP BY {q(c['name'])} HAVING COUNT(*) > 1 LIMIT 1")
        except Timeout:
            problems.append(f"{t}.{c['name']}: 키인지 재기 시간 초과")
            continue
        if not dup:
            c["is_key"] = 1
            keys.append(c)
    return keys


def find_near_keys(b, t, usable, rows, sample, problems):
    """몇 칸만 어긋나 키에서 떨어진 열을 찾아 표시한다. 다른 표가 가리키는 부모 열일 수 있다.

    실제 데이터의 부모 열은 깨끗하지 않다: 국가 코드 NA를 빈 값으로 읽거나, 선수 1명이 두 번 들어가 있다.
    "문제"에 적을 글은 여기서 만들어 두고, 그 열이 쓰일 때 rekey가 적는다.
    """
    for c in usable:
        if c["is_key"] or c["type"] == "float" or (c["avg_len"] or 0) > 64:
            continue
        nulls = c["nulls"] or 0
        filled = rows - nulls
        allowed = int(filled * NEAR_KEY_DUPS)
        if filled < 2 or nulls > max(1, rows * NEAR_KEY_NULLS) or (not nulls and not allowed):
            continue
        if c["top"] is not None:
            if len(c["top"]) < filled - allowed:
                continue
        else:
            vals = [v for v in sample[c["name"]] if v is not None]
            if len(vals) - len(set(vals)) > max(1, len(vals) // 100):
                continue
        try:
            ensure_index(b, t, [c["name"]])
            col = q(c["name"])
            _, extra = b.one(f"SELECT COUNT(*), TOTAL(n - 1) FROM (SELECT COUNT(*) AS n FROM {q(t)} "
                             f"WHERE {col} IS NOT NULL GROUP BY {col} HAVING COUNT(*) > 1 LIMIT {allowed + 1})")
        except Timeout:
            problems.append(f"{t}.{c['name']}: 거의 키인지 재기 시간 초과")
            continue
        dups = int(extra)
        if dups > allowed:
            continue
        c["near"] = True
        c["distinct_n"] = filled - dups
        dirt = [f"빈 값 {fmt_n(nulls)}건"] if nulls else []
        if dups:
            dirt.append(f"겹친 값 {fmt_n(dups)}건")
        c["note"] = "거의 키: " + ", ".join(dirt)
        msg = f"{t}.{c['name']}: 거의 키다. {', '.join(dirt)}만 빼면 행마다 값이 다르다. 다른 표가 가리키는 부모 열일 수 있어 관계 후보에 넣었다"
        words = json.loads(c["null_words"]) if c.get("null_words") else {}
        if words:
            msg += (". 빈 값 중 " + ", ".join(f"'{w}' {fmt_n(n)}건" for w, n in sorted(words.items()))
                    + "은 원래 글자였다. 진짜 값이면(코드 NA 같은) 이 열과 이 열을 가리키는 열에서 그 값이 빈 값으로 들어가 있다")
        c["near_msg"] = msg


def find_composite(conn, b, t, usable, rows, problems):
    cands = [c for c in usable if c["type"] != "float" and (c["nulls"] or 0) <= rows * NEAR_KEY_NULLS
             and (c["avg_len"] or 0) <= 64]
    if len(cands) < 2:
        return None, "한 행을 정하는 열이 없다"
    names = [c["name"] for c in cands]
    big = sample_rows(conn, t, names, COMBO_SAMPLE_ROWS)
    pos = {n: i for i, n in enumerate(names)}
    sd = {n: len({r[i] for r in big}) for i, n in enumerate(names)}
    # 다른 표에도 같은 이름으로 있는 열(doc, lecture_id 같은)이 키의 일부일 가능성이 높다. 해시처럼 긴 값은 뒤로 미룬다.
    shared = {r[0]: r[1] for r in conn.execute("SELECT LOWER(name), COUNT(DISTINCT tbl) FROM _dm_columns GROUP BY LOWER(name)")}

    def rank(c):
        n = shared.get(c["name"].lower(), 1)
        return (n <= 1, (c["avg_len"] or 0) > 20, -n, -sd[c["name"]], c["pos"])

    ranked = sorted((c for c in cands if sd[c["name"]] >= 2), key=rank)[:6]
    deadline = time.monotonic() + COMPOSITE_SECONDS
    for size in (2, 3):
        for combo in itertools.combinations(ranked, size):
            idx = [pos[c["name"]] for c in combo]
            tuples = [tuple(r[i] for i in idx) for r in big]
            if len(set(tuples)) < len(tuples):
                continue
            left = deadline - time.monotonic()
            if left <= 1:
                problems.append(f"{t}: 열 조합 키 찾기 시간 초과")
                return None, "열 조합 확인 시간 초과"
            cols_sql = ", ".join(q(c["name"]) for c in combo)
            try:
                dup = b.all(f"SELECT 1 FROM {q(t)} GROUP BY {cols_sql} HAVING COUNT(*) > 1 LIMIT 1", seconds=left)
            except Timeout:
                problems.append(f"{t}: 열 조합 키 찾기 시간 초과")
                return None, "열 조합 확인 시간 초과"
            if not dup:
                holes = ", ".join(f"{c['name']}에 빈 값 {fmt_n(c['nulls'])}건" for c in combo if c["nulls"])
                return [c["name"] for c in sorted(combo, key=lambda c: c["pos"])], holes
    return None, f"열 {min(len(ranked), 3)}개 조합까지 봤지만 한 행을 정하는 조합이 없다"


def compatible(x, y):
    # 실수·날짜·시각은 관계로 보지 않는다. 같은 시각에 만든 행끼리 created_at이 우연히 맞는다.
    if {x, y} & {"float", "empty", "date", "datetime"}:
        return False
    return x == y or "text" in (x, y)


def find_relations(conn, b, metas, problems, prog):
    conn.execute("DELETE FROM _dm_relations WHERE origin='auto'")
    checked = {(r[0], r[1], r[2], r[3]) for r in conn.execute(
        "SELECT child, child_cols, parent, parent_cols FROM _dm_relations WHERE origin IN ('check', 'drop')")}
    targets = [(t, k) for t, m in metas.items() for k in m["keys"] + m["near"]]
    # 여러 표가 같은 이름을 키로 쓰면(id, code) 그 이름만으로는 어느 표를 가리키는지 알 수 없다.
    key_names = Counter(norm(m["key_cols"][0]) for m in metas.values() if len(m["key_cols"]) == 1)
    generic = frozenset(n for n, c in key_names.items() if c > 1)
    deadline = time.monotonic() + RELATION_SECONDS
    for t, m in metas.items():
        prog.set_phase("관계", t)
        for a in m["cols"].values():
            if time.monotonic() > deadline:
                problems.append(f"관계 찾기가 {RELATION_SECONDS}초를 넘어 {t}.{a['name']}부터는 보지 못했다. "
                                "필요한 관계는 check로 잰다")
                conn.commit()
                return
            if a["type"] in ("float", "empty") or (a["avg_len"] or 0) > 64:
                continue
            vals = first_distinct(m["sample"].get(a["name"], []), SAMPLE_VALUES)
            if not vals and (a["nulls"] or 0) < m["rows"]:
                try:
                    vals = [r[0] for r in b.all(f"SELECT DISTINCT {q(a['name'])} FROM {q(t)} "
                                                f"WHERE {q(a['name'])} IS NOT NULL LIMIT {SAMPLE_VALUES}")]
                except Timeout:
                    vals = []
            if not vals:
                continue
            own_key = m["key_cols"] == [a["name"]]
            own_plain = []   # 자기 표의 키인데 이름 근거가 없는 후보. 가장 큰 부모 몇 개만 잰다
            for p, k in targets:
                # 같은 표의 키를 가리키는 열. 글자 키는 값이 우연히 다 들어가기 어려워 이름 단서 없이도 잰다.
                # 정수 키는 수량·상태 코드도 다 들어가므로 이름 단서가 있을 때만 잰다.
                if p == t and (k == a["name"] or metas[p]["cols"][k]["type"] == "int"
                               and name_score(a["name"], k, p, same_table=True, generic=generic) < 1):
                    continue
                pm = metas[p]
                if not compatible(a["type"], pm["cols"][k]["type"]):
                    continue
                if a["top"] is not None and len(a["top"]) > pm["rows"] / 0.9:
                    continue
                rkey = (t, json.dumps([a["name"]], ensure_ascii=False), p, json.dumps([k], ensure_ascii=False))
                if rkey in checked:
                    continue
                try:
                    hit = 0
                    for part in chunks(vals, 400):
                        hit += b.one(f"SELECT COUNT(*) FROM {q(p)} WHERE {q(k)} IN ({','.join('?' * len(part))})", part)[0]
                except Timeout:
                    problems.append(f"{t}.{a['name']} → {p}.{k}: 표본 대조 시간 초과")
                    continue
                if hit / len(vals) < 0.6:
                    continue
                ns = name_score(a["name"], k, p, same_table=(p == t), generic=generic, own_key=own_key)
                if own_key and ns < 1:
                    # 두 표의 키끼리 값이 맞는 경우다. 같은 키를 가진 표가 여럿이면 그 키가 전부 들어 있는 가장 큰 표가
                    # 그 대상을 정하는 표이므로 큰 부모부터 잰다.
                    own_plain.append((-pm["rows"], p, k, rkey))
                    continue
                rm = measure(b, t, [a["name"]], p, [k], problems, parent_unique=k in pm["keys"])
                save_relation(conn, rkey, "auto", rm, ns)
                if a["distinct_n"] is None and rm["child_distinct"] is not None:
                    a["distinct_n"] = rm["child_distinct"]
                    conn.execute("UPDATE _dm_columns SET distinct_n=? WHERE tbl=? AND name=?",
                                 (rm["child_distinct"], t, a["name"]))
            for _, p, k, rkey in sorted(own_plain)[:8]:
                save_relation(conn, rkey, "auto", measure(b, t, [a["name"]], p, [k], problems, parent_unique=k in metas[p]["keys"]), 0)
        conn.commit()
    find_composite_relations(conn, b, metas, checked, problems, deadline, generic)
    conn.commit()


def find_composite_relations(conn, b, metas, checked, problems, deadline, generic):
    """열 여럿이 키인 표를 가리키는 관계를 찾는다. 키 열마다 값이 들어맞는 자식 열을 고르고, 그 조합을 값으로 잰다.

    열 이름이 달라도(승자 팀, 패자 팀이 팀 표를 가리킬 때) 값이 맞으면 후보가 된다. 이름은 그릴지 정할 때만 쓴다.
    """
    for p, pm in metas.items():
        keys = pm["key_cols"]
        if len(keys) < 2:
            continue
        try:
            for k in keys:
                ensure_index(b, p, [k])
        except Timeout:
            problems.append(f"{p}: 여러 열 키의 색인 만들기 시간 초과")
            continue
        for t, m in metas.items():
            if t == p:
                continue
            if time.monotonic() > deadline:
                problems.append(f"관계 찾기가 {RELATION_SECONDS}초를 넘어 여러 열 관계는 다 보지 못했다")
                return
            options = []
            for k in keys:
                kt = pm["cols"][k]["type"]
                found = []
                for c in m["cols"].values():
                    if not compatible(c["type"], kt) or (c["avg_len"] or 0) > 64:
                        continue
                    vals = first_distinct(m["sample"].get(c["name"], []), 40)
                    if not vals:
                        continue
                    try:
                        hit = b.one(f"SELECT COUNT(*) FROM (SELECT DISTINCT {q(k)} FROM {q(p)} "
                                    f"WHERE {q(k)} IN ({','.join('?' * len(vals))}))", vals)[0]
                    except Timeout:
                        continue
                    if hit / len(vals) >= 0.6:
                        found.append((name_score(c["name"], k, p, generic=generic), hit / len(vals), c["name"]))
                options.append(sorted(found, reverse=True)[:4])
            if not all(options):
                continue
            cond = " AND ".join(f"p.{q(k)} IS v.column{i + 1}" for i, k in enumerate(keys))
            for combo in itertools.product(*options):
                mapped = [c[2] for c in combo]
                if len(set(mapped)) < len(mapped):
                    continue
                rkey = (t, json.dumps(mapped, ensure_ascii=False), p, json.dumps(keys, ensure_ascii=False))
                if rkey in checked:
                    continue
                tuples = []
                for row in zip(*(m["sample"].get(c, []) for c in mapped)):
                    if any(v is not None for v in row) and row not in tuples:
                        tuples.append(row)
                        if len(tuples) >= SAMPLE_VALUES:
                            break
                if not tuples:
                    continue
                try:
                    ensure_index(b, p, keys)
                    hit = 0
                    for part in chunks(tuples, max(1, 400 // len(keys))):
                        values = ", ".join("(" + ", ".join("?" * len(keys)) + ")" for _ in part)
                        hit += b.one(f"SELECT COUNT(*) FROM (VALUES {values}) v "
                                     f"WHERE EXISTS (SELECT 1 FROM {q(p)} p WHERE {cond})",
                                     [v for row in part for v in row])[0]
                except Timeout:
                    problems.append(f"{t}.{','.join(mapped)} → {p}.{','.join(keys)}: 표본 대조 시간 초과")
                    continue
                if hit / len(tuples) < 0.6:
                    continue
                rm = measure(b, t, mapped, p, keys, problems, parent_unique=True)
                save_relation(conn, rkey, "auto", rm, min(c[0] for c in combo))


def measure(b, child, ccols, parent, pcols, problems, parent_unique=False):
    label = f"{child}.{','.join(ccols)} → {parent}.{','.join(pcols)}"
    m = dict.fromkeys(("child_rows", "child_distinct", "matched", "parent_rows", "parent_distinct",
                       "inclusion", "coverage", "avg_fanout", "max_fanout", "orphan_rows", "join_rows"))
    m["orphan_examples"] = "[]"
    try:
        ensure_index(b, parent, pcols)
        ensure_index(b, child, ccols)
    except Timeout:
        problems.append(f"{label}: 색인 만들기 시간 초과")
        return m
    C, P = q(child), q(parent)
    # 열이 여럿이면 빈 값도 하나의 값으로 본다. 번호 뒤에 붙는 꼬리표처럼 대부분 비어 있는 열이 키의 한 부분일 수 있다.
    # 모든 열이 빈 행만 "가리키는 것이 없다"로 보고 뺀다.
    eq = "=" if len(ccols) == 1 else "IS"
    cn = "(" + " OR ".join(f"{q(c)} IS NOT NULL" for c in ccols) + ")"
    cn_c = "(" + " OR ".join(f"c.{q(c)} IS NOT NULL" for c in ccols) + ")"
    pn = "(" + " OR ".join(f"{q(c)} IS NOT NULL" for c in pcols) + ")"
    csel = ", ".join(q(c) for c in ccols)
    psel = ", ".join(q(c) for c in pcols)
    d_alias = ", ".join(f"{q(c)} AS v{i}" for i, c in enumerate(ccols))
    p_alias = ", ".join(f"{q(c)} AS w{i}" for i, c in enumerate(pcols))
    on_d = " AND ".join(f"p.{q(c)} {eq} d.v{i}" for i, c in enumerate(pcols))
    on_c = " AND ".join(f"p.{q(pc)} {eq} c.{q(cc)}" for pc, cc in zip(pcols, ccols))
    on_j = " AND ".join(f"l.v{i} {eq} r.w{i}" for i in range(len(ccols)))

    def run(sql, what):
        try:
            return b.one(sql)
        except Timeout:
            problems.append(f"{label}: {what} 재기 시간 초과")
            return None

    r = run(f"SELECT COUNT(*) FROM {C} WHERE {cn}", "자식 행 수")
    m["child_rows"] = r[0] if r else None
    r = run(f"SELECT COUNT(*), TOTAL(EXISTS (SELECT 1 FROM {P} p WHERE {on_d})) "
            f"FROM (SELECT DISTINCT {d_alias} FROM {C} WHERE {cn}) d", "포함률")
    if r:
        m["child_distinct"], m["matched"] = r[0], int(r[1])
    r = run(f"SELECT COUNT(*) FROM {P} WHERE {pn}", "부모 행 수")
    m["parent_rows"] = r[0] if r else None
    if parent_unique:
        m["parent_distinct"] = m["parent_rows"]
    else:
        r = run(f"SELECT COUNT(*) FROM (SELECT DISTINCT {psel} FROM {P} WHERE {pn})", "부모 값 수")
        m["parent_distinct"] = r[0] if r else None
    r = run(f"SELECT AVG(n), MAX(n) FROM (SELECT COUNT(*) AS n FROM {C} WHERE {cn} GROUP BY {csel})", "값 하나당 행 수")
    if r:
        m["avg_fanout"], m["max_fanout"] = r[0], r[1]
    if m["matched"] is not None:
        if m["matched"] < m["child_distinct"]:
            try:
                ex = b.all(f"SELECT DISTINCT {', '.join('c.' + q(c) for c in ccols)} FROM {C} c "
                           f"WHERE {cn_c} AND NOT EXISTS (SELECT 1 FROM {P} p WHERE {on_c}) LIMIT 3")
                m["orphan_examples"] = json.dumps([x[0] if len(ccols) == 1 else list(x) for x in ex], ensure_ascii=False)
            except Timeout:
                problems.append(f"{label}: 고아 값 예시 찾기 시간 초과")
            r = run(f"SELECT COUNT(*) FROM {C} c WHERE {cn_c} AND NOT EXISTS (SELECT 1 FROM {P} p WHERE {on_c})", "고아 행 수")
            m["orphan_rows"] = r[0] if r else None
        else:
            m["orphan_rows"] = 0
        m["inclusion"] = m["matched"] / m["child_distinct"] if m["child_distinct"] else None
        if m["parent_distinct"]:
            m["coverage"] = m["matched"] / m["parent_distinct"]
    unique = m["parent_distinct"] is not None and m["parent_distinct"] == m["parent_rows"]
    if unique:
        if m["child_rows"] is not None and m["orphan_rows"] is not None:
            m["join_rows"] = m["child_rows"] - m["orphan_rows"]
    else:
        r = run(f"SELECT TOTAL(l.n * r.n) FROM (SELECT {d_alias}, COUNT(*) AS n FROM {C} WHERE {cn} GROUP BY {csel}) l "
                f"JOIN (SELECT {p_alias}, COUNT(*) AS n FROM {P} WHERE {pn} GROUP BY {psel}) r ON {on_j}", "조인 행 수")
        m["join_rows"] = int(r[0]) if r else None
    return m


def one_row_parent(rows, distinct):
    """부모 쪽 값이 행마다 다른가. 거의 키만큼(겹친 값 0.1%까지) 어긋난 것도 받는다. build와 check가 같은 기준을 쓴다."""
    return rows is not None and distinct is not None and rows - distinct <= rows * NEAR_KEY_DUPS


def one_to_one(r):
    """자식 쪽 값도 행마다 다르다."""
    return r["child_distinct"] is not None and r["child_distinct"] == r["child_rows"]


def included(r):
    """포함률이 지도에 그릴 만큼 높다."""
    return (r["inclusion"] or 0) >= DRAW_INCLUSION


def column_types(conn):
    return {(r[0], r[1]): r[2] for r in conn.execute("SELECT tbl, name, type FROM _dm_columns")}


def number_child(r, types):
    """자식 열이 모두 정수인 후보다. 프로파일과 build 로그가 같은 기준으로 센다."""
    return all(types.get((r["child"], c)) == "int" for c in json.loads(r["child_cols"]))


def arrow(r):
    return f"{r['child']}.{jcols(r['child_cols'])} → {r['parent']}.{jcols(r['parent_cols'])}"


def save_relation(conn, rkey, origin, m, score):
    cols = ("child_rows", "child_distinct", "matched", "parent_rows", "parent_distinct", "inclusion",
            "coverage", "avg_fanout", "max_fanout", "orphan_rows", "orphan_examples", "join_rows")
    conn.execute(
        f"INSERT OR REPLACE INTO _dm_relations(child, child_cols, parent, parent_cols, origin, "
        f"{', '.join(cols)}, name_score) VALUES ({','.join('?' * (len(cols) + 6))})",
        rkey + (origin,) + tuple(m[c] for c in cols) + (score,))


def choose(conn):
    rels = [dict(r) for r in conn.execute("SELECT * FROM _dm_relations")]

    def key(r):
        return (r["child"], r["child_cols"], r["parent"], r["parent_cols"])

    keys = {r[0]: json.loads(r[1] or "[]") for r in conn.execute("SELECT name, key_cols FROM _dm_tables")}

    def to_key(r):
        return keys.get(r["parent"]) == json.loads(r["parent_cols"])

    def evidence(r):
        # 키가 아닌 유일한 열(주소, 이메일)은 이름이 똑같을 때만 근거로 본다. 뒤만 같은 것은 값을 베껴 둔 열일 수 있다.
        ns = r["name_score"] or 0
        return ns if ns >= 3 or to_key(r) else 0

    def score(r):
        return (evidence(r), round(r["coverage"] or 0, 2))

    types = column_types(conn)

    def distinctive(r):
        # 1..N 같은 정수 키에는 수량·상태 코드 같은 작은 정수가 우연히 다 들어간다. 정수 키는 이름이 맞아야 그린다.
        return to_key(r) and any(types.get((r["parent"], c)) != "int" for c in json.loads(r["parent_cols"]))

    def own_key(r):
        return keys.get(r["child"]) == json.loads(r["child_cols"])

    link = {key(r) for r in rels if included(r)}
    verdict = {}
    by_src = defaultdict(list)
    for r in rels:
        if r["origin"] == "auto":
            by_src[(r["child"], r["child_cols"])].append(r)
    judged_no = {(r["child"], frozenset(json.loads(r["child_cols"]))) for r in rels if r["origin"] == "drop"}
    # 한 열은 부모 하나만 가리킨다. check로 부모가 정해진 열의 나머지 후보는 그리지 않는다.
    decided = {(r["child"], frozenset(json.loads(r["child_cols"]))) for r in rels
               if r["origin"] == "check" and included(r)
               and one_row_parent(r["parent_rows"], r["parent_distinct"])}
    for (child, child_cols), cands in by_src.items():
        src = (child, frozenset(json.loads(child_cols)))
        good = [r for r in cands if included(r)]
        for r in cands:
            if r not in good:
                verdict[key(r)] = "low"
        if not good:
            continue
        if src in decided:
            for r in good:
                verdict[key(r)] = "other"
            continue
        plausible = [r for r in good if evidence(r) >= 1 or distinctive(r)]
        best = max(plausible or good, key=score)
        if evidence(best) >= 1:
            # 이름 근거가 같은 부모가 여럿이면 어느 쪽이 더 꼭 맞는지로 고르지 않는다. 기준 표가 하나로 정해질 때만 그린다.
            ties = [r for r in plausible if evidence(r) == evidence(best)]
        else:
            ties = [r for r in plausible if score(r) == score(best)]
        if len(ties) > 1:
            # 같은 키를 가진 표가 여럿이면 그 키가 전부 들어 있는 기준 표, 곧 다른 후보를 가리키지 않는 위쪽 부모를 고른다.
            up = [r for r in ties if not any((r["parent"], r["parent_cols"], o["parent"], o["parent_cols"]) in link
                                             for o in ties if o is not r)]
            if len(up) == 1:
                best, ties = up[0], up
        if len(ties) > 1:
            named = [r for r in ties if named_after(r)]
            if len(named) == 1:
                best, ties = named[0], named
        if evidence(best) < 1 and src in judged_no:
            # 이 열의 값만 맞는 후보를 판정으로 뺐다. 이름 근거 없는 나머지 후보를 다시 올리지 않는다.
            pass
        elif evidence(best) < 1 and own_key(best):
            # 두 표의 키끼리 값이 맞는다. 같은 키를 나눠 가졌거나 한쪽이 다른 쪽의 일부인데, 값만으로는 못 가른다.
            # 후보가 여럿이면 그 키를 가장 넓게 담은 표(덮는 비율이 가장 낮은 쪽)를 보여 준다.
            verdict[key(min(good, key=lambda r: (r["coverage"] or 0, r["parent"])))] = "samekey"
        elif len(ties) > 1:
            for r in ties:
                verdict[key(r)] = "ambiguous"
        # 같은 표 안에서는 이름 단서 없이 값만 맞으면 그리지 않고 후보로 둔다.
        # 같은 행을 가리키는 또 다른 ID 열도 값이 다 들어간다.
        elif evidence(best) >= 1 or ((best["coverage"] or 0) >= 0.5 and distinctive(best)
                                      and best["child"] != best["parent"]):
            verdict[key(best)] = "drawn"
        else:
            verdict[key(best)] = "weak"
        for r in good:
            verdict.setdefault(key(r), "other")
    for r in rels:
        if r["origin"] == "check":
            if not one_row_parent(r["parent_rows"], r["parent_distinct"]):
                verdict[key(r)] = "checked-nm"
            else:
                verdict[key(r)] = "checked" if included(r) else "checked-low"
        elif r["origin"] == "drop":
            verdict[key(r)] = "dropped"

    # 1:1로 서로 들어맞는 두 표는 한 방향만 그린다. check로 정한 방향이 있으면 그쪽을 남긴다.
    def pairs(r):
        return frozenset(zip(json.loads(r["child_cols"]), json.loads(r["parent_cols"])))

    on_map = {(r["child"], r["parent"], pairs(r)): r for r in rels if verdict.get(key(r)) in ("drawn", "checked")}
    for r in on_map.values():
        o = on_map.get((r["parent"], r["child"], frozenset((p, c) for c, p in pairs(r))))
        if o is None or verdict[key(r)] != "drawn":
            continue
        if verdict[key(o)] == "checked":
            verdict[key(r)] = "reverse"
        elif verdict[key(o)] == "drawn":
            keep_r = (not named_after(r), (r["child_rows"] or 0), r["child"]) <= \
                     (not named_after(o), (o["child_rows"] or 0), o["child"])
            verdict[key(o) if keep_r else key(r)] = "reverse"
    for k, v in verdict.items():
        conn.execute("UPDATE _dm_relations SET verdict=? WHERE child=? AND child_cols=? AND parent=? AND parent_cols=?",
                     (v,) + k)
    conn.commit()


def rekey(conn, metas, problems):
    """키 후보가 여럿인 표의 키를 다른 표들이 가리키는 열로 바꾸고, 쓰이는 거의 키의 어긋난 칸을 보고한다."""
    refs, named = Counter(), Counter()
    for r in conn.execute("SELECT child, parent, parent_cols, name_score, inclusion, origin FROM _dm_relations"):
        pcols = json.loads(r["parent_cols"])
        if len(pcols) != 1 or r["child"] == r["parent"] or not included(r) or r["origin"] == "drop":
            continue
        target, by_name = (r["parent"], pcols[0]), (r["name_score"] or 0) >= 1
        # 정수 키에는 작은 정수가 우연히 다 들어가므로, 이름 근거가 있는 것만 "가리킨다"고 센다.
        if by_name or metas[r["parent"]]["cols"][pcols[0]]["type"] != "int":
            refs[target] += 1
            named[target] += by_name
    for t, m in metas.items():
        cands = m["keys"] + m["near"]
        if m["kind"] in ("single", "near") and len(cands) > 1:
            def rank(c):
                return (named[(t, c)], refs[(t, c)], c in m["keys"], -m["cols"][c]["pos"])
            best, cur = max(cands, key=rank), m["key_cols"][0]
            if best != cur and rank(best)[:2] > rank(cur)[:2]:
                exact = best in m["keys"]
                m["key_cols"], m["kind"] = [best], "single" if exact else "near"
                conn.execute("UPDATE _dm_tables SET key_cols=?, key_kind=?, key_note=? WHERE name=?",
                             (json.dumps([best], ensure_ascii=False), m["kind"], "" if exact else m["cols"][best]["note"], t))
        for c in m["near"]:
            if refs[(t, c)] or m["key_cols"] == [c]:
                problems.append(m["cols"][c]["near_msg"])
    conn.commit()


def remeasure_checks(conn, b, problems):
    known = {r[0]: {c[0] for c in conn.execute("SELECT name FROM _dm_columns WHERE tbl=?", (r[0],))}
             for r in conn.execute("SELECT name FROM _dm_tables")}
    for r in [dict(x) for x in conn.execute("SELECT * FROM _dm_relations WHERE origin='check'")]:
        ccols, pcols = json.loads(r["child_cols"]), json.loads(r["parent_cols"])
        k = (r["child"], r["child_cols"], r["parent"], r["parent_cols"])
        if r["child"] not in known or r["parent"] not in known or not set(ccols) <= known[r["child"]] \
                or not set(pcols) <= known[r["parent"]]:
            conn.execute("DELETE FROM _dm_relations WHERE child=? AND child_cols=? AND parent=? AND parent_cols=?", k)
            continue
        save_relation(conn, k, "check", measure(b, r["child"], ccols, r["parent"], pcols, problems), r["name_score"])
    conn.commit()


# ---------------------------------------------------------------- 보고서

def table_rows(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM _dm_tables ORDER BY name")]


def grain(t):
    kc = json.loads(t["key_cols"] or "[]")
    if t["key_kind"] == "single-row":
        return "행 1개"
    if kc:
        return "키 " + (kc[0] if len(kc) == 1 else "(" + ", ".join(kc) + ")")
    return "키 없음"


def edge_text(e):
    s = f"{arrow(e)} · 포함 {pct(e['inclusion'])}"
    if e["avg_fanout"] is not None:
        s += f" · 부모 하나에 평균 {e['avg_fanout']:.1f}행, 최대 {fmt_n(e['max_fanout'])}행"
    if one_to_one(e):
        s += " · 1:1"
    if e["orphan_rows"]:
        s += f" · 고아 {fmt_n(e['orphan_rows'])}행"
    if e["join_rows"] is not None and e["child_rows"] is not None and e["join_rows"] > e["child_rows"]:
        s += f" · 조인하면 {fmt_n(e['child_rows'])}→{fmt_n(e['join_rows'])}행"
    if e["origin"] == "check":
        s += " · 직접 확인"
    return s


def tree_lines(tables, edges):
    meta = {t["name"]: t for t in tables}
    kids, has_parent, selfref = defaultdict(list), set(), defaultdict(list)
    for e in edges:
        if e["child"] == e["parent"]:
            selfref[e["child"]].append(e)
        else:
            kids[e["parent"]].append(e)
            has_parent.add(e["child"])
    linked = (set(kids) | has_parent | set(selfref)) & set(meta)
    out, seen = [], set()

    def label(t):
        m = meta[t]
        return f"{t} ({fmt_n(m['rows'])}행, {grain(m)}{', 앞부분만' if m['truncated'] else ''})"

    def walk(t, prefix, edge, last):
        branch = "" if edge is None else ("└── " if last else "├── ")
        text = f"{t} (위에 나옴)" if t in seen else label(t)
        if edge is not None:
            text += "  ← " + edge_text(edge)
        out.append(prefix + branch + text)
        if t in seen:
            return
        seen.add(t)
        sub = prefix + ("" if edge is None else ("    " if last else "│   "))
        for e in selfref[t]:
            out.append((sub or "  ") + "↺ " + edge_text(e))
        ch = sorted(kids[t], key=lambda e: (e["child"], e["child_cols"]))
        for i, e in enumerate(ch):
            walk(e["child"], sub, e, i == len(ch) - 1)

    for t in sorted(x for x in linked if x not in has_parent):
        walk(t, "", None, True)
    for t in sorted(linked - seen):
        walk(t, "", None, True)
    lone = sorted(t["name"] for t in tables if t["name"] not in linked)
    if lone:
        out += ["", "연결 없음: " + ", ".join(lone)]
    return out or ["(표 없음)"]


def drawn_edges(conn):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM _dm_relations WHERE verdict IN ('drawn','checked') ORDER BY child, parent")]


def value_text(c, rows):
    top = json.loads(c["top_values"]) if c["top_values"] else None
    nonnull = max((rows or 0) - (c["nulls"] or 0), 1)
    if top:
        shown = " · ".join(f"{short(v, 16)} {pct(n / nonnull)}" for v, n in top[:5])
        return shown + (f" 외 {len(top) - 5}개" if len(top) > 5 else "")
    if c["type"] in ("int", "float", "date", "datetime") and c["minv"] is not None:
        return f"{short(c['minv'], 20)} ~ {short(c['maxv'], 20)}"
    ex = json.loads(c["examples"] or "[]")
    return ("예: " + ", ".join(short(v, 20) for v in ex)) if ex else ""


def distinct_text(c):
    if c["is_key"]:
        return "전부 다름"
    if c["distinct_n"] is not None:
        return fmt_n(c["distinct_n"])
    return f"{LOWCARD} 초과"


def render(conn):
    run = get_run(conn)
    tables = table_rows(conn)
    rels = [dict(r) for r in conn.execute("SELECT * FROM _dm_relations")]
    edges = [r for r in rels if r["verdict"] in ("drawn", "checked")]
    in_rel = defaultdict(set)
    for r in rels:
        in_rel[r["child"]].update(json.loads(r["child_cols"]))
        in_rel[r["parent"]].update(json.loads(r["parent_cols"]))
    files = defaultdict(list)
    for f in conn.execute("SELECT * FROM _dm_files ORDER BY path"):
        files[f["tbl"]].append(dict(f))
    truncated = [t["name"] for t in tables if t["truncated"]]
    L = ["# 데이터 프로파일", "",
         f"> `{SCRIPT}`가 만든 파일이다. 손으로 고치지 않는다. 다시 만들기: `python3 {SCRIPT} {run.get('argv', 'build')}`. "
         "해석과 질문은 `notes/data-map.md`에 쓴다.", ""]
    peak = run.get("peak_mb")
    L.append(f"- 만든 때: {run.get('when', '-')} · 걸린 시간 {run.get('seconds', 0):.0f}초"
             + (f" · 최대 메모리 {peak:.0f}MB" if peak else ""))
    if truncated:
        L.append(f"- 범위: 파일마다 앞 {fmt_n(run.get('limit_rows'))}행만 읽었다. 잘린 표: {', '.join(truncated)}. "
                 "잘린 표가 부모 쪽이면 포함률이 실제보다 낮게 나온다")
    else:
        L.append("- 범위: 모든 행")
    L.append(f"- 표 {len(tables)}개 · 파일 {sum(len(v) for v in files.values())}개 · "
             f"전체 {fmt_n(sum(t['rows'] or 0 for t in tables))}행")
    L.append(f"- 더 보기: `python3 {SCRIPT} sql \"SELECT ...\"` · 값 따라가기: `python3 {SCRIPT} trace 표.열 값` · "
             f"관계 재기: `python3 {SCRIPT} check 자식.열 부모.열`")
    if run.get("docs"):
        L += ["", "## 먼저 읽을 문서", ""] + [f"- {d}" for d in run["docs"]]
    L += ["", "## 관계 지도", "",
          f"그림: `{SVG}` (보기: 터미널에서 `python3 -m http.server 8000 --bind 0.0.0.0 -d {SVG.parent}`, "
          f"Browser에서 8000번 포트의 `/{SVG.name}`)", "", f"![구조도]({SVG.name})", "",
          "부모 표 아래에 그 부모를 가리키는 자식 표를 단다. `자식.열 → 부모.열`이고, 포함은 자식 값 중 부모에 있는 비율, "
          "'부모 하나에'는 부모 값 하나를 가리키는 자식 행 수다. 포함률 95% 이상이고 이름이 맞거나 부모를 절반 넘게 덮는 관계만 그렸다.",
          "", "```"] + tree_lines(tables, edges) + ["```"]
    L += ["", "## 표", "", "| 표 | 행 | 한 행을 정하는 열 | 파일 |", "|---|---:|---|---|"]
    for t in tables:
        fl = files.get(t["name"], [])
        ftxt = fl[0]["path"] if len(fl) == 1 else f"{len(fl)}개 ({fl[0]['path']} …)" if fl else "-"
        L.append(f"| {md_cell(t['name'])} | {fmt_n(t['rows'])} | {md_cell(grain(t))} | {md_cell(ftxt, 80)} |")
    for t in tables:
        L += ["", f"### {t['name']}", ""]
        for f in files.get(t["name"], []):
            bits = [f"{f['encoding']}", DELIM_KO.get(f["delimiter"], repr(f["delimiter"])), fmt_size(f["size"] or 0),
                    f"{fmt_n(f['rows'])}행"]
            if not f["has_header"]:
                bits.append("머리 줄 없음")
            if f["truncated"]:
                bits.append("앞부분만")
            L.append(f"- `{f['path']}`: " + ", ".join(bits))
        L.append(f"- {grain(t)}" + (f" ({t['key_note']})" if t["key_note"] else ""))
        if t["dup_groups"]:
            L.append(f"- 완전히 같은 행이 {fmt_n(t['dup_groups'])}묶음 있다. 합계를 낼 때 두 번 셀 수 있다")
        cols = [dict(c) for c in conn.execute("SELECT * FROM _dm_columns WHERE tbl=? ORDER BY pos", (t["name"],))]
        if len(cols) > MAX_DETAIL_COLUMNS:
            rank = sorted(cols, key=lambda c: (not c["is_key"], c["name"] not in in_rel[t["name"]],
                                               c["type"] in ("float", "empty"), c["pos"]))
            show = {c["name"] for c in rank[:MAX_DETAIL_COLUMNS]}
        else:
            show = {c["name"] for c in cols}
        key_cols = json.loads(t["key_cols"] or "[]")
        L += ["", "| 열 | 타입 | 빈 값 | 고유값 | 값 | 메모 |", "|---|---|---:|---:|---|---|"]
        for c in cols:
            if c["name"] not in show:
                continue
            nul = fmt_n(c["nulls"]) + (f" ({pct(c['nulls'] / t['rows'])})" if c["nulls"] and t["rows"] else "")
            L.append(f"| {md_cell(c['name'])}{' (키)' if c['name'] in key_cols else ''} | {TYPE_KO.get(c['type'], c['type'])} | {nul} | "
                     f"{distinct_text(c)} | {md_cell(value_text(c, t['rows']), 90)} | {md_cell(c['note'] or '')} |")
        rest = [c for c in cols if c["name"] not in show]
        if rest:
            L.append("")
            L.append(f"나머지 열 {len(rest)}개 (실수 {sum(c['type'] == 'float' for c in rest)}개): "
                     + ", ".join(c["name"] for c in rest[:20]) + (" …" if len(rest) > 20 else ""))
    def listed(r):
        if r["verdict"] in ("drawn", "checked", "checked-low", "checked-nm", "ambiguous", "reverse", "dropped"):
            return True
        return r["verdict"] == "low" and (r["name_score"] or 0) >= 1 and (r["inclusion"] or 0) >= SHOW_INCLUSION

    shown = sorted((r for r in rels if listed(r)),
                   key=lambda r: (VERDICT_ORDER.get(r["verdict"], 99), r["child"], r["child_cols"]))
    weak = sorted((r for r in rels if r["verdict"] == "weak"), key=lambda r: (r["child"], r["child_cols"]))
    hidden = sum(1 for r in rels if r["verdict"] == "other")
    L += ["", "## 관계 후보", "",
          "값으로 잰 관계다. 포함 = 자식 값 중 부모에 있는 비율, 덮음 = 부모 값 중 자식이 가리키는 비율. "
          "모호는 README와 `check`로 정한다. 이름이 맞는데 포함률이 낮은 줄은 키 형식(앞자리 0, 공백, 대소문자)이 다를 수 있다.", "",
          "| 자식.열 | 부모.열 | 포함 | 덮음 | 부모 하나에 (평균/최대) | 고아 행 (예) | 판정 |", "|---|---|---:|---:|---|---|---|"]
    for r in shown:
        ex = json.loads(r["orphan_examples"] or "[]")
        orphan = fmt_n(r["orphan_rows"]) + (f" ({', '.join(short(x, 12) for x in ex)})" if ex else "")
        fan = "-" if r["avg_fanout"] is None else f"{r['avg_fanout']:.1f} / {fmt_n(r['max_fanout'])}"
        L.append(f"| {md_cell(r['child'] + '.' + jcols(r['child_cols']))} | {md_cell(r['parent'] + '.' + jcols(r['parent_cols']))} | "
                 f"{pct(r['inclusion'])} | {pct(r['coverage'])} | {fan} | {md_cell(orphan)} | {VERDICT_KO.get(r['verdict'], r['verdict'] or '-')}"
                 + (f": {md_cell(r['note'])}" if r["verdict"] == "dropped" and r["note"] else "") + " |")
    if not shown:
        L.append("| - | - | - | - | - | - | 값이 맞는 관계 후보가 없다 |")
    # 값만 맞는 후보를 자식 열이 글자인지 숫자인지로 나눈다. 숫자 열은 1부터 매긴 번호에 우연히 다 들어가서 대부분 관계가 아니다.
    types = column_types(conn)

    def names(rows):
        return ", ".join(f"{arrow(r)} (덮음 {pct(r['coverage'])})" for r in rows)

    weak_text = [r for r in weak if not number_child(r, types)]
    weak_number = [r for r in weak if number_child(r, types)]
    if weak_text:
        L += ["", "이름 근거 없이 값만 맞는 후보 (글자 값은 우연히 맞기 어렵다. 관계면 `check`로 넣고 아니면 `drop`으로 뺀다): "
              + names(weak_text)]
    if weak_number:
        L += ["", "숫자가 번호 범위에 들어간 후보 (연도나 수량 같은 숫자는 1부터 매긴 번호에 우연히 다 들어간다. "
              "뜻으로 보아 그 표를 가리키는 열만 `check`로 넣고 나머지는 그대로 둔다): " + names(weak_number)]
    samekey = sorted((r for r in rels if r["verdict"] == "samekey"), key=lambda r: (r["child"], r["child_cols"]))
    if samekey:
        L += ["", "키끼리 값이 들어맞는 표 (같은 키를 나눠 가졌거나, 왼쪽이 오른쪽의 일부다. 정수 번호는 우연히 맞기도 한다. "
              "왼쪽 표가 오른쪽 대상의 일부를 담은 표면 `check`로 넣는다): " + names(samekey)]
    if hidden:
        L += ["", f"같은 열에 더 맞는 부모가 있어 뺀 후보 {hidden}개는 `_dm_relations` 표에 있다."]
    probs = list(run.get("problems", []))
    for t in tables:
        for f in files.get(t["name"], []):
            if f["bad_rows"]:
                probs.append(f"{f['path']}: 칸 수가 머리 줄과 다른 행 {fmt_n(f['bad_rows'])}개 (줄 {', '.join(map(str, json.loads(f['bad_lines'] or '[]')))}). "
                             "모자란 칸은 비우고 남는 칸은 마지막 열에 붙였다")
            if f["replaced"]:
                probs.append(f"{f['path']}: {f['encoding']}로 읽을 수 없는 글자 {fmt_n(f['replaced'])}곳을 \ufffd로 바꿨다. 인코딩을 확인한다")
            if f["encoding_note"]:
                probs.append(f"{f['path']}: {f['encoding_note']}")
            if not f["has_header"]:
                probs.append(f"{f['path']}: 첫 줄이 값처럼 보여 머리 줄이 없다고 보고 col_1… 이름을 붙였다")
            if f["skip_rows"]:
                probs.append(f"{f['path']}: 표 위의 설명 줄 {f['skip_rows']}개를 건너뛰었다 ({' / '.join(json.loads(f['skipped'] or '[]'))})")
            if f["repeated_headers"]:
                probs.append(f"{f['path']}: 머리 줄이 데이터 중간에 {fmt_n(f['repeated_headers'])}번 더 나와 뺐다 (파일을 이어 붙인 흔적)")
            if f["merged_lines"]:
                probs.append(f"{f['path']}: 칸 안에 줄바꿈이 있어 줄 {fmt_n(f['merged_lines'])}개가 앞 행에 붙었다. "
                             "메모 같은 긴 글인지, 따옴표가 안 닫혀 행을 삼킨 건지 확인한다")
            if f["parse_note"]:
                probs.append(f"{f['path']}: {f['parse_note']}. 칸 수가 틀린 행이 늘었을 수 있다")
    if run.get("others"):
        probs.append("이 도구가 읽지 않은 데이터 파일: " + ", ".join(run["others"]))
    L += ["", "## 문제", ""] + ([f"- {p}" for p in probs] or ["- 없음"])
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE.write_text("\n".join(L) + "\n", encoding="utf-8")
    SVG.write_text(render_svg(conn, tables, edges), encoding="utf-8")


# ---------------------------------------------------------------- 구조도 (ERD, SVG)

SVG_FONT = "'Noto Sans KR','Apple SD Gothic Neo','Malgun Gothic',sans-serif"
MARGIN, HEAD_H, ROW_H, GAP_Y, MAX_ROWS, LONE_ROWS = 24, 26, 18, 30, 14, 6


def text_width(s, size):
    return size * sum(1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.6 for ch in str(s))


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def ratio_label(e):
    if one_to_one(e):
        return "1 : 1"
    a = e["avg_fanout"]
    if a is None:
        return ""
    return "1 : " + (f"{a:,.0f}" if a >= 10 else f"{a:.1f}".rstrip("0").rstrip("."))


def erd_table(t, cols, fks, orphans, cap):
    """ERD 상자 하나. 키(PK)와 다른 표를 가리키는 열(FK)을 먼저 보이고, 나머지 열은 cap까지만 보인다."""
    key = json.loads(t["key_cols"] or "[]")
    order = sorted(cols, key=lambda c: (c["name"] not in key, c["name"] not in fks, c["pos"]))
    must = sum(1 for c in order if c["name"] in key or c["name"] in fks)
    shown = order[:max(cap, must)]
    rows = []
    for c in shown:
        mark = ",".join(m for m, on in (("PK", c["name"] in key), ("FK", c["name"] in fks)) if on)
        note = f"고아 {fmt_n(orphans[c['name']])}" if orphans.get(c["name"]) else ""
        rows.append((mark, c["name"], c["type"] if c["type"] != "empty" else "-", note))
    more = len(cols) - len(shown)
    sub = f"{fmt_n(t['rows'])}행" + (" · 앞부분만" if t["truncated"] else "")
    w = max([text_width(t["name"], 13) + text_width(sub, 10) + 40, 170]
            + [40 + text_width(n, 12) + (text_width(note, 10) + 8 if note else 0) + 24 + text_width(ty, 10) + 12
               for _, n, ty, note in rows])
    h = HEAD_H + ROW_H * (len(rows) + (1 if more else 0)) + 6
    return {"name": t["name"], "sub": sub, "rows": rows, "more": more, "w": w, "h": h,
            "idx": {r[1]: i for i, r in enumerate(rows)}}


def anchor(b, cols):
    """선이 붙는 높이. 여러 열로 된 관계는 그 열들의 가운데에 붙여 한 열짜리 관계와 겹치지 않게 한다."""
    cols = json.loads(cols)
    return sum(HEAD_H + ROW_H * b["idx"].get(c, 0) + ROW_H / 2 for c in cols) / len(cols)


def draw_table(parts, b, x, y, layer):
    parts.append(f'<g class="table" data-name="{esc(b["name"])}" data-layer="{layer}">')
    parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{b["w"]:.1f}" height="{b["h"]:.1f}" fill="#fff" stroke="#000" stroke-width="1.4"/>')
    parts.append(f'<text x="{x + 10:.1f}" y="{y + 18:.1f}" font-size="13" font-weight="bold">{esc(b["name"])}</text>')
    parts.append(f'<text x="{x + b["w"] - 10:.1f}" y="{y + 18:.1f}" font-size="10" text-anchor="end">{esc(b["sub"])}</text>')
    parts.append(f'<path d="M{x:.1f},{y + HEAD_H:.1f} H{x + b["w"]:.1f}" stroke="#000" stroke-width="1"/>')
    for i, (mark, name, ty, note) in enumerate(b["rows"]):
        ry = y + HEAD_H + ROW_H * i + 13
        if mark:
            parts.append(f'<text x="{x + 8:.1f}" y="{ry:.1f}" font-size="9" font-weight="bold">{mark}</text>')
        weight = ' font-weight="bold"' if "PK" in mark else ""
        parts.append(f'<text x="{x + 40:.1f}" y="{ry:.1f}" font-size="12"{weight}>{esc(name)}</text>')
        if note:
            parts.append(f'<text x="{x + 48 + text_width(name, 12):.1f}" y="{ry:.1f}" font-size="10">{esc(note)}</text>')
        parts.append(f'<text x="{x + b["w"] - 10:.1f}" y="{ry:.1f}" font-size="10" text-anchor="end">{esc(ty)}</text>')
    if b["more"]:
        ry = y + HEAD_H + ROW_H * len(b["rows"]) + 13
        parts.append(f'<text x="{x + 40:.1f}" y="{ry:.1f}" font-size="11">… 열 {b["more"]}개 더</text>')
    parts.append("</g>")


def end_marks(parts, x, y, d, many, optional):
    """까마귀발 표기. x는 선이 닿는 상자 가장자리, d는 상자 바깥 방향(오른쪽 +1, 왼쪽 -1)."""
    line = 'stroke="#000" stroke-width="1.1" fill="none"'
    if many:
        tip = x + 11 * d
        parts.append(f'<path d="M{tip:.1f},{y:.1f} L{x:.1f},{y - 6:.1f} M{tip:.1f},{y:.1f} L{x:.1f},{y + 6:.1f}" {line}/>')
        far = x + 16 * d
    else:
        parts.append(f'<path d="M{x + 7 * d:.1f},{y - 6:.1f} V{y + 6:.1f}" {line}/>')
        far = x + 13 * d
    if optional:
        parts.append(f'<circle cx="{far + 4 * d:.1f}" cy="{y:.1f}" r="3.5" fill="#fff" stroke="#000" stroke-width="1.1"/>')
    else:
        parts.append(f'<path d="M{far:.1f},{y - 6:.1f} V{y + 6:.1f}" {line}/>')


def render_svg(conn, tables, edges):
    """ERD처럼 표마다 열을 보이고, 자식 표의 FK 열에서 부모 표의 PK 열로 선을 잇는다. 부모가 왼쪽, 자식이 오른쪽이다."""
    tabs = {t["name"]: t for t in tables}
    cols = defaultdict(list)
    for r in conn.execute("SELECT tbl, pos, name, type, nulls FROM _dm_columns ORDER BY tbl, pos"):
        cols[r["tbl"]].append(dict(r))
    nulls = {(c["tbl"], c["name"]): c["nulls"] for cs in cols.values() for c in cs}
    edges = [e for e in edges if e["child"] in tabs and e["parent"] in tabs]
    fks, orphans, parents = defaultdict(set), defaultdict(dict), defaultdict(set)
    for e in edges:
        cc = json.loads(e["child_cols"])
        fks[e["child"]].update(cc)
        if e["orphan_rows"]:
            orphans[e["child"]][cc[0]] = e["orphan_rows"]
        if e["child"] != e["parent"]:
            parents[e["child"]].add(e["parent"])
    real = [e for e in edges if e["child"] != e["parent"]]
    selfref = [e for e in edges if e["child"] == e["parent"]]
    linked = sorted({e["child"] for e in edges} | {e["parent"] for e in edges})
    lone = [n for n in sorted(tabs) if n not in set(linked)]

    def fk_nullable(e):
        return bool(nulls.get((e["child"], json.loads(e["child_cols"])[0])))

    layer, state = {}, {}

    def depth(n):
        if n not in layer:
            state[n] = 1
            d = 0
            for p in sorted(parents[n]):
                if state.get(p) != 1:
                    d = max(d, depth(p) + 1)
            state[n] = 2
            layer[n] = d
        return layer[n]

    for n in linked:
        depth(n)
    nodes = {}
    for n in linked:
        nodes[n] = erd_table(tabs[n], cols[n], fks[n], orphans[n], MAX_ROWS)
        nodes[n].update(layer=layer[n], real=True)
    segs, back = [], []
    for i, e in enumerate(real):
        lp, lc = layer[e["parent"]], layer[e["child"]]
        if lc <= lp:
            back.append(e)
            continue
        prev, prev_a = e["parent"], anchor(nodes[e["parent"]], e["parent_cols"])
        for L in range(lp + 1, lc):
            d = f"\0{i}.{L}"
            nodes[d] = {"layer": L, "real": False, "w": 0, "h": ROW_H}
            segs.append((prev, d, e, prev_a, ROW_H / 2))
            prev, prev_a = d, ROW_H / 2
        segs.append((prev, e["child"], e, prev_a, anchor(nodes[e["child"]], e["child_cols"])))
    ups, downs = defaultdict(list), defaultdict(list)
    for k, s in enumerate(segs):
        downs[s[0]].append(k)
        ups[s[1]].append(k)
    nl = 1 + max((nd["layer"] for nd in nodes.values()), default=-1)
    uf = {n: n for n in nodes}

    def find(a):
        while uf[a] != a:
            uf[a] = uf[uf[a]]
            a = uf[a]
        return a

    for s in segs:
        uf[find(s[0])] = find(s[1])
    groups = defaultdict(list)
    for n in nodes:
        groups[find(n)].append(n)
    y = {}

    def crossings(rows, L):
        if L < 0 or L >= nl - 1:
            return 0
        pu = {n: i for i, n in enumerate(rows[L])}
        pl = {n: i for i, n in enumerate(rows[L + 1])}
        pairs = [(pu[s[0]], pl[s[1]]) for s in segs if s[0] in pu and s[1] in pl]
        return sum(1 for i, (a, b) in enumerate(pairs) for c, d in pairs[i + 1:] if (a - c) * (b - d) < 0)

    def layout(group, top):
        """연결된 표 묶음 하나를 층(세로 줄)마다 위아래로 세운다. FK 열이 PK 열과 같은 높이에 오도록 당긴다."""
        rows = [sorted((n for n in group if nodes[n]["layer"] == L), key=lambda n: (not nodes[n]["real"], n))
                for L in range(nl)]

        def reorder(L, other, links, end):
            pos = {n: i for i, n in enumerate(rows[other])}
            cur = {n: i for i, n in enumerate(rows[L])}

            def key(n):
                ps = [pos[segs[k][end]] for k in links[n] if segs[k][end] in pos]
                return sum(ps) / len(ps) if ps else cur[n]

            rows[L].sort(key=lambda n: (key(n), cur[n]))

        for _ in range(4):
            for L in range(1, nl):
                reorder(L, L - 1, ups, 0)
            for L in range(nl - 2, -1, -1):
                reorder(L, L + 1, downs, 1)
        # 이웃한 두 상자를 바꿔 선이 덜 엇갈리면 바꾼다.
        for _ in range(10 if len(segs) <= 400 else 0):
            improved = False
            for L in range(nl):
                row = rows[L]
                for i in range(len(row) - 1):
                    before = crossings(rows, L - 1) + crossings(rows, L)
                    row[i], row[i + 1] = row[i + 1], row[i]
                    if crossings(rows, L - 1) + crossings(rows, L) < before:
                        improved = True
                    else:
                        row[i], row[i + 1] = row[i + 1], row[i]
            if not improved:
                break
        for row in rows:
            cy = 0.0
            for n in row:
                y[n] = cy
                cy += nodes[n]["h"] + GAP_Y
        for _ in range(8):
            for L in list(range(1, nl)) + list(range(nl - 2, -1, -1)):
                row = rows[L]
                want = []
                for n in row:
                    vals = ([y[segs[k][0]] + segs[k][3] - segs[k][4] for k in ups[n]]
                            + [y[segs[k][1]] + segs[k][4] - segs[k][3] for k in downs[n]])
                    want.append(sum(vals) / len(vals) if vals else y[n])
                for i in range(1, len(row)):
                    want[i] = max(want[i], want[i - 1] + nodes[row[i - 1]]["h"] + GAP_Y)
                for i in range(len(row) - 2, -1, -1):
                    want[i] = min(want[i], want[i + 1] - nodes[row[i]]["h"] - GAP_Y)
                for n, v in zip(row, want):
                    y[n] = v
        shift = top - min(y[n] for n in group)
        for n in group:
            y[n] += shift
        return max(y[n] + nodes[n]["h"] for n in group)

    bottom = 56.0
    for group in sorted(groups.values(), key=lambda g: (-len(g), min((n for n in g if nodes[n]["real"]), default=""))):
        bottom = layout(group, bottom) + 44
    col_w = [max([nd["w"] for nd in nodes.values() if nd["real"] and nd["layer"] == L] or [60]) for L in range(nl)]
    self_pad = [36 if any(layer[e["child"]] == L for e in selfref) else 0 for L in range(nl)]
    tracks, gap_w = {}, []
    for L in range(nl - 1):
        spans = []
        for k, (u, lo, e, au, al) in enumerate(segs):
            if nodes[u]["layer"] == L and abs((y[u] + au) - (y[lo] + al)) > 0.5:
                spans.append((min(y[u] + au, y[lo] + al), max(y[u] + au, y[lo] + al), k))
        ends = []
        for lo_, hi, k in sorted(spans):
            t = next((i for i, end in enumerate(ends) if end < lo_ - 6), None)
            if t is None:
                ends.append(hi)
                t = len(ends) - 1
            else:
                ends[t] = hi
            tracks[k] = t
        gap_w.append(64 + 12 * len(ends))
    col_x = [float(MARGIN) + (self_pad[0] if nl else 0)]
    for L in range(1, nl):
        col_x.append(col_x[-1] + col_w[L - 1] + gap_w[L - 1] + self_pad[L])
    parts, placed = [], []

    def label_pos(x_end, y_line, text):
        """숫자 이름표는 선 위에 쓰고, 다른 이름표와 겹치면 선 아래로 내린다."""
        w = text_width(text, 10)
        for dx, dy in ((0, -6), (0, 14), (-(w + 8), -6), (-(w + 8), 14)):
            xe, yy = x_end + dx, y_line + dy
            if all(abs(yy - py) >= 11 or xe - w >= px1 or xe <= px0 for px0, px1, py in placed):
                break
        placed.append((xe - w, xe, yy))
        return xe, yy

    for k, (u, lo, e, au, al) in enumerate(segs):
        L = nodes[u]["layer"]
        x1 = col_x[L] + (nodes[u]["w"] if nodes[u]["real"] else col_w[L])
        y1, x2, y2 = y[u] + au, col_x[L + 1], y[lo] + al
        if k in tracks:
            tx = col_x[L] + col_w[L] + 26 + 12 * tracks[k]
            d = f"M{x1:.1f},{y1:.1f} H{tx:.1f} V{y2:.1f} H{x2:.1f}"
        else:
            d = f"M{x1:.1f},{y1:.1f} H{x2:.1f}"
        parts.append(f'<path class="edge" data-child="{esc(e["child"])}" data-parent="{esc(e["parent"])}" d="{d}" '
                     'fill="none" stroke="#000" stroke-width="1.1"/>')
        if nodes[u]["real"]:
            end_marks(parts, x1, y1, 1, many=False, optional=fk_nullable(e))
        if nodes[lo]["real"]:
            end_marks(parts, x2, y2, -1, many=not one_to_one(e), optional=(e["coverage"] or 0) < 1)
            label = ratio_label(e)
            if label:
                lx, ly = label_pos(x2 - 24, y2, label)
                parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="10" text-anchor="end" '
                             f'stroke="#fff" stroke-width="3" paint-order="stroke">{esc(label)}</text>')
    for n, nd in nodes.items():
        if not nd["real"]:
            L = nd["layer"]
            parts.append(f'<path d="M{col_x[L]:.1f},{y[n] + ROW_H / 2:.1f} H{col_x[L] + col_w[L]:.1f}" '
                         'fill="none" stroke="#000" stroke-width="1.1"/>')
    for e in selfref:
        b = nodes[e["child"]]
        xl = col_x[b["layer"]]
        yp = y[e["child"]] + anchor(b, e["parent_cols"])
        yc = y[e["child"]] + anchor(b, e["child_cols"])
        parts.append(f'<path class="edge" data-child="{esc(e["child"])}" data-parent="{esc(e["parent"])}" '
                     f'd="M{xl:.1f},{yp:.1f} H{xl - 30:.1f} V{yc:.1f} H{xl:.1f}" fill="none" stroke="#000" stroke-width="1.1"/>')
        end_marks(parts, xl, yp, -1, many=False, optional=fk_nullable(e))
        end_marks(parts, xl, yc, -1, many=not one_to_one(e), optional=(e["coverage"] or 0) < 1)
    for e in back:
        c, p = nodes[e["child"]], nodes[e["parent"]]
        parts.append(f'<path class="edge" data-child="{esc(e["child"])}" data-parent="{esc(e["parent"])}" '
                     f'd="M{col_x[c["layer"]]:.1f},{y[e["child"]] + anchor(c, e["child_cols"]):.1f} '
                     f'L{col_x[p["layer"]] + p["w"]:.1f},{y[e["parent"]] + anchor(p, e["parent_cols"]):.1f}" '
                     'fill="none" stroke="#000" stroke-dasharray="4 3"/>')
    for n in linked:
        draw_table(parts, nodes[n], col_x[layer[n]], y[n], layer[n])
    width = max([col_x[L] + col_w[L] for L in range(nl)] + [900.0])
    cur = (bottom - 4) if linked else 56.0
    if lone:
        parts.append(f'<text x="{MARGIN}" y="{cur:.1f}" font-size="12" font-weight="bold">연결 없음</text>')
        cur += 12
        cx, row_h = float(MARGIN), 0.0
        for n in lone[:30]:
            b = erd_table(tabs[n], cols[n], set(), {}, LONE_ROWS)
            if cx + b["w"] > width and cx > MARGIN:
                cx, cur, row_h = float(MARGIN), cur + row_h + 20, 0.0
            draw_table(parts, b, cx, cur, "lone")
            cx, row_h = cx + b["w"] + 30, max(row_h, b["h"])
        cur += row_h
        if len(lone) > 30:
            cur += 20
            parts.append(f'<text x="{MARGIN}" y="{cur:.1f}" font-size="11">외 {len(lone) - 30}개</text>')
    legend = ["PK = 한 행을 정하는 열(키), FK = 다른 표의 키를 가리키는 열. 왼쪽이 부모, 오른쪽이 자식이다.",
              "선 끝: 갈퀴 = 여러 행, 막대 = 한 행, 동그라미 = 없을 수도 있음. 1 : 25 = 부모 한 행에 자식 평균 25행."]
    cur += 36
    for i, s in enumerate(legend):
        parts.append(f'<text x="{MARGIN}" y="{cur + 16 * i:.1f}" font-size="11">{esc(s)}</text>')
    width = max([width] + [MARGIN + text_width(s, 11) for s in legend]) + MARGIN
    height = cur + 16 * len(legend) + MARGIN
    total = sum(t["rows"] or 0 for t in tables)
    title = f"데이터 구조도 · 표 {len(tables)}개 · {total:,}행" + (" · 앞부분만 읽은 표 있음" if any(t["truncated"] for t in tables) else "")
    head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
            f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="{SVG_FONT}">',
            '<rect width="100%" height="100%" fill="#fff"/>',
            f'<text x="{MARGIN}" y="30" font-size="15" font-weight="bold">{esc(title)}</text>']
    return "\n".join(head + parts + ["</svg>"]) + "\n"


# ---------------------------------------------------------------- 명령

def running_pid():
    try:
        pid = int(LOCK.read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        return pid
    return pid


def refuse_while_building():
    pid = running_pid()
    if pid and pid != os.getpid():
        die(f"build가 도는 중이다 (pid {pid}). 끝난 뒤에 다시 한다. 진행: python3 {SCRIPT} status")


def cmd_scan(args):
    data, docs, others = find_files(args.paths or default_roots())
    infos, bad = [], []
    for p in data:
        try:
            infos.append(sniff(p))
        except Exception as e:
            bad.append(f"{rel(p)} ({str(e)[:200]})")
    total = sum(i["size"] for i in infos)
    print(f"CSV·TSV {len(infos)}개 · 합계 {fmt_size(total)} · 예상 약 {sum(i['est_rows'] for i in infos):,}행 (파일 앞부분으로 셈)")
    if infos:
        print()
        print(f"{'파일':<40} {'크기':>9} {'예상 행':>12}  인코딩     구분자   열")
        for i in infos:
            print(f"{short(i['rel'], 40):<40} {fmt_size(i['size']):>9} {i['est_rows']:>12,}  "
                  f"{i['encoding']:<10} {DELIM_KO.get(i['delimiter'], i['delimiter']):<7} {len(i['columns']):>3}")
        groups = group_files([i for i in infos if i["columns"]], args.split)
        multi = [(n, fs) for n, fs in groups if len(fs) > 1]
        if multi:
            print()
            for n, fs in multi:
                print(f"머리 줄이 같아 한 표로 묶음: {n} ← 파일 {len(fs)}개 ("
                      + ", ".join(Path(f["rel"]).stem for f in fs[:40]) + (" …" if len(fs) > 40 else "") + ")")
            print("묶인 파일들이 같은 것을 나눠 담았으면 그대로 두고, 서로 다른 것을 담았으면 build에 --split을 붙여 파일마다 따로 표로 둔다")
        print()
        print(f"표 {len(groups)}개가 된다: " + ", ".join(n for n, _ in groups))
    for i in infos:
        if not i["columns"]:
            print(f"빈 파일: {i['rel']}")
        elif not i["has_header"]:
            print(f"머리 줄이 없어 보임: {i['rel']} (col_1… 이름을 붙인다)")
        if i["skip"]:
            print(f"표 위 설명 줄 {i['skip']}개를 건너뜀: {i['rel']} ({' / '.join(i['skipped'])})")
        if i["encoding_note"]:
            print(f"인코딩 불확실: {i['rel']} — {i['encoding_note']}")
    for why in bad:
        print(f"열 수 없음: {why}")
    print("\n먼저 읽을 문서: " + (", ".join(rel(d) for d in docs) if docs else "없음"))
    if others:
        print("이 도구가 읽지 않는 데이터 파일: " + ", ".join(f"{rel(o)} ({fmt_size(o.stat().st_size)})" for o in others))
    if infos:
        target = " ".join(args.paths) if args.paths else default_roots()[0]
        print(f"\n다음: python3 {SCRIPT} build {target} --background")


def cmd_build(args):
    roots = args.paths or default_roots()
    HOME.mkdir(exist_ok=True)
    (HOME / ".gitignore").write_text("*\n", encoding="utf-8")
    pid = running_pid()
    if pid and pid != os.getpid():
        die(f"build가 이미 돈다 (pid {pid}). 진행: python3 {SCRIPT} status · 멈추기: python3 {SCRIPT} stop")
    if args.background:
        argv = [a for a in sys.argv[1:] if a != "--background"]
        child = subprocess.Popen([sys.executable, os.path.abspath(__file__)] + argv, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        LOCK.write_text(str(child.pid))
        print(f"뒤에서 시작했다 (pid {child.pid}). 진행: python3 {SCRIPT} status · 로그: {LOG}")
        return
    LOCK.write_text(str(os.getpid()))
    log = Log(LOG)
    try:
        build(roots, args, log)
    except SystemExit as e:
        log(f"실패: {e}")
        raise
    except KeyboardInterrupt:
        log("중단됨")
        raise SystemExit(130)
    except Exception:
        log("실패:\n" + traceback.format_exc())
        raise SystemExit(1)
    finally:
        if running_pid() == os.getpid():
            LOCK.unlink()


def build(roots, args, log):
    t0 = time.monotonic()
    problems = []
    data, docs, others = find_files(roots)
    if not data:
        die(f"CSV·TSV 파일이 없다: {', '.join(roots)}")
    infos = []
    for p in data:
        try:
            infos.append(sniff(p))
        except Exception as e:
            problems.append(f"{rel(p)}: 모양을 읽지 못해 건너뛰었다 ({str(e)[:200]})")
    for i in infos:
        if not i["columns"]:
            problems.append(f"{i['rel']}: 빈 파일이라 건너뛰었다")
    groups = group_files([i for i in infos if i["columns"]], args.split)
    log(f"파일 {len(infos)}개 → 표 {len(groups)}개: " + ", ".join(n for n, _ in groups))
    conn = connect(write=True)
    if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
        conn.close()
        DB.unlink()
        conn = connect(write=True)
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    init_meta(conn)
    loaded = {r[0]: r[1] for r in conn.execute("SELECT name, signature FROM _dm_tables WHERE loaded=1")}
    todo = [(n, fs) for n, fs in groups if loaded.get(n) != signature(fs, args.limit_rows)]
    need = 0
    for _, fs in todo:
        for f in fs:
            ratio = min(args.limit_rows / f["est_rows"], 1) if args.limit_rows and f["est_rows"] else 1
            need += f["size"] * ratio
    free = shutil.disk_usage(HOME).free
    if need * 1.6 > free:
        die(f"디스크가 모자라다: 읽을 파일 {fmt_size(need)}에 색인·정렬용 자리까지 약 {fmt_size(need * 1.6)}가 필요한데 "
            f"{fmt_size(free)} 남았다. --limit-rows로 줄인다")
    names = [n for n, _ in groups]
    for (old,) in conn.execute("SELECT name FROM _dm_tables").fetchall():
        if old not in names:
            drop_table(conn, old)
    prog = Progress(log, sum((min(f["est_rows"], args.limit_rows) if args.limit_rows else f["est_rows"])
                             for _, fs in todo for f in fs))
    todo_names = {n for n, _ in todo}
    for n, fs in groups:
        if n in todo_names:
            load_table(conn, n, fs, args.limit_rows, log, prog, problems)
        else:
            log(f"{n}: 지난번과 같은 파일이라 다시 읽지 않는다")
    t_load = time.monotonic() - t0
    log(f"적재 끝: {t_load:.0f}초")
    b = Budget(conn, args.query_timeout)
    metas = {}
    for n in names:
        if conn.execute("SELECT 1 FROM _dm_tables WHERE name=?", (n,)).fetchone():
            t1 = time.monotonic()
            metas[n] = analyze_table(conn, b, n, problems, prog)
            log(f"{n}: 키 · {grain(dict(conn.execute('SELECT * FROM _dm_tables WHERE name=?', (n,)).fetchone()))} "
                f"({time.monotonic() - t1:.0f}초)")
    t1 = time.monotonic()
    find_relations(conn, b, metas, problems, prog)
    remeasure_checks(conn, b, problems)
    rekey(conn, metas, problems)
    choose(conn)
    log(f"관계 재기 끝: {time.monotonic() - t1:.0f}초")
    seconds = time.monotonic() - t0
    run = {"when": time.strftime("%Y-%m-%d %H:%M"), "seconds": seconds, "peak_mb": peak_mb(),
           "argv": " ".join(sys.argv[1:]).replace("--background", "").strip(), "limit_rows": args.limit_rows,
           "docs": [rel(d) for d in docs], "others": [f"{rel(o)} ({fmt_size(o.stat().st_size)})" for o in others],
           "problems": problems}
    conn.execute("INSERT OR REPLACE INTO _dm_run(key, value) VALUES ('run', ?)", (json.dumps(run, ensure_ascii=False),))
    conn.commit()
    render(conn)
    tables = table_rows(conn)
    log("")
    log("관계 지도:")
    for line in tree_lines(tables, drawn_edges(conn)):
        log("  " + line)
    types = column_types(conn)
    amb = conn.execute("SELECT COUNT(*) FROM _dm_relations WHERE verdict='ambiguous'").fetchone()[0]
    weak = conn.execute("SELECT child, child_cols FROM _dm_relations WHERE verdict='weak'").fetchall()
    numeric = sum(number_child(r, types) for r in weak)
    if amb or weak:
        log(f"판정할 관계 후보: 모호 {amb}줄, 이름 근거 없이 값만 맞는 후보 {len(weak) - numeric}개 · "
            f"읽어 볼 후보: 숫자가 번호 범위에 들어간 후보 {numeric}개 ({PROFILE}의 '관계 후보')")
    if problems:
        log(f"문제 {len(problems)}건: {PROFILE}의 '문제'")
    prog.set_phase("끝")
    log(f"끝: 표 {len(tables)}개, {fmt_n(sum(t['rows'] or 0 for t in tables))}행, {seconds:.0f}초"
        + (f", 최대 메모리 {run['peak_mb']:.0f}MB" if run["peak_mb"] else "") + f" · 프로파일 {PROFILE}")


def cmd_status(args):
    pid = running_pid()
    p = None
    if PROGRESS.exists():
        try:
            p = json.loads(PROGRESS.read_text(encoding="utf-8"))
        except ValueError:
            p = None
    if pid:
        print(f"도는 중 (pid {pid})")
        if p:
            elapsed = p["elapsed"] + max(time.time() - p["at"], 0)
            print(f"단계: {p['phase']} {p['detail']} · 시작 뒤 {elapsed:.0f}초")
            if p["phase"] == "적재" and p["rate"] > 0:
                left = max(p["total_est"] - p["done"], 0) / p["rate"]
                print(f"적재: {p['done']:,}/약 {p['total_est']:,}행 · 초당 {p['rate']:,.0f}행 · "
                      f"남은 적재 약 {left / 60:.1f}분 (예상 행 수를 지금 속도로 나눈 값)")
    else:
        print("도는 build 없음")
        if p:
            print("마지막 build: " + ("끝났다" if p["phase"] == "끝" else f"'{p['phase']}' 단계에서 끝나지 않고 멈췄다. 로그를 본다"))
    if LOG.exists():
        lines = LOG.read_text(encoding="utf-8").splitlines()
        print("--- 로그 끝")
        print("\n".join(lines[-12:]))


def cmd_stop(args):
    pid = running_pid()
    if not pid:
        print("도는 build 없음")
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if running_pid() != pid:
            break
        time.sleep(0.1)
    if LOCK.exists():
        LOCK.unlink()
    print(f"멈췄다 (pid {pid}). 다 읽은 표는 남는다. 같은 파일로 다시 build하면 그 표는 다시 읽지 않는다")


def parse_ref(conn, ref):
    if "." not in ref:
        die(f"표.열 모양으로 쓴다: {ref}")
    tname, colpart = ref.split(".", 1)
    tables = {r[0].lower(): r[0] for r in conn.execute("SELECT name FROM _dm_tables")}
    if tname.lower() not in tables:
        die(f"없는 표: {tname}. 있는 표: {', '.join(sorted(tables.values()))}")
    t = tables[tname.lower()]
    known = {r[0].lower(): r[0] for r in conn.execute("SELECT name FROM _dm_columns WHERE tbl=?", (t,))}
    cols = []
    for c in colpart.split(","):
        c = c.strip()
        if c.lower() not in known:
            die(f"{t}에 없는 열: {c}. 있는 열: {', '.join(known.values())}")
        cols.append(known[c.lower()])
    return t, cols


def same_relation(conn, child, ccols, parent, pcols):
    """이미 있는 같은 관계의 열쇠를 돌려준다. 열을 다른 순서로 적어도 같은 관계다. 없으면 적은 그대로."""
    want = set(zip(ccols, pcols))
    for cc, pc in conn.execute("SELECT child_cols, parent_cols FROM _dm_relations WHERE child=? AND parent=?", (child, parent)):
        if set(zip(json.loads(cc), json.loads(pc))) == want:
            return (child, cc, parent, pc)
    return (child, json.dumps(ccols, ensure_ascii=False), parent, json.dumps(pcols, ensure_ascii=False))


def cmd_drop(args):
    """값은 맞지만 뜻으로 보아 관계가 아닌 선을 지도에서 뺀다(같은 키를 나눠 가진 형제 표, 우연히 겹친 번호)."""
    refuse_while_building()
    conn = connect(write=True)
    child, ccols = parse_ref(conn, args.child)
    parent, pcols = parse_ref(conn, args.parent)
    if len(ccols) != len(pcols):
        die("양쪽 열 개수가 같아야 한다")
    rkey = same_relation(conn, child, ccols, parent, pcols)
    where = "child=? AND child_cols=? AND parent=? AND parent_cols=?"
    if not conn.execute(f"SELECT 1 FROM _dm_relations WHERE {where}", rkey).fetchone():
        m = measure(Budget(conn, args.query_timeout), child, ccols, parent, pcols, [])
        save_relation(conn, rkey, "drop", m, 0)
    conn.execute(f"UPDATE _dm_relations SET origin='drop', note=? WHERE {where}", (args.reason,) + rkey)
    conn.commit()
    choose(conn)
    render(conn)
    print(f"{child}.{jcols(rkey[1])} → {parent}.{jcols(rkey[3])}: 지도에서 뺐다 ({args.reason})")
    for r in conn.execute("SELECT parent, parent_cols, verdict, inclusion FROM _dm_relations "
                          "WHERE child=? AND child_cols=? AND origin != 'drop' ORDER BY verdict", rkey[:2]):
        print(f"  같은 열의 다른 후보: → {r['parent']}.{jcols(r['parent_cols'])} · "
              f"{VERDICT_KO.get(r['verdict'], r['verdict'] or '-')} · 포함 {pct(r['inclusion'])}")
    print("되돌리려면 같은 쌍으로 check를 돌린다")


def cmd_key(args):
    """표의 키를 정한다. 값이 받쳐 줄 때만 받는다: 행마다 다르거나, 거의 키만큼만 어긋난다."""
    refuse_while_building()
    conn = connect(write=True)
    t, cols = parse_ref(conn, args.ref)
    b = Budget(conn, args.query_timeout)
    sel = ", ".join(q(c) for c in cols)
    filled_cond = "(" + " OR ".join(f"{q(c)} IS NOT NULL" for c in cols) + ")"
    try:
        rows = b.one(f"SELECT COUNT(*) FROM {q(t)}")[0]
        filled = b.one(f"SELECT COUNT(*) FROM {q(t)} WHERE {filled_cond}")[0]
        _, extra = b.one(f"SELECT COUNT(*), TOTAL(n - 1) FROM (SELECT COUNT(*) AS n FROM {q(t)} "
                         f"WHERE {filled_cond} GROUP BY {sel} HAVING COUNT(*) > 1)")
        examples = b.all(f"SELECT {sel}, COUNT(*) FROM {q(t)} WHERE {filled_cond} GROUP BY {sel} HAVING COUNT(*) > 1 LIMIT 3")
    except Timeout:
        die(f"{t}.{','.join(cols)}: 키인지 재기 시간 초과")
    holes, dups = rows - filled, int(extra)
    label = f"{t}.({', '.join(cols)})" if len(cols) > 1 else f"{t}.{cols[0]}"
    empty = "빈 값이 든 행" if len(cols) == 1 else "모든 열이 빈 행"
    print(f"{label}: 행 {fmt_n(rows)}개 · {empty} {fmt_n(holes)}개 · 겹친 값 {fmt_n(dups)}건")
    if holes > max(1, rows * NEAR_KEY_NULLS) or dups > filled * NEAR_KEY_DUPS:
        for ex in examples:
            print(f"  겹친 예: {', '.join(short(v) for v in ex[:-1])} ({fmt_n(ex[-1])}행)")
        die(f"키로 정하지 않았다. 빈 값은 행의 {pct(NEAR_KEY_NULLS)}, 겹친 값은 {pct(NEAR_KEY_DUPS)}까지만 받는다")
    dirt = ([f"빈 값 {fmt_n(holes)}건"] if holes else []) + ([f"겹친 값 {fmt_n(dups)}건"] if dups else [])
    note = "판정으로 정함" + (": 거의 키, " + ", ".join(dirt) if dirt else "")
    conn.execute("UPDATE _dm_tables SET key_cols=?, key_kind='manual', key_note=? WHERE name=?",
                 (json.dumps(cols, ensure_ascii=False), note, t))
    conn.commit()
    render(conn)
    print(f"키로 정했다 ({note}). {PROFILE}와 그림에 넣었다")


def cmd_check(args):
    refuse_while_building()
    conn = connect(write=True)
    child, ccols = parse_ref(conn, args.child)
    parent, pcols = parse_ref(conn, args.parent)
    if len(ccols) != len(pcols):
        die("양쪽 열 개수가 같아야 한다")
    problems = []
    rkey = same_relation(conn, child, ccols, parent, pcols)
    ccols, pcols = json.loads(rkey[1]), json.loads(rkey[3])
    m = measure(Budget(conn, args.query_timeout), child, ccols, parent, pcols, problems)
    save_relation(conn, rkey, "check", m, name_score(ccols[0], pcols[0], parent) if len(ccols) == 1 else 2)
    conn.commit()
    choose(conn)
    render(conn)
    cn, pn = f"{child}.{','.join(ccols)}", f"{parent}.{','.join(pcols)}"
    print(f"{cn} → {pn}")
    if m["matched"] is not None:
        print(f"  자식 값 {fmt_n(m['child_distinct'])}개 중 {fmt_n(m['matched'])}개가 부모에 있다 (포함 {pct(m['inclusion'])})")
        print(f"  부모 값 {fmt_n(m['parent_distinct'])}개 중 {fmt_n(m['matched'])}개를 자식이 가리킨다 (덮음 {pct(m['coverage'])})")
    unique = one_row_parent(m["parent_rows"], m["parent_distinct"])
    if unique:
        dups = m["parent_rows"] - m["parent_distinct"]
        print("  부모 쪽은 이 열로 한 행이 정해진다" + (f" (겹친 값 {fmt_n(dups)}건은 거의 키로 받았다)" if dups else "")
              + " → " + ("1:1" if one_to_one(m) else "자식 여러 행이 부모 한 행을 가리킨다 (N:1)"))
    elif m["parent_distinct"] is not None:
        print(f"  부모 쪽 값이 겹친다 (값 {fmt_n(m['parent_distinct'])}개, 행 {fmt_n(m['parent_rows'])}개) → N:M")
    if m["avg_fanout"] is not None:
        print(f"  부모 값 하나에 자식 평균 {m['avg_fanout']:.1f}행, 최대 {fmt_n(m['max_fanout'])}행")
    if m["join_rows"] is not None and m["child_rows"] is not None:
        grow = m["join_rows"] > m["child_rows"]
        print(f"  조인하면 {fmt_n(m['child_rows'])}행 → {fmt_n(m['join_rows'])}행"
              + (" (늘어난다: 합계를 내면 두 번 센다)" if grow else ""))
    ex = json.loads(m["orphan_examples"] or "[]")
    print("  부모에 없는 자식 값: " + (f"{fmt_n(m['orphan_rows'])}행, 예 {', '.join(map(str, ex))}" if ex else "없음"))
    for p in problems:
        print(f"  {p}")
    drawn = unique and included(m)
    print(f"기록: {PROFILE}의 관계 후보" + (" · 지도에 그림" if drawn else " · 지도에는 안 그림"))


def summarize(row, keys):
    names = [d for d in row.keys() if d not in ("__dm_rowid", "_dm_file")]
    order = [n for n in keys if n in names] + [n for n in names if n not in keys]
    parts = [f"{n}={short(row[n])}" for n in order if row[n] is not None][:6]
    return " · ".join(parts)


def cmd_trace(args):
    refuse_while_building()
    conn = connect(write=False)
    t, cols = parse_ref(conn, args.ref)
    if len(args.values) != len(cols):
        die(f"값 {len(cols)}개가 필요하다: {', '.join(cols)}")
    edges = drawn_edges(conn)
    keys = {r["name"]: json.loads(r["key_cols"] or "[]") for r in table_rows(conn)}
    def where(cs):
        return " AND ".join(f"{q(c)} = ?" for c in cs)

    rows = conn.execute(f"SELECT {rid(conn, t)} AS __dm_rowid, * FROM {q(t)} WHERE {where(cols)} LIMIT 3", args.values).fetchall()
    if not rows:
        print(f"{t}에서 {', '.join(cols)} = {', '.join(args.values)}인 행이 없다. 값 모양은 sql로 확인한다: "
              f"python3 {SCRIPT} sql \"SELECT {', '.join(q(c) for c in cols)} FROM {q(t)} LIMIT 5\"")
        return
    out = []

    def expand(tbl, row, depth, indent, came, visited):
        for e in edges:
            ek = (e["child"], e["child_cols"], e["parent"], e["parent_cols"])
            if ek == came:
                continue
            cc, pc = json.loads(e["child_cols"]), json.loads(e["parent_cols"])
            if e["child"] == tbl:
                vals = [row[c] for c in cc]
                if any(v is None for v in vals):
                    continue
                prow = conn.execute(f"SELECT {rid(conn, e['parent'])} AS __dm_rowid, * FROM {q(e['parent'])} WHERE {where(pc)} LIMIT 1", vals).fetchone()
                if prow is None:
                    out.append(f"{indent}↑ {e['parent']} ({arrow(e)}): 없음 — 고아 값")
                    continue
                out.append(f"{indent}↑ {e['parent']} ({arrow(e)}): {summarize(prow, keys.get(e['parent'], []))}")
                vk = (e["parent"], prow["__dm_rowid"])
                if depth > 1 and vk not in visited:
                    visited.add(vk)
                    expand(e["parent"], prow, depth - 1, indent + "    ", ek, visited)
            if e["parent"] == tbl:
                vals = [row[c] for c in pc]
                if any(v is None for v in vals):
                    continue
                n = conn.execute(f"SELECT COUNT(*) FROM {q(e['child'])} WHERE {where(cc)}", vals).fetchone()[0]
                out.append(f"{indent}↓ {e['child']} ({arrow(e)}): {n:,}행")
                for crow in conn.execute(f"SELECT {rid(conn, e['child'])} AS __dm_rowid, * FROM {q(e['child'])} WHERE {where(cc)} LIMIT 2", vals).fetchall():
                    out.append(f"{indent}    - {summarize(crow, keys.get(e['child'], []))}")
                    vk = (e["child"], crow["__dm_rowid"])
                    if depth > 1 and vk not in visited:
                        visited.add(vk)
                        expand(e["child"], crow, depth - 1, indent + "        ", ek, visited)
                if n > 2:
                    out.append(f"{indent}    … {n - 2:,}행 더")

    for row in rows:
        out.append(f"{t}: {summarize(row, keys.get(t, []))}")
        expand(t, row, args.depth, "  ", None, {(t, row["__dm_rowid"])})
    if not edges:
        out.append("  (지도에 그린 관계가 없어 따라갈 곳이 없다. check로 관계를 먼저 잰다)")
    print("\n".join(out))


def cmd_sql(args):
    refuse_while_building()
    conn = connect(write=False)
    b = Budget(conn, args.query_timeout)
    b.deadline = time.monotonic() + args.query_timeout
    import sqlite3
    try:
        cur = conn.execute(args.query)
        names = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(args.limit + 1)
    except sqlite3.OperationalError as e:
        die(f"SQL 오류: {e}" if "interrupt" not in str(e).lower() else f"{args.query_timeout}초가 넘어 멈췄다. 조건이나 LIMIT을 더한다")
    finally:
        b.deadline = None
    if not names:
        print("결과 없음")
        return
    more = len(rows) > args.limit
    rows = rows[:args.limit]
    cells = [[short(v, 40) if v is not None else "" for v in r] for r in rows]
    widths = [max([len(str(n))] + [len(c[i]) for c in cells]) for i, n in enumerate(names)]
    print("  ".join(str(n).ljust(w) for n, w in zip(names, widths)))
    for c in cells:
        print("  ".join(v.ljust(w) for v, w in zip(c, widths)))
    print(f"({len(rows)}행" + ("까지만 보였다. 더 있다" if more else "") + ")")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="datamap.py", description="CSV·TSV를 SQLite에 담고 표의 키와 표끼리의 관계를 값으로 잰다.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="파일·인코딩·구분자·예상 행 수를 몇 초 안에 본다")
    s.add_argument("paths", nargs="*")
    s.add_argument("--split", action="store_true", help="머리 줄이 같은 파일도 묶지 않고 파일마다 따로 표로 둔다")
    s = sub.add_parser("build", help=f"적재하고 키·관계를 재서 {PROFILE}를 만든다")
    s.add_argument("paths", nargs="*")
    s.add_argument("--limit-rows", type=int, default=0, help="파일마다 앞 N행만 읽는다")
    s.add_argument("--split", action="store_true", help="머리 줄이 같은 파일도 묶지 않고 파일마다 따로 표로 둔다")
    s.add_argument("--background", action="store_true", help="뒤에서 돌리고 바로 돌아온다. 진행은 status로 본다")
    s.add_argument("--query-timeout", type=int, default=120, help="질의 하나의 시간 한도(초)")
    sub.add_parser("status", help="build 진행과 로그 끝을 본다")
    sub.add_parser("stop", help="뒤에서 도는 build를 멈춘다")
    s = sub.add_parser("check", help="관계 하나를 잰다: check 자식표.열[,열] 부모표.열[,열]")
    s.add_argument("child")
    s.add_argument("parent")
    s.add_argument("--query-timeout", type=int, default=300)
    s = sub.add_parser("drop", help="뜻으로 보아 관계가 아닌 선을 지도에서 뺀다: drop 자식표.열[,열] 부모표.열[,열] \"이유\"")
    s.add_argument("child")
    s.add_argument("parent")
    s.add_argument("reason")
    s.add_argument("--query-timeout", type=int, default=300)
    s = sub.add_parser("key", help="표의 키를 정한다. 값이 받쳐 줄 때만 받는다: key 표.열[,열]")
    s.add_argument("ref")
    s.add_argument("--query-timeout", type=int, default=300)
    s = sub.add_parser("trace", help="값 하나를 관계를 따라 여러 표에서 찾는다: trace 표.열 값")
    s.add_argument("ref")
    s.add_argument("values", nargs="+")
    s.add_argument("--depth", type=int, default=2)
    s = sub.add_parser("sql", help="읽기 전용 SQL을 돌리고 앞 N행만 보여 준다")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--query-timeout", type=int, default=120)
    args = ap.parse_args(argv)
    {"scan": cmd_scan, "build": cmd_build, "status": cmd_status, "stop": cmd_stop, "check": cmd_check,
     "drop": cmd_drop, "key": cmd_key, "trace": cmd_trace, "sql": cmd_sql}[args.cmd](args)


if __name__ == "__main__":
    main()
