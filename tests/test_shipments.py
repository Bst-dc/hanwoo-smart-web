"""1단계 · 출하성적 비교분석(조회) 검사 — 손으로 계산할 수 있는 소량 데이터로 기대값을 직접 적어 비교한다.

외부(KOSIS)에는 붙지 않는다(기본값 전국 통계). 실행: python -m unittest tests.test_shipments
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
from api.services import shipments  # noqa: E402

NOW = datetime(2026, 10, 13)


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db_schema.SQLITE_DDL)
    conn.executemany("INSERT INTO farms (id, farm_name, farm_code, region) VALUES (?, ?, ?, ?)",
                     [(1, "가농가", "A001", "구미"), (2, "나농가", None, None)])
    # (농가, 번호, 성별, 도축일, 연도, 도체중, 육질, 육량, BMS, 단면적, 등지방, 월령)
    rows = [
        (1, "s1", "거세", "2024-03-01", 2024, 400, "1++", "A", 8, 100, 10, 30),
        (1, "s2", "거세", "2024-05-01", 2024, 420, "1", "C", 4, 90, 14, 32),
        (1, "s3", "거세", "2025-02-01", 2025, 500, "1+", "B", 7, 110, 12, 31),
        (1, "s4", "거세", "2025-06-01", 2025, 480, "2", "C", 3, 96, 16, 33),
        (1, "c1", "암", "2025-04-01", 2025, 350, "1+", "B", 5, 85, 11, 60),
        (2, "c2", "암", "2026-01-10", 2026, 380, "1", "B", 4, 90, 13, 55),
        (2, "c3", "암", "2026-02-10", 2026, 400, "1++", "A", 6, 94, 12, 57),
        (2, "b1", "수", "2026-03-10", 2026, 600, "2", "A", 2, 99, 6, 28),
    ]
    conn.executemany("""INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_date, slaughter_year,
        carcass_weight, grade_quality, grade_yield, bms, ribeye, backfat, month_age) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    return conn


class ShipmentsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        national_stats._cache.update(at=0.0, stats=None, source=None)
        cls.conn = _conn()

    def build(self, farm, year=None, gender=None):
        return shipments.build(self.conn, farm, year, gender, NOW)

    def test_all_years_compares_steers_against_latest_national(self):
        d = self.build(1)
        self.assertEqual(d["years"], [2025, 2024])
        self.assertEqual((d["cmp_gender"], d["gender_forced"], d["total_count"]), ("거세", True, 4))
        self.assertEqual(d["national_year"], 2026)
        c = {r["item"]: r for r in d["comparison"]}
        self.assertEqual(c["도체중 (kg)"], {"item": "도체중 (kg)", "farm": "450.0", "national": "490.4", "diff": "-40.4", "diagnosis": "미흡 (▼)"})
        self.assertEqual((c["근내지방도 (BMS)"]["national"], c["근내지방도 (BMS)"]["diff"]), ("6.5", "-1.0"))   # 수동 보정 6.5
        self.assertEqual((c["등심단면적 (㎠)"]["farm"], c["등심단면적 (㎠)"]["diagnosis"]), ("99.0", "미흡 (▼)"))
        self.assertEqual((c["등지방두께 (mm)"]["diff"], c["등지방두께 (mm)"]["diagnosis"]), ("0.5", "적정"))     # +1.0 이하는 적정
        self.assertEqual((c["1+이상 출현율 (%)"]["farm"], c["1+이상 출현율 (%)"]["diagnosis"]), ("50.0", "개선필요"))
        self.assertEqual((c["C등급 출현율 (%)"]["diff"], c["C등급 출현율 (%)"]["diagnosis"]), ("33.5", "개선필요 (▲)"))
        self.assertEqual((c["출하월령 (개월)"]["diff"], c["출하월령 (개월)"]["diagnosis"]), ("-0.2", "단기출하 (우수)"))

    def test_low_backfat_with_two_low_metrics_needs_improvement(self):
        def rows(**d):
            base = {"carcass_weight": 1.0, "bms": 1.0, "ribeye": 1.0, "backfat": 1.0}
            base.update(d)
            return base, [{"item": "등지방두께 (mm)", "diagnosis": "적정"}]
        for diffs, expect in [
            (dict(carcass_weight=-1, bms=-1, backfat=-0.5), "개선필요"),             # 2개 낮음 + 등지방 낮음
            (dict(carcass_weight=-1, bms=-1, ribeye=-1, backfat=-0.1), "개선필요"),  # 3개 낮음
            (dict(carcass_weight=-1, backfat=-0.5), "적정"),                          # 1개만 낮음
            (dict(carcass_weight=-1, bms=-1, backfat=0.5), "적정"),                   # 등지방이 낮지 않음
            (dict(carcass_weight=-1, bms=-1, backfat=0.0), "적정"),                   # 같으면 낮은 게 아님
            (dict(carcass_weight=-1, bms=None, ribeye=-1, backfat=None), "적정"),     # 등지방 값 없음
        ]:
            d, comp = rows(**diffs)
            shipments._flag_low_backfat(comp, d)
            self.assertEqual(comp[0]["diagnosis"], expect, diffs)

    def test_profit_uses_weight_gap_times_21000_truncated(self):
        d = self.build(1)
        per_head = int((450.0 - 490.4) * 21000)
        self.assertEqual(d["profit"], {"available": True, "per_head": per_head, "total": per_head * 4})

    def test_records_include_every_gender_newest_first(self):
        d = self.build(1)
        self.assertEqual([r["animal_no"] for r in d["records"]], ["s4", "c1", "s3", "s2", "s1"])
        self.assertEqual(d["records"][0]["carcass_weight"], 480.0)

    def test_recent_trend_series_and_table(self):
        t = self.build(1)["trend"]
        self.assertEqual(t["years"], [2024, 2025])
        self.assertEqual(t["series"]["carcass_weight"], {"farm": [410.0, 490.0], "national": [470.6, 478.1]})
        self.assertEqual(t["table"][0]["year"], 2024)
        self.assertEqual(t["table"][0]["farm"][0], "410.0")
        self.assertEqual(t["table"][1]["national"][4], "71.3")              # 2025 전국 1+이상

    def test_single_year_uses_that_years_national(self):
        d = self.build(1, year=2025)
        self.assertEqual((d["total_count"], d["national_year"]), (2, 2025))
        w = d["comparison"][0]
        self.assertEqual((w["farm"], w["national"], w["diff"], w["diagnosis"]), ("490.0", "478.1", "11.9", "우수 (▲)"))
        self.assertEqual(len(d["records"]), 3)                               # 그해 거세 2 + 암 1

    def test_cows_selected_explicitly(self):
        d = self.build(1, year=2025, gender="암")
        self.assertEqual((d["cmp_gender"], d["gender_forced"], d["total_count"]), ("암", False, 1))
        self.assertEqual(d["comparison"][0]["national"], "377.3")
        self.assertEqual([r["animal_no"] for r in d["records"]], ["c1"])

    def test_farm_without_steers_falls_back_to_cows(self):
        d = self.build(2)
        self.assertEqual((d["cmp_gender"], d["total_count"]), ("암", 2))   # 수소 1두는 비교에서 빠진다
        self.assertEqual(d["comparison"][0]["farm"], "390.0")
        self.assertEqual(len(d["records"]), 3)                               # 개체 표에는 수소도 나온다
        c = {r["item"]: r for r in d["comparison"]}
        self.assertEqual((c["C등급 출현율 (%)"]["national"], c["C등급 출현율 (%)"]["diff"], c["C등급 출현율 (%)"]["diagnosis"]), ("-", "-", "-"))  # 암소 2026 육량 전국 통계 없음

    def test_no_data_for_selected_gender(self):
        d = self.build(2, gender="거세")
        self.assertEqual((d["has_data"], d["total_count"], d["records"]), (False, 0, []))
        self.assertNotIn("comparison", d)

    def test_farm_info(self):
        self.assertEqual(shipments.farm_info(self.conn, 1), {"id": 1, "name": "가농가", "code": "A001", "region": "구미"})
        self.assertEqual(shipments.farm_info(self.conn, 2)["code"], "")
        self.assertIsNone(shipments.farm_info(self.conn, 99))


if __name__ == "__main__":
    unittest.main()
