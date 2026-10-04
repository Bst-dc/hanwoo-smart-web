"""SQLite DB 파일(.db)을 Supabase 의 hanwoo 스키마로 옮긴다 (Turso → Supabase 이관, 1회성).

사용법 (프로젝트 폴더에서):
    python migrate_to_supabase.py <파일.db>          # 확인만 (원본·Supabase 행 수 비교)
    python migrate_to_supabase.py <파일.db> --run    # 실제로 옮기고, 모든 행·칸을 원본과 대조

- 원본 파일은 '데이터 관리 · 백업' 메뉴의 'DB 파일 준비' 로 받은 것(운영 Turso 의 그 시점 사본)을 쓴다.
- hanwoo 스키마를 통째로 지우고 db_schema.PG_DDL 로 다시 만든 뒤 넣는다. 한 트랜잭션이라 도중에 실패하면
  Supabase 는 이전 상태 그대로 남는다. 같은 프로젝트의 시험농장 스키마(sunsan, goa 등)는 건드리지 않는다.
- 원본 SQLite 파일은 읽기만 한다.
- 접속 주소: 환경변수 DATABASE_URL, 없으면 .streamlit/secrets.toml 의 DATABASE_URL.
"""
import math
import os
import sqlite3
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if not os.environ.get("DATABASE_URL"):
    try:
        with open(os.path.join(HERE, ".streamlit", "secrets.toml"), "rb") as f:
            os.environ["DATABASE_URL"] = tomllib.load(f)["DATABASE_URL"]
    except (OSError, KeyError):
        sys.exit("DATABASE_URL 이 없습니다 (환경변수 또는 .streamlit/secrets.toml).")

import db_adapter  # noqa: E402
from db_schema import PG_DDL, SCHEMA, TABLES  # noqa: E402

assert SCHEMA == "hanwoo", "이 스크립트는 hanwoo 스키마만 지우고 다시 만든다"


def local_counts(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if t in tables else None for t in TABLES}
    finally:
        conn.close()


def remote_counts():
    if not db_adapter.database_exists(SCHEMA):
        return {t: None for t in TABLES}
    conn = db_adapter.connect(SCHEMA)
    try:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    finally:
        conn.close()


def _same(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-9)
    return str(a) == str(b)


def verify(path):
    """원본의 모든 행·칸이 Supabase 에 똑같이 들어갔는지 id 기준으로 대조한다. 반환: 문제 목록."""
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    dst = db_adapter.connect(SCHEMA)
    problems = []
    try:
        for t in TABLES:
            src_cols = [r[1] for r in src.execute(f"PRAGMA table_info({t})")]
            dst_cols = {r[1] for r in dst.execute(f"PRAGMA table_info({t})").fetchall()}
            missing = [c for c in src_cols if c not in dst_cols]
            if missing:
                problems.append(f"{t}: Supabase 에 없는 원본 컬럼 {missing} (값이 옮겨지지 않음)")
            cols = [c for c in src_cols if c in dst_cols]
            col_sql = ", ".join(cols)
            a = {r[0]: r for r in src.execute(f"SELECT {col_sql} FROM {t} ORDER BY id")}
            b = {r[0]: tuple(r) for r in dst.execute(f"SELECT {col_sql} FROM {t} ORDER BY id").fetchall()}
            if a.keys() != b.keys():
                problems.append(f"{t}: id 목록이 다름 (원본 {len(a)}행, Supabase {len(b)}행)")
                continue
            diff = [(i, c) for i in a for c, x, y in zip(cols, a[i], b[i]) if not _same(x, y)]
            if diff:
                problems.append(f"{t}: 값이 다른 칸 {len(diff)}개, 예: {diff[:5]}")
            # 다음 새 행 번호가 기존 id 와 겹치지 않는지 (SERIAL 시퀀스)
            nxt = dst.execute(f"SELECT nextval(pg_get_serial_sequence('{t}', 'id'))").fetchone()[0]
            dst.rollback()  # nextval 은 롤백해도 되돌아가지 않지만 번호 하나 건너뛰는 것뿐이라 무해하다
            if a and nxt <= max(a):
                problems.append(f"{t}: 다음 id({nxt})가 기존 최댓값({max(a)}) 이하")
    finally:
        src.close()
        dst.close()
    return problems


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1 or not os.path.isfile(args[0]):
        sys.exit(__doc__)
    path = os.path.abspath(args[0])
    run = "--run" in sys.argv

    print("원본:", path)
    lc, rc = local_counts(path), remote_counts()
    print(f"{'표':<18}{'원본':>8}{'Supabase(현재)':>16}")
    for t in TABLES:
        print(f"{t:<18}{str(lc[t]):>8}{str(rc[t]):>16}")
    if not run:
        print("\n확인만 했습니다. 실제로 옮기려면 --run 을 붙이세요 (hanwoo 스키마를 통째로 교체).")
        return

    counts = db_adapter.import_from_sqlite(SCHEMA, path, PG_DDL, TABLES)
    print("\n옮긴 행 수:", counts)
    problems = verify(path)
    if problems:
        print("\n⚠️ 대조 결과 문제:")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("\n✅ 모든 표의 모든 행·칸이 원본과 같습니다.")


if __name__ == "__main__":
    main()
