"""datamap.py 부하 시험용 가짜 제조 데이터 7종을 만든다. 실행: python3 tests/make_big_data.py <폴더> [--lots 40000]

lot 하나에 wafer 25장, wafer 하나에 측정 4번이라 기본값이면 534만 행, 240MB다.
"""
import argparse
import csv
import random
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--lots", type=int, default=40000)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(1)

    def writer(name, header, encoding="utf-8"):
        f = open(out / name, "w", encoding=encoding, newline="")
        w = csv.writer(f)
        w.writerow(header)
        return f, w

    types = [f"TYPE{i}" for i in range(1, 9)]
    f, w = writer("equipment.csv", ["equipment_id", "equipment_type", "fab"])
    equipment = [f"EQ{i:04d}" for i in range(1, 201)]
    for e in equipment:
        w.writerow([e, rng.choice(types), rng.choice(["FAB-A", "FAB-B", "FAB-C"])])
    f.close()

    f, w = writer("recipes.csv", ["recipe_id", "recipe_name", "equipment_type"])
    recipes = [f"RCP{i:04d}" for i in range(1, 301)]
    for r in recipes:
        w.writerow([r, f"recipe-{r[-4:]}", rng.choice(types)])
    f.close()

    f, w = writer("steps.csv", ["step_id", "step_name", "recipe_id"])
    for s in range(1, 31):
        w.writerow([s, f"STEP-{s:02d}", rng.choice(recipes)])
    f.close()

    f, w = writer("lots.csv", ["lot_id", "product", "start_time", "parent_lot_id"])
    lots = [f"L{i:07d}" for i in range(1, args.lots + 1)]
    for i, lot in enumerate(lots):
        parent = lots[rng.randrange(i)] if i and rng.random() < 0.05 else ""
        w.writerow([lot, rng.choice(["PROD-A", "PROD-B", "PROD-C", "PROD-D", "PROD-E"]),
                    f"2026-0{1 + i % 6}-{1 + i % 28:02d} {i % 24:02d}:{i % 60:02d}:00", parent])
    f.close()

    f, w = writer("wafers.csv", ["wafer_id", "lot_id", "wafer_no"])
    parts = [writer(f"measurements_{p:02d}.csv", ["wafer_id", "step_id", "equipment_id", "param", "value", "measured_at"])
             for p in range(1, 5)]
    params = ["THK", "CD", "OVL", "TEMP", "PRES", "RS"]
    n = 0
    for lot in lots:
        for no in range(1, 26):
            n += 1
            wid = f"W{n:08d}"
            w.writerow([wid, lot, no])
            mw = parts[(n - 1) * 4 // (len(lots) * 25)][1]
            for step in rng.sample(range(1, 31), 4):
                mw.writerow([wid, step, rng.choice(equipment), rng.choice(params), round(rng.gauss(100, 15), 3),
                             f"2026-0{1 + n % 6}-{1 + n % 28:02d} {n % 24:02d}:{step:02d}:{n % 60:02d}"])
    f.close()
    for pf, _ in parts:
        pf.close()

    f, w = writer("alarms.csv", ["alarm_id", "equipment_id", "lot_id", "severity", "occurred_at", "message"], "cp949")
    messages = ["온도 초과", "압력 저하", "진공 이상", "도어 열림", "통신 끊김"]
    for i in range(1, args.lots * 15 // 2 + 1):
        lot = rng.choice(lots) if rng.random() > 0.005 else f"L9{rng.randrange(10 ** 6):06d}"
        w.writerow([i, rng.choice(equipment), lot, rng.randint(1, 5), f"2026-0{1 + i % 6}-{1 + i % 28:02d} 12:00:00",
                    rng.choice(messages)])
    f.close()
    (out / "README.md").write_text("# 가짜 제조 데이터\nlot은 wafer 25장을 담는다. 측정은 wafer와 공정 단계마다 남는다.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
