"""종합 현황 대시보드 — 전국 평균(KOSIS 해석·병합)과 계산 서비스 검사.

임시 SQLite DB 에 손으로 계산할 수 있는 소량 데이터를 넣고, 기대값을 직접 적어 비교한다.
외부(KOSIS)에는 붙지 않는다. 실행: python -m unittest tests.test_dashboard
"""
import os
import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CONSULTING_LOCAL_ONLY", "1")
os.environ.pop("KOSIS_API_KEY", None)

import db_schema  # noqa: E402
from api import national_stats  # noqa: E402
from api.services import dashboard  # noqa: E402

NOW = datetime(2026, 10, 13)


class NationalStatsTest(unittest.TestCase):
    def test_parse_detail_keeps_only_valid_hanwoo_rows(self):
        rows = [
            {"C1_NM": "한우", "C2_NM": "거세", "C3_NM": "도체중", "PRD_DE": "2026", "DT": "491.26"},
            {"C1_NM": "한우", "C2_NM": "거세", "C3_NM": "근내지방", "PRD_DE": "2026", "DT": "7.04"},
            {"C1_NM": "육우", "C2_NM": "거세", "C3_NM": "도체중", "PRD_DE": "2026", "DT": "999"},     # 한우가 아님
            {"C1_NM": "한우", "C2_NM": "미상", "C3_NM": "도체중", "PRD_DE": "2026", "DT": "999"},     # 모르는 성별
            {"C1_NM": "한우", "C2_NM": "암", "C3_NM": "도체중", "PRD_DE": "2026", "DT": "-"},         # 숫자가 아님
            {"C1_NM": "한우", "C2_NM": "암", "C3_NM": "등심면적", "PRD_DE": "2025", "DT": "88.84"},
        ]
        out = national_stats.parse_detail(rows)
        self.assertEqual(out["거세"], {"도체중": {2026: 491.3}, "BMS": {2026: 7.0}})
        self.assertEqual(out["암"], {"단면적": {2025: 88.8}})
        self.assertEqual(out["수"], {})

    def test_parse_grades_percentages(self):
        rows = [{"C1_NM": "한우", "C2_NM": "거세", "PRD_DE": "2026", "C3_NM": g, "DT": str(v)} for g, v in [
            ("전체", 100), ("1++A", 30), ("1+B", 20), ("1B", 30), ("2C", 15), ("등외", 5)]]
        out = national_stats.parse_grades(rows)["거세"]
        self.assertEqual(out["grade_quality"][2026], {"1++": 30.0, "1+": 20.0, "1": 30.0, "2": 15.0, "3": 0.0, "1+이상": 50.0})
        self.assertEqual(out["grade_yield"][2026], {"A": 30.0, "B": 50.0, "C": 15.0})

    def test_merge_overrides_adds_and_applies_manual_bms(self):
        before = national_stats.BASELINE["거세"]["도체중"][2026]
        live = {"거세": {"도체중": {2026: 495.5, 2027: 500.0}, "BMS": {2026: 7.1}, "새지표": {2026: 1.0}}, "수": {"도체중": {2026: 1.0}}}
        merged = national_stats.merge(national_stats.BASELINE, live)
        self.assertEqual(merged["거세"]["도체중"][2026], 495.5)       # 같은 연도는 덮어씀
        self.assertEqual(merged["거세"]["도체중"][2027], 500.0)       # 새 연도는 추가
        self.assertEqual(merged["거세"]["새지표"], {2026: 1.0})       # 없던 지표는 추가
        self.assertEqual(merged["거세"]["BMS"][2026], 6.5)            # KOSIS 값 7.1 보다 수동 보정이 우선
        self.assertNotIn("수", merged)                                # 기본값에 없는 성별은 무시
        self.assertEqual(national_stats.BASELINE["거세"]["도체중"][2026], before)   # 기본값 원본은 그대로

    def test_get_without_key_uses_baseline_and_says_so(self):
        national_stats._cache.update(at=0.0, stats=None, source=None)
        stats, source = national_stats.get()
        self.assertEqual(source["kosis"], "baseline")
        self.assertEqual(stats["거세"]["BMS"][2026], 6.5)
        self.assertEqual(stats["암"]["도체중"][2025], 377.3)


def _seed(conn):
    conn.executescript(db_schema.SQLITE_DDL)
    conn.executemany("INSERT INTO farms (id, farm_name) VALUES (?, ?)", [(1, "가농가"), (2, "나농가"), (3, "다농가")])
    conn.executemany("INSERT INTO visits (id, farm_id, visit_number, visit_date) VALUES (?, ?, 1, '2026-01-01')", [(1, 1), (2, 2)])
    conn.executemany("INSERT INTO field_surveys (visit_id, survey_data) VALUES (?, '{}')", [(1,), (2,)])
    # (농가, 번호, 성별, 도축연도, 도체중, 육질, 육량, BMS, 단면적, 등지방, 월령)
    ships = [
        (1, "a1", "거세", 2025, 400, "1++", "A", 6, 90, 10, 30),
        (1, "a2", "거세", 2025, 500, "1+", "B", 7, 100, 12, 32),
        (3, "a3", "거세", 2025, 450, "1", "C", 8, 95, 14, 34),
        (3, "a4", "거세", 2025, 550, "2", "C", 5, 105, 16, 36),
        (1, "b1", "암", 2026, 300, "1+", "B", 4, 80, 10, 50),
        (1, "b2", "암", 2026, 320, "3", "B", 5, 90, 20, 60),
        (3, "c1", "수", 2024, 600, "1", "A", 3, 70, 5, 28),
    ]
    conn.executemany("""INSERT INTO shipment_records
        (farm_id, animal_no, gender, slaughter_year, carcass_weight, grade_quality, grade_yield, bms, ribeye, backfat, month_age)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", ships)
    conn.commit()


class DashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        national_stats._cache.update(at=0.0, stats=None, source=None)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _seed(conn)
        cls.d = dashboard.build(conn, NOW)

    def test_kpi_counts(self):
        k = self.d["kpi"]
        self.assertEqual((k["farms"], k["visits"], k["shipments"]), (3, 2, 7))

    def test_missing_lists(self):
        k = self.d["kpi"]
        self.assertEqual(k["missing_survey"], ["다농가"])      # 출하성적만 있고 조사표 없음
        self.assertEqual(k["missing_shipment"], ["나농가"])    # 조사표만 있고 출하성적 없음

    def test_one_plus_vs_national(self):
        s, c = self.d["kpi"]["steer_1plus"], self.d["kpi"]["cow_1plus"]
        self.assertEqual((s["value"], s["national"], s["base_year"], s["delta"]), (50.0, 71.3, 2025, -21.3))
        self.assertEqual((c["value"], c["national"], c["base_year"], c["delta"]), (50.0, 36.9, 2025, 13.1))

    def test_steer_yearly_row(self):
        g = self.d["trend"]["genders"]["거세"]
        self.assertEqual(len(g["rows"]), 1)
        self.assertEqual(g["rows"][0], {
            "year": 2025, "farms": 2, "heads": 4, "carcass_weight": 475.0, "bms": 6.5, "ribeye": 97.5,
            "backfat": 13.0, "q1plus": 50.0, "c_grade": 50.0, "month_age": 33.0})

    def test_series_align_with_years_and_national(self):
        t = self.d["trend"]
        self.assertEqual(t["years"], [2023, 2024, 2025, 2026])
        s = t["genders"]["거세"]["series"]["carcass_weight"]
        self.assertEqual(s["farm"], [None, None, 475.0, None])
        self.assertEqual(s["national"], [467.0, 470.6, 478.1, 490.4])
        self.assertEqual(t["genders"]["거세"]["series"]["bms"]["national"][3], 6.5)        # 수동 보정
        cow = t["genders"]["암"]
        self.assertEqual(cow["series"]["c_grade"]["farm"], [None, None, None, 0.0])
        self.assertEqual(cow["series"]["c_grade"]["national"], [20.4, 19.6, 19.2, None])    # 암소 2026 육량등급은 전국 통계 없음
        self.assertEqual(cow["rows"][0]["heads"], 2)

    def test_compare_by_gender_includes_bulls(self):
        c = {r["gender"]: r for r in self.d["compare"]}
        self.assertEqual([r["gender"] for r in self.d["compare"]], ["거세", "수", "암"])
        self.assertEqual((c["거세"]["heads"], c["거세"]["carcass_weight"]), (4, 475.0))
        self.assertEqual((c["수"]["heads"], c["수"]["carcass_weight"]), (1, 600.0))
        self.assertEqual((c["암"]["heads"], c["암"]["carcass_weight"], c["암"]["q1plus"]), (2, 310.0, 50.0))

    def test_source_is_reported(self):
        self.assertEqual(self.d["national_source"]["kosis"], "baseline")


class EmptyDbTest(unittest.TestCase):
    def test_empty_db_does_not_break(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db_schema.SQLITE_DDL)
        d = dashboard.build(conn, NOW)
        self.assertEqual((d["kpi"]["farms"], d["kpi"]["shipments"]), (0, 0))
        self.assertEqual(d["kpi"]["steer_1plus"]["value"], 0.0)
        self.assertEqual(d["trend"]["genders"]["거세"]["rows"], [])
        self.assertEqual(d["compare"], [])


if __name__ == "__main__":
    unittest.main()
