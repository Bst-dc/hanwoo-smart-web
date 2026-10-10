"""데이터 관리 · 백업 API 시험 — 기존 화면(메뉴 5)의 SQL·CSV 와 같은지 본다.

기존 앱의 f_df/s_df/v_df/r_df 조회 SQL 을 소스에서 그대로 꺼내 같은 시험 DB 에 돌려 표와 CSV 바이트를 비교한다.
실행: python -m unittest tests.test_api_data
"""
import io
import re
import sqlite3
import unittest
from unittest import mock

import pandas as pd

from test_api_dashboard import APP_SOURCE, ApiTestBase  # noqa: E402

from api.services import backup, data_export  # noqa: E402

SECTION = APP_SOURCE[APP_SOURCE.index('elif menu == "데이터 관리 · 백업":'):]


def legacy(var: str, farm: bool) -> str:
    """기존 화면의 `{var} = pd.read_sql_query(...)` SQL (농가 선택 있음/없음). v_cols·r_cols 는 값을 채워 넣는다."""
    branch = SECTION.split("if filter_farm_id:", 1)[1]
    part = branch.split("    else:\n", 1)[0] if farm else branch.split("    else:\n", 1)[1]
    m = re.search(var + r' = pd\.read_sql_query\(f?"([^"]*)"', part)   # SQL 안에 큰따옴표는 없다
    assert m, var
    sql = m.group(1)
    for name in ("v_cols", "r_cols"):
        sql = sql.replace("{" + name + "}", re.search(rf'^    {name} = "(.*)"$', SECTION, re.M).group(1))
    return sql


def legacy_frame(conn, var, farm_id=None):
    sql = legacy(var, farm_id is not None)
    return pd.read_sql_query(sql, conn, params=(farm_id,) if farm_id is not None else None)


class DataTest(ApiTestBase):
    def setUp(self):
        super().setUp()
        self.p = mock.patch("api.config.app_password", return_value=None)
        self.p.start()
        c = self.conn
        c.execute("INSERT INTO ai_reports (visit_id, report_mode, full_markdown, created_at) VALUES (1, '전문', ?, '2026-10-11 01:00:00')",
                  ("# 리포트\n" + "가" * 100,))
        c.execute("INSERT INTO ai_reports (visit_id, report_mode, full_markdown, created_at) VALUES (1, '일반', '짧음', '2026-10-11 02:00:00')")
        c.execute("INSERT INTO ai_reports (visit_id, report_mode, full_markdown, created_at) VALUES (2, '일반', '다른 농가', '2026-10-11 03:00:00')")
        c.commit()

    def tearDown(self):
        self.p.stop()
        super().tearDown()

    def test_tables_match_legacy_all_and_per_farm(self):
        keys = {"farms": "f_df", "shipments": "s_df", "visits": "v_df", "reports": "r_df"}
        for farm_id in (None, 1, 2, 3, 5):
            got = self.client.get("/api/data/tables", params={} if farm_id is None else {"farm_id": farm_id}).json()
            for name, var in keys.items():
                with self.subTest(farm=farm_id, table=name):
                    want = legacy_frame(self.conn, var, farm_id)
                    if name == "reports":
                        md = want["full_markdown"].str.slice(0, 60) + "…"
                        want = want.drop(columns=["full_markdown"]).assign(미리보기=md)
                    self.assertEqual(got[name]["columns"], list(want.columns))
                    self.assertEqual(len(got[name]["rows"]), len(want))
                    self.assertEqual(pd.DataFrame(got[name]["rows"], columns=got[name]["columns"]).to_csv(index=False),
                                     want.to_csv(index=False))

    def test_csv_matches_legacy_bytes(self):
        for name, var in [("farms", "f_df"), ("shipments", "s_df"), ("visits", "v_df")]:
            for farm_id in (None, 1):
                r = self.client.get(f"/api/data/export/{name}.csv", params={} if farm_id is None else {"farm_id": farm_id})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.content, legacy_frame(self.conn, var, farm_id).to_csv(index=False).encode("utf-8-sig"))
        self.assertIn("filename*=UTF-8''", r.headers["content-disposition"])

    def test_report_detail_and_html(self):
        rid = self.conn.execute("SELECT id FROM ai_reports WHERE report_mode='전문'").fetchone()[0]
        r = self.client.get(f"/api/data/reports/{rid}").json()
        self.assertEqual((r["farm_name"], r["report_mode"], r["markdown"][:4]), ("가농장", "전문", "# 리포"))
        h = self.client.get(f"/api/data/reports/{rid}/html")
        self.assertIn("가농장 AI 컨설팅 리포트 (전문)", h.text)
        self.assertEqual(self.client.get("/api/data/reports/999").status_code, 404)
        self.assertEqual(self.client.get("/api/data/reports/999/html").status_code, 404)

    def test_unknown_farm_and_name(self):
        self.assertEqual(self.client.get("/api/data/tables", params={"farm_id": 999}).status_code, 404)
        self.assertEqual(self.client.get("/api/data/export/farms.csv", params={"farm_id": 999}).status_code, 404)
        self.assertEqual(self.client.get("/api/data/export/reports.csv").status_code, 422)

    def test_db_file(self):
        with mock.patch.object(backup.db, "using_supabase", return_value=False), \
             mock.patch.object(backup, "db_file_bytes", return_value=(b"SQLite format 3\x00abc", None)):
            r = self.client.get("/api/data/db-file")
        self.assertEqual((r.status_code, r.content[:6]), (200, b"SQLite"))
        self.assertRegex(r.headers["content-disposition"], r"consulting_\d{8}_\d{4}\.db")
        with mock.patch.object(backup, "db_file_bytes", return_value=(None, "스냅샷 실패")):
            r = self.client.get("/api/data/db-file")
        self.assertEqual((r.status_code, r.json()["detail"]), (500, "스냅샷 실패"))

    def test_real_sqlite_snapshot_is_readable(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "consulting.db"
            src = sqlite3.connect(path)
            self.conn.backup(src)
            src.close()
            with mock.patch.object(backup.db, "using_supabase", return_value=False), mock.patch.object(backup.db, "LOCAL_DB", path):
                r = self.client.get("/api/data/db-file")
            out = Path(d) / "copy.db"
            out.write_bytes(r.content)
            copy = sqlite3.connect(out)
            try:
                self.assertEqual(copy.execute("SELECT COUNT(*) FROM farms").fetchone()[0], 5)
            finally:
                copy.close()


if __name__ == "__main__":
    unittest.main()
