"""전국 한우 도체성적 평균 — 기존 앱(streamlit_app.py 3번 구역 NATIONAL_STATS)과 같은 규칙.

1. 기본값(BASELINE): 축평원·통계청 자료를 옮겨 둔 고정값.
2. KOSIS 통계청 API 로 받은 최신 값이 있으면 같은 연도·지표를 덮어쓰고 없는 지표는 추가한다 (24시간 캐시).
3. 사용자 수동 보정: 2026년 거세우 BMS = 6.5 (요청사항).

기존 앱은 KOSIS 호출이 실패해도 말없이 기본값으로 넘어갔다. 여기서는 실패 이유를 기록(logging)하고,
화면이 "지금 보이는 전국 평균이 기본값인지 KOSIS 최신값인지" 알 수 있게 source 를 돌려준다.
"""
import copy
import json
import logging
import threading
import time
import urllib.request
from datetime import datetime

from . import config

log = logging.getLogger("consulting.national")

BASELINE = {
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
        # 2026년은 아직 확정 통계연보가 없어(연중 진행형) 비워 둠.
        "grade_yield": {
            2023: {"A": 26.6, "B": 52.6, "C": 20.4},
            2024: {"A": 28.7, "B": 51.3, "C": 19.6},
            2025: {"A": 29.1, "B": 51.3, "C": 19.2},
        },
    },
}

MANUAL_BMS_2026_STEER = 6.5


# ---------- KOSIS 응답 해석 (외부 호출과 분리해서 시험할 수 있게 순수 함수로 둔다) ----------
def parse_detail(rows) -> dict:
    """도체성적 상세(도체중·근내지방·등지방·등심면적) 행 → {성별: {지표: {연도: 값}}}"""
    out = {"거세": {}, "암": {}, "수": {}}
    metric_map = {"도체중": "도체중", "근내지방": "BMS", "등지방": "등지방", "등심면적": "단면적"}
    for row in rows:
        if row.get("C1_NM") != "한우":
            continue
        gender = row.get("C2_NM")
        if gender not in out:
            continue
        metric = row.get("C3_NM")
        try:
            year = int(row.get("PRD_DE"))
            val = float(row.get("DT", 0))
        except (TypeError, ValueError):
            continue
        if metric in metric_map:
            out[gender].setdefault(metric_map[metric], {})[year] = round(val, 1)
    return out


def parse_grades(rows) -> dict:
    """등급별 판정 두수 행 → {성별: {"grade_quality": {연도: {...}}, "grade_yield": {연도: {...}}}}"""
    counts: dict = {}
    for row in rows:
        if row.get("C1_NM") != "한우":
            continue
        gender = row.get("C2_NM")
        if gender not in ("거세", "암", "수"):
            continue
        try:
            year = int(row.get("PRD_DE"))
            val = float(row.get("DT", 0))
        except (TypeError, ValueError):
            continue
        grade = row.get("C3_NM") or ""
        by_gender = counts.setdefault(year, {"거세": {}, "암": {}, "수": {}})[gender]
        if grade == "전체":
            by_gender["total"] = val
        elif len(grade) >= 2 and grade not in ("등외", "D"):
            q_grade, y_grade = grade[:-1], grade[-1]        # "1++A" → "1++", "A"
            by_gender[q_grade] = by_gender.get(q_grade, 0) + val
            by_gender[y_grade] = by_gender.get(y_grade, 0) + val

    out = {"거세": {}, "암": {}, "수": {}}
    for year, genders in counts.items():
        for gender, c in genders.items():
            total = c.get("total", 0)
            if total <= 0:
                continue
            gq = {q: round(c.get(q, 0) / total * 100, 1) for q in ["1++", "1+", "1", "2", "3"]}
            gq["1+이상"] = round((c.get("1++", 0) + c.get("1+", 0)) / total * 100, 1)
            out[gender].setdefault("grade_quality", {})[year] = gq
            out[gender].setdefault("grade_yield", {})[year] = {y: round(c.get(y, 0) / total * 100, 1) for y in ["A", "B", "C"]}
    return out


def merge(baseline: dict, live: dict | None) -> dict:
    """기본값 위에 KOSIS 값을 덮어쓰고(같은 연도) 없는 지표는 추가한 뒤, 수동 보정을 적용한 새 사본을 돌려준다."""
    merged = copy.deepcopy(baseline)
    for gender, metrics in (live or {}).items():
        if gender not in merged:
            continue
        for metric, years_data in metrics.items():
            if metric in merged[gender]:
                merged[gender][metric].update(years_data)
            else:
                merged[gender][metric] = years_data
    if "BMS" in merged.get("거세", {}):
        merged["거세"]["BMS"][2026] = MANUAL_BMS_2026_STEER
    return merged


# ---------- KOSIS 호출 ----------
_KOSIS_URL = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey={key}&itmId={item}"
              "&objL1=ALL&objL2=ALL&objL3=ALL&objL4=&objL5=&objL6=&objL7=&objL8=&format=json&jsonVD=Y&prdSe=Y&newEstPrdCnt=10"
              "&outputFields=TBL_NM+OBJ_NM+NM+ITM_NM+UNIT_NM+PRD_SE+PRD_DE+LST_CHN_DE+&orgId=323&tblId={tbl}")


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as res:
        return json.loads(res.read().decode("utf-8"))


def fetch_live(key: str) -> tuple[dict, list[str]]:
    """KOSIS 에서 두 표를 받아 {성별: {지표: ...}} 로 돌려준다. 실패한 부분은 빼고 이유를 목록으로 같이 돌려준다."""
    live: dict = {}
    problems: list[str] = []
    for label, item, tbl, parser in (("도체성적 상세", "13103112721T1+", "DT_APGS_011", parse_detail),
                                     ("등급 판정 두수", "13103112713T1+", "DT_APGS_002", parse_grades)):
        try:
            rows = _get_json(_KOSIS_URL.format(key=key, item=item, tbl=tbl))
            if not isinstance(rows, list):
                raise ValueError(f"예상과 다른 응답: {str(rows)[:120]}")      # 키 오류 등은 {"err": ...} 로 온다
            parsed = parser(rows)
            for gender, metrics in parsed.items():
                live.setdefault(gender, {}).update(metrics)
        except Exception as e:  # noqa: BLE001 — 외부 서비스 오류는 화면을 막지 않고 기본값으로 넘어가되 이유를 남긴다
            problems.append(f"{label}: {type(e).__name__}: {e}")
            log.warning("KOSIS %s 호출 실패 — 기본값을 씁니다: %s", label, e)
    return live, problems


# ---------- 24시간 캐시 ----------
CACHE_SECONDS = 24 * 60 * 60
_lock = threading.Lock()
_cache: dict = {"at": 0.0, "stats": None, "source": None}


def get() -> tuple[dict, dict]:
    """(전국 통계, 출처 정보). 출처: {"kosis": "live" | "partial" | "baseline", "problems": [...]}"""
    now = time.time()
    with _lock:
        if _cache["stats"] is not None and now - _cache["at"] < CACHE_SECONDS:
            return _cache["stats"], _cache["source"]
        key = config.secret("KOSIS_API_KEY")
        if not key:
            log.warning("KOSIS_API_KEY 가 없어 전국 평균은 기본값만 씁니다.")
            stats, source = merge(BASELINE, None), {"kosis": "baseline", "problems": ["KOSIS_API_KEY 없음"]}
        else:
            live, problems = fetch_live(key)
            state = "baseline" if not live else ("partial" if problems else "live")
            stats, source = merge(BASELINE, live), {"kosis": state, "problems": problems}
        # 실패(baseline)는 오래 붙잡지 않고 10분 뒤 다시 시도한다
        _cache.update(at=now - (CACHE_SECONDS - 600 if source["kosis"] == "baseline" else 0), stats=stats, source=source)
        return stats, source


def latest_year(stats: dict, gender: str, metric: str = "도체중"):
    """전국 통계에서 해당 성별·지표의 가장 최근 연도(올해 이하). 없으면 None"""
    years = [y for y in stats.get(gender, {}).get(metric, {}) if isinstance(y, int) and y <= datetime.now().year]
    return max(years) if years else None
