"""데이터 관리 · 백업, 신규 농가 등록 — 기존 앱 메뉴 5와 사이드바 '신규 농가 등록'과 같은 내용.

- 농가·출하성적·방문 이력: 표 미리보기와 CSV(엑셀에서 한글이 깨지지 않게 UTF-8 BOM) 내려받기. 열·파일 이름은 기존 앱과 같다.
- DB 전체 파일(.db): Supabase 면 hanwoo 스키마를 SQLite 파일로 떠서, 로컬이면 파일 그대로.
- 신규 농가: 이름이나 조합원번호가 기존 농가와 정확히 같으면 확인을 받는다 (같은 농가가 둘로 쪼개지면
  출하성적과 조사표가 서로 연결되지 않는다). 조합원번호를 비우면 기존 앱처럼 F + 숫자 4자리를 붙인다.
"""
import logging
import os
import tempfile
from datetime import datetime

import pandas as pd

from .. import config, db

log = logging.getLogger("consulting.datamgmt")

FARM_COLS = "id AS 농가ID, farm_code, farm_name, owner_name, region, breeding_type, total_heads, created_at"
SHIP_COLS = "s.animal_no, f.farm_name, s.gender, s.slaughter_date, s.carcass_weight, s.grade_quality, s.grade_yield, s.bms, s.backfat, s.ribeye"
VISIT_COLS = ("v.id AS 방문ID, v.farm_id AS 농가ID, f.farm_name, v.visit_number, v.visit_date, v.consultant_name, "
              "s.consult_notes, s.consultant_memo, s.facility_info, s.feed_info")
REPORT_COLS = "r.id AS 리포트ID, v.farm_id AS 농가ID, f.farm_name, v.visit_date, r.report_type, r.report_mode, r.created_at"
BREEDING_TYPES = ["비육우", "일관사육", "번식우"]


def _sql(kind: str, farm_id: int | None) -> tuple[str, tuple]:
    where_f, where_v = ("WHERE id = ?", "WHERE v.farm_id = ?") if farm_id else ("", "")
    p = (farm_id,) if farm_id else ()
    return {
        "farms": (f"SELECT {FARM_COLS} FROM farms {where_f}", p),
        "shipments": (f"SELECT {SHIP_COLS} FROM shipment_records s JOIN farms f ON s.farm_id = f.id "
                      f"{'WHERE s.farm_id = ?' if farm_id else ''} ORDER BY s.slaughter_date DESC", p),
        "visits": (f"SELECT {VISIT_COLS} FROM visits v JOIN farms f ON v.farm_id = f.id LEFT JOIN field_surveys s ON s.visit_id = v.id "
                   f"{where_v} ORDER BY v.visit_date DESC", p),
        "reports": (f"SELECT {REPORT_COLS} FROM ai_reports r JOIN visits v ON r.visit_id = v.id JOIN farms f ON v.farm_id = f.id "
                    f"{where_v} ORDER BY r.created_at DESC", p),
    }[kind]


def frame(conn, kind: str, farm_id: int | None) -> pd.DataFrame:
    sql, p = _sql(kind, farm_id)
    cur = conn.execute(sql, p)
    return pd.DataFrame([tuple(r) for r in cur.fetchall()], columns=[c[0] for c in cur.description])


CSV_NAMES = {"farms": "농가목록_DB.csv", "shipments": "출하성적_전체_DB.csv", "visits": "현장방문이력_전체_DB.csv"}


def csv_bytes(conn, kind: str, farm_id: int | None) -> bytes:
    return frame(conn, kind, farm_id).to_csv(index=False).encode("utf-8-sig")


def _jsonable(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def summary(conn, farm_id: int | None, preview: int = 30) -> dict:
    out = {}
    for kind in ("farms", "shipments", "visits", "reports"):
        df = frame(conn, kind, farm_id)
        if kind == "visits":                     # 긴 원본 글은 미리보기에서 줄인다
            for c in ("consult_notes", "consultant_memo", "facility_info", "feed_info"):
                df[c] = df[c].map(lambda s: (str(s)[:40] + "…") if isinstance(s, str) and len(s) > 40 else s)
        out[kind] = {"count": len(df), "columns": list(df.columns),
                     "rows": [[_jsonable(v) for v in row] for row in df.head(preview if kind != "reports" else len(df)).itertuples(index=False)]}
    return out


def db_file() -> tuple[bytes, str]:
    """DB 전체를 SQLite 파일 바이트로. (내용, 파일 이름)"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    name = f"consulting_{stamp}.db"
    if not db.using_supabase():
        return config.DB_PATH.read_bytes(), name
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(tmp)
    try:
        db.db_adapter.export_to_sqlite(db.db_schema.SCHEMA, tmp, db.db_schema.SQLITE_DDL, db.db_schema.TABLES)
        with open(tmp, "rb") as f:
            data = f.read()
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    log.info("DB 파일 만듦: %d bytes", len(data))
    return data, name


# ---------------------------------------------------------------- 신규 농가
class FarmError(ValueError):
    pass


def find_duplicate(conn, name: str, code: str) -> dict | None:
    name, code = name.strip(), code.strip()
    if not name and not code:
        return None
    for r in conn.execute("SELECT id, farm_name, owner_name, region, farm_code FROM farms ORDER BY id DESC").fetchall():
        if (name and (r[1] or "").strip() == name) or (code and (r[4] or "").strip() == code):
            return {"id": r[0], "name": r[1], "owner": r[2] or "", "region": r[3] or "", "code": r[4] or ""}
    return None


def create_farm(conn, d: dict, now: datetime | None = None) -> int:
    name = d["name"].strip()
    if not name:
        raise FarmError("농가명을 넣어주세요.")
    member_type = d.get("member_type", "조합원")
    # 번호를 비우면 자동 번호: 조합원 F+숫자, 비조합원 N+숫자 (비조합원은 조합원번호가 없는 게 정상)
    code = d.get("code", "").strip() or f"{'N' if member_type == '비조합원' else 'F'}{int((now or datetime.now()).timestamp()) % 10000}"
    try:
        new_id = conn.execute("""INSERT INTO farms (farm_code, farm_name, owner_name, region, breeding_type, total_heads, member_type)
                                 VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                              (code, name, d.get("owner", "").strip(), d.get("region", "").strip(), d["breeding_type"], int(d["total_heads"]), member_type)).fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        if "UNIQUE" in str(e).upper():
            raise FarmError(f"조합원번호 '{code}'가 이미 다른 농가에 등록되어 있어 저장하지 못했습니다. 별개의 농가라면 조합원번호를 다르게 넣어주세요.") from None
        raise
    log.info("신규 농가 등록: %s (id %s)", code, new_id)
    return new_id


def region_from_surveys(conn) -> dict:
    """기존 앱처럼 농가 지역은 조사표에 적힌 가장 최근(조사일 기준) 지역으로 보여 준다. {농가ID: 지역}"""
    import json
    out = {}
    for fid, s in conn.execute("""SELECT v.farm_id, fs.survey_data FROM visits v JOIN field_surveys fs ON v.id = fs.visit_id
                                  WHERE fs.survey_data IS NOT NULL ORDER BY v.visit_date ASC""").fetchall():
        try:
            d = json.loads(s)
        except (TypeError, ValueError):
            continue
        if isinstance(d, dict) and d.get("region"):
            out[fid] = d["region"]
    return out
