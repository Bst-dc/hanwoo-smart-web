"""tools/fix_shipments.py 검사 — 임시 SQLite DB 로 운영 DB 를 흉내 낸다 (백업·Supabase 는 가짜)."""
import io
import json
import os
import sqlite3
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CONSULTING_LOCAL_ONLY", "1")

import db_schema  # noqa: E402
from api import backup, db  # noqa: E402
from tools import fix_shipments  # noqa: E402


class KeepOpen:
    def __init__(self, conn):
        self._c = conn

    def __getattr__(self, name):
        return getattr(self._c, name)

    def close(self):
        pass


class FixShipmentsTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(db_schema.SQLITE_DDL)
        self.conn.execute("INSERT INTO farms (id, farm_name) VALUES (1, '가농가')")
        self.conn.executemany(
            "INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_date, slaughter_year, month_age, carcass_weight,"
            " grade_quality, grade_yield, bms, price_per_kg) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 20000)",
            [("002000000001", "거세", "2026-03-11", 2026, 72, 361, "3", "A", 2),
             ("002000000002", "암", "2025-12-30", 2025, 33, 479, "1", "B", 4)])
        self.conn.commit()
        self.backups = []
        self.patches = [mock.patch.object(db, "using_supabase", lambda: True), mock.patch.object(db, "connect", lambda: KeepOpen(self.conn)),
                        mock.patch.object(db.db_adapter, "export_to_sqlite", lambda *a, **k: self.backups.append("file")),
                        mock.patch.object(db.db_adapter, "clear_cache", lambda: None),
                        mock.patch.object(backup, "run", lambda reason: self.backups.append(reason) or {"ok": True, "message": "ok"})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    ROWS = [
        {"animal_no": "002000000001",
         "from": {"gender": "거세", "slaughter_date": "2026-03-11", "month_age": 72, "carcass_weight": 361, "grade_quality": "3", "bms": 2},
         "to": {"gender": "암", "slaughter_date": "2024-03-11", "month_age": 128, "carcass_weight": 394, "grade_quality": "1", "bms": 6}},
        {"animal_no": "002000000002",
         "from": {"carcass_weight": 479, "grade_yield": "B"},
         "to": {"carcass_weight": 285, "grade_yield": "A"}},
    ]

    def run_tool(self, rows, *argv):
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(rows))), mock.patch.object(sys, "argv", ["fix_shipments", *argv]), redirect_stdout(out):
            try:
                fix_shipments.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def row(self, no):
        return self.conn.execute("SELECT gender, slaughter_date, slaughter_year, month_age, carcass_weight, grade_quality,"
                                 " grade_yield, bms, price_per_kg FROM shipment_records WHERE animal_no=?", (no,)).fetchone()

    def test_preview_changes_nothing(self):
        code, out = self.run_tool(self.ROWS)
        self.assertIn("carcass_weight 2", out)
        self.assertEqual(self.row("002000000001")[4], 361)
        self.assertEqual(self.backups, [])

    def test_apply_fixes_listed_columns_year_follows_and_price_untouched(self):
        code, out = self.run_tool(self.ROWS, "--apply")
        self.assertIn("검증: 2/2두", out)
        self.assertEqual(self.row("002000000001"), ("암", "2024-03-11", 2024, 128, 394, "1", "A", 6, 20000))
        self.assertEqual(self.row("002000000002"), ("암", "2025-12-30", 2025, 33, 285, "1", "A", 4, 20000))
        self.assertEqual(self.backups[:2], ["file", "출하성적 고치기 전 백업"])

    def test_stops_when_current_value_differs(self):
        bad = json.loads(json.dumps(self.ROWS))
        bad[1]["from"]["carcass_weight"] = 480
        code, out = self.run_tool(bad, "--apply")
        self.assertIn("멈춤", str(code))
        self.assertEqual(self.row("002000000001")[4], 361)           # 다른 행도 안 바뀜
        self.assertEqual(self.backups, [])

    def test_rejects_column_outside_whitelist(self):
        bad = [{"animal_no": "002000000001", "from": {"price_per_kg": 20000}, "to": {"price_per_kg": 1}}]
        code, out = self.run_tool(bad, "--apply")
        self.assertIn("입력 오류", str(code))

    def test_stops_without_github_backup(self):
        with mock.patch.object(backup, "run", lambda reason: {"ok": None, "message": "설정 안 됨"}):
            code, out = self.run_tool(self.ROWS, "--apply")
        self.assertIn("GitHub 백업이 되지 않아", str(code))
        self.assertEqual(self.row("002000000001")[4], 361)


if __name__ == "__main__":
    unittest.main()
