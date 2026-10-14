"""DB 연결 — 기존 앱의 get_db() 와 같은 규칙.

DATABASE_URL 이 있으면 Supabase(hanwoo 스키마, db_adapter 가 sqlite3 처럼 맞춰 줌), 없으면 로컬 SQLite 파일.
요청마다 연결을 열고 닫는다 (db_adapter 가 연결 풀을 갖고 있다).
"""
import sqlite3
import sys

from . import config

sys.path.insert(0, str(config.BASE_DIR))
import db_adapter  # noqa: E402
import db_schema  # noqa: E402


def using_supabase() -> bool:
    return not config.LOCAL_ONLY and db_adapter.enabled()


def connect():
    if using_supabase():
        # member_type 칸이 이미 있으면 DDL 을 실행하지 않고 건너뛴다 (프로세스당 한 번 점검)
        db_adapter.ensure_schema(db_schema.SCHEMA, db_schema.PG_DDL, extra_sql=db_schema.EXTRA_SQL,
                                 required_tables=db_schema.TABLES, required_columns=db_schema.REQUIRED_COLUMNS)
        return db_adapter.connect(db_schema.SCHEMA)
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(farms)")}
    if cols and "member_type" not in cols:                 # 기존 농가는 모두 조합원
        conn.execute("ALTER TABLE farms ADD COLUMN member_type TEXT NOT NULL DEFAULT '조합원'")
        conn.commit()
    return conn


def get_conn():
    """FastAPI 의존성 — 요청이 끝나면 닫는다."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
