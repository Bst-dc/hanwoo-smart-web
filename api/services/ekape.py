"""축평원(eKAPE) 도체 등급판정 조회 — 기존 앱 fetch_cattle_grade() 와 같은 두 번 호출.

이력번호 → 등급판정 확인서번호(issueNo)·발급일 → 그 확인서의 도체 성적(item).
기존 앱은 두 번째 조회에 발급일을 빠뜨려, 번호가 다시 쓰인 오래된 소는 다른 소의 성적을 받아 왔다 (2026-10 고침).
기존 앱은 실패 이유를 모두 None 으로 뭉갰는데, 여기서는 어떤 번호가 왜 안 됐는지 화면에 알려 준다.
"""
import logging
import math
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from .. import config

log = logging.getLogger("consulting.ekape")

BASE = "http://data.ekape.or.kr/openapi-data/service/user/grade/confirm"
TIMEOUT = 6           # 기존 앱과 같다 (요청 하나당 초)
WORKERS = 4           # 동시에 묻는 수. 공공데이터 포털이 막지 않도록 작게 둔다
MAX_LOOKUP = 200      # 한 번에 조회할 수 있는 최대 두수 (휴대폰에서 너무 오래 기다리지 않게)


def api_key() -> str:
    return config.secret("EKAPE_API_KEY")


def normalize_animal_no(value) -> str:
    """기존 앱과 같은 규칙: 띄어쓰기·'-' 를 없애고, 엑셀이 숫자로 읽어 떨어진 앞자리 0 을 12자리로 되살린다."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    s = re.sub(r"[\s\-]", "", str(value))
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    if s.isdigit() and len(s) < 12:
        s = s.zfill(12)
    return s


def split_input(text: str) -> tuple[list[str], int]:
    """입력 칸의 글을 이력번호 목록으로. 기존 앱처럼 쉼표·줄바꿈으로 나누고 8자 미만 줄은 버린다.
    같은 번호를 두 번 적었으면 한 번만 묻는다. 반환: (번호 목록, 겹쳐서 뺀 수)"""
    raw = [s.strip() for s in (text or "").replace(",", "\n").split("\n") if len(s.strip()) >= 8]
    seen, out = set(), []
    for s in raw:
        n = normalize_animal_no(s)
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out, len(raw) - len(out)


def _to_f(v):
    try:
        return float(v) if v else None
    except (TypeError, ValueError):
        return None


def _text(node, tag) -> str:
    n = node.find(tag)
    return (n.text or "").strip() if n is not None else ""


def parse_issue(xml_text: str, animal_no: str) -> dict | None:
    """이력번호 조회 XML → 확인서 {issue_no, issue_date, abatt_date}. 없으면 None.

    확인서 번호(예: 0905-50642)는 몇 년 뒤 다른 소에게 다시 쓰인다. 그래서 다음 조회에 발급일을 같이 보내야
    이 소의 성적이 나온다 (번호만 보내면 가장 최근에 그 번호로 발급된 다른 소가 나온다 — 2026-10 확인).
    """
    items = ET.fromstring(xml_text).findall(".//item")
    mine = [i for i in items if normalize_animal_no(_text(i, "animalNo")) == animal_no] or items
    for it in mine:
        if _text(it, "issueNo"):
            return {"issue_no": _text(it, "issueNo"), "issue_date": _text(it, "issueDate"), "abatt_date": _text(it, "abattDate")}
    return None


def cattle_no(xml_text: str) -> str:
    """확인서 성적 XML 의 이력번호(cattleNo). 없으면 빈 문자열."""
    item = ET.fromstring(xml_text).find(".//item")
    return normalize_animal_no(_text(item, "cattleNo")) if item is not None else ""


def parse_grade(xml_text: str, animal_no: str) -> dict | None:
    """확인서 성적 XML → 기존 앱과 같은 키의 dict. item 이 없으면 None."""
    item = ET.fromstring(xml_text).find(".//item")
    if item is None:
        return None

    def get_t(tag):
        n = item.find(tag)
        return n.text if n is not None else None

    # judgeSexNm: "거세" / "암" / "수" — DB 의 gender 값과 같은 표기로 맞춘다
    sex_nm = (get_t("judgeSexNm") or "").strip()
    gender = "거세" if "거세" in sex_nm else ("암" if "암" in sex_nm else ("수" if "수" in sex_nm else None))
    return {
        "animal_no": animal_no,
        "gender": gender,
        "costAmt": _to_f(get_t("costAmt")),
        "carcass_weight": _to_f(get_t("weight")),
        "grade_quality": get_t("qgrade"),
        "grade_yield": get_t("wgrade"),
        "bms": _to_f(get_t("insfat")),
        "backfat": _to_f(get_t("backfat")),
        "ribeye": _to_f(get_t("rea")),
        "month_age": _to_f(get_t("birthmonth")),
        # abattDate=도축일자, judgeDate=등급판정일(도축 다음날)
        "slaughter_date": get_t("abattDate") or get_t("judgeDate"),
    }


def _http_get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8")


def fetch_one(animal_no: str, key: str, get=_http_get) -> tuple[dict | None, str]:
    """반환: (성적 또는 None, 실패 이유). get 은 시험에서 가짜로 바꿔 끼운다."""
    q = urllib.parse.quote
    try:
        issue = parse_issue(get(f"{BASE}/issueNo?animalNo={q(animal_no)}&ServiceKey={key}"), animal_no)
        if not issue:
            return None, "등급판정 기록 없음 (번호 확인 또는 아직 판정 전)"
        xml = get(f"{BASE}/cattle?issueNo={q(issue['issue_no'])}&issueDate={q(issue['issue_date'])}&ServiceKey={key}")
        rec = parse_grade(xml, animal_no)
        if rec is None:
            return None, "확인서에 성적이 없음"
        # 받은 성적이 정말 이 소의 것인지 대조한다 (다른 소 성적이 저장되는 것을 막는다)
        got = cattle_no(xml)
        if (got and got != animal_no) or (issue["abatt_date"] and rec["slaughter_date"] and issue["abatt_date"] != rec["slaughter_date"]):
            log.warning("축평원 성적이 다른 소의 것: %s… (확인서 %s)", animal_no[:5], issue["issue_no"])
            return None, "축평원이 다른 소의 성적을 돌려줌 (저장하지 않음)"
        return rec, ""
    except ET.ParseError:
        log.warning("축평원 응답을 읽지 못함: %s…", animal_no[:5])
        return None, "축평원 응답 형식 오류 (API 키를 확인하세요)"
    except Exception as e:                       # 통신 오류·시간 초과 등
        log.warning("축평원 조회 실패 %s…: %s", animal_no[:5], e)
        return None, f"축평원 연결 실패 ({type(e).__name__})"


def fetch_many(animal_nos: list[str], key: str, get=_http_get) -> tuple[list[dict], list[dict]]:
    """여러 두를 동시에 조회. 반환: (성공 성적 목록, [{animal_no, reason}] 실패 목록) — 둘 다 입력 순서를 지킨다."""
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda n: fetch_one(n, key, get), animal_nos))
    found = [r for r, _ in results if r]
    failed = [{"animal_no": n, "reason": why} for n, (r, why) in zip(animal_nos, results) if not r]
    log.info("축평원 조회 %d두: 성공 %d, 실패 %d", len(animal_nos), len(found), len(failed))
    return found, failed
