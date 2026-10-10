"""메뉴 1: 종합 현황 대시보드 — streamlit_app.py '메뉴 1' 의 계산을 그대로 옮겼다.

SQL 은 기존 앱과 같은 식이다. 다른 점은 0으로 나누기 방어(NULLIF) 하나뿐인데,
SQLite 는 원래 NULL 을 돌려주고 Postgres 는 오류를 내던 경우라 결과가 있는 경우의 값은 같다.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from ..auth import require_auth
from ..db import get_db
from ..models import DashboardSummary, GenderCompareRow, Plus1Rate, YearlyTrend, YearMetrics, YearRow
from ..services import national_stats as ns

router = APIRouter(prefix="/api/dashboard", tags=["종합 현황 대시보드"], dependencies=[Depends(require_auth)])

START_YEAR = 2023
PLUS1_SQL = ("SELECT ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0"
             "/NULLIF(COUNT(*), 0), 1) FROM shipment_records WHERE gender=?")

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
YEARLY_SQL = """
    SELECT
        slaughter_year AS year,
        COUNT(DISTINCT farm_id) AS farms,
        COUNT(id) AS heads,
        ROUND(AVG(carcass_weight), 1) AS carcass_weight,
        ROUND(AVG(bms), 1) AS bms,
        ROUND(AVG(ribeye), 1) AS ribeye,
        ROUND(AVG(backfat), 1) AS backfat,
        ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS plus1_rate,
        ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS c_rate,
        ROUND(AVG(month_age), 1) AS month_age
    FROM shipment_records
    WHERE gender = ? AND slaughter_year BETWEEN ? AND ?
    GROUP BY slaughter_year
    ORDER BY slaughter_year ASC
"""
COMPARE_SQL = """
    SELECT
        gender,
        COUNT(id) AS heads,
        ROUND(AVG(carcass_weight), 1) AS carcass_weight,
        ROUND(AVG(bms), 1) AS bms,
        ROUND(AVG(ribeye), 1) AS ribeye,
        ROUND(AVG(backfat), 1) AS backfat,
        ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS plus1_rate,
        ROUND(AVG(month_age), 1) AS month_age
    FROM shipment_records
    GROUP BY gender
    ORDER BY gender
"""
METRIC_KEYS = list(YearMetrics.model_fields)


def _num(v):
    return None if v is None else float(v)


def _plus1(conn, stats, gender_key) -> Plus1Rate:
    row = conn.execute(PLUS1_SQL, (gender_key,)).fetchone()
    value = float(row[0]) if row and row[0] else 0.0
    # 기준 연도는 1년치가 다 채워진 작년 통계 (올해는 누계라 연중에 계속 변함). 없으면 가장 최근 연도.
    gq = stats.get(gender_key, {}).get("grade_quality", {})
    base_year = datetime.now().year - 1
    if not isinstance(gq.get(base_year), dict):
        base_year = ns.nat_latest_year(stats, gender_key, "grade_quality")
    national = (gq.get(base_year) or {}).get("1+이상")
    if national is None:
        return Plus1Rate(value=value)
    return Plus1Rate(value=value, national=national, base_year=base_year, delta=round(value - national, 1))


@router.get("/summary", response_model=DashboardSummary)
def summary(conn=Depends(get_db)):
    count = lambda table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    stats = ns.national_stats()
    return DashboardSummary(
        total_farms=count("farms"),
        total_visits=count("visits"),
        total_shipments=count("shipment_records"),
        steer_plus1=_plus1(conn, stats, "거세"),
        cow_plus1=_plus1(conn, stats, "암"),
        farms_missing_survey=[r[0] for r in conn.execute(MISSING_SURVEY_SQL).fetchall()],
        farms_missing_shipment=[r[0] for r in conn.execute(MISSING_SHIPMENT_SQL).fetchall()],
    )


@router.get("/yearly", response_model=YearlyTrend)
def yearly(gender: str = Query("거세", pattern="^(거세|암)$"), conn=Depends(get_db)):
    """연도별 추이·집계표. 출하가 없는 해도 전국값은 채워서 돌려준다(차트의 전국선이 끊기지 않게)."""
    current_year = datetime.now().year
    found = {r["year"]: r for r in conn.execute(YEARLY_SQL, (gender, START_YEAR, current_year)).fetchall()}
    stats = ns.national_stats()
    rows = []
    for y in range(START_YEAR, current_year + 1):
        r = found.get(y)
        rows.append(YearRow(
            year=y,
            farms=r["farms"] if r else None,
            heads=r["heads"] if r else None,
            farm=YearMetrics(**{k: _num(r[k]) for k in METRIC_KEYS}) if r else YearMetrics(),
            national=YearMetrics(**ns.metric_by_year(stats, gender, y)),
        ))
    return YearlyTrend(gender=gender, rows=rows)


@router.get("/gender-compare", response_model=list[GenderCompareRow])
def gender_compare(conn=Depends(get_db)):
    """거세우 vs 암소(수소 포함) 전체 누적 평균."""
    out = []
    for r in conn.execute(COMPARE_SQL).fetchall():
        out.append(GenderCompareRow(
            gender=r["gender"] or "(미입력)", heads=r["heads"],
            **{k: _num(r[k]) for k in ["carcass_weight", "bms", "ribeye", "backfat", "plus1_rate", "month_age"]},
        ))
    return out
