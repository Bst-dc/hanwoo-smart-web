"""FastAPI 대시보드·농가 API 가 기존 Streamlit 앱과 같은 값을 내는지 확인한다.

농가 몇 곳짜리 시험 DB(메모리 SQLite, 실제 스키마)에 대해
  1) streamlit_app.py 소스에서 그대로 뽑아낸 SQL 의 결과와 API 결과가 같은지,
  2) 손으로 계산한 값과 같은지
를 본다. 실행: python -m unittest tests.test_api_dashboard
"""
import re
import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import db_schema  # noqa: E402
from api import auth, db  # noqa: E402
from api.main import app  # noqa: E402
from api.services import national_stats as ns  # noqa: E402

APP_SOURCE = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
NOW_YEAR = datetime.now().year


def legacy_sql(pattern: str) -> str:
    """streamlit_app.py 에서 SQL 문자열을 그대로 꺼낸다. 못 찾으면 기존 앱이 바뀐 것이니 테스트를 고칠 것."""
    m = re.search(pattern, APP_SOURCE, re.DOTALL)
    if not m:
        raise AssertionError(f"streamlit_app.py 에서 SQL 을 찾지 못함: {pattern[:60]}")
    return m.group(1)


LEGACY = {
    "steer": legacy_sql(r'row_1plus_steer = conn\.execute\("(.*?)"\)\.fetchone\(\)'),
    "cow": legacy_sql(r'row_1plus_cow = conn\.execute\("(.*?)"\)\.fetchone\(\)'),
    "missing_survey": legacy_sql(r'farms_missing_survey_list = conn\.execute\("""(.*?)"""\)\.fetchall\(\)'),
    "missing_shipment": legacy_sql(r'farms_missing_shipment_list = conn\.execute\("""(.*?)"""\)\.fetchall\(\)'),
    "yearly": legacy_sql(r'yearly_df = pd\.read_sql_query\(f"""(.*?)""", conn, params=\(trend_gender,\)\)')
              .replace("{start_year}", "2023").replace("{current_year}", str(NOW_YEAR)),
    "compare": legacy_sql(r'compare_df = pd\.read_sql_query\("""(.*?)""", conn\)'),
}

# (농가, 성별, 연도, 육질, 육량, 도체중, BMS, 단면적, 등지방, 월령)
SHIPMENTS = [
    (1, "거세", 2025, "1++", "A", 500, 9, 100, 10, 30),
    (1, "거세", 2025, "1+", "B", 480, 7, 95, 12, 31),
    (1, "거세", 2025, "2", "C", 420, 3, 85, 15, 33),
    (1, "암", 2025, "1", "B", 380, 5, 90, 13, 60),
    (2, "거세", 2024, "1++", "B", 510, 8, 105, 11, 30),
    (2, "거세", 2024, "1", "C", 450, 4, 90, 14, 32),
    (2, "수", 2024, "1", "A", 400, 4, 88, 9, 25),
]


def make_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(db_schema.SQLITE_DDL)
    farms = [  # id, 이름, 지역
        (1, "가농장", "대구"),   # 출하성적 + 조사표 (조사표 지역 '영천' 이 우선)
        (2, "나농장", "경산"),   # 출하성적만
        (3, "다농장", None),     # 조사표만
        (4, "라농장", "구미"),   # 방문은 있지만 조사표 내용 없음 → 어느 명단에도 없음
        (5, "가농장", "영천"),   # 1번과 표시 이름이 같아지는 농가
    ]
    for fid, name, region in farms:
        conn.execute("INSERT INTO farms (id, farm_code, farm_name, region) VALUES (?, ?, ?, ?)",
                     (fid, f"T{fid}", name, region))
    for vid, fid, survey in [(1, 1, '{"region": "영천"}'), (2, 3, '{"region": ""}'), (3, 4, None)]:
        conn.execute("INSERT INTO visits (id, farm_id, visit_date) VALUES (?, ?, '2026-01-01')", (vid, fid))
        conn.execute("INSERT INTO field_surveys (visit_id, survey_data) VALUES (?, ?)", (vid, survey))
    for i, (fid, g, y, q, yl, cw, bms, rib, bf, age) in enumerate(SHIPMENTS):
        conn.execute(
            "INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_date, slaughter_year, grade_quality,"
            " grade_yield, carcass_weight, bms, ribeye, backfat, month_age) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid, f"00{i}", g, f"{y}-05-01", y, q, yl, cw, bms, rib, bf, age))
    conn.commit()
    return conn


class ApiTestBase(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        app.dependency_overrides[db.get_db] = lambda: self.conn
        self.kosis = mock.patch.object(ns, "_kosis_cached", return_value=None)  # 외부 호출 없이 내장값만
        self.kosis.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.kosis.stop()
        app.dependency_overrides.clear()
        self.conn.close()


class DashboardSummaryTest(ApiTestBase):
    def setUp(self):
        super().setUp()
        self.nopw = mock.patch("api.config.app_password", return_value=None)
        self.nopw.start()
        self.body = self.client.get("/api/dashboard/summary").json()

    def tearDown(self):
        self.nopw.stop()
        super().tearDown()

    def test_counts(self):
        self.assertEqual((self.body["total_farms"], self.body["total_visits"], self.body["total_shipments"]), (5, 3, 7))

    def test_plus1_matches_legacy_sql(self):
        self.assertEqual(self.body["steer_plus1"]["value"], self.conn.execute(LEGACY["steer"]).fetchone()[0])
        self.assertEqual(self.body["cow_plus1"]["value"], self.conn.execute(LEGACY["cow"]).fetchone()[0] or 0.0)

    def test_plus1_hand_calculated(self):
        base = NOW_YEAR - 1
        steer, cow = self.body["steer_plus1"], self.body["cow_plus1"]
        self.assertEqual(steer["value"], 60.0)              # 거세 5두 중 1++·1+ 3두
        self.assertEqual(cow["value"], 0.0)                 # 암 1두, 1등급
        nat = ns.NATIONAL_STATS_BASE["거세"]["grade_quality"][base]["1+이상"]
        self.assertEqual((steer["base_year"], steer["national"], steer["delta"]), (base, nat, round(60.0 - nat, 1)))

    def test_missing_lists_match_legacy_sql(self):
        self.assertEqual(self.body["farms_missing_survey"], [r[0] for r in self.conn.execute(LEGACY["missing_survey"])])
        self.assertEqual(self.body["farms_missing_shipment"], [r[0] for r in self.conn.execute(LEGACY["missing_shipment"])])
        self.assertEqual((self.body["farms_missing_survey"], self.body["farms_missing_shipment"]), (["나농장"], ["다농장"]))


class YearlyTest(ApiTestBase):
    KEYS = ["farms", "heads", "carcass_weight", "bms", "ribeye", "backfat", "plus1_rate", "c_rate", "month_age"]

    def _api_rows(self, gender):
        with mock.patch("api.config.app_password", return_value=None):
            rows = self.client.get("/api/dashboard/yearly", params={"gender": gender}).json()["rows"]
        return rows

    def test_matches_legacy_sql_both_genders(self):
        for gender in ["거세", "암"]:
            legacy = {r[0]: list(r[1:]) for r in self.conn.execute(LEGACY["yearly"], (gender,)).fetchall()}
            for row in self._api_rows(gender):
                if row["heads"] is None:
                    self.assertNotIn(row["year"], legacy)
                    continue
                got = [row["farms"], row["heads"]] + [row["farm"][k] for k in self.KEYS[2:]]
                self.assertEqual(got, legacy[row["year"]], f"{gender} {row['year']}")

    def test_hand_calculated_2025_steer(self):
        row = next(r for r in self._api_rows("거세") if r["year"] == 2025)
        self.assertEqual((row["farms"], row["heads"]), (1, 3))
        self.assertEqual(row["farm"], {"carcass_weight": 466.7, "bms": 6.3, "ribeye": 93.3, "backfat": 12.3,
                                       "plus1_rate": 66.7, "c_rate": 33.3, "month_age": 31.3})

    def test_every_year_has_national_values(self):
        rows = self._api_rows("거세")
        self.assertEqual([r["year"] for r in rows], list(range(2023, NOW_YEAR + 1)))
        self.assertEqual(next(r for r in rows if r["year"] == 2023)["farm"]["bms"], None)   # 2023 출하 없음
        if NOW_YEAR >= 2026:
            self.assertEqual(next(r for r in rows if r["year"] == 2026)["national"]["bms"], 6.5)  # 수동 보정

    def test_cow_yield_missing_national_is_null(self):
        rows = self._api_rows("암")
        if NOW_YEAR >= 2026:
            self.assertIsNone(next(r for r in rows if r["year"] == 2026)["national"]["c_rate"])


class GenderCompareTest(ApiTestBase):
    def test_matches_legacy_sql(self):
        with mock.patch("api.config.app_password", return_value=None):
            api_rows = self.client.get("/api/dashboard/gender-compare").json()
        legacy = [list(r) for r in self.conn.execute(LEGACY["compare"]).fetchall()]
        keys = ["gender", "heads", "carcass_weight", "bms", "ribeye", "backfat", "plus1_rate", "month_age"]
        self.assertEqual([[r[k] for k in keys] for r in api_rows], legacy)


class FarmsTest(ApiTestBase):
    def test_labels(self):
        with mock.patch("api.config.app_password", return_value=None):
            farms = self.client.get("/api/farms").json()
        labels = {f["id"]: f["label"] for f in farms}
        self.assertEqual([f["id"] for f in farms], [5, 4, 3, 2, 1])            # 최근 등록 순
        self.assertEqual(labels[5], "가농장 (대표자, 영천)")
        self.assertEqual(labels[1], "가농장 (대표자, 영천) #1")                  # 조사표 지역 우선 → 이름 겹침 → #id
        self.assertEqual(labels[3], "다농장 (대표자, 지역)")                     # 조사표 지역이 비면 원래 값(없음)


class AuthTest(ApiTestBase):
    def test_password_gate(self):
        with mock.patch("api.config.app_password", return_value="pw"), \
             mock.patch.object(auth.time, "sleep"):
            self.assertEqual(self.client.get("/api/dashboard/summary").status_code, 401)
            self.assertEqual(self.client.post("/api/auth/login", json={"password": "x"}).status_code, 401)
            self.assertEqual(self.client.get("/api/farms").status_code, 401)
            self.assertEqual(self.client.post("/api/auth/login", json={"password": "pw"}).status_code, 200)
            self.assertEqual(self.client.get("/api/dashboard/summary").status_code, 200)
            self.client.post("/api/auth/logout")
            self.assertEqual(self.client.get("/api/farms").status_code, 401)

    def test_health_needs_no_login(self):
        with mock.patch("api.config.app_password", return_value="pw"):
            self.assertEqual(self.client.get("/api/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
