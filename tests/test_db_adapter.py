"""Supabase 이관(2026-10-04) 회귀 테스트.

- db_adapter.Row 가 sqlite3.Row 처럼 동작하는지 (이름/위치 접근, dict(row), pandas 가 값으로 읽는지)
- 앱의 SQL 이 Postgres 용으로 변환될 때 ? 자리표시자가 남지 않는지
- 저장 SQL(INSERT ... ON CONFLICT, RETURNING)을 운영 DB 와 같은 SQLite 표(db_schema.SQLITE_DDL)에서 실행해
  Turso·로컬 파일 모드에서도 그대로 동작하는지

Postgres 자체는 이 PC 에 없어 여기서 돌리지 않는다. 실제 Supabase 대조는 migrate_to_supabase.py --run 이 한다.
streamlit_app.py 는 import 할 수 없으므로(화면을 그림) SQL 은 소스에서 그대로 꺼내 쓴다.
"""
import re
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

import db_adapter  # noqa: E402
import db_schema  # noqa: E402

SOURCE = (ROOT / "tests" / "legacy_snapshot" / "streamlit_app_legacy.py").read_text(encoding="utf-8")


def _shipment_upserts():
    found = re.findall(r'cur\.execute\("""\s*(INSERT INTO shipment_records.*?)"""', SOURCE, re.S)
    if len(found) != 2:
        raise AssertionError("출하성적 저장 SQL 2개(API·엑셀)를 찾지 못했습니다 — 테스트를 코드에 맞게 고치세요.")
    api, excel = found
    return api, excel


def _report_upsert():
    m = re.search(r'c\.cursor\(\)\.execute\("""\s*(INSERT INTO ai_reports.*?)"""', SOURCE, re.S)
    if not m:
        raise AssertionError("AI 리포트 저장 SQL을 찾지 못했습니다.")
    return m.group(1)


def _visit_insert():
    m = re.search(r'cur\.execute\("(INSERT INTO visits[^"]*RETURNING id)"', SOURCE)
    if not m:
        raise AssertionError("방문 저장 SQL(RETURNING id)을 찾지 못했습니다.")
    return m.group(1)


class RowTest(unittest.TestCase):
    def test_behaves_like_sqlite_row(self):
        r = db_adapter.Row(("id", "name"), (1, "a"))
        self.assertEqual(r[0], 1)
        self.assertEqual(r["name"], "a")
        self.assertEqual(dict(r), {"id": 1, "name": "a"})
        self.assertEqual(list(r), [1, "a"])  # 순회하면 키가 아니라 값

    def test_pandas_reads_values_not_keys(self):
        rows = [db_adapter.Row(("a", "b"), (1, 2)), db_adapter.Row(("a", "b"), (3, 4))]
        df = pd.DataFrame(rows, columns=["a", "b"])
        self.assertEqual(df.to_dict("records"), [{"a": 1, "b": 2}, {"a": 3, "b": 4}])


class TranslateTest(unittest.TestCase):
    def test_no_question_mark_left_outside_literals(self):
        sqls = [m.group(2) for m in re.finditer(r'(?:execute|read_sql_query)\(\s*f?("""|")(.*?)\1', SOURCE, re.S)]
        self.assertGreater(len(sqls), 40)
        for sql in sqls:
            out = db_adapter._bind(db_adapter._translate(sql))
            outside = "".join(db_adapter._LITERAL_RE.split(out)[0::2])
            self.assertNotIn("?", outside, sql)

    def test_mixed_case_alias_is_quoted(self):
        out = db_adapter._translate("SELECT ROUND(AVG(bms), 1) AS BMS, id AS 농가ID FROM shipment_records")
        self.assertIn('AS "BMS"', out)
        self.assertIn('AS "농가ID"', out)


class SaveSqlOnSqliteTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db_schema.SQLITE_DDL)
        c = self.conn
        c.execute("INSERT INTO farms (id, farm_code, farm_name) VALUES (1, 'A', '가농가'), (2, 'B', '나농가')")
        c.execute("INSERT INTO shipment_records (farm_id, animal_no, gender, carcass_weight, price_per_kg, total_price, data_source)"
                  " VALUES (1, '002000000001', '거세', 400, 20000, 8000000, 'ekape_api')")

    def _row(self, ano):
        return dict(self.conn.execute("SELECT * FROM shipment_records WHERE animal_no = ?", (ano,)).fetchone())

    def test_excel_upsert_updates_but_keeps_price(self):
        _, excel = _shipment_upserts()
        self.conn.execute(excel, (1, "002000000001", "거세", "2025-05-05", 2025, 30, 450.5, "1+", "B", 7, 12.0, 95.0))
        r = self._row("002000000001")
        self.assertEqual(r["carcass_weight"], 450.5)
        self.assertEqual(r["price_per_kg"], 20000)  # 엑셀엔 단가가 없으니 유지
        self.assertEqual(r["data_source"], "excel")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM shipment_records").fetchone()[0], 1)

    def test_api_upsert_moves_animal_and_updates_price(self):
        api, _ = _shipment_upserts()
        self.conn.execute(api, (2, "002000000001", "거세", "2025-05-06", 2025, 31, 460, "1++", "A", 9, 11, 99, 25000, 11500000))
        r = self._row("002000000001")
        self.assertEqual((r["farm_id"], r["price_per_kg"], r["data_source"]), (2, 25000, "ekape_api"))

    def test_new_animal_is_inserted(self):
        _, excel = _shipment_upserts()
        self.conn.execute(excel, (1, "002000000002", "암", "2025-01-01", 2025, 28, 400, "1", "B", 5, 10, 90))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM shipment_records").fetchone()[0], 2)

    def test_visit_returning_and_report_upsert(self):
        cur = self.conn.cursor()
        cur.execute(_visit_insert(), (1, 1, "2026-10-04", "상담사"))
        vid = cur.fetchone()[0]
        self.assertEqual(vid, self.conn.execute("SELECT MAX(id) FROM visits").fetchone()[0])
        for md in ("첫 리포트", "다시 만든 리포트"):
            self.conn.execute(_report_upsert(), (vid, "전문", md, "2026-10-04 04:00:00"))
        self.conn.execute(_report_upsert(), (vid, "일반", "일반 리포트", "2026-10-04 04:01:00"))
        rows = self.conn.execute("SELECT report_mode, full_markdown FROM ai_reports WHERE visit_id = ? ORDER BY report_mode",
                                 (vid,)).fetchall()
        self.assertEqual([tuple(r) for r in rows], [("일반", "일반 리포트"), ("전문", "다시 만든 리포트")])


# ---------- 끊긴 연결 처리 (2026-11-06 운영 장애 재현) ----------
# 풀에 쉬던 연결을 Supavisor 가 끊어 두었는데, psycopg2 가 OperationalError 가 아닌 DatabaseError 를 내고
# raw.closed 도 0 으로 둬서 재접속을 하지 않고 같은 죽은 연결을 계속 풀로 돌려 썼다 → 모든 조회가 500.
class _FakeCur:
    def __init__(self, raw):
        self.raw, self.description, self.rowcount = raw, None, -1

    def execute(self, sql, params=None):
        if self.raw.dead:
            raise db_adapter.psycopg2.DatabaseError("server closed the connection unexpectedly")
        if self.raw.sql_error:
            e = db_adapter.psycopg2.errors.UndefinedTable('relation "x" does not exist')
            raise e
        self.raw.executed.append(sql)
        self.description, self.rowcount = (("n",),), 1

    def fetchall(self):
        return [(1,)]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeRaw:
    made = []

    def __init__(self, dead=False):
        self.dead, self.sql_error, self.closed, self.autocommit, self.executed = dead, False, 0, False, []
        _FakeRaw.made.append(self)

    def cursor(self):
        return _FakeCur(self)

    def close(self):
        self.closed = 1

    def rollback(self):
        if self.dead:
            raise db_adapter.psycopg2.DatabaseError("server closed the connection unexpectedly")

    def commit(self):
        pass

    def get_transaction_status(self):
        return db_adapter.ext.TRANSACTION_STATUS_IDLE


class DeadConnectionTest(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        _FakeRaw.made = []
        self.pool = db_adapter._Pool()
        patches = [
            mock.patch.object(db_adapter, "_POOL", self.pool),
            mock.patch.object(db_adapter, "database_url", lambda: "postgresql://fake"),
            mock.patch.object(db_adapter.psycopg2, "connect", lambda *a, **k: _FakeRaw()),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        db_adapter.invalidate("hanwoo")  # 조회 캐시가 결과를 대신 내주지 않게

    def _park(self, raw, age=0):
        self.pool._idle.append((raw, "hanwoo", db_adapter.time.time() - age))

    def test_dead_idle_connection_is_replaced_and_query_succeeds(self):
        dead = _FakeRaw(dead=True)
        self._park(dead)
        conn = db_adapter.connect("hanwoo")
        row = conn.execute("SELECT 1 AS n").fetchone()
        self.assertEqual(row[0], 1)
        self.assertTrue(dead.closed, "끊긴 연결은 닫아야 한다")
        conn.close()
        self.assertNotIn(dead, [r for r, _, _ in self.pool._idle], "끊긴 연결이 풀로 돌아가면 안 된다")

    def test_dead_connection_with_pending_write_is_not_retried_but_discarded(self):
        dead = _FakeRaw(dead=True)
        self._park(dead)
        conn = db_adapter.connect("hanwoo")
        conn._dirty = True  # 이 트랜잭션에 쓰기가 있었다면 다시 시도하면 안 된다 (쓰기가 사라짐)
        with self.assertRaises(db_adapter.OperationalError):
            conn.execute("SELECT 1 AS n")
        self.assertTrue(dead.closed)
        conn.rollback()
        conn.close()
        self.assertEqual(self.pool._idle, [])
        # 다음 요청은 새 연결로 정상 동작
        self.assertEqual(db_adapter.connect("hanwoo").execute("SELECT 2 AS n").fetchone()[0], 1)

    def test_sql_error_keeps_connection(self):
        raw = _FakeRaw()
        self._park(raw)
        conn = db_adapter.connect("hanwoo")
        raw.sql_error = True
        with self.assertRaises(db_adapter.OperationalError):
            conn.execute("SELECT * FROM x")
        self.assertFalse(raw.closed, "SQL 오류(pgcode 있음)는 연결 끊김이 아니다")

    def test_long_idle_connection_is_not_reused(self):
        old = _FakeRaw()
        self._park(old, age=db_adapter._Pool.MAX_IDLE_AGE + 1)
        raw, _ = self.pool.get()
        self.assertIsNot(raw, old)
        self.assertTrue(old.closed)


if __name__ == "__main__":
    unittest.main()
