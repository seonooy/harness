"""공개 예제 DB(Chinook, Northwind, Sakila)로 datamap.py를 채점한다. 실행: python3 tests/bench_public_dbs.py

DB를 내려받아 표마다 CSV로 풀고 build를 돌린 뒤, 지도에 그린 관계를 DB에 선언된 외래키와 대조해
재현율(선언된 것 중 찾은 것)과 정밀도(그린 것 중 맞은 것)를 낸다. 네트워크가 필요하다.
"""
import csv, json, re, shutil, sqlite3, subprocess, sys, tempfile, urllib.request
from pathlib import Path

DBS = {
    "chinook": "https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite",
    "northwind": "https://raw.githubusercontent.com/jpwhite3/northwind-SQLite3/main/dist/northwind.db",
    "sakila": "https://raw.githubusercontent.com/bradleygrant/sakila-sqlite3/main/sakila_master.db",
}
SCRIPT = str(Path(__file__).resolve().parent.parent / "skills" / "data-map" / "scripts" / "datamap.py")


def norm(s):
    return re.sub(r"[^0-9a-z]+", "_", s.lower()).strip("_")


def bench(db, work):
    shutil.rmtree(work, ignore_errors=True)
    (work / "data").mkdir(parents=True)
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    src.text_factory = lambda b: b.decode("utf-8", "replace")
    tables = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    truth = set()
    for t in tables:
        cur = src.execute(f'SELECT * FROM "{t}"')
        with open(work / "data" / f"{t}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([d[0] for d in cur.description])
            for row in cur:
                w.writerow([v.hex() if isinstance(v, bytes) else v for v in row])
        fks = {}
        for fid, seq, parent, frm, to, *_ in src.execute(f'PRAGMA foreign_key_list("{t}")'):
            fks.setdefault(fid, []).append((seq, parent, frm, to))
        for parts in fks.values():
            parts.sort()
            parent = parts[0][1]
            tos = [p[3] for p in parts]
            if None in tos:
                tos = [r[1] for r in sorted(src.execute(f'PRAGMA table_info("{parent}")'), key=lambda r: r[5]) if r[5]]
            truth.add((norm(t), tuple(norm(p[2]) for p in parts), norm(parent), tuple(norm(x) for x in tos)))
    r = subprocess.run([sys.executable, SCRIPT, "build", "data"], cwd=work, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-2000:]); return
    out = sqlite3.connect(work / ".datamap" / "data.sqlite")
    drawn = {(norm(c), tuple(norm(x) for x in json.loads(cc)), norm(p), tuple(norm(x) for x in json.loads(pc))): v
             for c, cc, p, pc, v in out.execute("SELECT child, child_cols, parent, parent_cols, verdict FROM _dm_relations")}
    got = {k for k, v in drawn.items() if v in ("drawn", "checked")}
    ok = truth & got
    fmt = lambda k: f"{k[0]}.{','.join(k[1])} → {k[2]}.{','.join(k[3])}"
    print(f"{db.name}: 표 {len(tables)}개 · 선언된 외래키 {len(truth)}개 · 지도에 그림 {len(got)}개 · 맞음 {len(ok)}개 "
          f"(재현율 {len(ok)}/{len(truth)}, 정밀도 {len(ok)}/{len(got)})  [{r.stdout.strip().splitlines()[-1][:60]}]")
    for k in sorted(truth - got):
        print(f"  놓침  {fmt(k)}  (판정: {drawn.get(k, '후보 아님')})")
    for k in sorted(got - truth):
        print(f"  틀림  {fmt(k)}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for name, url in DBS.items():
            db = root / f"{name}.db"
            urllib.request.urlretrieve(url, db)
            bench(db, root / name)
