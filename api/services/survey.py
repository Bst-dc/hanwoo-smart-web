"""현장 방문 조사표 — streamlit_app.py '메뉴 3: 2단계 · 현장방문조사' 를 옮긴 것.

조사표는 field_surveys.survey_data 에 JSON 한 덩어리로 들어간다(키·값 모양은 기존 앱과 같다).
상수(지역·날씨·선택지)는 기존 앱에서 그대로 옮겼고, tests/test_api_survey.py 가 소스와 같은지 확인한다.

기존 앱과 다른 점 하나: 수정 저장할 때 양식에 없는 키(엑셀에서 옮겨 온 '_extra' 등)를 지우지 않고 남긴다.
기존 앱은 양식 값만으로 JSON 을 새로 만들어 덮어써서, 조사표를 한 번 고치면 그 값들이 사라졌다.
"""
import json
import logging

log = logging.getLogger(__name__)

NATIONAL_PRECIP_2025 = 1325.6
WEATHER_DATA = {
    '대구': {'avgTemp':15.2, 'highTemp':37.4, 'lowTemp':-10.7, 'precip':1029.0, 'wind':2.2, 'humid':61.1, 'source':'대구 관측소 (직접)'},
    '경산': {'avgTemp':15.2, 'highTemp':37.4, 'lowTemp':-10.7, 'precip':1029.0, 'wind':2.2, 'humid':61.1, 'source':'인접 대구 관측소 값 준용'},
    '영천': {'avgTemp':14.0, 'highTemp':36.7, 'lowTemp':-11.8, 'precip':1047.7, 'wind':1.7, 'humid':67.3, 'source':'영천 관측소 (직접)'},
    '구미': {'avgTemp':14.6, 'highTemp':38.3, 'lowTemp':-11.0, 'precip':1046.5, 'wind':1.3, 'humid':65.0, 'source':'구미 관측소 (직접)'},
    '군위': {'avgTemp':13.3, 'highTemp':38.3, 'lowTemp':-17.1, 'precip':964.3,  'wind':1.1, 'humid':71.5, 'source':'인접 의성 관측소 값 준용'},
    '청도': {'avgTemp':15.1, 'highTemp':39.2, 'lowTemp':-12.0, 'precip':1314.0, 'wind':1.3, 'humid':64.3, 'source':'인접 밀양 관측소 값 준용'},
    '고령': {'avgTemp':14.6, 'highTemp':37.7, 'lowTemp':-12.7, 'precip':1580.6, 'wind':0.9, 'humid':72.2, 'source':'인접 합천 관측소 값 준용'},
    '성주': {'avgTemp':14.6, 'highTemp':38.3, 'lowTemp':-11.0, 'precip':1046.5, 'wind':1.3, 'humid':65.0, 'source':'인접 구미 관측소 값 준용'},
    '합천': {'avgTemp':14.6, 'highTemp':37.7, 'lowTemp':-12.7, 'precip':1580.6, 'wind':0.9, 'humid':72.2, 'source':'합천 관측소 (직접)'},
    '창녕': {'avgTemp':15.1, 'highTemp':39.2, 'lowTemp':-12.0, 'precip':1314.0, 'wind':1.3, 'humid':64.3, 'source':'인접 밀양 관측소 값 준용'},
    '경주': {'avgTemp':14.6, 'highTemp':37.6, 'lowTemp':-11.3, 'precip':1033.0, 'wind':2.6, 'humid':65.7, 'source':'경주 관측소 (직접)'},
    '의성': {'avgTemp':13.3, 'highTemp':38.3, 'lowTemp':-17.1, 'precip':964.3,  'wind':1.1, 'humid':71.5, 'source':'의성 관측소 (직접)'},
    '청송': {'avgTemp':12.5, 'highTemp':38.2, 'lowTemp':-18.1, 'precip':957.3,  'wind':1.9, 'humid':69.5, 'source':'청송 관측소 (직접)'},
    '안동': {'avgTemp':13.5, 'highTemp':37.6, 'lowTemp':-15.0, 'precip':887.2,  'wind':1.5, 'humid':66.0, 'source':'안동 관측소 (직접)'},
    '김천': {'avgTemp':14.6, 'highTemp':38.3, 'lowTemp':-11.0, 'precip':1046.5, 'wind':1.3, 'humid':65.0, 'source':'인접 구미 관측소 값 준용'},
    '칠곡': {'avgTemp':14.6, 'highTemp':38.3, 'lowTemp':-11.0, 'precip':1046.5, 'wind':1.3, 'humid':65.0, 'source':'인접 구미 관측소 값 준용'},
}
REGION_OPTIONS = list(WEATHER_DATA.keys()) + ['기타']
FEED_CATS = [
    {'key': 'calf', 'label': '송아지'},
    {'key': 'growing', 'label': '육성우'},
    {'key': 'fatten1', 'label': '비육전기'},
    {'key': 'fatten2', 'label': '비육후기'},
    {'key': 'dam', 'label': '번식우'},
]
FEED_ROWS = ["배합사료 품목", "배합사료 급여수준", "조사료 품목", "조사료 급여수준", "첨가제 품목", "첨가제 급여수준"]
FEED_COLS = [c['label'] for c in FEED_CATS]

# 양식의 선택지 (기존 화면에 적힌 그대로). 화면은 이 순서대로 보여 주고, 저장값이 목록에 없으면 그 값을 그대로 둔다.
CHOICES = {
    "farmType": ["전업", "겸업"],
    "bizGoal": ["28개월 조기출하(회전율 최우선)", "30개월 이상 장기비육(육질 투플러스 최우선)", "복합"],
    "breedingType": ["일관사육", "암소번식", "비육전문(거)", "비육전문(암)", "비육전문(거,암)"],
    "penSize": ["5X10", "4X8", "3X6", "운동장", "계류", "기타"],
    "penDensity": ["높음", "적정", "낮음"],
    "yesNo": ["여", "부"],
    "castrationMethod": ["무혈", "유혈"],
    "floorCondition": ["우수", "양호", "미흡"],
    "waterQuality": ["매우 청결", "보통", "불량(이끼, 분변 오염 등)"],
    "manureScore": ["과도하게 묽음", "적정(모양 유지)", "과도하게 단단함"],
    "yesNo2": ["예", "아니오"],
    "forageQuality": ["우수(알팔파, 티모시 등 수입산 위주)", "보통(볏짚/라이그라스 혼합)", "미흡(수분 과다, 곰팡이 관찰)"],
    "aiMethod": ["자가 수정", "수정사 의뢰"],
}


def form_options() -> dict:
    return {"regions": REGION_OPTIONS, "weather": WEATHER_DATA, "feed_rows": FEED_ROWS, "feed_cols": FEED_COLS,
            "choices": CHOICES, "national_precip_2025": NATIONAL_PRECIP_2025}


def full_feed_matrix(matrix: dict | None) -> dict:
    """{성장단계: {행: 값}} — 기존 화면 표(DataFrame.to_dict())와 같은 모양으로, 빠진 칸은 '' 로 채운다."""
    matrix = matrix or {}
    return {col: {row: str((matrix.get(col) or {}).get(row) or "") for row in FEED_ROWS} for col in FEED_COLS}


def _load(text) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        log.warning("조사표 JSON 을 읽지 못해 빈 양식으로 엽니다")
        return {}
    return data if isinstance(data, dict) else {}


def list_visits(conn, farm_id: int) -> list[dict]:
    rows = conn.execute("""
        SELECT v.id, v.visit_number, v.visit_date, v.consultant_name, s.survey_data
        FROM visits v LEFT JOIN field_surveys s ON s.visit_id = v.id
        WHERE v.farm_id = ? ORDER BY v.visit_number
    """, (farm_id,)).fetchall()
    return [{"id": r["id"], "visit_number": r["visit_number"], "visit_date": str(r["visit_date"]),
             "consultant_name": r["consultant_name"], "has_survey": bool(_load(r["survey_data"]))} for r in rows]


def get_visit(conn, visit_id: int) -> dict | None:
    r = conn.execute("""
        SELECT v.id, v.farm_id, v.visit_number, v.visit_date, s.survey_data
        FROM visits v LEFT JOIN field_surveys s ON s.visit_id = v.id WHERE v.id = ?
    """, (visit_id,)).fetchone()
    if r is None:
        return None
    return {"id": r["id"], "farm_id": r["farm_id"], "visit_number": r["visit_number"],
            "visit_date": str(r["visit_date"]), "survey": _load(r["survey_data"])}


def create_visit(conn, farm_id: int, survey: dict) -> tuple[int, int]:
    """새 방문(회차 = 그 농가 최대 회차 + 1)과 조사표를 만든다. (방문 ID, 회차) 를 돌려준다."""
    v_no = conn.execute("SELECT COALESCE(MAX(visit_number), 0) + 1 FROM visits WHERE farm_id = ?", (farm_id,)).fetchone()[0]
    v_id = conn.execute(
        "INSERT INTO visits (farm_id, visit_number, visit_date, consultant_name) VALUES (?, ?, ?, ?) RETURNING id",
        (farm_id, v_no, survey["visitDate"], survey["investigator"])).fetchone()[0]
    conn.execute("INSERT INTO field_surveys (visit_id, survey_data) VALUES (?, ?)",
                 (v_id, json.dumps(survey, ensure_ascii=False)))
    return int(v_id), int(v_no)


def update_visit(conn, visit_id: int, survey: dict) -> dict:
    """방문일·조사자를 고치고 조사표를 덮어쓴다. 양식에 없는 기존 키는 남긴다. 저장한 조사표를 돌려준다."""
    old = get_visit(conn, visit_id)
    merged = {**old["survey"], **survey}
    conn.execute("UPDATE visits SET visit_date = ?, consultant_name = ? WHERE id = ?",
                 (survey["visitDate"], survey["investigator"], visit_id))
    conn.execute("""
        INSERT INTO field_surveys (visit_id, survey_data) VALUES (?, ?)
        ON CONFLICT(visit_id) DO UPDATE SET survey_data = excluded.survey_data
    """, (visit_id, json.dumps(merged, ensure_ascii=False)))
    return merged
