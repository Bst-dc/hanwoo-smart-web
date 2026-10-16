"""1단계 · 출하성적 비교분석(조회·분석) — 기존 앱(streamlit_app.py '메뉴 2')과 같은 SQL·같은 규칙.

농가 한 곳의 출하성적을 전국 평균과 1:1로 비교하고(진단 문구 포함), 최근 3년 추이, 수익성 추정, 개체별 성적표를 만든다.
표에 보이는 숫자 글자는 기존 앱의 f1()과 똑같이 서버에서 만든다 (JS 와 Python 의 반올림이 달라지지 않게).
"""
from datetime import datetime

from .. import national_stats

# 농가 평균을 구하는 공식 (기존 앱 stats_row 의 SQL). 성별 조건은 호출 쪽에서 붙인다.
STATS_SELECT = """
SELECT
    COUNT(id) AS total_count,
    ROUND(AVG(carcass_weight), 1) AS avg_weight,
    ROUND(AVG(bms), 1) AS avg_bms,
    ROUND(AVG(ribeye), 1) AS avg_ribeye,
    ROUND(AVG(backfat), 1) AS avg_backfat,
    ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS rate_1plus_above,
    ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS rate_c_grade,
    ROUND(AVG(month_age), 1) AS avg_month_age
FROM shipment_records
"""

YEARLY_SELECT = """
SELECT slaughter_year AS year,
    ROUND(AVG(carcass_weight), 1) AS carcass_weight,
    ROUND(AVG(bms), 1) AS bms,
    ROUND(AVG(ribeye), 1) AS ribeye,
    ROUND(AVG(backfat), 1) AS backfat,
    ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS q1plus,
    ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS c_grade,
    ROUND(AVG(month_age), 1) AS month_age
FROM shipment_records
"""

RECORDS_SELECT = """
SELECT animal_no, gender, slaughter_date, carcass_weight, grade_quality, grade_yield, bms, backfat, ribeye, month_age
FROM shipment_records
"""

TREND_METRICS = [
    ("carcass_weight", "도체중 (kg)"), ("bms", "BMS"), ("ribeye", "단면적 (㎠)"), ("backfat", "등지방 (mm)"),
    ("q1plus", "1+ 이상 출현율 (%)"), ("c_grade", "C등급 출현율 (%)"), ("month_age", "출하월령 (개월)"),
]

PRICE_PER_KG = 21000        # 음성공판장 kg당 평균 21,000원 기준 (기존 앱과 같음)


def _f1(v) -> str:
    """기존 앱 f1(): 값이 없으면 '-', 있으면 소수 첫째 자리 글자."""
    return "-" if v is None else f"{float(v):.1f}"


def _num(v):
    return None if v is None else float(v)


def _diff(a, b):
    """농가값이나 전국값이 없으면 None (예전엔 0 으로 처리돼 '우수'로 잘못 판정됐다)."""
    return None if a is None or b is None else float(a) - float(b)


def _judge(diff, good, bad, good_if=lambda d: d >= 0):
    return "-" if diff is None else (good if good_if(diff) else bad)


def _nat_value(nat_g: dict, key: str, year: int):
    if key == "q1plus":
        return (nat_g.get("grade_quality", {}).get(year) or {}).get("1+이상")
    if key == "c_grade":
        return (nat_g.get("grade_yield", {}).get(year) or {}).get("C")
    name = {"carcass_weight": "도체중", "bms": "BMS", "ribeye": "단면적", "backfat": "등지방", "month_age": "출하월령"}[key]
    return nat_g.get(name, {}).get(year)


def _flag_low_backfat(comparison, d):
    """도체중·BMS·등심단면적 중 2개 이상이 전국 평균보다 낮고 등지방도 낮으면, 등지방 행 진단을 '개선필요'로 바꾼다."""
    below = sum(1 for k in ("carcass_weight", "bms", "ribeye") if d[k] is not None and d[k] < 0)
    if below >= 2 and d["backfat"] is not None and d["backfat"] < 0:
        for c in comparison:
            if c["item"].startswith("등지방두께"):
                c["diagnosis"] = "개선필요"


def farm_info(conn, farm_id: int):
    r = conn.execute("SELECT id, farm_name, farm_code, region FROM farms WHERE id = ?", (farm_id,)).fetchone()
    if r is None:
        return None
    return {"id": r["id"], "name": r["farm_name"], "code": r["farm_code"] or "", "region": r["region"] or ""}


def build(conn, farm_id: int, year: int | None, gender: str | None, now: datetime | None = None) -> dict:
    """gender 는 None(전체) | '거세' | '암'. year 는 None(전체 누적) 또는 도축연도."""
    nat_all, source = national_stats.get()

    years = [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT slaughter_year FROM shipment_records WHERE farm_id = ? AND slaughter_year IS NOT NULL ORDER BY slaughter_year DESC",
        (farm_id,)).fetchall()]

    # 전국 비교는 성별이 섞이면 의미가 없으므로 한 성별로만 한다.
    # '전체'를 고르면 거세우로 비교하되, 거세우 출하가 없는 농가(그 연도)는 암소로 비교한다.
    cmp_gender = gender
    if not cmp_gender:
        sql = "SELECT COUNT(*) FROM shipment_records WHERE farm_id = ? AND gender = '거세'" + (" AND slaughter_year = ?" if year else "")
        steer_cnt = conn.execute(sql, (farm_id, year) if year else (farm_id,)).fetchone()[0]
        cmp_gender = "거세" if steer_cnt > 0 else "암"

    where_year = " AND slaughter_year = ?" if year else ""
    params = (farm_id, year) if year else (farm_id,)
    stats = conn.execute(STATS_SELECT + f" WHERE farm_id = ?{where_year} AND gender = ?", (*params, cmp_gender)).fetchone()

    gender_sql = " AND gender = ?" if gender else ""
    rec_rows = conn.execute(
        RECORDS_SELECT + f" WHERE farm_id = ?{where_year}{gender_sql} ORDER BY slaughter_date DESC",
        (*params, *((gender,) if gender else ()))).fetchall()
    records = [{"animal_no": r["animal_no"], "gender": r["gender"], "date": r["slaughter_date"],
                "carcass_weight": _num(r["carcass_weight"]), "grade_quality": r["grade_quality"], "grade_yield": r["grade_yield"],
                "bms": _num(r["bms"]), "backfat": _num(r["backfat"]), "ribeye": _num(r["ribeye"]), "month_age": _num(r["month_age"])}
               for r in rec_rows]

    out = {"years": years, "cmp_gender": cmp_gender, "gender_forced": not gender, "national_source": source,
           "records": records, "total_count": int(stats["total_count"] or 0)}
    if out["total_count"] == 0:
        out["has_data"] = False
        return out

    nat = nat_all[cmp_gender]
    # 비교 기준 연도: 선택한 연도에 전국 통계가 있으면 그 해, 없으면 가장 최근 연도
    cy = year if (year and year in nat.get("도체중", {})) else (national_stats.latest_year(nat_all, cmp_gender) or 2025)
    n = {k: _nat_value(nat, k, cy) for k, _ in TREND_METRICS}
    s = {"carcass_weight": stats["avg_weight"], "bms": stats["avg_bms"], "ribeye": stats["avg_ribeye"], "backfat": stats["avg_backfat"],
         "q1plus": stats["rate_1plus_above"], "c_grade": stats["rate_c_grade"], "month_age": stats["avg_month_age"]}
    d = {k: _diff(s[k], n[k]) for k in s}

    def row(label, key, good, bad, good_if=lambda x: x >= 0):
        return {"item": label, "farm": _f1(s[key]), "national": _f1(n[key]), "diff": _f1(d[key]), "diagnosis": _judge(d[key], good, bad, good_if)}

    out["has_data"] = True
    out["national_year"] = cy
    out["comparison"] = [
        row("도체중 (kg)", "carcass_weight", "우수 (▲)", "미흡 (▼)"),
        row("근내지방도 (BMS)", "bms", "우수 (▲)", "미흡 (▼)"),
        row("등심단면적 (㎠)", "ribeye", "우수 (▲)", "미흡 (▼)"),
        row("등지방두께 (mm)", "backfat", "적정", "과비주의 (과다)", lambda x: x <= 1.0),
        row("1+이상 출현율 (%)", "q1plus", "우수 (▲)", "개선필요"),
        row("C등급 출현율 (%)", "c_grade", "우수 (▼)", "개선필요 (▲)", lambda x: x <= 0),
        row("출하월령 (개월)", "month_age", "단기출하 (우수)", "지연출하", lambda x: x <= 0),
    ]
    _flag_low_backfat(out["comparison"], d)

    # 최근 3년(농가에 성적이 있는 해 기준) 추이 — 지표마다 농가 평균과 그 해 전국 평균
    recent = sorted(years, reverse=True)[:3]
    recent.sort()
    placeholders = ",".join(["?"] * len(recent))
    yearly = {int(r["year"]): r for r in conn.execute(
        YEARLY_SELECT + f" WHERE farm_id = ? AND gender = ? AND slaughter_year IN ({placeholders}) GROUP BY slaughter_year ORDER BY slaughter_year",
        (farm_id, cmp_gender, *recent)).fetchall()}
    out["trend"] = {
        "years": recent,
        "metrics": [{"key": k, "label": label} for k, label in TREND_METRICS],
        "series": {k: {"farm": [_num(yearly[y][k]) if y in yearly else None for y in recent],
                       "national": [_nat_value(nat, k, y) for y in recent]} for k, _ in TREND_METRICS},
    }
    out["trend"]["table"] = [
        {"year": y, "farm": [_f1(yearly[y][k]) if y in yearly else "-" for k, _ in TREND_METRICS],
         "national": [_f1(_nat_value(nat, k, y)) for k, _ in TREND_METRICS]} for y in recent]

    # 수익성 임팩트: 도체중 격차 × kg당 21,000원 (int() 는 0 쪽으로 자른다 — 기존 앱과 같음)
    diff_w = d["carcass_weight"]
    per_head = int(diff_w * PRICE_PER_KG) if diff_w is not None else 0
    out["profit"] = {"available": diff_w is not None, "per_head": per_head, "total": per_head * out["total_count"]}
    return out
