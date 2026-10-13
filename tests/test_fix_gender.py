"""tools/fix_gender.py 검사 — 임시 SQLite DB 로 운영 DB 를 흉내 낸다 (백업·Supabase 는 가짜)."""
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
from tools import fix_gender  # noqa: E402


class KeepOpen:
    """스크립트가 연결을 닫아도 검사에서 다시 읽을 수 있게 close 만 무시한다."""
    def __init__(self, conn):
        self._c = conn

    def __getattr__(self, name):
        return getattr(self._c, name)

    def close(self):
        pass


class FixGenderTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(db_schema.SQLITE_DDL)
        self.conn.execute("INSERT INTO farms (id, farm_name) VALUES (1, '가농가')")
        self.conn.executemany("INSERT INTO shipment_records (farm_id, animal_no, gender, carcass_weight) VALUES (1, ?, ?, ?)",
                              [("002000000001", "암", 500), ("002000000002", "거세", 380), ("002000000003", "수", 400)])
        self.conn.commit()
        self.backups = []
        self.patches = [mock.patch.object(db, "using_supabase", lambda: True), mock.patch.object(db, "connect", lambda: KeepOpen(self.conn)),
                        mock.patch.object(db.db_adapter, "export_to_sqlite", lambda *a, **k: self.backups.append("file")),
                        mock.patch.object(db.db_adapter, "clear_cache", lambda: None),
                        mock.patch.object(backup, "run", lambda reason: self.backups.append(reason) or {"ok": True, "message": "ok"})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def run_tool(self, rows, *argv):
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(rows))), mock.patch.object(sys, "argv", ["fix_gender", *argv]), redirect_stdout(out):
            try:
                fix_gender.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def genders(self):
        return dict(self.conn.execute("SELECT animal_no, gender FROM shipment_records").fetchall())

    ROWS = [{"animal_no": "002000000001", "from": "암", "to": "거세"}, {"animal_no": "002000000002", "from": "거세", "to": "암"}]

    def test_preview_changes_nothing(self):
        code, out = self.run_tool(self.ROWS)
        self.assertIn("암→거세 1두", out)
        self.assertEqual(self.genders()["002000000001"], "암")
        self.assertEqual(self.backups, [])

    def test_apply_backs_up_then_fixes_only_gender(self):
        code, out = self.run_tool(self.ROWS, "--apply")
        self.assertIn("검증: 2/2두", out)
        self.assertEqual(self.genders(), {"002000000001": "거세", "002000000002": "암", "002000000003": "수"})
        self.assertEqual(self.backups[:2], ["file", "성별 고치기 전 백업"])
        self.assertEqual(self.conn.execute("SELECT carcass_weight FROM shipment_records WHERE animal_no='002000000001'").fetchone()[0], 500)

    def test_stops_when_current_value_differs(self):
        code, out = self.run_tool([{"animal_no": "002000000001", "from": "거세", "to": "암"}] + self.ROWS[1:], "--apply")
        self.assertIn("멈춤", str(code))
        self.assertEqual(self.genders()["002000000002"], "거세")           # 다른 행도 안 바뀜
        self.assertEqual(self.backups, [])

    def test_stops_without_github_backup(self):
        with mock.patch.object(backup, "run", lambda reason: {"ok": None, "message": "설정 안 됨"}):
            code, out = self.run_tool(self.ROWS, "--apply")
        self.assertIn("GitHub 백업이 되지 않아", str(code))
        self.assertEqual(self.genders()["002000000001"], "암")


if __name__ == "__main__":
    unittest.main()
