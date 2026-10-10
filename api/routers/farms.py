import json
import logging
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..auth import require_auth
from ..db import IntegrityErrors, get_db
from ..models import FarmCreate, FarmCreated, FarmOption
from ..services.backup import persist_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/farms", tags=["농가"], dependencies=[Depends(require_auth)])


def survey_regions(conn) -> dict[int, str]:
    """농가별로 방문조사표에 적힌 가장 최근 지역 (기존 앱 사이드바와 같은 규칙: 방문일 오름차순으로 덮어쓰기)."""
    rows = conn.execute("""
        SELECT v.farm_id, fs.survey_data
        FROM visits v
        JOIN field_surveys fs ON v.id = fs.visit_id
        WHERE fs.survey_data IS NOT NULL
        ORDER BY v.visit_date ASC
    """).fetchall()
    regions = {}
    for r in rows:
        try:
            data = json.loads(r["survey_data"])
        except (TypeError, ValueError):
            log.warning("농가 %s 조사표 JSON 을 읽지 못함", r["farm_id"])
            continue
        if data and data.get("region"):
            regions[r["farm_id"]] = data["region"]
    return regions


@router.get("", response_model=list[FarmOption])
def list_farms(conn=Depends(get_db)):
    """농가 선택 목록. 최근 등록 순. 표시 이름이 겹치면 뒤 농가에 '#농가ID' 를 붙인다(build_farm_options)."""
    farms = conn.execute("SELECT * FROM farms ORDER BY id DESC").fetchall()
    regions = survey_regions(conn)
    out, seen = [], set()
    for f in farms:
        region = regions.get(f["id"], f["region"])
        label = f"{f['farm_name']} ({f['owner_name'] or '대표자'}, {region or '지역'})"
        if label in seen:
            label = f"{label} #{f['id']}"
        seen.add(label)
        out.append(FarmOption(
            id=f["id"], label=label, farm_name=f["farm_name"], farm_code=f["farm_code"],
            owner_name=f["owner_name"], region=region, breeding_type=f["breeding_type"],
            total_heads=f["total_heads"],
        ))
    return out


def find_duplicate(conn, name: str, code: str):
    """이름 또는 조합원번호가 기존 농가와 정확히 같은 첫 농가.
    같은 농가를 또 등록하면 farm_id 가 둘로 쪼개져 출하성적과 조사표가 영영 연결되지 않는다 (과거에 실제로 겪은 문제)."""
    if not (name or code):
        return None
    for r in conn.execute("SELECT * FROM farms ORDER BY id DESC").fetchall():
        if (name and str(r["farm_name"] or "").strip() == name) or (code and str(r["farm_code"] or "").strip() == code):
            return r
    return None


@router.get("/duplicate", response_model=FarmOption | None)
def check_duplicate(name: str = "", code: str = "", conn=Depends(get_db)):
    """입력하는 동안 화면이 미리 경고를 띄우는 데 쓴다. 없으면 null."""
    r = find_duplicate(conn, name.strip(), code.strip())
    if r is None:
        return None
    return FarmOption(id=r["id"], label=r["farm_name"], farm_name=r["farm_name"], farm_code=r["farm_code"],
                      owner_name=r["owner_name"], region=r["region"], breeding_type=r["breeding_type"],
                      total_heads=r["total_heads"])


@router.post("", response_model=FarmCreated, status_code=201,
             responses={409: {"description": "같은 농가가 이미 있음(confirm_duplicate 로 강행 가능) 또는 조합원번호 중복"}})
def create_farm(body: FarmCreate, conn=Depends(get_db)):
    name, code = body.farm_name.strip(), body.farm_code.strip()
    if not name:
        return JSONResponse(status_code=422, content={"detail": "농가명을 입력해주세요."})
    dup = find_duplicate(conn, name, code)
    if dup is not None and not body.confirm_duplicate:
        return JSONResponse(status_code=409, content={
            "detail": (f"이미 등록된 농가와 일치합니다 — {dup['farm_name']} ({dup['owner_name'] or '대표자 미입력'}, "
                       f"{dup['region'] or '지역 미입력'}, 조합원번호 {dup['farm_code'] or '미입력'}). "
                       "같은 농가라면 다시 등록하지 말고 '현재 컨설팅 농가 선택'에서 이 농가를 고르세요. "
                       "여기서 새로 저장하면 출하성적과 조사표가 서로 다른 농가로 쪼개져 연결되지 않습니다."),
            "duplicate_id": dup["id"],
        })
    final_code = code or f"F{int(datetime.now().timestamp()) % 10000}"
    try:
        new_id = conn.execute(
            "INSERT INTO farms (farm_code, farm_name, owner_name, region, breeding_type, total_heads)"
            " VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
            (final_code, name, body.owner_name, body.region, body.breeding_type, body.total_heads),
        ).fetchone()[0]
        conn.commit()
    except IntegrityErrors as e:
        conn.rollback()
        # farm_code 는 UNIQUE 라서 '그래도 등록' 을 해도 같은 조합원번호로는 저장할 수 없다.
        # Supabase 어댑터는 제약 위반을 모두 IntegrityError 로 던지므로 UNIQUE 위반만 골라 안내한다.
        if not isinstance(e, sqlite3.IntegrityError) and "UNIQUE" not in str(e):
            raise
        return JSONResponse(status_code=409, content={"detail": (
            f"조합원번호 '{code or '(자동생성 번호)'}'가 이미 다른 농가에 등록되어 있어 저장하지 못했습니다."
            " 별개의 농가라면 조합원번호를 다르게 입력해주세요.")})
    log.info("신규 농가 등록: id=%s", new_id)
    backup = persist_db("신규 농가 등록")
    farm = next(f for f in list_farms(conn) if f.id == new_id)
    return FarmCreated(farm=farm, backup=backup.model_dump())
