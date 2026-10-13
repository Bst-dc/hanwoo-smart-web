"""새 앱(FastAPI) 뼈대 검사 — 로그인과 농가 목록.

임시 SQLite DB 에 농가 2곳을 넣고(A: 방문 2회·출하 3두, B: 없음) 숫자가 정확히 나오는지 본다.
운영 DB 에는 붙지 않는다 (CONSULTING_LOCAL_ONLY=1).
실행: python -m unittest tests.test_api_skeleton
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["CONSULTING_LOCAL_ONLY"] = "1"
os.environ["CONSULTING_DB_PATH"] = str(Path(_tmp.name) / "consulting.db")
os.environ["APP_PASSWORD"] = "test-pass"

from fastapi.testclient import TestClient  # noqa: E402

import db_schema  # noqa: E402
from api import config  # noqa: E402
from api.main import app  # noqa: E402

# 다른 시험 파일이 먼저 api 를 불러왔어도 이 시험의 임시 DB 를 쓰게 경로를 직접 지정한다
config.DB_PATH = Path(os.environ["CONSULTING_DB_PATH"])


def _seed():
    conn = sqlite3.connect(os.environ["CONSULTING_DB_PATH"])
    conn.executescript(db_schema.SQLITE_DDL)
    conn.execute("INSERT INTO farms (id, farm_name, owner_name, region) VALUES (1, '가농가', '홍길동', '구미')")
    conn.execute("INSERT INTO farms (id, farm_name) VALUES (2, '나농가')")
    conn.execute("INSERT INTO visits (farm_id, visit_number, visit_date) VALUES (1, 1, '2026-01-01')")
    conn.execute("INSERT INTO visits (farm_id, visit_number, visit_date) VALUES (1, 2, '2026-06-01')")
    for i in range(3):
        conn.execute("INSERT INTO shipment_records (farm_id, animal_no) VALUES (1, ?)", (f"00{i}",))
    conn.commit()
    conn.close()


class ApiSkeletonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed()

    def setUp(self):
        self.client = TestClient(app)

    def test_health_needs_no_login(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True, "db": "sqlite"})

    def test_farms_requires_login(self):
        self.assertEqual(self.client.get("/api/farms").status_code, 401)

    def test_wrong_password_rejected(self):
        r = self.client.post("/api/auth/login", json={"password": "wrong"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.client.get("/api/farms").status_code, 401)

    def test_login_then_farms_counts(self):
        r = self.client.post("/api/auth/login", json={"password": "test-pass"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["logged_in"])
        farms = self.client.get("/api/farms").json()["farms"]
        self.assertEqual([f["name"] for f in farms], ["가농가", "나농가"])
        a, b = farms
        self.assertEqual((a["visits"], a["shipments"]), (2, 3))
        self.assertEqual((b["visits"], b["shipments"]), (0, 0))
        self.assertEqual(a["owner"], "홍길동")
        self.assertEqual(b["owner"], "")

    def test_logout_clears_session(self):
        self.client.post("/api/auth/login", json={"password": "test-pass"})
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/farms").status_code, 401)


if __name__ == "__main__":
    unittest.main()
