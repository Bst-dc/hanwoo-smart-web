"""AI 리포트에 넣을 데이터 모으기 — 기존 앱 메뉴 4(3단계 · AI 리포트)와 같은 계산.

- 성별(거세우·암소)마다: 전체 통계(SQL 그대로), 연도별 추이·등급 분포, 수익성 추정
- 농가의 마지막 방문 조사표
기존 앱과 다르게 한 곳: 조사표 안쪽(survey_data)의 영문 키도 한글 라벨로 바꾼다.
(기존 앱은 바깥 키만 바꿔서, 의도와 달리 조사 항목이 영문 키 그대로 Claude 에 들어갔다)
"""
import json
import logging
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

import pandas as pd

from .. import national_stats
from . import ekape

log = logging.getLogger("consulting.report_data")

YEAR_SPAN = 4                                          # 올해 포함 최근 몇 개 연도를 리포트에 넣는가 (기존 앱 PRINT_REPORT_YEARS 는 2023~2026 고정이었다)
GENDERS = [("거세", "거세우"), ("암", "암소")]
EUMSEONG_PRICES_2025 = {"1++": 23038, "1+": 19590, "1": 18165, "2": 14969, "3": 12735, "등외": 10000}

SURVEY_FIELD_LABELS = {
    "investigator": "조사자 성명", "visitDate": "조사일자",
    "memberName": "조합원명", "memberId": "조합원번호",
    "region": "지역", "farmType": "전업여부", "bizGoal": "농가 경영 목표(출하 전략)",
    "dailyAvgTemp": "연평균기온(℃)", "highTemp": "최고기온(℃)", "lowTemp": "최저기온(℃)",
    "annualPrecip": "평균강수량(연간, mm)", "avgWindSpeed": "평균풍속(m/s)", "avgHumidity": "평균상대습도(%)",
    "breedingType": "사육형태",
    "fatteningPenSize": "비육우방 크기", "fatteningPenDensity": "비육우방 밀도",
    "breedingPenSize": "번식우방 크기", "breedingPenDensity": "번식우방 밀도",
    "calfPenSize": "송아지우방 크기", "calfPenDensity": "송아지우방 밀도",
    "bulkBin": "벌크빈 보유", "autoFeeder": "자동급이시설", "tmr": "TMR 급여", "selfMix": "자가배합",
    "castrationAge": "거세시기(개월)", "castrationMethod": "거세방법",
    "floorCondition": "축사바닥 상태", "dewormingCount": "정기구충(회/년)",
    "waterQuality": "음수(물) 관리 실태", "manureScore": "소 분변 상태",
    "troughCleaning": "사조(밥통) 매일 청소 및 잔량 폐기 여부",
    "feedOrder": "급여순서", "feedFrequency": "급여횟수(회/일)", "forageQuality": "조사료 품질(질) 평가",
    "feed_matrix": "성장단계별(송아지/육성우/비육전기/비육후기/번식우) 배합사료·조사료·첨가제 급여 현황",
    "countCow": "번식우(암소) 두수", "countSteer": "거세우 두수", "countGrowing": "육성우 두수",
    "countCalf": "송아지 두수", "countOptimal": "적정 사육두수",
    "aiMethod": "인공수정 방법", "calvingInterval": "평균 분만간격(개월)", "mortalityRate": "최근 1년 폐사율(%)",
    "weaningAge": "송아지 이유 월령", "artificialRearing": "인공포유 여부",
    "consultingNotes": "현장 점검 소견 및 컨설팅사항",
}

STATS_SQL = """
SELECT
    COUNT(id) as total_count,
    ROUND(AVG(carcass_weight), 1) as avg_weight,
    ROUND(AVG(bms), 1) as avg_bms,
    ROUND(AVG(backfat), 1) as avg_backfat,
    ROUND(AVG(ribeye), 1) as avg_ribeye,
    ROUND(AVG(month_age), 1) as avg_month_age,
    ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as rate_1plus_above,
    ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as rate_c_grade
FROM shipment_records WHERE farm_id = ? AND gender = ?
"""


def relabel(d):
    if not isinstance(d, dict):
        return d
    return {SURVEY_FIELD_LABELS.get(k, k): v for k, v in d.items()}


def _frame(conn, sql, params) -> pd.DataFrame:
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description]
    df = pd.DataFrame([tuple(r) for r in cur.fetchall()], columns=cols)
    for c in cols:
        if c not in ("grade_quality", "grade_yield"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _r1(x):
    """기존 앱처럼 pandas 평균(numpy 값)을 numpy 방식으로 반올림한다. 파이썬 round(float) 와는 12.95 같은 값에서 0.1 차이가 난다."""
    return None if x is None or pd.isna(x) else float(round(x, 1))


def report_years(today: date | None = None) -> list[int]:
    """리포트에 넣을 연도: 올해를 끝으로 최근 YEAR_SPAN 개 (오름차순). 성적이 없는 해는 yearly_breakdown 이 건너뛴다."""
    end = (today or date.today()).year
    return list(range(end - YEAR_SPAN + 1, end + 1))


def yearly_breakdown(conn, farm_id, gender, stats, years=None) -> list[dict]:
    df =_frame(conn, """SELECT slaughter_year, carcass_weight, bms, backfat, ribeye, month_age, grade_quality, grade_yield
                         FROM shipment_records WHERE farm_id = ? AND gender = ?""", (farm_id, gender))
    nat = stats.get(gender, {})
    out = []
    for year in (years or report_years()):
        y = df[df["slaughter_year"] == year]
        n = len(y)
        if n == 0:
            continue
        avg = lambda col: _r1(y[col].mean()) if y[col].notna().any() else None   # noqa: E731
        q = {g: round((y["grade_quality"] == g).sum() * 100.0 / n, 1) for g in ["1++", "1+", "1", "2", "3"]}
        q["1+이상"] = round(y["grade_quality"].isin(["1++", "1+"]).sum() * 100.0 / n, 1)
        yp = {g: round((y["grade_yield"] == g).sum() * 100.0 / n, 1) for g in ["A", "B", "C"]}
        out.append({
            "year": year, "head_count": n,
            "carcass_weight_kg": {"농가": avg("carcass_weight"), "전국": nat.get("도체중", {}).get(year)},
            "bms": {"농가": avg("bms"), "전국": nat.get("BMS", {}).get(year)},
            "backfat_mm": {"농가": avg("backfat"), "전국": nat.get("등지방", {}).get(year)},
            "ribeye_cm2": {"농가": avg("ribeye"), "전국": nat.get("단면적", {}).get(year)},
            "month_age": {"농가": avg("month_age"), "전국": nat.get("출하월령", {}).get(year)},
            "grade_quality_pct": {"농가": q, "전국": nat.get("grade_quality", {}).get(year)},
            "grade_yield_pct": {"농가": yp, "전국": nat.get("grade_yield", {}).get(year)},
        })
    return out


# 음성공판장(도축장 0905) 등급별 경락단가 — 축평원 조회, 연도별 24시간 캐시 (실패는 캐시하지 않음)
_price_cache: dict = {}


def eumseong_prices(year, get=None):
    key = ekape.api_key()
    if not key or not year:
        return None
    hit = _price_cache.get(year)
    if hit and time.time() - hit[0] < 86400:
        return hit[1]
    try:
        url = (f"http://data.ekape.or.kr/openapi-data/service/user/grade/auct/cattle"
               f"?startYmd={year}0101&endYmd={year}1231&qgradeYn=Y&ServiceKey={key}")
        xml = get(url) if get else urllib.request.urlopen(url, timeout=8).read()
        grade_map = {"1++": "1++", "1+": "1+", "1": "1", "2": "2", "3": "3", "D": "등외"}
        prices = {}
        for item in ET.fromstring(xml).findall(".//item"):
            grade = grade_map.get(item.findtext("gradeNm"))
            try:
                amt, cnt = float(item.findtext("c_0905Amt")), int(item.findtext("c_0905Cnt"))
            except (TypeError, ValueError):
                continue
            if grade and cnt > 0:
                prices[grade] = amt
    except Exception as e:
        log.warning("음성공판장 경락단가 조회 실패 (%s년): %s", year, e)
        return None
    if prices:
        _price_cache[year] = (time.time(), prices)
    return prices or None


def profit_estimate(conn, farm_id, gender, stats, prices=None) -> dict:
    """기존 앱 build_ai_report_profit_estimate 와 같다. prices 를 주면 축평원을 묻지 않는다(시험용)."""
    df = _frame(conn, "SELECT carcass_weight, grade_quality, price_per_kg, total_price FROM shipment_records WHERE farm_id = ? AND gender = ?",
                (farm_id, gender))
    n = len(df)
    if n == 0:
        return {}
    nat_year = national_stats.latest_year(stats, gender)
    nat = stats.get(gender, {})
    nat_w = nat.get("도체중", {}).get(nat_year) if nat_year else None
    nat_grade = nat.get("grade_quality", {}).get(nat_year, {}) if nat_year else {}
    farm_w = _r1(df["carcass_weight"].mean()) if df["carcass_weight"].notna().any() else None

    live = prices if prices is not None else eumseong_prices(nat_year)
    if live:
        table = {**EUMSEONG_PRICES_2025, **live}
        basis = f"음성공판장(도축장코드 0905) {nat_year}년 육질등급별 실시간 경락단가 (축평원 OpenAPI)"
    else:
        table = EUMSEONG_PRICES_2025
        basis = "음성공판장 2025년 육질등급별 낙찰가 (EUMSEONG_PRICES_2025 고정값, 실시간 API 조회 실패로 대체 사용)"

    real = df[df["total_price"].notna() & (df["total_price"] > 0)]
    if len(real) >= max(3, n * 0.5):
        farm_rev = real["total_price"].mean()
        method = "실측 두당 정산액(shipment_records.total_price) 평균"
    else:
        counts = df["grade_quality"].value_counts()
        per_kg = sum(table.get(g, table["등외"]) * c for g, c in counts.items()) / n
        farm_rev = (farm_w * per_kg) if (farm_w and per_kg) else None
        method = f"{basis} × 농가 등급분포 가중평균 추정 (실제 두당 정산액 데이터 없음)"

    nat_rev = None
    if nat_w and nat_grade:
        nat_per_kg = sum(table[g] * (p / 100.0) for g, p in nat_grade.items() if g in table)
        nat_rev = nat_w * nat_per_kg if nat_per_kg else None

    out = {"계산_방식": method, "가격_기준": basis, "national_base_year": nat_year, "head_count": n}
    if farm_rev is not None and nat_rev is not None:
        diff = round(farm_rev - nat_rev)
        out.update({"farm_revenue_per_head_est": int(round(farm_rev)), "national_revenue_per_head_est": int(round(nat_rev)),
                    "diff_revenue_per_head": diff, "total_diff_revenue": diff * n})
    return out


def gender_data(conn, farm_id, stats, prices=None, years=None) -> dict:
    out = {}
    for gkey, glabel in GENDERS:
        row = conn.execute(STATS_SQL, (farm_id, gkey)).fetchone()
        if not row or not row[0]:
            continue                         # 그 성별 출하가 없으면 통째로 뺀다 (없는 데이터를 지어내지 않게)
        s = {k: row[i] for i, k in enumerate(["total_count", "avg_weight", "avg_bms", "avg_backfat", "avg_ribeye",
                                               "avg_month_age", "rate_1plus_above", "rate_c_grade"])}
        profit = profit_estimate(conn, farm_id, gkey, stats, prices)
        ny = national_stats.latest_year(stats, gkey)
        nat_w = stats.get(gkey, {}).get("도체중", {}).get(ny) if ny else None
        if s["avg_weight"] is not None and nat_w:
            profit["diff_weight_per_head_kg"] = round(s["avg_weight"] - nat_w, 1)
        out[glabel] = {"shipment_stats": s, "yearly_breakdown": yearly_breakdown(conn, farm_id, gkey, stats, years), "profit_data": profit}
    return out


def last_visit(conn, farm_id) -> dict | None:
    r = conn.execute("""SELECT v.id, v.visit_number, v.visit_date, s.survey_data, s.consult_notes
                        FROM visits v LEFT JOIN field_surveys s ON s.visit_id = v.id
                        WHERE v.farm_id = ? ORDER BY v.visit_number DESC LIMIT 1""", (farm_id,)).fetchone()
    if r is None:
        return None
    d = {"id": r[0], "visit_number": r[1], "visit_date": r[2], "survey_data": r[3], "consult_notes": r[4]}
    if isinstance(d["survey_data"], str):
        try:
            d["survey_data"] = json.loads(d["survey_data"])
        except ValueError:
            pass
    return d


def survey_for_prompt(visit: dict | None) -> dict:
    if not visit:
        return {}
    d = dict(visit)
    d["survey_data"] = relabel(d.get("survey_data"))
    return relabel(d)
