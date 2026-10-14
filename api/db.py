"""DB 연결 — 기존 앱의 get_db() 와 같은 규칙.

DATABASE_URL 이 있으면 Supabase(hanwoo 스키마, db_adapter 가 sqlite3 처럼 맞춰 줌),
없으면 로컬 SQLite 파일 data/consulting.db. (Turso 예비 연결은 옮기지 않는다 — 곧 지울 예정)
"""
import logging
import sqlite3
import sys
from pathlib import Path

from . import config  # noqa: F401  — DATABASE_URL 을 환경변수로 넘겨 두기 위해 먼저 불러온다

sys.path.insert(0, str(config.BASE_DIR))
import db_adapter  # noqa: E402
import db_schema  # noqa: E402

log = logging.getLogger(__name__)
LOCAL_DB = Path(config.LOCAL_DB_OVERRIDE) if config.LOCAL_DB_OVERRIDE else config.BASE_DIR / "data" / "consulting.db"


def using_supabase() -> bool:
    return not config.LOCAL_DB_OVERRIDE and db_adapter.enabled()


def connect():
    if using_supabase():
        db_adapter.ensure_schema(db_schema.SCHEMA, db_schema.PG_DDL, extra_sql=db_schema.EXTRA_SQL,
                                 required_tables=db_schema.TABLES, required_columns=db_schema.REQUIRED_COLUMNS)
        return db_adapter.connect(db_schema.SCHEMA)
    fresh = not LOCAL_DB.exists()
    LOCAL_DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(LOCAL_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if fresh:
        log.info("로컬 DB 새로 만듦: %s", LOCAL_DB)
        conn.executescript(db_schema.SQLITE_DDL)
    elif "member_type" not in {r[1] for r in conn.execute("PRAGMA table_info(farms)")}:
        log.info("farms 에 member_type 칸 추가 (기존 농가는 모두 조합원)")
        conn.execute("ALTER TABLE farms ADD COLUMN member_type TEXT NOT NULL DEFAULT '조합원'")
        conn.commit()
    return conn


def get_db():
    """FastAPI 의존성: 요청마다 연결을 열고, 끝나면 닫는다(Supabase 는 연결 풀로 돌아간다)."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


IntegrityErrors = (sqlite3.IntegrityError, db_adapter.IntegrityError)
