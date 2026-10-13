"""종합 현황 대시보드 계산 — 기존 앱(streamlit_app.py '메뉴 1: 종합 현황 대시보드')과 같은 SQL·같은 규칙.

SQL 공식은 기존 앱에서 그대로 옮겼다 (ROUND(AVG(..), 1), 1+ 이상 출현율 등). 바꾸면 두 앱의 숫자가 달라지므로
tests/test_dashboard.py 와 기존 앱 SQL 대조(개발 때 실제 DB 로 확인)가 같이 깨진다.
"""
from datetime import datetime

from .. import national_stats

START_YEAR = 2023

# (키, 화면 이름, 전국 통계 안의 이름, 전국 통계 꺼내는 방식)
TREND_METRICS = [
    ("carcass_weight", "도체중 (kg)"),
    ("bms", "BMS"),
    ("ribeye", "단면적 (㎠)"),
    ("backfat", "등지방 (mm)"),
    ("q1plus", "1+ 이상 출현율 (%)"),
    ("c_grade", "C등급 출현율 (%)"),
    ("month_age", "출하월령 (개월)"),
]

YEARLY_SQL = f"""
SELECT
    slaughter_year AS year,
    COUNT(DISTINCT farm_id) AS farms,
    COUNT(id) AS heads,
    ROUND(AVG(carcass_weight), 1) AS carcass_weight,
    ROUND(AVG(bms), 1) AS bms,
    ROUND(AVG(ribeye), 1) AS ribeye,
    ROUND(AVG(backfat), 1) AS backfat,
    ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS q1plus,
    ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS c_grade,
    ROUND(AVG(month_age), 1) AS month_age
FROM shipment_records
WHERE gender = ? AND slaughter_year BETWEEN {START_YEAR} AND ?
GROUP BY slaughter_year
ORDER BY slaughter_year ASC
"""

COMPARE_SQL = """
SELECT
    gender AS gender,
    COUNT(id) AS heads,
    ROUND(AVG(carcass_weight), 1) AS carcass_weight,
    ROUND(AVG(bms), 1) AS bms,
    ROUND(AVG(ribeye), 1) AS ribeye,
    ROUND(AVG(backfat), 1) AS backfat,
    ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS q1plus,
    ROUND(AVG(month_age), 1) AS month_age
FROM shipment_records
GROUP BY gender
ORDER BY gender
"""

ONE_PLUS_SQL = ("SELECT ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(*), 1) "
                "FROM shipment_records WHERE gender=?")

MISSING_SURVEY_SQL = """
    SELECT f.farm_name FROM farms f
    WHERE EXISTS (SELECT 1 FROM shipment_records s WHERE s.farm_id = f.id)
    AND NOT EXISTS (
        SELECT 1 FROM visits v
        JOIN field_surveys fs ON fs.visit_id = v.id
        WHERE v.farm_id = f.id AND fs.survey_data IS NOT NULL
    )
"""

MISSING_SHIPMENT_SQL = """
    SELECT f.farm_name FROM farms f
    WHERE EXISTS (
        SELECT 1 FROM visits v
        JOIN field_surveys fs ON fs.visit_id = v.id
        WHERE v.farm_id = f.id AND fs.survey_data IS NOT NULL
    )
    AND NOT EXISTS (SELECT 1 FROM shipment_records s WHERE s.farm_id = f.id)
"""


def _num(v):
    """DB 숫자(Decimal·정수·실수)를 JSON 으로 보낼 수 있게 float 로. 없으면 None."""
    return None if v is None else float(v)


def _nat_series(nat_g: dict, key: str, years: list[int]):
    """연도 목록에 맞춘 전국 평균 값 목록 (없는 연도는 None). 기존 앱의 nat_map 과 같은 매핑."""
    if key == "q1plus":
        return [(nat_g.get("grade_quality", {}).get(y) or {}).get("1+이상") for y in years]
    if key == "c_grade":
        return [(nat_g.get("grade_yield", {}).get(y) or {}).get("C") for y in years]
    name = {"carcass_weight": "도체중", "bms": "BMS", "ribeye": "단면적", "backfat": "등지방", "month_age": "출하월령"}[key]
    return [nat_g.get(name, {}).get(y) for y in years]


def build(conn, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    nat, source = national_stats.get()
    one = lambda sql, *p: conn.execute(sql, p).fetchone()[0]

    kpi = {
        "farms": one("SELECT COUNT(*) FROM farms"),
        "visits": one("SELECT COUNT(*) FROM visits"),
        "shipments": one("SELECT COUNT(*) FROM shipment_records"),
        "missing_survey": [r[0] for r in conn.execute(MISSING_SURVEY_SQL).fetchall()],
        "missing_shipment": [r[0] for r in conn.execute(MISSING_SHIPMENT_SQL).fetchall()],
    }

    def one_plus(gender: str) -> dict:
        value = _num(one(ONE_PLUS_SQL, gender)) or 0.0           # 기존 앱: 값이 없거나 0 이면 0.0
        # 기준 연도는 1년치가 다 채워진 작년 (올해는 누계라 연중에 변함). 작년 값이 없으면 가장 최근 연도.
        gq = nat.get(gender, {}).get("grade_quality", {})
        base_year = now.year - 1
        if not isinstance(gq.get(base_year), dict):
            base_year = national_stats.latest_year(nat, gender, "grade_quality")
        nat_val = (gq.get(base_year) or {}).get("1+이상") if base_year else None
        return {"value": value, "national": nat_val, "base_year": base_year if nat_val is not None else None,
                "delta": None if nat_val is None else round(value - nat_val, 1)}

    kpi["steer_1plus"] = one_plus("거세")
    kpi["cow_1plus"] = one_plus("암")

    years = list(range(START_YEAR, now.year + 1))
    genders = {}
    for g in ("거세", "암"):
        rows = conn.execute(YEARLY_SQL, (g, now.year)).fetchall()
        by_year = {int(r["year"]): {k: _num(r[k]) for k in r.keys() if k != "year"} for r in rows}
        for v in by_year.values():                                      # 정수 두수는 정수로
            v["farms"] = int(v["farms"] or 0)
            v["heads"] = int(v["heads"] or 0)
        nat_g = nat.get(g, {})
        genders[g] = {
            "rows": [{"year": y, **by_year[y]} for y in years if y in by_year],
            "series": {key: {"farm": [by_year.get(y, {}).get(key) for y in years], "national": _nat_series(nat_g, key, years)}
                       for key, _ in TREND_METRICS},
        }

    compare = []
    for r in conn.execute(COMPARE_SQL).fetchall():
        compare.append({"gender": r["gender"], "heads": int(r["heads"]),
                        **{k: _num(r[k]) for k in ("carcass_weight", "bms", "ribeye", "backfat", "q1plus", "month_age")}})

    return {
        "kpi": kpi,
        "trend": {"years": years, "metrics": [{"key": k, "label": label} for k, label in TREND_METRICS], "genders": genders},
        "compare": compare,
        "national_source": source,
    }
