"""전국 평균 통계 — streamlit_app.py 섹션 3 을 옮긴 것.

내장값(NATIONAL_STATS_BASE) 위에 KOSIS 최신값을 덮어쓰고(24시간 캐시), 마지막에 수동 보정을 적용한다.
기존 앱과 같은 순서·규칙이다. KOSIS 키가 없거나 호출이 실패하면 내장값만 쓴다.
"""
import copy
import json
import logging
import threading
import time
import urllib.request
from datetime import datetime

from .. import config

log = logging.getLogger(__name__)

NATIONAL_STATS_BASE = {
    "거세": {
        "도체중": {2023: 467.0, 2024: 470.6, 2025: 478.1, 2026: 490.4},
        "BMS": {2023: 6.2, 2024: 6.2, 2025: 6.3, 2026: 7.0},
        "등지방": {2023: 12.7, 2024: 12.3, 2025: 12.4, 2026: 12.5},
        "단면적": {2023: 97.7, 2024: 97.6, 2025: 100.3, 2026: 106.7},
        "출하월령": {2023: 31.1, 2024: 31.6, 2025: 31.7, 2026: 31.7},
        "grade_quality": {
            2023: {"1++": 39.1, "1+": 30.0, "1": 22.1, "2": 7.9, "3": 0.9, "1+이상": 69.1},
            2024: {"1++": 39.1, "1+": 29.8, "1": 22.1, "2": 8.2, "3": 0.9, "1+이상": 68.9},
            2025: {"1++": 41.5, "1+": 29.9, "1": 20.7, "2": 7.1, "3": 0.8, "1+이상": 71.3},
            2026: {"1++": 45.5, "1+": 28.7, "1": 19.0, "2": 6.1, "3": 0.8, "1+이상": 74.2},
        },
        "grade_yield": {
            2023: {"A": 29.3, "B": 50.9, "C": 19.7},
            2024: {"A": 32.2, "B": 49.0, "C": 18.8},
            2025: {"A": 33.6, "B": 49.6, "C": 16.7},
            2026: {"A": 33.3, "B": 50.1, "C": 16.5},
        },
    },
    "암": {
        "도체중": {2023: 366.1, 2024: 371.0, 2025: 377.3, 2026: 393.1},
        "BMS": {2023: 4.5, 2024: 4.6, 2025: 4.7, 2026: 5.0},
        "등지방": {2023: 13.0, 2024: 12.7, 2025: 12.9, 2026: 13.1},
        "단면적": {2023: 86.3, 2024: 87.2, 2025: 88.8, 2026: 96.3},
        "출하월령": {2023: 55.7, 2024: 53.4, 2025: 53.2, 2026: 53.2},
        "grade_quality": {
            2023: {"1++": 12.2, "1+": 19.9, "1": 27.2, "2": 26.2, "3": 14.6, "1+이상": 32.1},
            2024: {"1++": 14.7, "1+": 20.7, "1": 27.5, "2": 24.6, "3": 12.6, "1+이상": 35.4},
            2025: {"1++": 15.4, "1+": 21.5, "1": 27.4, "2": 23.7, "3": 12.0, "1+이상": 36.9},
            2026: {"1++": 16.4, "1+": 22.1, "1": 28.1, "2": 22.7, "3": 10.6, "1+이상": 38.5},
        },
        # 2026년 육량등급은 아직 확정 통계연보가 없어 비워 둔다 (기존 앱 주석 참고).
        "grade_yield": {
            2023: {"A": 26.6, "B": 52.6, "C": 20.4},
            2024: {"A": 28.7, "B": 51.3, "C": 19.6},
            2025: {"A": 29.1, "B": 51.3, "C": 19.2},
        },
    },
}

KOSIS_TTL = 24 * 60 * 60
_kosis_cache = {"at": 0.0, "data": None}
_kosis_lock = threading.Lock()


def _kosis_url(item_id, table_id):
    key = config.secret("KOSIS_API_KEY")
    return (
        "https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
        f"&apiKey={key}&itmId={item_id}+&objL1=ALL&objL2=ALL&objL3=ALL&objL4=&objL5=&objL6=&objL7=&objL8="
        "&format=json&jsonVD=Y&prdSe=Y&newEstPrdCnt=10"
        "&outputFields=TBL_NM+OBJ_NM+NM+ITM_NM+UNIT_NM+PRD_SE+PRD_DE+LST_CHN_DE+"
        f"&orgId=323&tblId={table_id}"
    )


def fetch_kosis_national_stats():
    """기존 fetch_kosis_national_stats() 와 같은 계산. 키가 없거나 결과가 비면 None."""
    new_stats = {"거세": {}, "암": {}, "수": {}}
    if not config.secret("KOSIS_API_KEY"):
        return None

    # 1. 도체성적 상세 (도체중, BMS, 등지방, 단면적)
    metric_map = {"도체중": "도체중", "근내지방": "BMS", "등지방": "등지방", "등심면적": "단면적"}
    try:
        with urllib.request.urlopen(_kosis_url("13103112721T1", "DT_APGS_011"), timeout=10) as r:
            rows = json.loads(r.read().decode("utf-8"))
        for row in rows:
            if row.get("C1_NM") != "한우" or row.get("C2_NM") not in new_stats:
                continue
            try:
                year, val = int(row.get("PRD_DE")), float(row.get("DT", 0))
            except (TypeError, ValueError):
                continue
            mm = metric_map.get(row.get("C3_NM"))
            if mm:
                new_stats[row["C2_NM"]].setdefault(mm, {})[year] = round(val, 1)
    except Exception as e:
        log.warning("KOSIS 도체성적 조회 실패 — 내장값 사용: %s", type(e).__name__)

    # 2. 등급 판정 두수 → 출현율
    try:
        with urllib.request.urlopen(_kosis_url("13103112713T1", "DT_APGS_002"), timeout=10) as r:
            rows = json.loads(r.read().decode("utf-8"))
        grade_counts = {}
        for row in rows:
            gender = row.get("C2_NM")
            if row.get("C1_NM") != "한우" or gender not in new_stats:
                continue
            try:
                year, val = int(row.get("PRD_DE")), float(row.get("DT", 0))
            except (TypeError, ValueError):
                continue
            grade_str = row.get("C3_NM") or ""
            counts = grade_counts.setdefault(year, {"거세": {}, "암": {}, "수": {}})[gender]
            if grade_str == "전체":
                counts["total"] = val
            elif len(grade_str) >= 2 and grade_str not in ["등외", "D"]:
                q_grade, y_grade = grade_str[:-1], grade_str[-1]   # "1++A" → "1++", "A"
                counts[q_grade] = counts.get(q_grade, 0) + val
                counts[y_grade] = counts.get(y_grade, 0) + val
        for year, genders in grade_counts.items():
            for gender, counts in genders.items():
                total = counts.get("total", 0)
                if total > 0:
                    gq = {q: round(counts.get(q, 0) / total * 100, 1) for q in ["1++", "1+", "1", "2", "3"]}
                    gq["1+이상"] = round((counts.get("1++", 0) + counts.get("1+", 0)) / total * 100, 1)
                    new_stats[gender].setdefault("grade_quality", {})[year] = gq
                    new_stats[gender].setdefault("grade_yield", {})[year] = {
                        y: round(counts.get(y, 0) / total * 100, 1) for y in ["A", "B", "C"]}
    except Exception as e:
        log.warning("KOSIS 등급 출현율 조회 실패 — 내장값 사용: %s", type(e).__name__)

    return new_stats if any(new_stats.values()) else None


def _kosis_cached():
    with _kosis_lock:
        if time.time() - _kosis_cache["at"] > KOSIS_TTL:
            _kosis_cache["data"] = fetch_kosis_national_stats()
            _kosis_cache["at"] = time.time()
            log.info("KOSIS 전국 통계 %s", "갱신" if _kosis_cache["data"] else "없음(내장값 사용)")
        return _kosis_cache["data"]


def national_stats() -> dict:
    """내장값 + KOSIS 최신값 + 수동 보정. 호출마다 새 사본을 돌려준다(호출한 쪽이 고쳐도 안전)."""
    stats = copy.deepcopy(NATIONAL_STATS_BASE)
    live = _kosis_cached()
    if live:
        for gender, metrics in live.items():
            if gender in stats:
                for metric, years_data in metrics.items():
                    stats[gender].setdefault(metric, {}).update(years_data)
    # 사용자 수동 보정 (요청사항: 26년 전국 BMS 6.5)
    if "BMS" in stats.get("거세", {}):
        stats["거세"]["BMS"][2026] = 6.5
    return stats


def nat_latest_year(stats, gender_key, metric="도체중"):
    """해당 성별·지표의 가장 최근 연도(올해 이하). 없으면 None."""
    years = [y for y in stats.get(gender_key, {}).get(metric, {}) if isinstance(y, int) and y <= datetime.now().year]
    return max(years) if years else None


def metric_by_year(stats, gender_key, year):
    """대시보드 지표 이름 → 그 해 전국값. 없는 값은 None (암소는 육량등급 통계가 없는 해가 있다)."""
    g = stats.get(gender_key, {})
    return {
        "carcass_weight": g.get("도체중", {}).get(year),
        "bms": g.get("BMS", {}).get(year),
        "ribeye": g.get("단면적", {}).get(year),
        "backfat": g.get("등지방", {}).get(year),
        "plus1_rate": g.get("grade_quality", {}).get(year, {}).get("1+이상"),
        "c_rate": g.get("grade_yield", {}).get(year, {}).get("C"),
        "month_age": g.get("출하월령", {}).get(year),
    }
