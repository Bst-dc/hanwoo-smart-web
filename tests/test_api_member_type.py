"""조합원/비조합원 구분 시험 — 농가 등록·목록, 대시보드 필터, 기존 DB 에 칸 추가(마이그레이션).

시험 DB 에서 2번 농가(나농장)만 비조합원으로 바꿔 쓴다. 나머지 4곳은 기본값(조합원).
실행: python -m unittest tests.test_api_member_type
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_api_dashboard import ApiTestBase  # noqa: E402

from api import db  # noqa: E402


class MemberTypeTest(ApiTestBase):
    def setUp(self):
        super().setUp()
        self.nopw = mock.patch("api.config.app_password", return_value=None)
        self.nopw.start()
        self.conn.execute("UPDATE farms SET member_type = '비조합원' WHERE id = 2")
        self.conn.commit()

    def tearDown(self):
        self.nopw.stop()
        super().tearDown()

    def get(self, path, **params):
        return self.client.get(path, params=params)

    def test_default_is_member_and_list_exposes_type(self):
        types = {f["id"]: f["member_type"] for f in self.get("/api/farms").json()}
        self.assertEqual(types, {1: "조합원", 2: "비조합원", 3: "조합원", 4: "조합원", 5: "조합원"})

    def test_create_non_member_gets_N_code(self):
        with mock.patch("api.routers.farms.persist_db", return_value=mock.Mock(model_dump=lambda: {"ok": None, "message": ""})):
            r = self.client.post("/api/farms", json={"farm_name": "새비조합원농장", "member_type": "비조합원"})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["farm"]["member_type"], "비조합원")
        self.assertTrue(r.json()["farm"]["farm_code"].startswith("N"))

    def test_create_member_without_code_keeps_F_code(self):
        with mock.patch("api.routers.farms.persist_db", return_value=mock.Mock(model_dump=lambda: {"ok": None, "message": ""})):
            r = self.client.post("/api/farms", json={"farm_name": "새조합원농장"})
        self.assertEqual((r.json()["farm"]["member_type"], r.json()["farm"]["farm_code"][0]), ("조합원", "F"))

    def test_invalid_member_type_rejected(self):
        self.assertEqual(self.client.post("/api/farms", json={"farm_name": "x", "member_type": "준조합원"}).status_code, 422)
        self.assertEqual(self.get("/api/dashboard/summary", member="준조합원").status_code, 422)

    def test_summary_split_adds_up_to_total(self):
        s = {m: self.get("/api/dashboard/summary", member=m).json() for m in ["전체", "조합원", "비조합원"]}
        self.assertEqual((s["전체"]["total_farms"], s["전체"]["total_shipments"]), (5, 7))   # 필터 없으면 기존과 같다
        self.assertEqual((s["조합원"]["total_farms"], s["조합원"]["total_visits"], s["조합원"]["total_shipments"]), (4, 3, 4))
        self.assertEqual((s["비조합원"]["total_farms"], s["비조합원"]["total_visits"], s["비조합원"]["total_shipments"]), (1, 0, 3))
        for key in ["total_farms", "total_visits", "total_shipments"]:
            self.assertEqual(s["조합원"][key] + s["비조합원"][key], s["전체"][key], key)

    def test_plus1_by_member(self):
        self.assertEqual(self.get("/api/dashboard/summary", member="조합원").json()["steer_plus1"]["value"], 66.7)  # 1++·1+·2
        self.assertEqual(self.get("/api/dashboard/summary", member="비조합원").json()["steer_plus1"]["value"], 50.0)  # 1++·1

    def test_missing_lists_filtered(self):
        m = self.get("/api/dashboard/summary", member="조합원").json()
        n = self.get("/api/dashboard/summary", member="비조합원").json()
        self.assertEqual((m["farms_missing_survey"], m["farms_missing_shipment"]), ([], ["다농장"]))
        self.assertEqual((n["farms_missing_survey"], n["farms_missing_shipment"]), (["나농장"], []))

    def test_yearly_and_gender_compare_filtered(self):
        rows = {r["year"]: r for r in self.get("/api/dashboard/yearly", gender="거세", member="비조합원").json()["rows"]}
        self.assertEqual(rows[2024]["heads"], 2)
        self.assertIsNone(rows[2025]["heads"])
        rows = {r["year"]: r for r in self.get("/api/dashboard/yearly", gender="거세", member="조합원").json()["rows"]}
        self.assertIsNone(rows[2024]["heads"])
        self.assertEqual(rows[2025]["heads"], 3)
        cmp_n = {r["gender"]: r["heads"] for r in self.get("/api/dashboard/gender-compare", member="비조합원").json()}
        self.assertEqual(cmp_n, {"거세": 2, "수": 1})


class MigrationTest(unittest.TestCase):
    def test_old_db_gets_column_and_members_default(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "old.db"
            c = sqlite3.connect(path)   # member_type 이 없던 시절의 farms
            c.execute("CREATE TABLE farms (id INTEGER PRIMARY KEY, farm_code TEXT UNIQUE, farm_name TEXT NOT NULL)")
            c.execute("INSERT INTO farms (farm_code, farm_name) VALUES ('M1', '옛농가')")
            c.commit(); c.close()
            with mock.patch.object(db, "LOCAL_DB", path), mock.patch.object(db, "using_supabase", return_value=False):
                conn = db.connect()
                self.assertEqual(conn.execute("SELECT member_type FROM farms").fetchone()[0], "조합원")
                conn.close()
                db.connect().close()   # 두 번째 연결에서 다시 추가하려다 오류 나지 않는다


if __name__ == "__main__":
    unittest.main()
