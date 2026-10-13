"""2단계 · 현장방문조사 — 방문 목록, 조사표 읽기·새로 쓰기·고치기.

조사표는 field_surveys.survey_data 에 JSON 으로 들어 있다. 항목 이름(키)·선택지·새 조사표 기본값은
기존 앱(streamlit_app.py 메뉴 3)과 같다. 양식은 여기 FORM 한 곳에만 적고, 화면은 /api/surveys/form 을 받아 그린다.

기존 앱과 같은 저장 규칙:
- 고칠 때 저장된 값이 선택지에 없으면(예: 빈 칸 '') 화면은 '선택 안 함'으로 열고, 그대로 저장하면 원래 값을 지킨다.
- 양식에 없는 기존 키(엑셀에서 옮긴 _extra 등)는 지우지 않는다: {**기존, **새 값}.
- 날씨 칸은 저장된 값이 0·빈 값이면 지역의 기본 날씨로 채워 보여 준다.
- 새 방문은 그 농가의 마지막 회차 + 1, visits 와 field_surveys 를 함께 넣는다. 고치면 visits 의 날짜·조사자도 고친다.
"""
import json
import logging
import math
from datetime import date

log = logging.getLogger("consulting.surveys")

# 2025년 기준 지역 날씨 (기존 앱 WEATHER_DATA 와 같다)
WEATHER = {
    '대구': {'avgTemp': 15.2, 'highTemp': 37.4, 'lowTemp': -10.7, 'precip': 1029.0, 'wind': 2.2, 'humid': 61.1, 'source': '대구 관측소 (직접)'},
    '경산': {'avgTemp': 15.2, 'highTemp': 37.4, 'lowTemp': -10.7, 'precip': 1029.0, 'wind': 2.2, 'humid': 61.1, 'source': '인접 대구 관측소 값 준용'},
    '영천': {'avgTemp': 14.0, 'highTemp': 36.7, 'lowTemp': -11.8, 'precip': 1047.7, 'wind': 1.7, 'humid': 67.3, 'source': '영천 관측소 (직접)'},
    '구미': {'avgTemp': 14.6, 'highTemp': 38.3, 'lowTemp': -11.0, 'precip': 1046.5, 'wind': 1.3, 'humid': 65.0, 'source': '구미 관측소 (직접)'},
    '군위': {'avgTemp': 13.3, 'highTemp': 38.3, 'lowTemp': -17.1, 'precip': 964.3, 'wind': 1.1, 'humid': 71.5, 'source': '인접 의성 관측소 값 준용'},
    '청도': {'avgTemp': 15.1, 'highTemp': 39.2, 'lowTemp': -12.0, 'precip': 1314.0, 'wind': 1.3, 'humid': 64.3, 'source': '인접 밀양 관측소 값 준용'},
    '고령': {'avgTemp': 14.6, 'highTemp': 37.7, 'lowTemp': -12.7, 'precip': 1580.6, 'wind': 0.9, 'humid': 72.2, 'source': '인접 합천 관측소 값 준용'},
    '성주': {'avgTemp': 14.6, 'highTemp': 38.3, 'lowTemp': -11.0, 'precip': 1046.5, 'wind': 1.3, 'humid': 65.0, 'source': '인접 구미 관측소 값 준용'},
    '합천': {'avgTemp': 14.6, 'highTemp': 37.7, 'lowTemp': -12.7, 'precip': 1580.6, 'wind': 0.9, 'humid': 72.2, 'source': '합천 관측소 (직접)'},
    '창녕': {'avgTemp': 15.1, 'highTemp': 39.2, 'lowTemp': -12.0, 'precip': 1314.0, 'wind': 1.3, 'humid': 64.3, 'source': '인접 밀양 관측소 값 준용'},
    '경주': {'avgTemp': 14.6, 'highTemp': 37.6, 'lowTemp': -11.3, 'precip': 1033.0, 'wind': 2.6, 'humid': 65.7, 'source': '경주 관측소 (직접)'},
    '의성': {'avgTemp': 13.3, 'highTemp': 38.3, 'lowTemp': -17.1, 'precip': 964.3, 'wind': 1.1, 'humid': 71.5, 'source': '의성 관측소 (직접)'},
    '청송': {'avgTemp': 12.5, 'highTemp': 38.2, 'lowTemp': -18.1, 'precip': 957.3, 'wind': 1.9, 'humid': 69.5, 'source': '청송 관측소 (직접)'},
    '안동': {'avgTemp': 13.5, 'highTemp': 37.6, 'lowTemp': -15.0, 'precip': 887.2, 'wind': 1.5, 'humid': 66.0, 'source': '안동 관측소 (직접)'},
    '김천': {'avgTemp': 14.6, 'highTemp': 38.3, 'lowTemp': -11.0, 'precip': 1046.5, 'wind': 1.3, 'humid': 65.0, 'source': '인접 구미 관측소 값 준용'},
    '칠곡': {'avgTemp': 14.6, 'highTemp': 38.3, 'lowTemp': -11.0, 'precip': 1046.5, 'wind': 1.3, 'humid': 65.0, 'source': '인접 구미 관측소 값 준용'},
}
REGIONS = list(WEATHER) + ['기타']
# 날씨 칸 → WEATHER 의 키
WEATHER_FIELDS = {'dailyAvgTemp': 'avgTemp', 'highTemp': 'highTemp', 'lowTemp': 'lowTemp',
                  'annualPrecip': 'precip', 'avgWindSpeed': 'wind', 'avgHumidity': 'humid'}

FEED_STAGES = ['송아지', '육성우', '비육전기', '비육후기', '번식우']
FEED_ROWS = ['배합사료 품목', '배합사료 급여수준', '조사료 품목', '조사료 급여수준', '첨가제 품목', '첨가제 급여수준']
FEED_LEVELS = ['낮음', '적정', '높음']

PEN_SIZE = ["5X10", "4X8", "3X6", "운동장", "계류", "기타"]
DENSITY = ["높음", "적정", "낮음"]
YES_NO = ["여", "부"]
YES_NO2 = ["예", "아니오"]
DEFAULT_INVESTIGATOR = "컨설턴트 배성태"   # 기존 앱과 같은 기본값


def _f(key, label, kind, default=None, options=None, **extra):
    """항목 하나. kind: text | date | select | radio | int | float | textarea | feed"""
    d = {"key": key, "label": label, "kind": kind, "default": default}
    if options is not None:
        d["options"] = options
    d.update(extra)
    return d


# 양식 — 기존 앱의 순서·이름·선택지·새 조사표 기본값 그대로
FORM = [
    {"title": "1. 조사 기본정보", "open": True, "fields": [
        _f("investigator", "조사자 성명", "text", DEFAULT_INVESTIGATOR),
        _f("visitDate", "조사일자", "date", None),
        _f("memberName", "조합원명", "text", ""),
        _f("memberId", "조합원번호", "text", ""),
        _f("region", "지역", "select", REGIONS[0], REGIONS, hint="고르면 아래 날씨 정보가 그 지역 값으로 채워집니다"),
        _f("farmType", "전업여부", "radio", "전업", ["전업", "겸업"]),
        _f("bizGoal", "🎯 농가 경영 목표 (출하 전략)", "select", "28개월 조기출하(회전율 최우선)",
           ["28개월 조기출하(회전율 최우선)", "30개월 이상 장기비육(육질 투플러스 최우선)", "복합"]),
    ]},
    {"title": "2. 날씨 정보 (2025년 기준)", "open": True, "fields": [
        _f("dailyAvgTemp", "연평균기온 (℃)", "float", 0.0),
        _f("highTemp", "최고기온 (℃)", "float", 0.0),
        _f("lowTemp", "최저기온 (℃)", "float", 0.0),
        _f("annualPrecip", "평균강수량 (연간) (mm)", "float", 0.0),
        _f("avgWindSpeed", "평균풍속 (m/s)", "float", 0.0),
        _f("avgHumidity", "평균상대습도 (%)", "float", 0.0),
    ]},
    {"title": "3. 축산 사육환경", "open": False, "fields": [
        _f("breedingType", "사육형태", "select", "일관사육", ["일관사육", "암소번식", "비육전문(거)", "비육전문(암)", "비육전문(거,암)"]),
        _f("fatteningPenSize", "비육우방 크기", "select", "5X10", PEN_SIZE),
        _f("fatteningPenDensity", "비육우방 밀도", "select", "적정", DENSITY),
        _f("breedingPenSize", "번식우방 크기", "select", "5X10", PEN_SIZE),
        _f("breedingPenDensity", "번식우방 밀도", "select", "적정", DENSITY),
        _f("calfPenSize", "송아지우방 크기", "select", "5X10", PEN_SIZE),
        _f("calfPenDensity", "송아지우방 밀도", "select", "적정", DENSITY),
        _f("bulkBin", "벌크빈", "radio", "부", YES_NO),
        _f("autoFeeder", "자동급이시설", "radio", "부", YES_NO),
        _f("tmr", "TMR 급여", "radio", "부", YES_NO),
        _f("selfMix", "자가배합", "radio", "부", YES_NO),
        _f("castrationAge", "거세시기 (개월)", "int", 0),
        _f("castrationMethod", "거세방법", "radio", "무혈", ["무혈", "유혈"]),
        _f("floorCondition", "축사바닥", "select", "양호", ["우수", "양호", "미흡"]),
        _f("dewormingCount", "정기구충 (회/년)", "int", 0),
        _f("waterQuality", "💧 음수(물) 관리 실태", "select", "보통", ["매우 청결", "보통", "불량(이끼, 분변 오염 등)"]),
        _f("manureScore", "💩 소 분변 상태", "select", "적정(모양 유지)", ["과도하게 묽음", "적정(모양 유지)", "과도하게 단단함"]),
        _f("troughCleaning", "🍽️ 사조(밥통) 매일 청소 및 잔량 폐기", "radio", "예", YES_NO2),
    ]},
    {"title": "4. 사료급여", "open": False, "fields": [
        _f("feedOrder", "급여순서", "text", "", placeholder="예: 조사료 → 배합사료"),
        _f("feedFrequency", "급여횟수 (회/일)", "int", 2),
        _f("forageQuality", "🌾 조사료의 품질(질) 평가", "select", "보통(볏짚/라이그라스 혼합)",
           ["우수(알팔파, 티모시 등 수입산 위주)", "보통(볏짚/라이그라스 혼합)", "미흡(수분 과다, 곰팡이 관찰)"]),
        _f("feed_matrix", "단계별 사료 품목·급여수준", "feed", None),
    ]},
    {"title": "5. 사육두수 현황", "open": False, "fields": [
        _f("countCow", "번식우(암소) (두)", "int", 0),
        _f("countSteer", "거세우 (두)", "int", 0),
        _f("countGrowing", "육성우 (두)", "int", 0),
        _f("countCalf", "송아지 (두)", "int", 0),
        _f("countOptimal", "적정 사육두수 (두)", "int", 0),
    ]},
    {"title": "6. 번식관리 · 7. 질병예방 · 8. 특이사항", "open": False, "fields": [
        _f("aiMethod", "인공수정 방법", "radio", "자가 수정", ["자가 수정", "수정사 의뢰"]),
        _f("calvingInterval", "평균 분만간격 (개월)", "float", 0.0),
        _f("mortalityRate", "최근 1년 폐사율 (%)", "float", 0.0),
        _f("weaningAge", "송아지 이유 월령", "float", 0.0, step=0.5),
        _f("artificialRearing", "인공포유 여부", "radio", "아니오", YES_NO2),
        _f("consultingNotes", "현장 점검 소견 및 컨설팅사항", "textarea", ""),
    ]},
]
FIELDS = {f["key"]: f for s in FORM for f in s["fields"]}
TEXT_MAX = {"text": 100, "textarea": 5000, "feed": 100}


class SurveyError(ValueError):
    """사용자에게 그대로 보여 줄 입력 오류."""


def form_schema() -> dict:
    return {"sections": FORM, "weather": WEATHER, "weather_fields": WEATHER_FIELDS,
            "feed": {"stages": FEED_STAGES, "rows": FEED_ROWS, "levels": FEED_LEVELS}}


# ---------------------------------------------------------------- 읽기
def visits(conn, farm_id: int) -> list[dict]:
    rows = conn.execute("""
        SELECT v.id, v.visit_number, v.visit_date, v.consultant_name,
               CASE WHEN s.survey_data IS NOT NULL AND s.survey_data <> '' THEN 1 ELSE 0 END AS has_survey
        FROM visits v LEFT JOIN field_surveys s ON s.visit_id = v.id
        WHERE v.farm_id = ? ORDER BY v.visit_number""", (farm_id,)).fetchall()
    return [{"id": r[0], "visit_number": r[1], "visit_date": r[2], "investigator": r[3] or "", "has_survey": bool(r[4])} for r in rows]


def _stored(conn, farm_id: int, visit_id: int) -> tuple[dict, dict] | None:
    """(방문 정보, 저장된 survey_data dict). 이 농가의 방문이 아니면 None."""
    r = conn.execute("""
        SELECT v.id, v.visit_number, v.visit_date, v.consultant_name, s.survey_data
        FROM visits v LEFT JOIN field_surveys s ON s.visit_id = v.id
        WHERE v.id = ? AND v.farm_id = ?""", (visit_id, farm_id)).fetchone()
    if r is None:
        return None
    try:
        data = json.loads(r[4]) if r[4] else {}
    except (TypeError, ValueError):
        log.warning("조사표 JSON 을 읽지 못함: 방문 %s", visit_id)
        data = {}
    return {"id": r[0], "visit_number": r[1], "visit_date": r[2], "investigator": r[3] or ""}, data if isinstance(data, dict) else {}


def _empty_feed() -> dict:
    return {st: {row: "" for row in FEED_ROWS} for st in FEED_STAGES}


def _feed_for_form(saved) -> dict:
    """저장된 표를 양식 모양(5단계 × 6줄)으로 맞춘다. 빈 칸은 ''."""
    out = _empty_feed()
    if isinstance(saved, dict):
        for st in FEED_STAGES:
            col = saved.get(st) if isinstance(saved.get(st), dict) else {}
            for row in FEED_ROWS:
                v = col.get(row)
                out[st][row] = "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)
    return out


def form_values(existing: dict, today: date) -> dict:
    """화면에 채울 값. 기존 앱 gv/gi/wv 와 같은 규칙.
    선택 항목: 저장된 값이 선택지에 있으면 그 값, 키는 있는데 선택지에 없으면 None(선택 안 함), 키가 없으면 기본값."""
    vals = {}
    for key, f in FIELDS.items():
        kind = f["kind"]
        if kind in ("select", "radio"):
            v = existing.get(key, f["default"])
            vals[key] = v if v in f["options"] else (None if key in existing else f["default"])
        elif kind == "date":
            v = str(existing.get("visitDate") or "")[:10]
            try:
                vals[key] = date.fromisoformat(v).isoformat()
            except ValueError:
                vals[key] = today.isoformat()
        elif kind == "int":
            try:
                vals[key] = int(existing.get(key, f["default"]))
            except (TypeError, ValueError):
                vals[key] = f["default"]
        elif kind == "float":
            try:
                vals[key] = float(existing.get(key, f["default"]))
            except (TypeError, ValueError):
                vals[key] = f["default"]
        elif kind == "feed":
            vals[key] = _feed_for_form(existing.get(key))
        else:
            v = existing.get(key, f["default"])
            vals[key] = "" if v is None else str(v)
    # 날씨: 저장된 값이 0·빈 값이면 지역 기본값 (기존 앱 wv)
    wd = WEATHER.get(vals["region"] or "", {})
    for key, wkey in WEATHER_FIELDS.items():
        saved = existing.get(key)
        if saved in (None, 0, 0.0, ""):
            vals[key] = float(wd.get(wkey, 0.0))
    return vals


def read(conn, farm_id: int, visit_id: int, today: date) -> dict | None:
    got = _stored(conn, farm_id, visit_id)
    if got is None:
        return None
    meta, existing = got
    return {"visit": meta, "values": form_values(existing, today), "empty": not existing,
            "extra_keys": sorted(k for k in existing if k not in FIELDS)}


def blank(today: date) -> dict:
    return {"visit": None, "values": form_values({}, today), "empty": True, "extra_keys": []}


# ---------------------------------------------------------------- 저장
def clean(values: dict) -> dict:
    """화면에서 온 값을 검사해 저장할 모양으로. None 은 '선택 안 함'(원래 값 유지)으로 남긴다."""
    out = {}
    for key, f in FIELDS.items():
        if key not in values:
            raise SurveyError(f"'{f['label']}' 값이 빠졌습니다.")
        v, kind = values[key], f["kind"]
        if v is None and kind in ("select", "radio"):
            out[key] = None
        elif kind in ("select", "radio"):
            if v not in f["options"]:
                raise SurveyError(f"'{f['label']}' 선택지에 없는 값입니다: {v}")
            out[key] = v
        elif kind == "date":
            try:
                out[key] = date.fromisoformat(str(v)).isoformat()
            except ValueError:
                raise SurveyError("조사일자를 YYYY-MM-DD 형식으로 넣어주세요.") from None
        elif kind in ("int", "float"):
            try:
                n = float(v)
            except (TypeError, ValueError):
                raise SurveyError(f"'{f['label']}'에는 숫자를 넣어주세요.") from None
            if math.isnan(n) or math.isinf(n) or abs(n) > 1e7:
                raise SurveyError(f"'{f['label']}' 값이 너무 크거나 잘못되었습니다.")
            if kind == "int" and n != int(n):
                raise SurveyError(f"'{f['label']}'에는 정수를 넣어주세요.")
            out[key] = int(n) if kind == "int" else n
        elif kind == "feed":
            if not isinstance(v, dict):
                raise SurveyError("사료급여 표 모양이 잘못되었습니다.")
            fm = {}
            for st in FEED_STAGES:
                col = v.get(st) if isinstance(v.get(st), dict) else {}
                fm[st] = {}
                for row in FEED_ROWS:
                    cell = "" if col.get(row) is None else str(col.get(row)).strip()
                    if len(cell) > TEXT_MAX["feed"]:
                        raise SurveyError(f"사료급여 표 '{st} {row}' 글이 너무 깁니다.")
                    if "급여수준" in row and cell not in ("", *FEED_LEVELS):
                        raise SurveyError(f"사료급여 표 '{st} {row}'는 낮음/적정/높음 중에서 골라주세요.")
                    fm[st][row] = cell
            out[key] = fm
        else:
            s = "" if v is None else str(v)
            if len(s) > TEXT_MAX[kind]:
                raise SurveyError(f"'{f['label']}' 글이 너무 깁니다 (최대 {TEXT_MAX[kind]}자).")
            out[key] = s
    return out


def merge(existing: dict, cleaned: dict) -> dict:
    """기존 앱: 선택 안 함(None)은 원래 값('' 포함)으로 되돌리고, 양식에 없는 키는 남긴다."""
    kept = {k: (existing.get(k, "") if v is None else v) for k, v in cleaned.items()}
    return {**existing, **kept}


def create(conn, farm_id: int, values: dict) -> dict:
    s = merge({}, clean(values))
    try:
        v_no = conn.execute("SELECT COALESCE(MAX(visit_number), 0) + 1 FROM visits WHERE farm_id = ?", (farm_id,)).fetchone()[0]
        v_id = conn.execute("INSERT INTO visits (farm_id, visit_number, visit_date, consultant_name) VALUES (?, ?, ?, ?) RETURNING id",
                            (farm_id, v_no, s["visitDate"], s["investigator"])).fetchone()[0]
        conn.execute("INSERT INTO field_surveys (visit_id, survey_data) VALUES (?, ?)", (v_id, json.dumps(s, ensure_ascii=False)))
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("새 방문조사 저장 실패 — 되돌림 (농가 %s)", farm_id)
        raise
    log.info("새 방문조사 저장: 농가 %s, %s차 (방문 %s)", farm_id, v_no, v_id)
    return {"visit_id": v_id, "visit_number": v_no}


def update(conn, farm_id: int, visit_id: int, values: dict) -> dict | None:
    got = _stored(conn, farm_id, visit_id)
    if got is None:
        return None
    meta, existing = got
    s = merge(existing, clean(values))
    try:
        conn.execute("UPDATE visits SET visit_date = ?, consultant_name = ? WHERE id = ?", (s["visitDate"], s["investigator"], visit_id))
        conn.execute("""INSERT INTO field_surveys (visit_id, survey_data) VALUES (?, ?)
                        ON CONFLICT(visit_id) DO UPDATE SET survey_data = excluded.survey_data""",
                     (visit_id, json.dumps(s, ensure_ascii=False)))
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("방문조사 수정 저장 실패 — 되돌림 (방문 %s)", visit_id)
        raise
    log.info("방문조사 수정 저장: 농가 %s, 방문 %s", farm_id, visit_id)
    return {"visit_id": visit_id, "visit_number": meta["visit_number"]}
