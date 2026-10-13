"""출하성적 입력 — 축평원 조회 결과와 엑셀 파일을 shipment_records 에 저장한다.

저장 SQL 과 값 규칙(성별·도축일자 기본값·단가 계산)은 기존 앱(streamlit_app.py 메뉴 2)에서 그대로 옮겼다.
- 축평원: 이력번호가 이미 있으면 그 행을 새 값으로 고친다(단가·금액 포함). data_source='ekape_api'
- 엑셀: 같지만 단가·금액(price_per_kg, total_price)은 건드리지 않는다. data_source='excel'
기존 앱과 일부러 다르게 한 곳 (조용히 잘못 저장되던 경우를 막는다):
- 엑셀은 첫 시트가 아니라 '이력번호 칸이 있는 시트'를 읽는다. 실제 '농가출하데이터.xlsx' 는 첫 시트가 작업 기록이라
  기존 앱에서는 0두를 저장하고도 성공이라고 나왔다.
- 이름 칸에 '최종농장주' 도 넣고, 기본은 '이 농가 이름과 같은 행만' 저장한다 (여러 농가가 섞인 파일을 올려도
  다른 농가 성적이 이 농가로 옮겨지지 않게). 파일 전체를 저장하려면 확인을 받는다.
- 빈 도축일자는 'nan' 글자 대신 기존 기본값(2025-01-01)으로, 20230202·2023.02.02 는 2023-02-02 로 맞춘다.
- 다른 농가에 이미 있는 이력번호는 저장하면 이 농가로 옮겨진다(기존과 같음). 미리보기에서 알려 주고 확인을 받는다.
- 저장은 전부 되거나 전부 안 된다 (중간에 오류가 나면 되돌린다).
"""
import io
import logging
import math
import re
from collections import Counter

import pandas as pd

from .ekape import normalize_animal_no

log = logging.getLogger("consulting.shipment_input")

DEFAULT_DATE = "2025-01-01"     # 기존 앱: 도축일자를 모를 때 넣던 값
DEFAULT_YEAR = 2025

API_SQL = """
INSERT INTO shipment_records (
    farm_id, animal_no, gender, slaughter_date, slaughter_year, month_age,
    carcass_weight, grade_quality, grade_yield, bms, backfat, ribeye, price_per_kg, total_price, data_source
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ekape_api')
ON CONFLICT(animal_no) DO UPDATE SET
    farm_id = excluded.farm_id, gender = excluded.gender, slaughter_date = excluded.slaughter_date,
    slaughter_year = excluded.slaughter_year, month_age = excluded.month_age,
    carcass_weight = excluded.carcass_weight, grade_quality = excluded.grade_quality,
    grade_yield = excluded.grade_yield, bms = excluded.bms, backfat = excluded.backfat,
    ribeye = excluded.ribeye, price_per_kg = excluded.price_per_kg,
    total_price = excluded.total_price, data_source = excluded.data_source
"""

EXCEL_SQL = """
INSERT INTO shipment_records (
    farm_id, animal_no, gender, slaughter_date, slaughter_year, month_age,
    carcass_weight, grade_quality, grade_yield, bms, backfat, ribeye, data_source
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'excel')
ON CONFLICT(animal_no) DO UPDATE SET
    farm_id = excluded.farm_id, gender = excluded.gender, slaughter_date = excluded.slaughter_date,
    slaughter_year = excluded.slaughter_year, month_age = excluded.month_age,
    carcass_weight = excluded.carcass_weight, grade_quality = excluded.grade_quality,
    grade_yield = excluded.grade_yield, bms = excluded.bms, backfat = excluded.backfat,
    ribeye = excluded.ribeye, data_source = excluded.data_source
"""

# 엑셀 칸 이름 (기존 앱과 같다)
COL_MAP = {
    "이력번호": ["이력번호", "개체번호", "개체식별번호"],
    "성별": ["성별", "구분"],
    "도축일자": ["도축일자", "출하일자"],
    "도체중": ["도체중", "도체중량"],
    "육질등급": ["육질등급"],
    "육량등급": ["육량등급"],
    "BMS": ["근내지방도", "BMS"],
    "등지방": ["등지방두께", "등지방"],
    "단면적": ["등심단면적", "단면적"],
    "월령": ["도축개월령", "출하월령"],
}
# 농가 이름 칸. '최종농장주' 는 이력제에서 받은 파일(농가출하데이터.xlsx)의 이름 칸이다.
NAME_COLS = ["농가명", "조합원명", "성명", "대표자명", "최종농장주"]


class InputError(ValueError):
    """사용자에게 그대로 보여 줄 입력 오류."""


# ---------------------------------------------------------------- 값 다듬기
def _blank(v) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def num(v):
    """숫자 칸에 '-'·'' 같은 글자가 있으면 빈 값 (Postgres 숫자 컬럼은 글자를 거부한다)."""
    try:
        f = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def grade_text(v):
    """빈 칸(NaN)을 'nan' 글자로 저장하지 않는다."""
    if _blank(v):
        return None
    v = str(v).strip()
    return v or None


def excel_gender(v) -> str:
    """기존 앱 규칙: 비었거나 '거세' 포함 → 거세, '암' → 암, '수' → 수, 그 밖은 암."""
    g = "" if _blank(v) else str(v).strip()
    if not g or "거세" in g:
        return "거세"
    if "암" in g:
        return "암"
    if "수" in g:
        return "수"
    return "암"


def excel_date(v) -> tuple[str, int, bool]:
    """반환: (도축일자, 도축연도, 비어서 기본값을 넣었는지)."""
    if _blank(v) or not str(v).strip():
        return DEFAULT_DATE, DEFAULT_YEAR, True
    s = re.sub(r"\.0+$", "", str(v).strip())
    if m := re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s):
        s = "-".join(m.groups())
    elif m := re.fullmatch(r"(\d{4})\s*[./]\s*(\d{1,2})\s*[./]\s*(\d{1,2})\.?", s):
        s = f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
    s = s[:10]
    try:
        year = int(s[:4])
    except ValueError:
        year = DEFAULT_YEAR
    return s, year, False


# ---------------------------------------------------------------- 축평원 조회분
def _or_zero(v):
    """기존 앱의 `v if pd.notna(v) and v else 0`."""
    return v if isinstance(v, (int, float)) and not _blank(v) and v else 0


def api_params(farm_id: int, r: dict):
    """축평원 성적 한 두 → API_SQL 값. 이력번호가 없으면 None (건너뜀). 규칙은 기존 앱과 같다."""
    ano = normalize_animal_no(r.get("animal_no"))
    if not ano:
        return None
    sdate = r.get("slaughter_date")
    sdate = str(sdate) if isinstance(sdate, str) and sdate.strip() else DEFAULT_DATE
    try:
        syear = int(sdate[:4])
    except ValueError:
        syear = DEFAULT_YEAR
    cw = _or_zero(r.get("carcass_weight"))
    cost = _or_zero(r.get("costAmt"))
    total_price = int(cw * cost)
    # 축평원 판정 성별(judgeSexNm)을 쓴다. 응답에 성별이 없을 때만 거세로 간주
    gender = r.get("gender")
    gender = gender if isinstance(gender, str) and gender.strip() else "거세"
    return (farm_id, ano, gender.strip(), sdate, syear, r.get("month_age"),
            r.get("carcass_weight"), r.get("grade_quality"), r.get("grade_yield"), r.get("bms"),
            r.get("backfat"), r.get("ribeye"), cost, total_price)


# ---------------------------------------------------------------- 엑셀
def read_sheet(data: bytes) -> tuple[str, pd.DataFrame]:
    """이력번호 칸이 있는 첫 시트를 찾는다."""
    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    except Exception as e:
        log.warning("엑셀 읽기 실패: %s", e)
        raise InputError(f"엑셀 파일을 읽지 못했습니다 ({type(e).__name__}). .xlsx 파일인지 확인해주세요.") from None
    for name, df in sheets.items():
        df.columns = [str(c).strip() for c in df.columns]
        if any(k in df.columns for k in COL_MAP["이력번호"]):
            return name, df
    raise InputError("이력번호(또는 개체번호·개체식별번호) 칸이 있는 시트를 찾지 못했습니다.")


def parse_excel(data: bytes) -> dict:
    sheet, df = read_sheet(data)
    col = {k: next((c for c in keys if c in df.columns), None) for k, keys in COL_MAP.items()}
    name_col = next((c for c in NAME_COLS if c in df.columns), None)
    get = lambda row, key: row.get(col[key]) if col[key] else None   # noqa: E731
    rows, invalid = [], 0
    for _, row in df.iterrows():
        ano = normalize_animal_no(get(row, "이력번호"))
        if not ano or len(ano) < 8:
            invalid += 1
            continue
        sdate, syear, date_missing = excel_date(get(row, "도축일자"))
        name = row.get(name_col) if name_col else None
        rows.append({
            "animal_no": ano, "gender": excel_gender(get(row, "성별")),
            "slaughter_date": sdate, "slaughter_year": syear, "date_missing": date_missing,
            "month_age": num(get(row, "월령")), "carcass_weight": num(get(row, "도체중")),
            "grade_quality": grade_text(get(row, "육질등급")), "grade_yield": grade_text(get(row, "육량등급")),
            "bms": num(get(row, "BMS")), "backfat": num(get(row, "등지방")), "ribeye": num(get(row, "단면적")),
            "name": "" if _blank(name) else str(name).strip(),
        })
    log.info("엑셀 해석: 시트 %s, %d행 중 이력번호 정상 %d, 건너뜀 %d", sheet, len(df), len(rows), invalid)
    return {"sheet": sheet, "total_rows": len(df), "invalid": invalid, "name_col": name_col,
            "missing_cols": [k for k, c in col.items() if c is None], "rows": rows}


def name_summary(parsed: dict, farm_name: str) -> dict | None:
    if not parsed["name_col"]:
        return None
    target = str(farm_name).strip()
    counts = Counter(r["name"] for r in parsed["rows"])
    return {"col": parsed["name_col"], "match": counts.get(target, 0), "blank": counts.get("", 0),
            "others": [{"name": n, "count": c} for n, c in counts.most_common() if n not in (target, "")]}


def choose_rows(parsed: dict, farm_name: str, mode: str) -> list[dict]:
    """mode='match' 이고 이름 칸이 있으면 이 농가 이름 행만, 아니면 전부."""
    if parsed["name_col"] and mode == "match":
        target = str(farm_name).strip()
        return [r for r in parsed["rows"] if r["name"] == target]
    return parsed["rows"]


def excel_params(farm_id: int, r: dict):
    return (farm_id, r["animal_no"], r["gender"], r["slaughter_date"], r["slaughter_year"], r["month_age"],
            r["carcass_weight"], r["grade_quality"], r["grade_yield"], r["bms"], r["backfat"], r["ribeye"])


# ---------------------------------------------------------------- 공통
def ownership(conn, farm_id: int, animal_nos: list[str]) -> dict:
    """저장하면 어떻게 되는지: 새로 들어감 / 이 농가 것을 고침 / 다른 농가에서 이 농가로 옮겨짐."""
    owner = {}
    uniq = list(dict.fromkeys(animal_nos))
    for i in range(0, len(uniq), 500):
        part = uniq[i:i + 500]
        sql = f"""SELECT s.animal_no, s.farm_id, f.farm_name FROM shipment_records s
                  LEFT JOIN farms f ON f.id = s.farm_id WHERE s.animal_no IN ({",".join("?" * len(part))})"""
        for r in conn.execute(sql, part).fetchall():
            owner[r[0]] = (r[1], r[2])
    status, moved = {}, Counter()
    for a in uniq:
        if a not in owner:
            status[a] = "new"
        elif owner[a][0] == farm_id:
            status[a] = "update"
        else:
            status[a] = "move"
            moved[owner[a][1] or f"농가 {owner[a][0]}"] += 1
    c = Counter(status.values())
    return {"new": c["new"], "update": c["update"], "move": c["move"],
            "moved_from": [{"farm": n, "count": k} for n, k in moved.most_common()], "status": status}


def _save(conn, sql: str, params: list[tuple]) -> int:
    try:
        for p in params:
            conn.execute(sql, p)
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("출하성적 저장 실패 — 되돌림 (%d건)", len(params))
        raise
    return len(params)


def save_api(conn, farm_id: int, records: list[dict]) -> dict:
    params = [p for p in (api_params(farm_id, r) for r in records) if p]
    _save(conn, API_SQL, params)
    log.info("축평원 성적 저장: 농가 %s, %d두 (건너뜀 %d)", farm_id, len(params), len(records) - len(params))
    return {"saved": len({p[1] for p in params}), "skipped": len(records) - len(params)}


def save_excel(conn, farm_id: int, rows: list[dict]) -> dict:
    params = [excel_params(farm_id, r) for r in rows]
    _save(conn, EXCEL_SQL, params)
    log.info("엑셀 성적 저장: 농가 %s, %d행", farm_id, len(params))
    return {"saved": len({p[1] for p in params}), "rows": len(params)}
