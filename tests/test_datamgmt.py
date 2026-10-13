"""데이터 관리 · 백업, 신규 농가 등록 검사 — 임시 DB, 작은 데이터. 운영 DB 에는 붙지 않는다.
실행: python -m unittest tests.test_datamgmt
"""
import csv
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CONSULTING_LOCAL_ONLY"] = "1"
os.environ.setdefault("APP_PASSWORD", "test-pass")
os.environ.pop("GITHUB_TOKEN", None)

import db_schema  # noqa: E402
from api.services import datamgmt as dm  # noqa: E402


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db_schema.SQLITE_DDL)
    conn.executemany("INSERT INTO farms (id, farm_code, farm_name, region) VALUES (?, ?, ?, ?)",
                     [(1, "M0000001", "가농가", "구미"), (2, "F_12", "나농가", None)])
    conn.executemany("INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_date, carcass_weight) VALUES (?,?,?,?,?)",
                     [(1, "a1", "거세", "2025-01-02", 480), (1, "a2", "암", "2026-03-04", 390), (2, "b1", "거세", "2024-05-06", 450)])
    conn.execute("INSERT INTO visits (id, farm_id, visit_number, visit_date) VALUES (5, 2, 1, '2026-01-01')")
    conn.execute("INSERT INTO visits (id, farm_id, visit_number, visit_date) VALUES (6, 2, 2, '2026-05-01')")
    conn.execute("INSERT INTO field_surveys (visit_id, facility_info, survey_data) VALUES (5, ?, ?)", ("가" * 100, json.dumps({"region": "영천"})))
    conn.execute("INSERT INTO field_surveys (visit_id, survey_data) VALUES (6, ?)", (json.dumps({"region": "경산"}),))
    conn.execute("INSERT INTO ai_reports (visit_id, report_mode, full_markdown) VALUES (6, '일반', '# 리포트')")
    conn.commit()
    return conn


class DataTest(unittest.TestCase):
    def setUp(self):
        self.conn = memory_db()

    def test_summary_counts_and_filter(self):
        s = dm.summary(self.conn, None)
        self.assertEqual({k: v["count"] for k, v in s.items()}, {"farms": 2, "shipments": 3, "visits": 2, "reports": 1})
        self.assertEqual(s["shipments"]["rows"][0][0], "a2")                         # 도축일 최신 순
        self.assertEqual(s["farms"]["columns"][:3], ["농가ID", "farm_code", "farm_name"])
        one = dm.summary(self.conn, 1)
        self.assertEqual({k: v["count"] for k, v in one.items()}, {"farms": 1, "shipments": 2, "visits": 0, "reports": 0})
        fi = s["visits"]["columns"].index("facility_info")
        self.assertEqual(len([r for r in s["visits"]["rows"] if r[fi]][0][fi]), 41)    # 긴 글은 40자 + …

    def test_csv_has_bom_and_same_columns_as_old_app(self):
        b = dm.csv_bytes(self.conn, "shipments", None)
        self.assertTrue(b.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(b.decode("utf-8-sig"))))
        self.assertEqual(rows[0], ["animal_no", "farm_name", "gender", "slaughter_date", "carcass_weight", "grade_quality", "grade_yield", "bms", "backfat", "ribeye"])
        self.assertEqual(len(rows), 4)

    def test_region_comes_from_latest_survey(self):
        self.assertEqual(dm.region_from_surveys(self.conn), {2: "경산"})

    def test_duplicate_by_name_or_code(self):
        self.assertEqual(dm.find_duplicate(self.conn, " 가농가 ", "")["id"], 1)
        self.assertEqual(dm.find_duplicate(self.conn, "다른이름", "F_12")["id"], 2)
        self.assertIsNone(dm.find_duplicate(self.conn, "다농가", "M9"))
        self.assertIsNone(dm.find_duplicate(self.conn, "", ""))

    def test_create_farm_with_auto_code_and_unique_error(self):
        new = dm.create_farm(self.conn, {"name": " 다농가 ", "code": "", "owner": "", "region": "칠곡", "breeding_type": "번식우", "total_heads": 40},
                             now=datetime.fromtimestamp(1234567))
        r = self.conn.execute("SELECT farm_code, farm_name, breeding_type, total_heads FROM farms WHERE id = ?", (new,)).fetchone()
        self.assertEqual(tuple(r), ("F4567", "다농가", "번식우", 40))
        with self.assertRaisesRegex(dm.FarmError, "이미 다른 농가"):
            dm.create_farm(self.conn, {"name": "라농가", "code": "M0000001", "breeding_type": "비육우", "total_heads": 1})
        with self.assertRaisesRegex(dm.FarmError, "농가명"):
            dm.create_farm(self.conn, {"name": "  ", "breeding_type": "비육우", "total_heads": 1})


class DataApiTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from api import config
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

    def test_downloads(self):
        r = self.client.get("/api/data/export/visits?farm_id=2")
        self.assertIn("filename*=UTF-8''", r.headers["content-disposition"])
        self.assertEqual(len(r.content.decode("utf-8-sig").strip().splitlines()), 3)
        r = self.client.get("/api/data/db-file")
        self.assertTrue(r.content.startswith(b"SQLite format 3"))
        self.assertEqual(self.client.get("/api/data/export/secrets").status_code, 422)

    def test_farm_list_uses_survey_region(self):
        farms = {f["id"]: f for f in self.client.get("/api/farms").json()["farms"]}
        self.assertEqual((farms[1]["region"], farms[2]["region"]), ("구미", "경산"))

    def test_create_needs_confirm_for_duplicate(self):
        body = {"name": "가농가", "region": "구미"}
        self.assertEqual(self.client.get("/api/farms/duplicate", params={"name": "가농가"}).json()["match"]["id"], 1)
        self.assertEqual(self.client.post("/api/farms", json=body).status_code, 409)
        r = self.client.post("/api/farms", json={**body, "confirm_duplicate": True})
        self.assertEqual((r.status_code, r.json()["backup"]["ok"]), (200, None))
        self.assertEqual(self.client.post("/api/farms", json={"name": "새농가", "code": "M0000001"}).status_code, 409)
        self.assertEqual(len(self.client.get("/api/farms").json()["farms"]), 3)


if __name__ == "__main__":
    unittest.main()
