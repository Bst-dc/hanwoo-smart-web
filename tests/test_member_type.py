"""조합원/비조합원 구분 검사 — 대시보드 집계 필터, 농가 등록·목록, 기존 DB 에 칸 추가.

test_dashboard 의 시험 데이터를 쓰되 3번 농가(다농가)만 비조합원으로 바꾼다.
  조합원(1·2번): 방문 2회, 출하 4두 (거세 2 + 암 2) / 비조합원(3번): 방문 0회, 출하 3두 (거세 2 + 수 1)
외부(KOSIS)·운영 DB 에는 붙지 않는다. 실행: python -m unittest tests.test_member_type
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_dashboard import _seed  # noqa: E402  (환경변수·경로 설정도 같이 된다)
from test_datamgmt import memory_db  # noqa: E402

from api import config, db, national_stats  # noqa: E402
from api.services import dashboard  # noqa: E402

NOW = datetime(2026, 10, 13)


class DashboardMemberTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        national_stats._cache.update(at=0.0, stats=None, source=None)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _seed(conn)
        conn.execute("UPDATE farms SET member_type = '비조합원' WHERE id = 3")
        conn.commit()
        cls.d = {m: dashboard.build(conn, NOW, member=m) for m in dashboard.MEMBERS}

    def counts(self, m):
        k = self.d[m]["kpi"]
        return k["farms"], k["visits"], k["shipments"]

    def test_counts_split_and_add_up(self):
        self.assertEqual(self.counts("전체"), (3, 2, 7))        # 필터 없으면 기존과 같다
        self.assertEqual(self.counts("조합원"), (2, 2, 4))
        self.assertEqual(self.counts("비조합원"), (1, 0, 3))
        for i in range(3):
            self.assertEqual(self.counts("조합원")[i] + self.counts("비조합원")[i], self.counts("전체")[i])

    def test_one_plus_by_member(self):
        self.assertEqual(self.d["조합원"]["kpi"]["steer_1plus"]["value"], 100.0)     # 1++·1+
        self.assertEqual(self.d["비조합원"]["kpi"]["steer_1plus"]["value"], 0.0)     # 1·2
        self.assertEqual(self.d["전체"]["kpi"]["steer_1plus"]["value"], 50.0)

    def test_missing_lists_by_member(self):
        m, n = self.d["조합원"]["kpi"], self.d["비조합원"]["kpi"]
        self.assertEqual((m["missing_survey"], m["missing_shipment"]), ([], ["나농가"]))
        self.assertEqual((n["missing_survey"], n["missing_shipment"]), (["다농가"], []))

    def test_yearly_and_compare_by_member(self):
        row = self.d["조합원"]["trend"]["genders"]["거세"]["rows"][0]
        self.assertEqual((row["year"], row["farms"], row["heads"], row["carcass_weight"]), (2025, 1, 2, 450.0))
        row = self.d["비조합원"]["trend"]["genders"]["거세"]["rows"][0]
        self.assertEqual((row["farms"], row["heads"], row["carcass_weight"]), (1, 2, 500.0))
        self.assertEqual({r["gender"]: r["heads"] for r in self.d["비조합원"]["compare"]}, {"거세": 2, "수": 1})
        self.assertEqual({r["gender"]: r["heads"] for r in self.d["조합원"]["compare"]}, {"거세": 2, "암": 2})

    def test_unknown_member_rejected(self):
        with self.assertRaises(ValueError):
            dashboard.build(sqlite3.connect(":memory:"), NOW, member="x' OR '1'='1")


class MemberApiTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from api.main import app
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "consulting.db"
        disk = sqlite3.connect(self.path)
        memory_db().backup(disk)
        disk.close()
        p = mock.patch.object(config, "DB_PATH", self.path)
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(app)
        self.client.post("/api/auth/login", json={"password": os.environ["APP_PASSWORD"]})

    def code_of(self, farm_id):
        c = sqlite3.connect(self.path)
        try:
            return c.execute("SELECT farm_code FROM farms WHERE id = ?", (farm_id,)).fetchone()[0]
        finally:
            c.close()

    def farms(self):
        return {f["id"]: f for f in self.client.get("/api/farms").json()["farms"]}

    def test_old_farms_are_members(self):
        self.assertEqual({f["member_type"] for f in self.farms().values()}, {"조합원"})

    def test_create_non_member_gets_N_code(self):
        r = self.client.post("/api/farms", json={"name": "비조합원농가", "member_type": "비조합원"})
        self.assertEqual(r.status_code, 200, r.text)
        f = self.farms()[r.json()["id"]]
        self.assertEqual(f["member_type"], "비조합원")
        code = self.code_of(f["id"])
        self.assertTrue(code.startswith("N"), code)

    def test_create_member_without_code_keeps_F_code(self):
        r = self.client.post("/api/farms", json={"name": "조합원농가"})
        code = self.code_of(r.json()["id"])
        self.assertTrue(code.startswith("F"), code)
        self.assertEqual(self.farms()[r.json()["id"]]["member_type"], "조합원")

    def test_invalid_member_values_rejected(self):
        self.assertEqual(self.client.post("/api/farms", json={"name": "x", "member_type": "준조합원"}).status_code, 422)
        self.assertEqual(self.client.get("/api/dashboard", params={"member": "준조합원"}).status_code, 422)

    def test_dashboard_api_filter(self):
        a = self.client.get("/api/dashboard", params={"member": "비조합원"}).json()
        self.assertEqual((a["member"], a["kpi"]["farms"]), ("비조합원", 0))
        b = self.client.get("/api/dashboard").json()
        self.assertEqual(b["member"], "전체")


class MigrationTest(unittest.TestCase):
    def test_old_db_gets_column_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "old.db"
            c = sqlite3.connect(path)     # member_type 이 없던 시절의 farms
            c.execute("CREATE TABLE farms (id INTEGER PRIMARY KEY, farm_code TEXT UNIQUE, farm_name TEXT NOT NULL)")
            c.execute("INSERT INTO farms (farm_code, farm_name) VALUES ('M1', '옛농가')")
            c.commit()
            c.close()
            with mock.patch.object(config, "DB_PATH", path), mock.patch.object(db, "using_supabase", return_value=False):
                conn = db.connect()
                self.assertEqual(conn.execute("SELECT member_type FROM farms").fetchone()[0], "조합원")
                conn.close()
                db.connect().close()      # 두 번째 연결에서 다시 추가하려다 오류 나지 않는다


if __name__ == "__main__":
    unittest.main()
