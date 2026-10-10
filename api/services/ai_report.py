"""AI 컨설팅 리포트 — streamlit_app.py '메뉴 4: 3단계 · AI 리포트' 와 섹션 5(Claude 연동)를 옮긴 것.

프롬프트 문구·입력 데이터 구성(성별 통계, 연도별 추이, 수익성 추정)·모델·저장 규칙은 기존 앱과 같다.
입력 데이터가 같은지는 tests/test_api_ai_report.py 가 기존 함수를 그대로 실행해 대조한다.
"""
import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import anthropic
import markdown as md_lib
import pandas as pd

from .. import config
from . import ekape
from . import national_stats as ns

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-5"      # 기존 앱과 같은 모델
MAX_TOKENS = 32000             # 전문자료 근거 인용이 길어 12000 으로는 잘려서 올린 값 (기존과 같음)
PRINT_REPORT_YEARS = [2023, 2024, 2025, 2026]
REPORT_GENDERS = [("거세", "거세우"), ("암", "암소")]
EUMSEONG_PRICES_2025 = {"1++": 23038, "1+": 19590, "1": 18165, "2": 14969, "3": 12735, "등외": 10000}
KNOWLEDGE_DIR = config.BASE_DIR / "knowledge"

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


class ReportError(Exception):
    """리포트 생성 실패. 오류 문구가 리포트 본문으로 저장되지 않도록 예외로 알린다."""


def relabel_survey_data(survey_data):
    """AI 프롬프트에 넣기 전, 현장조사 원본 영문 키를 한글 라벨로 바꾼다 (해석 오류·환각 방지)."""
    if not isinstance(survey_data, dict):
        return survey_data
    return {SURVEY_FIELD_LABELS.get(k, k): v for k, v in survey_data.items()}


def api_key() -> str:
    """secrets.toml → api_key.txt(이 폴더) → 환경변수. 기존 get_claude_api_key() 와 같은 순서."""
    key = config._secrets().get("ANTHROPIC_API_KEY")
    if key:
        return str(key)
    path = config.BASE_DIR / "api_key.txt"
    if path.exists():
        k = path.read_text(encoding="utf-8").strip()
        if k:
            return k
    return os.environ.get("ANTHROPIC_API_KEY", "")


# ---------------------------------------------------------------- 전문자료 (knowledge/*.md)
_knowledge_lock = threading.Lock()
_knowledge: str | None = None


def _fetch_remote_knowledge_files() -> dict:
    """비공개 데이터 저장소(GITHUB_REPO)의 knowledge/*.md 를 {파일명: 본문}으로 받는다. 실패하면 예외."""
    token = config.secret("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN 없음")
    repo = config.secret("GITHUB_REPO", "Bst-dc/hanwoo-smart-consulting")
    branch = config.secret("GITHUB_BRANCH", "main")
    headers = {"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "hanwoo-consulting-app"}

    def _get(path, accept):
        url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
        req = urllib.request.Request(url, headers={**headers, "Accept": accept})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()

    listing = json.loads(_get("knowledge", "application/vnd.github+json").decode("utf-8"))
    names = [item["name"] for item in listing if item.get("type") == "file" and item["name"].endswith(".md")]
    if not names:
        raise RuntimeError("비공개 저장소에 knowledge/*.md 가 없음")
    return {name: _get(f"knowledge/{name}", "application/vnd.github.raw").decode("utf-8") for name in names}


def load_knowledge_base() -> str:
    """전문자료를 한 덩어리로. 파일명 정렬 순서를 고정해야 프롬프트 캐시가 유지된다(순서가 바뀌면 비용 10배).
    성공한 결과만 기억하고, 구하지 못하면 '' — 다음 호출 때 다시 시도한다."""
    global _knowledge
    with _knowledge_lock:
        if _knowledge is not None:
            return _knowledge
        try:
            if KNOWLEDGE_DIR.is_dir():
                files = {p.name: p.read_text(encoding="utf-8") for p in KNOWLEDGE_DIR.glob("*.md")}
            else:
                files = _fetch_remote_knowledge_files()
        except Exception as e:
            log.warning("전문자료를 불러오지 못함: %s", type(e).__name__)
            return ""
        _knowledge = "\n\n".join(f'<문서 제목="{name[:-3]}">\n{files[name]}\n</문서>' for name in sorted(files))
        return _knowledge


# ---------------------------------------------------------------- 음성공판장 등급별 경락단가
_price_cache: dict = {}
PRICE_TTL = 86400


def fetch_eumseong_grade_prices(year):
    """도축장코드 0905 의 연도별 육질등급 평균 경락단가(원/kg)를 축평원 OpenAPI 로 조회 (24시간 캐시, 실패도 캐시 — 기존과 같음).
    키 누락·호출 실패·데이터 없음이면 None → 호출 측이 EUMSEONG_PRICES_2025 로 대신한다."""
    hit = _price_cache.get(year)
    if hit and time.time() - hit[0] < PRICE_TTL:
        return hit[1]
    prices = _fetch_eumseong(year)
    _price_cache[year] = (time.time(), prices)
    return prices


def _fetch_eumseong(year):
    key = ekape.api_key()
    if not key or not year:
        return None
    try:
        url = ("http://data.ekape.or.kr/openapi-data/service/user/grade/auct/cattle"
               f"?startYmd={year}0101&endYmd={year}1231&qgradeYn=Y&ServiceKey={key}")
        root = ET.fromstring(urllib.request.urlopen(url, timeout=8).read())
        # gradeNm "D" 는 축평원 응답상 최하위 등급 구간 → 고정표의 "등외"
        grade_map = {"1++": "1++", "1+": "1+", "1": "1", "2": "2", "3": "3", "D": "등외"}
        prices = {}
        for item in root.findall(".//item"):
            def gt(tag):
                n = item.find(tag)
                return n.text if n is not None else None
            grade = grade_map.get(gt("gradeNm"))
            if not grade:
                continue
            try:
                amt, cnt = float(gt("c_0905Amt")), int(gt("c_0905Cnt"))
            except (TypeError, ValueError):
                continue
            if cnt > 0:
                prices[grade] = amt
        return prices or None
    except Exception:
        return None


# ---------------------------------------------------------------- 프롬프트에 넣을 데이터
def _frame(conn, cols: list[str], farm_id, gender) -> pd.DataFrame:
    """이 농가·성별의 출하 행을 숫자 칸은 실수로 바꿔 DataFrame 으로 (Postgres NUMERIC 도 같은 모양이 되게)."""
    rows = conn.execute(f"SELECT {', '.join(cols)} FROM shipment_records WHERE farm_id = ? AND gender = ?",
                        (farm_id, gender)).fetchall()
    df = pd.DataFrame([list(r) for r in rows], columns=cols)
    for c in cols:
        if c not in ("grade_quality", "grade_yield", "slaughter_year"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build_yearly_breakdown(conn, farm_id, gender, stats):
    """연도별 출하성적 추이 + 육질/육량 등급 전체 분포를 전국 평균과 함께 (기존 build_ai_report_yearly_breakdown)."""
    df = _frame(conn, ["slaughter_year", "carcass_weight", "bms", "backfat", "ribeye", "month_age",
                       "grade_quality", "grade_yield"], farm_id, gender)
    nat = stats.get(gender, {})
    nat_q = nat.get("grade_quality", {})
    nat_y = nat.get("grade_yield", {})
    quality_grades = ["1++", "1+", "1", "2", "3"]
    yield_grades = ["A", "B", "C"]

    breakdown = []
    for year in PRINT_REPORT_YEARS:
        ydf = df[df["slaughter_year"] == year]
        count = len(ydf)
        if count == 0:
            continue

        def avg(col):
            return round(ydf[col].mean(), 1) if ydf[col].notna().any() else None

        quality_pct = {g: round((ydf["grade_quality"] == g).sum() * 100.0 / count, 1) for g in quality_grades}
        quality_pct["1+이상"] = round(ydf["grade_quality"].isin(["1++", "1+"]).sum() * 100.0 / count, 1)
        yield_pct = {g: round((ydf["grade_yield"] == g).sum() * 100.0 / count, 1) for g in yield_grades}
        breakdown.append({
            "year": year,
            "head_count": count,
            "carcass_weight_kg": {"농가": avg("carcass_weight"), "전국": nat.get("도체중", {}).get(year)},
            "bms": {"농가": avg("bms"), "전국": nat.get("BMS", {}).get(year)},
            "backfat_mm": {"농가": avg("backfat"), "전국": nat.get("등지방", {}).get(year)},
            "ribeye_cm2": {"농가": avg("ribeye"), "전국": nat.get("단면적", {}).get(year)},
            "month_age": {"농가": avg("month_age"), "전국": nat.get("출하월령", {}).get(year)},
            "grade_quality_pct": {"농가": quality_pct, "전국": nat_q.get(year)},
            "grade_yield_pct": {"농가": yield_pct, "전국": nat_y.get(year)},
        })
    return breakdown


def build_profit_estimate(conn, farm_id, gender, stats):
    """수익성 추정 (기존 build_ai_report_profit_estimate). 실제 정산액이 절반 이상 있으면 그 평균,
    아니면 음성공판장 등급별 단가 × 등급분포 가중평균. 어떤 방식인지 결과에 적어 AI 가 추정치를 실측처럼 쓰지 않게 한다."""
    df = _frame(conn, ["carcass_weight", "grade_quality", "price_per_kg", "total_price"], farm_id, gender)
    head_count = len(df)
    if head_count == 0:
        return {}

    nat_year = ns.nat_latest_year(stats, gender)
    nat = stats.get(gender, {})
    nat_w = nat.get("도체중", {}).get(nat_year) if nat_year else None
    nat_grade_pct = nat.get("grade_quality", {}).get(nat_year, {}) if nat_year else {}
    farm_w = round(df["carcass_weight"].mean(), 1) if df["carcass_weight"].notna().any() else None

    live_prices = fetch_eumseong_grade_prices(nat_year)
    if live_prices:
        price_table = {**EUMSEONG_PRICES_2025, **live_prices}
        price_basis = f"음성공판장(도축장코드 0905) {nat_year}년 육질등급별 실시간 경락단가 (축평원 OpenAPI)"
    else:
        price_table = EUMSEONG_PRICES_2025
        price_basis = "음성공판장 2025년 육질등급별 낙찰가 (EUMSEONG_PRICES_2025 고정값, 실시간 API 조회 실패로 대체 사용)"

    real_price_df = df[df["total_price"].notna() & (df["total_price"] > 0)]
    if len(real_price_df) >= max(3, head_count * 0.5):
        farm_revenue_per_head = real_price_df["total_price"].mean()
        method = "실측 두당 정산액(shipment_records.total_price) 평균"
    else:
        grade_counts = df["grade_quality"].value_counts()
        farm_price_per_kg = (
            sum(price_table.get(g, price_table["등외"]) * c for g, c in grade_counts.items()) / head_count
            if head_count else None
        )
        farm_revenue_per_head = (farm_w * farm_price_per_kg) if (farm_w and farm_price_per_kg) else None
        method = f"{price_basis} × 농가 등급분포 가중평균 추정 (실제 두당 정산액 데이터 없음)"

    nat_revenue_per_head = None
    if nat_w and nat_grade_pct:
        nat_price_per_kg = sum(price_table[g] * (pct / 100.0) for g, pct in nat_grade_pct.items() if g in price_table)
        nat_revenue_per_head = nat_w * nat_price_per_kg if nat_price_per_kg else None

    result = {"계산_방식": method, "가격_기준": price_basis, "national_base_year": nat_year, "head_count": head_count}
    if farm_revenue_per_head is not None and nat_revenue_per_head is not None:
        diff = round(farm_revenue_per_head - nat_revenue_per_head)
        result.update({
            "farm_revenue_per_head_est": int(round(farm_revenue_per_head)),
            "national_revenue_per_head_est": int(round(nat_revenue_per_head)),
            "diff_revenue_per_head": diff,
            "total_diff_revenue": diff * head_count,
        })
    return result


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
STATS_KEYS = ["total_count", "avg_weight", "avg_bms", "avg_backfat", "avg_ribeye", "avg_month_age",
              "rate_1plus_above", "rate_c_grade"]


def _plain(v):
    """Postgres NUMERIC(Decimal) 를 float 로 — json.dumps 가 Decimal 을 못 다루고, 기존 SQLite 값과 모양을 맞춘다."""
    return float(v) if v is not None and not isinstance(v, (int, float, str)) else v


def gather_inputs(conn, farm_id: int) -> dict:
    """리포트 한 장에 들어갈 것: 농가명, 성별별 출하 데이터, 최근 방문 조사표, 그 방문 ID (기존 화면의 gen_click 블록)."""
    stats = ns.national_stats()
    farm = conn.execute("SELECT farm_name FROM farms WHERE id = ?", (farm_id,)).fetchone()
    last_visit = conn.execute("""
        SELECT v.id, v.visit_number, v.visit_date, s.survey_data, s.consult_notes
        FROM visits v LEFT JOIN field_surveys s ON s.visit_id = v.id
        WHERE v.farm_id = ? ORDER BY v.visit_number DESC LIMIT 1
    """, (farm_id,)).fetchone()

    # 거세우·암소를 함께 출하하는 농가가 많아 성별마다 따로 집계한다. 출하가 없는 성별은 통째로 뺀다(없는 데이터를 지어내지 않게).
    gender_data = {}
    for gkey, glabel in REPORT_GENDERS:
        row = conn.execute(STATS_SQL, (farm_id, gkey)).fetchone()
        if not row or not row[0]:
            continue
        shipment = {k: _plain(v) for k, v in zip(STATS_KEYS, row)}
        profit = build_profit_estimate(conn, farm_id, gkey, stats)
        nat_year_w = ns.nat_latest_year(stats, gkey)
        nat_w = stats.get(gkey, {}).get("도체중", {}).get(nat_year_w) if nat_year_w else None
        if shipment["avg_weight"] is not None and nat_w:
            profit["diff_weight_per_head_kg"] = round(shipment["avg_weight"] - nat_w, 1)
        gender_data[glabel] = {"shipment_stats": shipment,
                               "yearly_breakdown": build_yearly_breakdown(conn, farm_id, gkey, stats),
                               "profit_data": profit}

    survey = {}
    if last_visit:
        survey = {"id": last_visit[0], "visit_number": last_visit[1], "visit_date": str(last_visit[2]),
                  "survey_data": last_visit[3], "consult_notes": last_visit[4]}
        # survey_data 는 JSON 문자열 — 그대로 넣으면 프롬프트에 이스케이프된 한 줄로 들어간다
        if isinstance(survey["survey_data"], str):
            try:
                survey["survey_data"] = json.loads(survey["survey_data"])
            except ValueError:
                pass
    return {"farm_name": farm[0] if farm else "농가", "gender_data": gender_data, "survey": survey,
            "visit_id": last_visit[0] if last_visit else None}


# ---------------------------------------------------------------- 프롬프트
SYSTEM_PROMPT = (
    "당신은 대한민국 최고의 한우 사양관리 수석 컨설턴트입니다. "
    "농가의 최근 3개년 출하성적(정량 데이터)과 현장 방문 사양관리 실태(정성 데이터)를 종합 분석하여 "
    "'진단 → 원인 → 처방 → 액션플랜' 흐름의 7단 구성 맞춤형 컨설팅 리포트를 마크다운으로 작성하세요. "
    "농가가 거세우와 암소를 함께 출하하는 경우 두 성별의 데이터가 각각 주어지니 반드시 성별을 구분해서 분석하고, "
    "한 성별 데이터만 주어졌다면 그 성별만 다루고 없는 성별을 언급하지 마세요."
)
KNOWLEDGE_INSTRUCTION = (
    " 아래 [참고 전문자료]는 농협경제지주·농촌진흥청이 발간한 한우 사양관리 자료입니다. "
    "처방과 기준을 제시할 때 이 자료에 해당 내용이 있으면 반드시 근거로 삼고 어느 자료의 어떤 기준인지 밝히세요. "
    "자료에 없는 수치나 기준은 지어내지 말고, 일반적인 권장사항이라면 그렇다고 명시하세요."
)


def build_request(farm_name, gender_data, survey_data, use_knowledge) -> tuple[list, str]:
    """(system 블록, user 프롬프트). 농가마다 바뀌는 내용은 user 쪽에만 두어 전문자료 캐시가 유지되게 한다."""
    knowledge = load_knowledge_base() if use_knowledge else ""
    system_prompt = SYSTEM_PROMPT + (KNOWLEDGE_INSTRUCTION if knowledge else "")
    system_blocks = [{"type": "text", "text": system_prompt}]
    if knowledge:
        system_blocks.append({
            "type": "text",
            "text": f"[참고 전문자료]\n{knowledge}",
            # 여러 농가 리포트를 몰아서 만들 때 캐시가 살아있도록 1시간 유지 (기본값은 5분)
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        })

    gender_blocks = "\n\n".join(
        f"### {glabel} 출하성적\n"
        f"[출하성적 종합 통계 (전체 기간 통합 평균)]:\n{json.dumps(gd['shipment_stats'], ensure_ascii=False, indent=2)}\n\n"
        f"[연도별 출하성적 추이 및 등급 전체 분포 (전국 평균 대비, 연도 오름차순)]:\n{json.dumps(gd['yearly_breakdown'], ensure_ascii=False, indent=2)}\n\n"
        f"[수익성 분석 (전국 평균 대비 손익, \"계산_방식\" 필드에 실측치인지 추정치인지 명시됨)]:\n{json.dumps(gd['profit_data'], ensure_ascii=False, indent=2)}"
        for glabel, gd in gender_data.items()
    ) or "(이 농가는 등록된 출하성적이 없습니다)"

    prompt = f"""
[농가명]: {farm_name}

[출하 성별]: {", ".join(gender_data.keys()) if gender_data else "없음"}

{gender_blocks}

[현장 방문 조사표 실태 (사료급여, 축사환경, 농가 대화)]:
{json.dumps(relabel_survey_data(survey_data), ensure_ascii=False, indent=2)}

[보고서 작성 필수 7단 구성 가이드]
농장주가 이해하기 쉽고 현장에서 즉시 적용할 수 있도록 아래 목차에 맞추어 작성해 주세요:
# 1. 📋 종합 컨설팅 개요 배너 (농가명, 조사일, 컨설턴트, 핵심 평가)
# 2. ⚡ 핵심 진단 요약 (30초 요약 카드 3~4개: 성적 및 현장조사 핵심 이슈)
# 3. 📊 출하성적 전국 비교 및 수익성 임팩트 — 위 성별별 [연도별 출하성적 추이 및 등급 전체 분포] 데이터를 근거로 성별마다 연도별 표를 만들어 도체중·BMS·등지방·단면적 추이와, 1++/1+/1/2/3 등 육질등급·A/B/C 육량등급 전체 분포 변화를 전국 평균과 비교하세요. 두당/연간 수익 격차는 각 성별 [수익성 분석] 데이터의 값을 그대로 인용하고, "계산_방식"이 추정치라면 반드시 "~로 추정됩니다"처럼 추정임을 밝히세요. 해당 데이터에 없는 연도·수치·성별은 만들어내지 말고 언급하지 마세요.
# 4. 🔍 현장 사양관리 및 축사환경 실태 진단 (우방밀도, 환기, 성장단계별 사료 급여를 [양호/보통/미흡] 배지로 판정)
# 5. 💡 문제별 원인 분석 및 개선 처방 (1:1 매칭: [문제 현상] → [근본 원인] → [정밀 처방])
# 6. 🚀 실행 우선순위 로드맵 (1단계 즉시조치 1~2주, 2단계 기반구축 1~3개월, 3단계 성적개선 6개월~)
# 7. 📌 안내 및 출처 (농촌진흥청 국립축산과학원 사양표준 인용 및 축협 담당자 협의 권장 면책 문구)
"""
    return system_blocks, prompt


def stream_report(system_blocks, prompt):
    """리포트 글을 조각조각 돌려준다. 실패·잘림·거절은 ReportError (부분 결과가 완성본처럼 저장되지 않게)."""
    key = api_key()
    if not key:
        raise ReportError("Anthropic API 키가 설정되지 않았습니다. secrets.toml 또는 api_key.txt 를 확인해주세요.")
    client = anthropic.Anthropic(api_key=key)
    try:
        with client.messages.stream(model=MODEL, max_tokens=MAX_TOKENS, system=system_blocks,
                                    messages=[{"role": "user", "content": prompt}]) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
            u = final.usage
            log.info("AI 리포트 토큰: 입력 %s, 캐시 기록 %s, 캐시 읽기 %s, 출력 %s, 끝난 이유 %s",
                     u.input_tokens, u.cache_creation_input_tokens, u.cache_read_input_tokens, u.output_tokens,
                     final.stop_reason)
            if final.stop_reason == "max_tokens":
                raise ReportError("리포트가 최대 길이에 도달해 중간에 잘렸습니다. 다시 시도해주세요.")
            if final.stop_reason == "refusal":
                raise ReportError("Claude 가 이 요청에 대한 리포트 작성을 거절했습니다. 조사표 내용을 확인한 뒤 다시 시도해주세요.")
    except anthropic.AuthenticationError:
        raise ReportError("Anthropic API 키가 올바르지 않습니다. secrets.toml 또는 api_key.txt 를 확인해주세요.")
    except anthropic.RateLimitError:
        raise ReportError("Anthropic API 사용량 한도에 걸렸습니다. 잠시 후 다시 시도해주세요.")
    except anthropic.APIStatusError as e:
        raise ReportError(f"Claude API 오류가 발생했습니다 ({e.status_code}). 상세: {e.message}")
    except anthropic.APIConnectionError:
        raise ReportError("Anthropic API 에 연결하지 못했습니다. 네트워크 상태를 확인해주세요.")
    except ReportError:
        raise
    except Exception as e:
        raise ReportError(f"Claude 분석 중 오류 발생: {e}")


def save_report(conn, visit_id: int, mode: str, markdown_text: str):
    """같은 방문·같은 방식(전문/일반)으로 다시 만들 때만 덮어쓴다. 시각은 UTC 문자열 (기존과 같음)."""
    conn.execute("""
        INSERT INTO ai_reports (visit_id, report_mode, full_markdown, created_at) VALUES (?, ?, ?, ?)
        ON CONFLICT(visit_id, report_mode) DO UPDATE SET full_markdown = excluded.full_markdown, created_at = excluded.created_at
    """, (visit_id, mode, markdown_text, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))


def build_report_html(farm_name, report_markdown, report_mode=""):
    """리포트 마크다운 → 내려받기·인쇄용 단독 HTML (기존과 같은 모양)."""
    mode_suffix = f" ({report_mode})" if report_mode else ""
    body_html = md_lib.markdown(report_markdown, extensions=["tables", "nl2br", "fenced_code"])
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{farm_name} AI 컨설팅 리포트{mode_suffix}</title>
<style>
    body {{ font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #1e293b; line-height: 1.7; }}
    h1, h2, h3 {{ color: #1e3a8a; }}
    h1 {{ border-bottom: 3px solid #1e3a8a; padding-bottom: 10px; }}
    h2 {{ margin-top: 2rem; border-left: 5px solid #16a34a; padding-left: 10px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }}
    th {{ background-color: #eff6ff; color: #1e3a8a; }}
    tr:nth-child(even) {{ background-color: #f8fafc; }}
    blockquote {{ border-left: 4px solid #94a3b8; margin: 1rem 0; padding: 0.5rem 1rem; color: #64748b; background: #f8fafc; }}
    code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }}
    @media print {{ body {{ margin: 0; padding: 20px; }} }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""
