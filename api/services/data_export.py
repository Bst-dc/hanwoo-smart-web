"""데이터 관리 · 백업 — streamlit_app.py '메뉴 5: 데이터 관리 · 백업' 의 표 조회와 CSV 를 옮긴 것.

조회 SQL·열 이름·CSV 형식(utf-8-sig, 인덱스 없음)은 기존 앱과 같다. tests/test_api_data.py 가 기존 SQL 과 대조한다.
"""
import io

import pandas as pd

V_COLS = ("v.id AS 방문ID, v.farm_id AS 농가ID, f.farm_name, v.visit_number, v.visit_date, v.consultant_name, "
          "s.consult_notes, s.consultant_memo, s.facility_info, s.feed_info")
R_COLS = ("r.id AS 리포트ID, v.farm_id AS 농가ID, f.farm_name, v.visit_date, r.report_type, r.report_mode, "
          "r.created_at, r.full_markdown")
FARMS_SQL = "SELECT id AS 농가ID, farm_code, farm_name, owner_name, region, breeding_type, total_heads, created_at FROM farms"
SHIPMENTS_SQL = ("SELECT s.animal_no, f.farm_name, s.gender, s.slaughter_date, s.carcass_weight, s.grade_quality, "
                 "s.grade_yield, s.bms, s.backfat, s.ribeye FROM shipment_records s JOIN farms f ON s.farm_id = f.id")
VISITS_SQL = (f"SELECT {V_COLS} FROM visits v JOIN farms f ON v.farm_id = f.id "
              "LEFT JOIN field_surveys s ON s.visit_id = v.id")
REPORTS_SQL = (f"SELECT {R_COLS} FROM ai_reports r JOIN visits v ON r.visit_id = v.id "
               "JOIN farms f ON v.farm_id = f.id")

# (이름, SQL, 농가 조건 칸, 정렬) — 농가를 고르면 WHERE 가 붙고 정렬은 기존과 같다
TABLES = {
    "farms": (FARMS_SQL, "id", ""),
    "shipments": (SHIPMENTS_SQL, "s.farm_id", " ORDER BY s.slaughter_date DESC"),
    "visits": (VISITS_SQL, "v.farm_id", " ORDER BY v.visit_date DESC"),
    "reports": (REPORTS_SQL, "v.farm_id", " ORDER BY r.created_at DESC"),
}
CSV_NAMES = {"farms": "농가목록_DB.csv", "shipments": "출하성적_전체_DB.csv", "visits": "현장방문이력_전체_DB.csv"}


def _plain(v):
    """Postgres NUMERIC(Decimal)·날짜 객체를 JSON·CSV 에서 SQLite 값과 같은 모양으로."""
    if v is None or isinstance(v, (int, float, str)):
        return v
    if hasattr(v, "isoformat"):
        return str(v)
    return float(v)


def table(conn, name: str, farm_id: int | None = None, with_markdown: bool = False) -> dict:
    sql, farm_col, order = TABLES[name]
    params = ()
    if farm_id is not None:
        sql += f" WHERE {farm_col} = ?"
        params = (farm_id,)
    cur = conn.execute(sql + order, params)
    cols = [d[0] for d in cur.description]
    rows = [[_plain(v) for v in r] for r in cur.fetchall()]
    if name == "reports" and not with_markdown:
        i = cols.index("full_markdown")
        cols[i] = "미리보기"
        rows = [r[:i] + [(r[i] or "")[:60] + "…"] + r[i + 1:] for r in rows]
    return {"columns": cols, "rows": rows}


def csv_bytes(conn, name: str, farm_id: int | None = None) -> bytes:
    t = table(conn, name, farm_id)
    buf = io.StringIO()
    pd.DataFrame(t["rows"], columns=t["columns"]).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8-sig")


def get_report(conn, report_id: int) -> dict | None:
    r = conn.execute("""
        SELECT r.id, f.id, f.farm_name, v.visit_date, r.report_mode, r.created_at, r.full_markdown
        FROM ai_reports r JOIN visits v ON r.visit_id = v.id JOIN farms f ON v.farm_id = f.id WHERE r.id = ?
    """, (report_id,)).fetchone()
    if r is None:
        return None
    return {"id": r[0], "farm_id": r[1], "farm_name": r[2], "visit_date": str(r[3]), "report_mode": r[4],
            "created_at": str(r[5]), "markdown": r[6]}
