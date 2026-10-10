"""축평원(eKAPE) OpenAPI — streamlit_app.py 섹션 4 를 옮긴 것.

개체이력번호 → 등급판정 확인서 번호(issueNo) → 도체성적. 키는 반드시 '인코딩 키'를 쓴다
(코드가 URL 에 그대로 끼워 넣으므로 디코딩 키의 '+' 가 공백으로 읽혀 오류 없이 조회만 실패한다).
"""
import logging
import math
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .. import config

log = logging.getLogger(__name__)


def api_key() -> str:
    """secrets.toml → ekape_key.txt(이 폴더) → 환경변수. 기존 get_ekape_api_key() 와 같은 순서."""
    key = config._secrets().get("EKAPE_API_KEY")
    if key:
        return str(key)
    path = config.BASE_DIR / "ekape_key.txt"
    if path.exists():
        k = path.read_text(encoding="utf-8").strip()
        if k:
            return k
    import os
    return os.environ.get("EKAPE_API_KEY", "")


def normalize_animal_no(value) -> str:
    """이력번호를 12자리 문자열로. 띄어쓰기·'-' 를 없애고, 엑셀이 숫자로 읽어 앞자리 0 이 떨어진 값도 되살린다.
    값이 비어 있으면 ''."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    s = re.sub(r"[\s\-]", "", str(value))
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    if s.isdigit() and len(s) < 12:
        s = s.zfill(12)
    return s


def parse_animal_input(text: str) -> list[str]:
    """입력칸 글자 → 조회할 번호 목록. 줄바꿈·쉼표로 나누고 8자 미만은 버린다 (기존 화면과 같은 규칙)."""
    return [s.strip() for s in text.replace(",", "\n").split("\n") if len(s.strip()) >= 8]


def _get(url, timeout=6):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")


def fetch_cattle_grade(animal_no):
    """도체성적 dict. 조회 결과가 없거나 호출이 실패하면 None (기존과 같음 — 실패 이유는 기록에 남긴다)."""
    animal_no = normalize_animal_no(animal_no)
    key = api_key()
    if not key:
        return None
    try:
        root1 = ET.fromstring(_get(
            f"http://data.ekape.or.kr/openapi-data/service/user/grade/confirm/issueNo?animalNo={animal_no}&ServiceKey={key}"))
        issue_node = root1.find(".//issueNo")
        if issue_node is None or not issue_node.text:
            return None
        issue_no = issue_node.text.strip()
        root2 = ET.fromstring(_get(
            f"http://data.ekape.or.kr/openapi-data/service/user/grade/confirm/cattle?issueNo={urllib.parse.quote(issue_no)}&ServiceKey={key}"))
        item = root2.find(".//item")
        if item is None:
            return None

        def get_t(tag):
            n = item.find(tag)
            return n.text if n is not None else None

        def to_f(v):
            try:
                return float(v) if v else None
            except (TypeError, ValueError):
                return None

        # judgeSexNm: "거세" / "암" / "수" — DB 의 gender 와 같은 표기로
        sex_nm = (get_t("judgeSexNm") or "").strip()
        gender = "거세" if "거세" in sex_nm else ("암" if "암" in sex_nm else ("수" if "수" in sex_nm else None))
        return {
            "animal_no": animal_no,
            "gender": gender,
            "costAmt": to_f(get_t("costAmt")),
            "carcass_weight": to_f(get_t("weight")),
            "grade_quality": get_t("qgrade"),
            "grade_yield": get_t("wgrade"),
            "bms": to_f(get_t("insfat")),
            "backfat": to_f(get_t("backfat")),
            "ribeye": to_f(get_t("rea")),
            "month_age": to_f(get_t("birthmonth")),
            # abattDate=도축일자, judgeDate=등급판정일(도축 다음날)
            "slaughter_date": get_t("abattDate") or get_t("judgeDate"),
        }
    except Exception as e:
        log.warning("이력제 조회 실패 (%s…): %s", animal_no[:6], type(e).__name__)
        return None
