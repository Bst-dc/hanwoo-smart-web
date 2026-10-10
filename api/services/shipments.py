"""출하성적 저장·엑셀 적재·전국 1:1 비교 — streamlit_app.py '메뉴 2: 1단계' 를 옮긴 것.

계산식과 저장 규칙은 기존 앱과 같게 두었다(숫자 대조: tests/check_api_parity.py).
pandas 를 쓰는 부분(엑셀 읽기)은 기존과 같은 결과가 나오도록 그대로 pandas 로 둔다.
"""
import io
import logging
import math

import pandas as pd

from . import national_stats as ns
from .ekape import normalize_animal_no

log = logging.getLogger(__name__)

UPSERT_EKAPE_SQL = """
    INSERT INTO shipment_records (
        farm_id, animal_no, gender, slaughter_date, slaughter_year, month_age,
        carcass_weight, grade_quality, grade_yield, bms, backfat, ribeye, price_per_kg, total_price, data_source
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ekape_api')
    ON CONFLICT(animal_no) DO UPDATE SET
        farm_id = excluded.farm_id, gender = excluded.gender, slaughter_date = excluded.slaughter_date,
        slaughter_year = excluded.slaughter_year, month_age = excluded.month_age,
        carcass_weight = excluded.carcass_weight, grade_quality = excluded.grade_quality,
        grade_yield = excluded.grade_yield, bms = excluded.bms, backfat = excluded.backfat,
        ribeye = excluded.ribeye, price_per_kg = excluded.price_per_kg,
        total_price = excluded.total_price, data_source = excluded.data_source
"""
# 엑셀엔 단가·금액이 없으므로 이미 있는 행의 price_per_kg/total_price 는 건드리지 않는다
UPSERT_EXCEL_SQL = """
    INSERT INTO shipment_records (
        farm_id, animal_no, gender, slaughter_date, slaughter_year, month_age,
        carcass_weight, grade_quality, grade_yield, bms, backfat, ribeye, data_source
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'excel')
    ON CONFLICT(animal_no) DO UPDATE SET
        farm_id = excluded.farm_id, gender = excluded.gender, slaughter_date = excluded.slaughter_date,
        slaughter_year = excluded.slaughter_year, month_age = excluded.month_age,
        carcass_weight = excluded.carcass_weight, grade_quality = excluded.grade_quality,
        grade_yield = excluded.grade_yield, bms = excluded.bms, backfat = excluded.backfat,
        ribeye = excluded.ribeye, data_source = excluded.data_source
"""


def _present(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))


# ---------------------------------------------------------------- 이력제 조회분 저장
def save_ekape_records(conn, farm_id: int, records: list[dict]) -> int:
    """검토를 마친 조회 결과를 저장한다. 이력번호가 이미 있으면 새 값으로 고친다
    (다른 농가에 있던 개체면 이 농가로 옮겨진다 — 기존과 같음). 저장한 두수를 돌려준다."""
    saved = 0
    for row in records:
        ano = normalize_animal_no(row.get("animal_no"))
        if not ano:          # 표에 빈 행을 추가만 하고 비워 둔 경우
            continue
        sdate = row.get("slaughter_date")
        sdate = str(sdate) if isinstance(sdate, str) and sdate.strip() else "2025-01-01"
        try:
            syear = int(sdate[:4])
        except ValueError:
            syear = 2025
        cw = row.get("carcass_weight")
        cw = cw if _present(cw) and cw else 0
        cost = row.get("costAmt")
        cost = cost if _present(cost) and cost else 0
        total_price = int(cw * cost)
        # 축평원 판정 성별을 쓴다. 응답에 성별이 없을 때만 거세로 간주
        gender = row.get("gender")
        gender = gender if isinstance(gender, str) and gender.strip() else "거세"
        conn.execute(UPSERT_EKAPE_SQL, (
            farm_id, ano, gender.strip(), sdate, syear, row.get("month_age"),
            row.get("carcass_weight"), row.get("grade_quality"), row.get("grade_yield"), row.get("bms"),
            row.get("backfat"), row.get("ribeye"), cost, total_price,
        ))
        saved += 1
    return saved


# ---------------------------------------------------------------- 엑셀
EXCEL_COLS = {
    "이력번호": ["이력번호", "개체번호", "개체식별번호"],
    "성별": ["성별", "구분"],
    "도축일자": ["도축일자", "출하일자"],
    "도체중": ["도체중", "도체중량"],
    "육질등급": ["육질등급"],
    "육량등급": ["육량등급"],
    "BMS": ["근내지방도", "BMS"],
    "등지방": ["등지방두께", "등지방"],
    "단면적": ["등심단면적", "단면적"],
    "월령": ["도축개월령", "출하월령"],
}
NAME_COLS = ["농가명", "조합원명", "성명", "대표자명"]


def read_excel(data: bytes) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(data))


def _find_col(df, keys):
    return next((k for k in keys if k in df.columns), None)


def excel_preview(df: pd.DataFrame, farm_name: str) -> dict:
    """저장 전에 보여 줄 것: 행 수, 파일 안 이름과 선택 농가가 다른지, 저장되지 않거나 기본값이 들어갈 행 수."""
    name_col = _find_col(df, NAME_COLS)
    mismatched = []
    if name_col:
        file_names = {str(v).strip() for v in df[name_col].dropna().unique() if str(v).strip()}
        mismatched = sorted(file_names - {str(farm_name).strip()})
    no_col = _find_col(df, EXCEL_COLS["이력번호"])
    date_col = _find_col(df, EXCEL_COLS["도축일자"])
    skipped = missing_date = 0
    for _, row in df.iterrows():
        ano = normalize_animal_no(row.get(no_col)) if no_col else ""
        if not ano or len(ano) < 8:
            skipped += 1
            continue
        # save_excel 과 같은 방식으로 날짜를 읽어 보고, 연도를 못 읽으면 2025 로 들어가는 행으로 센다
        sdate = str(row.get(date_col, "2025-01-01"))[:10] if date_col else None
        try:
            int(sdate[:4])
        except (TypeError, ValueError):
            missing_date += 1
    return {
        "rows": len(df),
        "columns": [str(c) for c in df.columns],
        "animal_no_column": no_col,
        "name_column": name_col,
        "mismatched_names": mismatched,
        "will_skip": skipped,                 # 이력번호가 없거나 8자 미만이라 건너뛸 행
        "missing_date": missing_date,         # 도축일자 칸이 없거나 읽지 못해 연도가 2025 로 들어갈 행
        "missing_columns": [k for k, keys in EXCEL_COLS.items() if _find_col(df, keys) is None],
    }


def _num(v):
    # 숫자 칸의 '-'·'' 같은 글자는 빈 값으로 (Postgres 숫자 컬럼이 거부해 업로드 전체가 실패하던 문제)
    try:
        f = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _grade_text(v):
    # 빈 칸(NaN)을 str() 하면 'nan' 이라는 글자가 등급으로 저장되던 문제 방지
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    v = str(v).strip()
    return v or None


def save_excel(conn, farm_id: int, df: pd.DataFrame) -> int:
    find = lambda k: _find_col(df, EXCEL_COLS[k])
    saved = 0
    for _, row in df.iterrows():
        ano = normalize_animal_no(row.get(find("이력번호")))
        if not ano or len(ano) < 8:
            continue
        # '거세' 가 아니면 전부 '암' 으로 저장해 수소도 암소 통계에 섞이던 문제를 고친 규칙 (기존과 같음)
        g_raw = row.get(find("성별"))
        g_raw = "" if g_raw is None or (isinstance(g_raw, float) and pd.isna(g_raw)) else str(g_raw).strip()
        if not g_raw or "거세" in g_raw:
            gender = "거세"
        elif "암" in g_raw:
            gender = "암"
        elif "수" in g_raw:
            gender = "수"
        else:
            gender = "암"
        sdate = str(row.get(find("도축일자"), "2025-01-01"))[:10]
        try:
            syear = int(sdate[:4])
        except ValueError:
            syear = 2025
        conn.execute(UPSERT_EXCEL_SQL, (
            farm_id, ano, gender, sdate, syear,
            _num(row.get(find("월령"))), _num(row.get(find("도체중"))),
            _grade_text(row.get(find("육질등급"))), _grade_text(row.get(find("육량등급"))),
            _num(row.get(find("BMS"))), _num(row.get(find("등지방"))), _num(row.get(find("단면적"))),
        ))
        saved += 1
    return saved


# ---------------------------------------------------------------- 전국 1:1 비교
STATS_SELECT = """
    SELECT
        COUNT(id) as total_count,
        ROUND(AVG(carcass_weight), 1) as avg_weight,
        ROUND(AVG(bms), 1) as avg_bms,
        ROUND(AVG(ribeye), 1) as avg_ribeye,
        ROUND(AVG(backfat), 1) as avg_backfat,
        ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as rate_1plus_above,
        ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as rate_c_grade,
        ROUND(AVG(month_age), 1) as avg_month_age
    FROM shipment_records
"""
YEARLY_SELECT = """
    SELECT slaughter_year AS year,
        ROUND(AVG(carcass_weight), 1) as carcass_weight,
        ROUND(AVG(bms), 1) as bms,
        ROUND(AVG(ribeye), 1) as ribeye,
        ROUND(AVG(backfat), 1) as backfat,
        ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as plus1_rate,
        ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as c_rate,
        ROUND(AVG(month_age), 1) as month_age
    FROM shipment_records
"""
RECORDS_SELECT = """
    SELECT animal_no, gender, slaughter_date, carcass_weight, grade_quality, grade_yield, bms, backfat, ribeye, month_age
    FROM shipment_records
"""
GENDER_CAPTION = {"거세": "거세우", "암": "암소"}
PROFIT_PER_KG = 21000   # 수익성 추정: kg 당 평균 21,000원 (기존과 같음)


def _f(v):
    return None if v is None else float(v)


def available_years(conn, farm_id):
    rows = conn.execute("""
        SELECT DISTINCT slaughter_year FROM shipment_records
        WHERE farm_id = ? AND slaughter_year IS NOT NULL
        ORDER BY slaughter_year DESC
    """, (farm_id,)).fetchall()
    return [int(r[0]) for r in rows]


def comparison(conn, farm_id: int, year: int | None, gender: str | None) -> dict:
    stats = ns.national_stats()
    years = available_years(conn, farm_id)

    # 전국 비교는 성별이 섞이면 의미가 없으므로 한 성별로만 한다.
    # '전체' 면 거세우로 비교하되, 거세우 출하가 없는 농가는 암소로 비교한다.
    cmp_gender = gender
    if not cmp_gender:
        steer_cnt = conn.execute(
            "SELECT COUNT(*) FROM shipment_records WHERE farm_id = ? AND gender = '거세'" + (" AND slaughter_year = ?" if year else ""),
            (farm_id, year) if year else (farm_id,)).fetchone()[0]
        cmp_gender = "거세" if steer_cnt > 0 else "암"

    where, params = "WHERE farm_id = ? AND gender = ?", [farm_id, cmp_gender]
    if year:
        where += " AND slaughter_year = ?"
        params.append(year)
    s = conn.execute(STATS_SELECT + where, params).fetchone()

    rec_where, rec_params = "WHERE farm_id = ?", [farm_id]
    if year:
        rec_where += " AND slaughter_year = ?"
        rec_params.append(year)
    if gender:
        rec_where += " AND gender = ?"
        rec_params.append(gender)
    rec_cols = ["animal_no", "gender", "slaughter_date", "carcass_weight", "grade_quality", "grade_yield",
                "bms", "backfat", "ribeye", "month_age"]
    numeric = {"carcass_weight", "bms", "backfat", "ribeye", "month_age"}
    records = [{c: (_f(v) if c in numeric else v) for c, v in zip(rec_cols, r)}
               for r in conn.execute(RECORDS_SELECT + rec_where + " ORDER BY slaughter_date DESC", rec_params).fetchall()]

    out = {"years": years, "cmp_gender": cmp_gender, "gender_caption": GENDER_CAPTION.get(cmp_gender, cmp_gender),
           "year": year, "total_count": int(s["total_count"]) if s else 0, "records": records}
    if not s or not s["total_count"]:
        return out

    nat = stats[cmp_gender]
    cy = year if (year and year in nat["도체중"]) else (ns.nat_latest_year(stats, cmp_gender) or 2025)
    nat_vals = {
        "carcass_weight": nat["도체중"].get(cy), "bms": nat["BMS"].get(cy), "ribeye": nat["단면적"].get(cy),
        "backfat": nat["등지방"].get(cy), "plus1_rate": nat.get("grade_quality", {}).get(cy, {}).get("1+이상"),
        "c_rate": nat.get("grade_yield", {}).get(cy, {}).get("C"), "month_age": nat["출하월령"].get(cy),
    }
    farm_vals = {"carcass_weight": s["avg_weight"], "bms": s["avg_bms"], "ribeye": s["avg_ribeye"],
                 "backfat": s["avg_backfat"], "plus1_rate": s["rate_1plus_above"], "c_rate": s["rate_c_grade"],
                 "month_age": s["avg_month_age"]}
    # (항목, 키, 좋음 문구, 나쁨 문구, 좋음 조건) — 농가값이나 전국값이 없으면 진단 '-' (0 으로 두면 '우수' 로 잘못 판정)
    spec = [
        ("도체중 (kg)", "carcass_weight", "우수 (▲)", "미흡 (▼)", lambda d: d >= 0),
        ("근내지방도 (BMS)", "bms", "우수 (▲)", "미흡 (▼)", lambda d: d >= 0),
        ("등심단면적 (㎠)", "ribeye", "우수 (▲)", "미흡 (▼)", lambda d: d >= 0),
        ("등지방두께 (mm)", "backfat", "적정", "과비주의 (과다)", lambda d: d <= 1.0),
        ("1+이상 출현율 (%)", "plus1_rate", "우수 (▲)", "개선필요", lambda d: d >= 0),
        ("C등급 출현율 (%)", "c_rate", "우수 (▼)", "개선필요 (▲)", lambda d: d <= 0),
        ("출하월령 (개월)", "month_age", "단기출하 (우수)", "지연출하", lambda d: d <= 0),
    ]
    rows = []
    for label, key, good, bad, good_if in spec:
        fv, nv = _f(farm_vals[key]), nat_vals[key]
        diff = fv - nv if (fv is not None and nv is not None) else None
        rows.append({"label": label, "key": key, "farm": fv, "national": nv, "diff": diff,
                     "verdict": "-" if diff is None else (good if good_if(diff) else bad)})

    d_w = rows[0]["diff"]
    profit = None
    if d_w is not None:
        per_head = int(d_w * PROFIT_PER_KG)
        profit = {"per_head": per_head, "total": per_head * out["total_count"], "heads": out["total_count"]}

    recent = []
    if years:
        recent_years = sorted(sorted(years, reverse=True)[:3])
        ph = ",".join("?" * len(recent_years))
        found = {int(r["year"]): r for r in conn.execute(
            YEARLY_SELECT + f"WHERE farm_id = ? AND gender = ? AND slaughter_year IN ({ph}) GROUP BY slaughter_year ORDER BY slaughter_year",
            (farm_id, cmp_gender, *recent_years)).fetchall()}
        for y in recent_years:
            r = found.get(y)
            recent.append({"year": y,
                           "farm": {k: _f(r[k]) for k in nat_vals} if r else {k: None for k in nat_vals},
                           "national": ns.metric_by_year(stats, cmp_gender, y)})

    out.update({"national_year": cy, "rows": rows, "profit": profit, "recent": recent})
    return out
