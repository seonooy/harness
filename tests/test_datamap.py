"""data-map 스킬의 datamap.py (명령: scan, build, status, stop, check, drop, key, trace, sql)

명령줄 그대로 돌려 확인한다. 실행: python3 -m unittest discover -s tests

계약:
- scan은 적재 전에 파일마다 인코딩·구분자·머리 줄, 한 표로 묶일 파일, 읽을 문서를 알려 준다 → DataMapCase.test_scan_reports_shape_before_loading
- build는 지저분한 파일도 행을 잃지 않고 읽고, 못 읽은 곳은 이유와 함께 프로파일에 적는다 → DataMapCase.test_build_reads_messy_files_without_losing_rows, ShapesCase.test_build_survives_every_shape, ShapesCase.test_title_lines_above_the_table_are_skipped, ShapesCase.test_unclosed_quote_does_not_swallow_the_rest_of_a_file, ShapesCase.test_short_unclosed_quote_is_reported, ShapesCase.test_too_wide_tables_keep_the_first_columns, ShapesCase.test_excel_unicode_text_is_read_as_a_table, ShapesCase.test_cr_only_line_endings, ShapesCase.test_repeated_header_rows_are_dropped, ShapesCase.test_backslash_n_is_null, ShapesCase.test_compressed_file_is_skipped_with_a_reason, ShapesCase.test_odd_header_names_become_usable_column_names, ShapesCase.test_prose_txt_stays_a_document
- 값의 종류와 구분자를 값 모양으로 가린다 → DetectionTable.test_value_classes, DetectionTable.test_delimiters
- 표마다 한 행을 정하는 키를 찾는다. 한두 칸 어긋난 열도 거의 키로 받아 어긋난 칸을 문제에 적고, 다른 표가 가리키는 열을 키로 고른다 → DataMapCase.test_build_finds_the_row_key_of_each_table, DirtyKeyCase.test_parent_missing_being_a_key_by_a_few_cells_is_still_found, DirtyKeyCase.test_the_cells_that_break_a_key_are_reported, DirtyKeyCase.test_a_near_key_others_point_at_beats_a_number_that_happens_to_be_unique, DirtyKeyCase.test_the_column_other_tables_point_at_becomes_the_key, DirtyKeyCase.test_a_clean_key_stays_when_nothing_points_at_the_other_candidates, DirtyKeyCase.test_a_column_with_a_few_empty_values_can_be_part_of_a_key, DirtyKeyCase.test_a_column_with_many_repeats_is_not_called_a_near_key
- 초안은 값과 이름의 글자 모양이 함께 받치는 관계만 그리고, 값만 맞는 것은 후보로 올린다 → DataMapCase.test_build_draws_relations_that_values_and_names_support, DataMapCase.test_values_that_only_happen_to_match_are_not_drawn, DetectionTable.test_name_scores, ServiceShapeCase.test_one_to_one_extension_does_not_hide_the_real_parent, ServiceShapeCase.test_timestamps_made_together_are_not_a_relation, ServiceShapeCase.test_two_column_reference_with_other_names_is_listed_by_values, ServiceShapeCase.test_reference_into_a_two_column_key_is_found, ServiceShapeCase.test_self_reference_without_a_name_hint_is_listed_as_a_candidate, ServiceShapeCase.test_another_id_column_of_the_same_row_is_not_drawn_as_a_self_reference, DraftRuleCase.test_among_same_named_parents_the_table_that_holds_every_key_is_drawn, DraftRuleCase.test_a_copied_value_of_a_unique_non_key_column_is_not_drawn, DraftRuleCase.test_a_column_that_is_almost_all_empty_is_still_measured
- check는 관계 하나를 값으로 재고, 받치면 지도에 그린다(여러 열, 거의 키 부모, 한 열에 부모 하나, 조인하면 행이 느는 경고) → DataMapCase.test_check_measures_a_composite_relation_and_draws_it, DataMapCase.test_check_warns_when_join_multiplies_rows, DirtyKeyCase.test_check_draws_a_line_to_a_parent_with_one_duplicate_like_build_does, JudgeCase.test_after_check_picks_a_parent_the_other_candidates_are_not_drawn, EmptyPartKeyCase.test_check_counts_rows_with_an_empty_part_instead_of_skipping_them
- drop으로 뺀 선은 지도와 그림에서 빠지고 이유가 남으며, 다시 build해도 돌아오지 않는다 → JudgeCase.test_drop_takes_an_edge_off_the_map_and_check_puts_it_back, JudgeCase.test_drop_finds_the_same_relation_written_in_another_column_order, JudgeCase.test_dropping_a_value_only_candidate_does_not_raise_the_next_one
- key는 값이 받칠 때만 키를 바꾸고, 바꾼 키는 다시 build해도 남는다 → JudgeCase.test_key_sets_a_key_the_values_support_and_keeps_it_after_a_rebuild, JudgeCase.test_key_refuses_columns_whose_values_repeat, EmptyPartKeyCase.test_key_accepts_a_column_set_whose_second_column_is_mostly_empty
- 프로파일과 구조도는 관계 지도, 문제, 후보 목록, 키 표시를 보여 준다 → DataMapCase.test_profile_shows_tree_and_problems, DataMapCase.test_erd_puts_parents_left_and_marks_keys, ServiceShapeCase.test_value_only_candidates_are_listed_apart_by_whether_the_parent_key_is_a_number
- trace는 값 하나를 관계를 따라 여러 표에서 찾는다 → DataMapCase.test_trace_follows_one_value_across_tables, ShapesCase.test_trace_works_with_a_column_named_rowid
- sql은 읽기만 하고 앞 몇 행만 보여 준다 → DataMapCase.test_sql_is_read_only, DataMapCase.test_sql_prints_only_the_first_rows
- --split은 머리 줄이 같은 파일도 파일마다 표로 둔다 → JudgeCase.test_split_keeps_differently_named_files_with_one_header_as_separate_tables
- 앞부분만 읽은 표를 표시하고, 같은 파일은 다시 읽지 않으며, 뒤에서 돌린 build를 status가 알려 준다 → RebuildCase.test_limit_rows_marks_cut_tables_and_rebuild_reuses_loaded_tables, RebuildCase.test_background_build_finishes_and_status_reports_it
- stop은 뒤에서 도는 build를 멈춘다
"""
import csv
import importlib.util
import json
import random
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "data-map" / "scripts" / "datamap.py"
spec = importlib.util.spec_from_file_location("datamap", SCRIPT)
datamap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(datamap)
SVG_NS = "{http://www.w3.org/2000/svg}"


def write_csv(path, header, rows, encoding="utf-8", delimiter=","):
    with open(path, "w", encoding=encoding, newline="") as f:
        w = csv.writer(f, delimiter=delimiter)
        if header:
            w.writerow(header)
        w.writerows(rows)


def run_cli(root, *args, check=True):
    r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root, capture_output=True, text=True, timeout=120)
    if check and r.returncode != 0:
        raise AssertionError(f"{args} 실패\n{r.stdout}\n{r.stderr}")
    return r


def open_db(root):
    conn = sqlite3.connect(root / ".datamap" / "data.sqlite")
    conn.row_factory = sqlite3.Row
    return conn


def verdicts(root):
    conn = open_db(root)
    got = {(r["child"] + "." + ",".join(json.loads(r["child_cols"])),
            r["parent"] + "." + ",".join(json.loads(r["parent_cols"]))): r["verdict"]
           for r in conn.execute("SELECT * FROM _dm_relations")}
    conn.close()
    return got


def key_of(root, table):
    conn = open_db(root)
    row = conn.execute("SELECT key_cols FROM _dm_tables WHERE name=?", (table,)).fetchone()
    conn.close()
    return json.loads(row[0])


def svg_edges(root):
    svg = ET.parse(root / "notes" / "data-map.svg").getroot()
    return {(p.get("data-child"), p.get("data-parent")) for p in svg.iter(SVG_NS + "path") if p.get("class") == "edge"}


def make_fixture(root):
    rng = random.Random(7)
    data = root / "data"
    data.mkdir()
    (data / "README.md").write_text("# 주문 데이터\n고객이 주문하고, 주문에는 품목이 여러 줄 있다.\n", encoding="utf-8")
    write_csv(data / "customers.csv", ["customer_id", "name", "region", "grade"],
              [[i, f"고객{i}", rng.choice(["서울", "부산", "대구"]), rng.choice("ABC")] for i in range(1, 51)],
              encoding="utf-8-sig")
    orders = []
    for i in range(200):
        memo = "줄바꿈\n있는 메모" if i == 5 else f"메모{i}"
        orders.append([1001 + i, (i % 50) + 1, f"2024-01-{(i % 28) + 1:02d}", rng.choice([1, 2, 3]), memo])
    write_csv(data / "orders.csv", ["order_id", "customer_id", "order_date", "status", "memo"], orders, encoding="cp949")
    with open(data / "orders.csv", "a", encoding="cp949", newline="") as f:
        f.write("1201,3,2024-02-01,2,남는칸,하나더\n")
    items, ships = [], []
    for o in range(1001, 1202):
        for line in range(1, rng.randint(1, 4) + 1):
            items.append([o, line, f"P{rng.randint(1, 30):03d}", rng.randint(1, 5), round(rng.uniform(1, 99), 2)])
            if rng.random() < 0.5:
                ships.append([len(ships) + 1, o, line, f"2024-02-{(o % 28) + 1:02d} 10:00:00"])
    write_csv(data / "order_items.tsv", ["order_id", "line_no", "product_id", "qty", "price"], items, delimiter="\t")
    write_csv(data / "shipments.csv", ["shipment_id", "order_id", "line_no", "shipped_at"], ships)
    for part, ids in ((1, range(1, 16)), (2, range(16, 31))):
        write_csv(data / f"products_{part}.csv", ["product_id", "product_name", "category_code"],
                  [[f"P{i:03d}", f"상품{i}", f"C{(i % 6) + 1:02d}"] for i in ids])
    write_csv(data / "categories.csv", ["category_id", "parent_category_id", "category_name"],
              [["C01", "", "전체"], ["C02", "C01", "식품"], ["C03", "C01", "가전"], ["C04", "C02", "과자"],
               ["C05", "C02", "음료"], ["C06", "C03", "TV"]])
    with open(data / "events.csv", "w", encoding="utf-8", newline="") as f:
        f.write("event_id,customer_id,note\n1,1,ok\n2,2,bad\0byte\n3,3,ok\n")
    write_csv(data / "readings.csv", None, [[i, round(i * 0.5, 1), "2024-03-01"] for i in range(1, 11)])


class DataMapCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        make_fixture(cls.root)
        run_cli(cls.root, "build", "data")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_scan_reports_shape_before_loading(self):
        out = run_cli(self.root, "scan", "data").stdout
        self.assertIn("cp949", out)
        self.assertIn("utf-8-sig", out)
        self.assertIn("탭", out)
        self.assertIn("products ← 파일 2개", out)
        self.assertIn("머리 줄이 없어 보임: data/readings.csv", out)
        self.assertIn("먼저 읽을 문서: data/README.md", out)

    def test_build_finds_the_row_key_of_each_table(self):
        self.assertEqual(key_of(self.root, "customers"), ["customer_id"])
        self.assertEqual(key_of(self.root, "orders"), ["order_id"])
        self.assertEqual(key_of(self.root, "order_items"), ["order_id", "line_no"])
        self.assertEqual(key_of(self.root, "products"), ["product_id"])
        rows = open_db(self.root).execute("SELECT rows FROM _dm_tables WHERE name='products'").fetchone()[0]
        self.assertEqual(rows, 30)

    def test_build_draws_relations_that_values_and_names_support(self):
        v = verdicts(self.root)
        for edge in [("orders.customer_id", "customers.customer_id"),
                     ("order_items.order_id", "orders.order_id"),
                     ("order_items.product_id", "products.product_id"),
                     ("products.category_code", "categories.category_id"),
                     ("categories.parent_category_id", "categories.category_id"),
                     ("shipments.order_id", "orders.order_id")]:
            self.assertEqual(v.get(edge), "drawn", edge)

    def test_values_that_only_happen_to_match_are_not_drawn(self):
        v = verdicts(self.root)
        for edge in [("orders.status", "customers.customer_id"), ("order_items.qty", "readings.col_1"),
                     ("events.event_id", "events.customer_id")]:
            self.assertNotEqual(v.get(edge), "drawn", edge)

    def test_build_reads_messy_files_without_losing_rows(self):
        conn = open_db(self.root)
        f = conn.execute("SELECT * FROM _dm_files WHERE path LIKE '%orders.csv'").fetchone()
        self.assertEqual((f["encoding"], f["rows"], f["bad_rows"], f["replaced"]), ("cp949", 201, 1, 0))
        memo = conn.execute("SELECT memo FROM orders WHERE order_id='1006'").fetchone()[0]
        self.assertEqual(memo, "줄바꿈\n있는 메모")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 3)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0], 10)

    def test_profile_shows_tree_and_problems(self):
        text = (self.root / "notes" / "data-profile.md").read_text(encoding="utf-8")
        self.assertIn("## 관계 지도", text)
        self.assertIn("└── order_items", text)
        self.assertIn("칸 수가 머리 줄과 다른 행 1개", text)
        self.assertIn("data/README.md", text)

    def test_check_measures_a_composite_relation_and_draws_it(self):
        out = run_cli(self.root, "check", "shipments.order_id,line_no", "order_items.order_id,line_no").stdout
        self.assertIn("포함 100%", out)
        self.assertIn("1:1", out)
        self.assertEqual(verdicts(self.root).get(("shipments.order_id,line_no", "order_items.order_id,line_no")), "checked")

    def test_check_warns_when_join_multiplies_rows(self):
        out = run_cli(self.root, "check", "orders.order_id", "order_items.order_id").stdout
        self.assertIn("N:M", out)
        self.assertIn("두 번 센다", out)
        self.assertEqual(verdicts(self.root).get(("orders.order_id", "order_items.order_id")), "checked-nm")

    def test_trace_follows_one_value_across_tables(self):
        out = run_cli(self.root, "trace", "customers.customer_id", "1").stdout
        self.assertIn("↓ orders", out)
        self.assertIn("↓ order_items", out)

    def test_erd_puts_parents_left_and_marks_keys(self):
        root = ET.parse(self.root / "notes" / "data-map.svg").getroot()
        groups = {g.get("data-name"): g for g in root.iter(SVG_NS + "g") if g.get("class") == "table"}
        left = {n: float(g.find(SVG_NS + "rect").get("x")) for n, g in groups.items()}
        self.assertLess(left["customers"], left["orders"])
        self.assertLess(left["orders"], left["order_items"])
        self.assertLess(left["categories"], left["products"])
        self.assertIn("readings", left)
        texts = [t.text for t in groups["orders"].iter(SVG_NS + "text")]
        self.assertEqual(texts[texts.index("customer_id") - 1], "FK")
        self.assertEqual(texts[texts.index("order_id") - 1], "PK")
        edges = svg_edges(self.root)
        for pair in [("orders", "customers"), ("order_items", "orders"), ("order_items", "products"), ("shipments", "orders")]:
            self.assertIn(pair, edges)

    def test_sql_is_read_only(self):
        r = run_cli(self.root, "sql", "DELETE FROM customers", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(open_db(self.root).execute("SELECT COUNT(*) FROM customers").fetchone()[0], 50)

    def test_sql_prints_only_the_first_rows(self):
        out = run_cli(self.root, "sql", "SELECT * FROM order_items", "--limit", "3").stdout
        self.assertIn("3행까지만 보였다", out)


class RebuildCase(unittest.TestCase):
    def test_limit_rows_marks_cut_tables_and_rebuild_reuses_loaded_tables(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            make_fixture(root)
            run_cli(root, "build", "data", "--limit-rows", "20")
            text = (root / "notes" / "data-profile.md").read_text(encoding="utf-8")
            self.assertIn("앞 20행만", text)
            self.assertIn("orders", text.split("잘린 표:")[1].split("\n")[0])
            again = run_cli(root, "build", "data", "--limit-rows", "20").stdout
            self.assertIn("customers: 지난번과 같은 파일이라 다시 읽지 않는다", again)

    def test_background_build_finishes_and_status_reports_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            make_fixture(root)
            self.assertIn("뒤에서 시작했다", run_cli(root, "build", "data", "--background").stdout)
            deadline = time.time() + 60
            while time.time() < deadline and "도는 build 없음" not in run_cli(root, "status").stdout:
                time.sleep(0.5)
            status = run_cli(root, "status").stdout
            self.assertIn("마지막 build: 끝났다", status)
            self.assertIn("끝: 표", status)


class DetectionTable(unittest.TestCase):
    def test_value_classes(self):
        cases = [("12", datamap.INT | datamap.FLOAT), ("-3", datamap.INT | datamap.FLOAT), ("007", 0),
                 ("1.5", datamap.FLOAT), ("1e3", datamap.FLOAT), ("2024-01-02", datamap.DATE | datamap.DATETIME),
                 ("2024/1/2 10:30:00", datamap.DATETIME), ("A12", 0), ("1234567890123456789", 0)]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(datamap.vclass(value), expected)

    def test_delimiters(self):
        cases = [(["a,b,c", "1,2,3"], False, ","), (["a\tb", "1,5\t2"], False, "\t"),
                 (["a;b;c", "1;2;3"], False, ";"), (["a|b", "x|y"], False, "|"), (["a,b", "1,2"], True, ",")]
        for lines, prefer_tab, expected in cases:
            with self.subTest(lines=lines):
                self.assertEqual(datamap.detect_delim(lines, prefer_tab), expected)

    def test_name_scores(self):
        # 넷째 칸은 "이 데이터에서 여러 표가 키 이름으로 쓰는 이름", 다섯째 칸은 "자식 열이 자기 표의 키인가"다.
        cases = [("lot_id", "lot_id", "lots", set(), False, 3), ("customer_id", "id", "customers", {"id"}, False, 3),
                 ("id", "id", "orders", {"id"}, True, 0), ("parent_lot_id", "lot_id", "lots", set(), False, 2),
                 ("tool", "equipment_id", "equipment", set(), False, 0),
                 ("category_code", "category_id", "categories", set(), False, 0),
                 ("rental_duration", "rental_id", "rental", set(), False, 0),
                 ("order_code", "code", "products", {"code"}, False, 0),
                 ("user_id", "user_id", "users", {"userid"}, True, 3), ("member_id", "member_id", "teams", {"memberid"}, True, 0),
                 ("member_id", "member_id", "teams", {"memberid"}, False, 3)]
        for src, tgt, table, generic, own_key, expected in cases:
            with self.subTest(src=src, tgt=tgt, own_key=own_key):
                self.assertEqual(datamap.name_score(src, tgt, table, generic=frozenset(generic), own_key=own_key), expected)


def make_dirty(root):
    """실제 데이터에서 본 모양: 부모 열이 한두 칸 어긋나 키에서 떨어진다(글자 NA, 중복 1건, 빈 값 몇 건)."""
    rng = random.Random(11)
    data = root / "data"
    data.mkdir()
    codes = ["KR", "JP", "US", "NA", "DE", "FR", "GB", "IT", "ES", "CN", "IN", "BR", "MX", "CA", "AU", "NZ", "SE", "NO",
             "FI", "DK", "NL", "BE", "CH", "AT", "PL", "CZ", "HU", "PT", "GR", "TR"]
    write_csv(data / "country.csv", ["code", "name", "population"],
              [[c, f"나라{i}", 1000000 + i * 7919] for i, c in enumerate(codes)])
    write_csv(data / "city.csv", ["city_id", "city_name", "country"],
              [[i, f"도시{i}", codes[i % len(codes)]] for i in range(1, 301)])
    players = [[f"p{i:05d}", f"선수{i}"] for i in range(1, 2001)]
    players.append(["p00007", "선수7 다시"])
    write_csv(data / "player.csv", ["player_id", "player_name"], players)
    write_csv(data / "score.csv", ["score_id", "player_id", "points"],
              [[i, f"p{rng.randint(1, 2000):05d}", rng.randint(0, 50)] for i in range(1, 6001)])
    write_csv(data / "staff.csv", ["staff_no", "badge_id", "team"],
              [[i, "" if i % 40 == 0 else f"B{i:04d}", rng.choice("ABC")] for i in range(1, 401)])
    write_csv(data / "visit.csv", ["visit_id", "badge_id", "minutes"],
              [[i, f"B{rng.choice([n for n in range(1, 401) if n % 40]):04d}", rng.randint(1, 90)] for i in range(1, 1501)])
    # 지역 이름은 나라마다 되풀이된다. (region_name, country)가 한 행을 정하고, country의 NA는 빈 값으로 읽힌다.
    write_csv(data / "region.csv", ["region_name", "country", "area"],
              [[r, c, round(rng.uniform(1, 999), 1)] for c in codes for r in ("북부", "중부", "남부")])


class DirtyKeyCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        make_dirty(root)
        run_cli(root, "build", "data")
        cls.verdict = verdicts(root)
        conn = open_db(root)
        cls.keys = {r[0]: json.loads(r[1]) for r in conn.execute("SELECT name, key_cols FROM _dm_tables")}
        cls.notes = {(r[0], r[1]): r[2] or "" for r in conn.execute("SELECT tbl, name, note FROM _dm_columns")}
        conn.close()
        cls.profile = (root / "notes" / "data-profile.md").read_text(encoding="utf-8")
        cls.problems = cls.profile.split("## 문제")[1]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_parent_missing_being_a_key_by_a_few_cells_is_still_found(self):
        cases = [("빈 값으로 읽힌 글자 1건", ("city.country", "country.code")),
                 ("겹친 값 1건", ("score.player_id", "player.player_id")),
                 ("빈 값 몇 건", ("visit.badge_id", "staff.badge_id"))]
        for why, edge in cases:
            with self.subTest(why):
                self.assertEqual(self.verdict.get(edge), "drawn")

    def test_the_cells_that_break_a_key_are_reported(self):
        for part in ["country.code", "'NA' 1건", "player.player_id", "겹친 값 1건", "staff.badge_id", "빈 값 10건"]:
            self.assertIn(part, self.problems)

    def test_a_near_key_others_point_at_beats_a_number_that_happens_to_be_unique(self):
        self.assertEqual(self.keys["country"], ["code"])
        self.assertEqual(self.keys["player"], ["player_id"])
        self.assertIn("- 키 code (거의 키: 빈 값 1건)", self.profile)

    def test_the_column_other_tables_point_at_becomes_the_key(self):
        self.assertEqual(self.keys["staff"], ["badge_id"])

    def test_a_clean_key_stays_when_nothing_points_at_the_other_candidates(self):
        self.assertEqual(self.keys["city"], ["city_id"])
        self.assertEqual(self.keys["visit"], ["visit_id"])

    def test_a_column_with_a_few_empty_values_can_be_part_of_a_key(self):
        self.assertEqual(self.keys["region"], ["region_name", "country"])
        self.assertIn("- 키 (region_name, country) (country에 빈 값 3건)", self.profile)

    def test_check_draws_a_line_to_a_parent_with_one_duplicate_like_build_does(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            make_dirty(root)
            run_cli(root, "build", "data")
            out = run_cli(root, "check", "score.player_id", "player.player_id").stdout
            self.assertIn("지도에 그림", out)
            self.assertIn("겹친 값 1건", out)

    def test_a_column_with_many_repeats_is_not_called_a_near_key(self):
        self.assertIn("거의 키", self.notes[("player", "player_id")])
        self.assertNotIn("거의 키", self.notes[("score", "player_id")])
        self.assertNotIn("거의 키", self.notes[("city", "country")])


class JudgeCase(unittest.TestCase):
    """모델의 판정(선을 뺀다, 키를 정한다)이 프로파일과 그림에 들어간다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        make_fixture(cls.root)
        run_cli(cls.root, "build", "data")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_drop_takes_an_edge_off_the_map_and_check_puts_it_back(self):
        pair = ("events.customer_id", "customers.customer_id")
        self.assertEqual(verdicts(self.root).get(pair), "drawn")
        self.assertIn(("events", "customers"), svg_edges(self.root))
        out = run_cli(self.root, "drop", *pair, "시험 삼아 뺀다").stdout
        self.assertIn("지도에서 뺐다", out)
        self.assertEqual(verdicts(self.root).get(pair), "dropped")
        self.assertNotIn(("events", "customers"), svg_edges(self.root))
        self.assertIn("시험 삼아 뺀다", (self.root / "notes" / "data-profile.md").read_text(encoding="utf-8"))
        run_cli(self.root, "build", "data")
        self.assertEqual(verdicts(self.root).get(pair), "dropped", "다시 build해도 뺀 선은 돌아오지 않는다")
        run_cli(self.root, "check", *pair)
        self.assertEqual(verdicts(self.root).get(pair), "checked")
        self.assertIn(("events", "customers"), svg_edges(self.root))

    def test_drop_finds_the_same_relation_written_in_another_column_order(self):
        run_cli(self.root, "check", "shipments.order_id,line_no", "order_items.order_id,line_no")
        self.assertIn(("shipments", "order_items"), svg_edges(self.root))
        run_cli(self.root, "drop", "shipments.line_no,order_id", "order_items.line_no,order_id", "열 순서만 바꿔 썼다")
        self.assertEqual(verdicts(self.root).get(("shipments.order_id,line_no", "order_items.order_id,line_no")), "dropped")
        self.assertNotIn(("shipments", "order_items"), svg_edges(self.root))

    def test_key_sets_a_key_the_values_support_and_keeps_it_after_a_rebuild(self):
        self.assertEqual(key_of(self.root, "shipments"), ["shipment_id"])
        out = run_cli(self.root, "key", "shipments.order_id,line_no").stdout
        self.assertIn("키로 정했다", out)
        self.assertEqual(key_of(self.root, "shipments"), ["order_id", "line_no"])
        run_cli(self.root, "build", "data")
        self.assertEqual(key_of(self.root, "shipments"), ["order_id", "line_no"])

    def test_after_check_picks_a_parent_the_other_candidates_are_not_drawn(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "data").mkdir()
            ids = [[f"T{i:03d}", i] for i in range(1, 41)]
            write_csv(root / "data" / "squad_a.csv", ["team_id", "rank_a"], ids)
            write_csv(root / "data" / "squad_b.csv", ["team_id", "rank_b"], ids)
            write_csv(root / "data" / "game.csv", ["game_id", "team_id"], [[i, f"T{(i % 40) + 1:03d}"] for i in range(1, 201)])
            # club_stats는 club과 1:1이다. 열 이름에 club이 들어 있어 club_stats → club 한 방향만 그려진다.
            write_csv(root / "data" / "club.csv", ["club_id", "city"], [[f"C{i:03d}", f"도시{i}"] for i in range(1, 31)])
            write_csv(root / "data" / "club_stats.csv", ["club_id", "wins"], [[f"C{i:03d}", i * 3] for i in range(1, 31)])

            def verdict(child, parent):
                conn = open_db(root)
                col = child.split(".")[1]
                row = conn.execute("SELECT verdict FROM _dm_relations WHERE child=? AND child_cols=? AND parent=?",
                                   (child.split(".")[0], json.dumps([col]), parent)).fetchone()
                conn.close()
                return row and row[0]

            run_cli(root, "build", "data")
            self.assertEqual(verdict("game.team_id", "squad_a"), "ambiguous")
            run_cli(root, "check", "game.team_id", "squad_a.team_id")
            self.assertEqual(verdict("game.team_id", "squad_a"), "checked")
            self.assertEqual(verdict("game.team_id", "squad_b"), "other")
            self.assertEqual(verdict("club_stats.club_id", "club"), "drawn")
            self.assertEqual(verdict("club.club_id", "club_stats"), "samekey")
            profile = (root / "notes" / "data-profile.md").read_text(encoding="utf-8")
            listed = next((ln for ln in profile.splitlines() if ln.startswith("키끼리 값이 들어맞는 표")), "")
            self.assertIn("club.club_id → club_stats.club_id", listed)
            # 반대 방향을 check로 정하면 그려져 있던 쪽을 내린다.
            run_cli(root, "check", "club.club_id", "club_stats.club_id")
            self.assertEqual(verdict("club.club_id", "club_stats"), "checked")
            self.assertEqual(verdict("club_stats.club_id", "club"), "reverse")

    def test_split_keeps_differently_named_files_with_one_header_as_separate_tables(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "data").mkdir()
            names = [f"has_{w}" for w in "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
                                         "omicron pi rho sigma tau upsilon".split()]
            for n in names:
                write_csv(root / "data" / f"{n}.csv", ["item", "amount"], [[f"i{k}", k] for k in range(1, 6)])

            def tables(*args):
                run_cli(root, *args)
                conn = open_db(root)
                got = sorted(x[0] for x in conn.execute("SELECT name FROM _dm_tables"))
                conn.close()
                return got

            self.assertIn("--split", run_cli(root, "scan", "data").stdout)
            self.assertEqual(len(tables("build", "data")), 1)
            self.assertEqual(tables("build", "data", "--split"), sorted(names))

    def test_dropping_a_value_only_candidate_does_not_raise_the_next_one(self):
        def candidates():
            conn = open_db(self.root)
            rows = conn.execute("SELECT parent, parent_cols, verdict FROM _dm_relations "
                                "WHERE child='orders' AND child_cols='[\"status\"]'").fetchall()
            conn.close()
            return rows

        weak = [(p, json.loads(pc)[0]) for p, pc, v in candidates() if v == "weak"]
        self.assertEqual(len(weak), 1)
        self.assertGreater(len(candidates()), 1, "작은 정수는 여러 표의 번호에 다 들어간다")
        run_cli(self.root, "drop", "orders.status", f"{weak[0][0]}.{weak[0][1]}", "상태 코드라 다른 표를 가리키지 않는다")
        self.assertEqual([v for _, _, v in candidates() if v in ("weak", "drawn", "ambiguous")], [])

    def test_key_refuses_columns_whose_values_repeat(self):
        r = run_cli(self.root, "key", "orders.customer_id", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("겹친", r.stdout + r.stderr)
        self.assertEqual(key_of(self.root, "orders"), ["order_id"])


class EmptyPartKeyCase(unittest.TestCase):
    """키의 한 열이 대부분 비어 있는 표: 번호에 꼬리표가 붙은 몇 행만 꼬리표 열이 차 있다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        data = cls.root / "data"
        data.mkdir()
        trips = [[n, "", f"배{n}"] for n in range(1, 201)] + [[n, "A", f"배{n}A"] for n in (7, 50, 120)]
        write_csv(data / "trip.csv", ["number", "suffix", "ship"], trips)
        crew = [[n, "", n % 9 + 1] for n in range(1, 201, 2)] + [[7, "A", 3], [50, "A", 4], [120, "B", 5]]
        write_csv(data / "crew.csv", ["number", "suffix", "people"], crew)
        run_cli(cls.root, "build", "data")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_key_accepts_a_column_set_whose_second_column_is_mostly_empty(self):
        out = run_cli(self.root, "key", "trip.number,suffix").stdout
        self.assertIn("키로 정했다", out)

    def test_check_counts_rows_with_an_empty_part_instead_of_skipping_them(self):
        out = run_cli(self.root, "check", "crew.number,suffix", "trip.number,suffix").stdout
        # 꼬리표가 빈 100행도 값으로 센다. 부모에 없는 것은 (120, B) 하나뿐이다.
        self.assertIn("자식 값 103개 중 102개가 부모에 있다", out)
        self.assertIn("지도에 그림", out)
        self.assertIn("부모에 없는 자식 값: 1행", out)


class DraftRuleCase(unittest.TestCase):
    """스크립트가 초안에서 선을 그을지 정하는 규칙. 모두 열 이름의 뜻이 아니라 값과 이름의 글자 모양으로 정한다."""

    def build(self, files):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "data").mkdir()
        for name, header, rows in files:
            write_csv(root / "data" / name, header, rows)
        run_cli(root, "build", "data")
        self.conn = open_db(root)
        self.addCleanup(self.conn.close)
        return verdicts(root)

    def test_among_same_named_parents_the_table_that_holds_every_key_is_drawn(self):
        # film_rating은 film의 일부(40편)만 담은 1:1 표다. screening은 그 40편만 가리켜서 film_rating에 더 꼭 맞는다.
        films = [[f"F{i:03d}", f"영화{i}"] for i in range(1, 61)]
        v = self.build([
            ("film.csv", ["film_id", "title"], films),
            ("film_rating.csv", ["film_id", "stars"], [[f"F{i:03d}", i % 5 + 1] for i in range(1, 41)]),
            ("screening.csv", ["screening_id", "film_id"], [[i, f"F{i % 40 + 1:03d}"] for i in range(1, 301)]),
        ])
        self.assertEqual(v.get(("screening.film_id", "film.film_id")), "drawn")
        self.assertEqual(v.get(("screening.film_id", "film_rating.film_id")), "other")

    def test_a_copied_value_of_a_unique_non_key_column_is_not_drawn(self):
        # billing_address는 고객의 address를 베껴 둔 값이다. 이름 뒤가 같고 값도 다 맞지만 address는 고객의 키가 아니다.
        customers = [[f"C{i:03d}", f"{i}번길 {i * 3}호"] for i in range(1, 51)]
        v = self.build([
            ("customer.csv", ["customer_id", "address"], customers),
            ("invoice.csv", ["invoice_id", "customer_id", "billing_address"],
             [[i, customers[i % 50][0], customers[i % 50][1]] for i in range(1, 201)]),
        ])
        self.assertEqual(v.get(("invoice.customer_id", "customer.customer_id")), "drawn")
        self.assertEqual(v.get(("invoice.billing_address", "customer.address")), "weak")

    def test_a_column_that_is_almost_all_empty_is_still_measured(self):
        # 4만 행 중 한 행만 값이 있는 열. 표본 2,000행에 그 값이 안 잡혀도 후보에서 빠지면 안 된다.
        rows = [[i, "AAA", ""] for i in range(1, 40001)]
        rows[31416][2] = "CCC"
        v = self.build([
            ("airport.csv", ["code", "airport_name"], [[c, f"{c} 공항"] for c in ("AAA", "BBB", "CCC", "DDD")]),
            ("flight.csv", ["flight_id", "origin", "diverted_to"], rows),
        ])
        sample = datamap.sample_rows(self.conn, "flight", ["diverted_to"], datamap.SAMPLE_ROWS)
        self.assertEqual({r[0] for r in sample}, {None}, "이 시험은 표본에 값이 안 잡힌 경우를 본다")
        self.assertIn(v.get(("flight.diverted_to", "airport.code")), ("weak", "drawn"))


def make_shapes(root):
    """실무에서 자주 깨지는 CSV 모양을 한 폴더에 모은다."""
    data = root / "data"
    data.mkdir()
    (data / "preamble.csv").write_bytes("자료명,2024년 생산 실적\n단위: 개\n\nlot_id,product,qty\nL1,A,10\nL2,B,20\n".encode("cp949"))
    lines = ["id,note"] + [f"{i},ok" for i in range(1, 6)] + ['6,"broken'] + [f"{i},ok" for i in range(7, 1300)]
    (data / "unclosed.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (data / "small_unclosed.csv").write_text('id,note\n1,ok\n2,"broken\n3,ok\n4,ok\n', encoding="utf-8")
    header = ",".join(f"s{i}" for i in range(2100))
    (data / "wide.csv").write_text(header + "\n" + "\n".join(",".join(str(r + i) for i in range(2100)) for r in range(5)) + "\n", encoding="utf-8")
    (data / "excel_unicode.txt").write_bytes(("품번\t이름\t수량\r\nA1\t볼트\t3\r\nA2\t너트\t5\r\nA3\t와셔\t7\r\n").encode("utf-16"))
    (data / "cr_only.csv").write_bytes(b"a,b\r1,2\r3,4\r")
    (data / "concat.csv").write_text("step_id,name\n1,x\n2,y\nstep_id,name\n3,z\n", encoding="utf-8")
    (data / "dump.csv").write_text("id,parent\n1,\\N\n2,1\n", encoding="utf-8")
    (data / "packed.csv").write_bytes(b"\x1f\x8b\x08\x00" + bytes(range(60)))
    (data / "rowid_col.csv").write_text("rowid,v\n10,a\n20,b\n", encoding="utf-8")
    (data / "messy_header.csv").write_text('"lot\nid",LOT_ID,,name\n1,2,3,4\n', encoding="utf-8")
    (data / "notes.txt").write_text("이 폴더는 시험용이다.\n문장으로 된 설명 파일이다.\n표가 아니다.\n", encoding="utf-8")


class ShapesCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        make_shapes(cls.root)
        cls.out = run_cli(cls.root, "build", "data", check=False)
        cls.profile = (cls.root / "notes" / "data-profile.md").read_text(encoding="utf-8")
        cls.conn = open_db(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.tmp.cleanup()

    def cols(self, table):
        return [r[0] for r in self.conn.execute("SELECT name FROM _dm_columns WHERE tbl=? ORDER BY pos", (table,))]

    def count(self, table):
        return self.conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

    def test_build_survives_every_shape(self):
        self.assertEqual(self.out.returncode, 0, self.out.stdout + self.out.stderr)

    def test_title_lines_above_the_table_are_skipped(self):
        self.assertEqual(self.cols("preamble"), ["lot_id", "product", "qty"])
        self.assertEqual(self.count("preamble"), 2)
        self.assertIn("표 위의 설명 줄 2개를 건너뛰었다", self.profile)

    def test_unclosed_quote_does_not_swallow_the_rest_of_a_file(self):
        self.assertEqual(self.count("unclosed"), 1299)
        self.assertIn("따옴표가 닫히지 않은 칸이 있어", self.profile)

    def test_short_unclosed_quote_is_reported(self):
        self.assertIn("small_unclosed.csv: 칸 안에 줄바꿈이 있어 줄 2개가 앞 행에 붙었다", self.profile)

    def test_too_wide_tables_keep_the_first_columns(self):
        self.assertEqual(len(self.cols("wide")), 1990)
        self.assertEqual(self.count("wide"), 5)
        self.assertIn("열이 2,100개라", self.profile)

    def test_excel_unicode_text_is_read_as_a_table(self):
        self.assertEqual(self.cols("excel_unicode"), ["품번", "이름", "수량"])
        self.assertEqual(self.count("excel_unicode"), 3)

    def test_cr_only_line_endings(self):
        self.assertEqual(self.count("cr_only"), 2)

    def test_repeated_header_rows_are_dropped(self):
        self.assertEqual(self.count("concat"), 3)
        t = self.conn.execute("SELECT type FROM _dm_columns WHERE tbl='concat' AND name='step_id'").fetchone()[0]
        self.assertEqual(t, "int")

    def test_backslash_n_is_null(self):
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM dump WHERE parent IS NULL").fetchone()[0], 1)

    def test_compressed_file_is_skipped_with_a_reason(self):
        self.assertIn("packed.csv: 모양을 읽지 못해 건너뛰었다 (압축 파일이다", self.profile)

    def test_odd_header_names_become_usable_column_names(self):
        self.assertEqual(self.cols("messy_header"), ["lot id", "LOT_ID", "col_3", "name"])

    def test_prose_txt_stays_a_document(self):
        self.assertNotIn("notes", [r[0] for r in self.conn.execute("SELECT name FROM _dm_tables")])

    def test_trace_works_with_a_column_named_rowid(self):
        out = run_cli(self.root, "trace", "rowid_col.rowid", "20").stdout
        self.assertIn("rowid=20 · v=b", out)


def make_service(root):
    """서비스 DB에서 흔한 모양: 1:1 확장 표, 같은 시각 created_at, 강의 안에서만 유일한 id(두 열 키)."""
    rng = random.Random(3)
    data = root / "data"
    data.mkdir()
    lectures = [[i, f"2026-10-{i:02d} 10:00:00"] for i in range(1, 21)]
    write_csv(data / "lecture.csv", ["id", "created_at"], lectures)
    write_csv(data / "transcript.csv", ["lecture_id", "duration_ms"], [[i, rng.randint(1000, 9999)] for i in range(1, 21)])
    write_csv(data / "experiment.csv", ["id", "lecture_id", "created_at"],
              [[100 + i, i, created] for i, created in lectures])
    write_csv(data / "sentence.csv", ["lecture_id", "id", "text"],
              [[i, f"s{n}", f"문장 {n}"] for i in range(1, 21) for n in range(1, 41)])
    write_csv(data / "cue.csv", ["lecture_id", "sentence_id", "ord"],
              [[i, f"s{rng.randint(1, 40)}", k] for i in range(1, 21) for k in range(1, 3)])
    write_csv(data / "judge.csv", ["judge_id", "scope", "target", "score"],
              [[k, (k % 20) + 1, f"s{rng.randint(1, 40)}", rng.randint(1, 5)] for k in range(1, 301)])
    # 같은 표의 키를 가리키지만 이름에 단서가 없는 열(회원 → 멘토). 키가 글자다.
    # legacy_code는 같은 회원을 가리키는 또 다른 ID라 값이 member_id와 거의 같다. 관계가 아니다.
    write_csv(data / "member.csv", ["member_id", "name", "mentor", "legacy_code"],
              [[f"M{i:03d}", f"회원{i}", f"M{i // 3:03d}" if i >= 3 else "", f"M{i:03d}" if i > 2 else ""]
               for i in range(1, 41)])


class ServiceShapeCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        make_service(root)
        run_cli(root, "build", "data")
        cls.verdict = verdicts(root)
        cls.profile = (root / "notes" / "data-profile.md").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_value_only_candidates_are_listed_apart_by_whether_the_parent_key_is_a_number(self):
        def line(head):
            return next((ln for ln in self.profile.splitlines() if ln.startswith(head)), "")

        # 글자 키에 값이 맞는 후보는 우연히 맞기 어려워 하나씩 판정할 목록에 든다.
        self.assertIn("member.mentor → member.member_id", line("이름 근거 없이 값만 맞는 후보"))
        # 숫자 열은 1부터 매긴 번호에 우연히 다 들어간다. 따로 모아 보여 주고 하나씩 판정하게 하지 않는다.
        self.assertIn("judge.score → ", line("숫자가 번호 범위에 들어간 후보"))
        self.assertNotIn("judge.score → ", line("이름 근거 없이 값만 맞는 후보"))

    def test_one_to_one_extension_does_not_hide_the_real_parent(self):
        self.assertEqual(self.verdict.get(("experiment.lecture_id", "lecture.id")), "drawn")

    def test_timestamps_made_together_are_not_a_relation(self):
        self.assertNotIn(("experiment.created_at", "lecture.created_at"), self.verdict)

    def test_two_column_reference_with_other_names_is_listed_by_values(self):
        # judge는 문장을 열 이름이 다른 두 열(scope, target)로 가리킨다. 이름 근거가 없어 그리지는 않고 후보로 올린다.
        self.assertIn(self.verdict.get(("judge.scope,target", "sentence.lecture_id,id")), ("weak", "drawn"))

    def test_reference_into_a_two_column_key_is_found(self):
        self.assertEqual(self.verdict.get(("cue.lecture_id,sentence_id", "sentence.lecture_id,id")), "drawn")

    def test_self_reference_without_a_name_hint_is_listed_as_a_candidate(self):
        self.assertEqual(self.verdict.get(("member.mentor", "member.member_id")), "weak")

    def test_another_id_column_of_the_same_row_is_not_drawn_as_a_self_reference(self):
        self.assertEqual(self.verdict.get(("member.legacy_code", "member.member_id")), "weak")


if __name__ == "__main__":
    unittest.main()
