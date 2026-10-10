"""메뉴 2: 1단계 · 출하성적 비교분석 — 이력제 조회·저장, 엑셀 적재, 전국 1:1 비교, 인쇄 리포트."""
import logging
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from ..auth import require_auth
from ..db import get_db
from ..models import (Comparison, EkapeLookupRequest, EkapeLookupResult, ExcelPreview, SaveDraftsRequest,
                      SaveResult, ShipmentDraft)
from ..services import ekape, national_stats, print_report, shipments
from ..services.backup import persist_db

log = logging.getLogger(__name__)
router = APIRouter(tags=["1단계 · 출하성적"], dependencies=[Depends(require_auth)])
MAX_EXCEL_BYTES = 10 * 1024 * 1024


def get_farm(conn, farm_id: int):
    row = conn.execute("SELECT id, farm_name, farm_code, region FROM farms WHERE id = ?", (farm_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="농가를 찾을 수 없습니다. 농가 목록을 새로 고쳐주세요.")
    return row


# ---------------------------------------------------------------- 이력제
@router.post("/api/ekape/lookup", response_model=EkapeLookupResult)
def ekape_lookup(body: EkapeLookupRequest):
    """이력번호로 축평원 도체성적을 가져온다 (저장하지 않음 — 화면에서 검토한 뒤 저장)."""
    if not ekape.api_key():
        return EkapeLookupResult(key_configured=False, records=[], not_found=body.animal_nos)
    # 한 두당 축평원 호출이 두 번이라 동시에 4개씩 묻는다 (순서는 입력 순서대로 돌려준다)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(ekape.fetch_cattle_grade, body.animal_nos))
    found = [ShipmentDraft(**r) for r in results if r]
    missing = [no for no, r in zip(body.animal_nos, results) if not r]
    log.info("이력제 조회 %d건 → 성공 %d, 실패 %d", len(body.animal_nos), len(found), len(missing))
    return EkapeLookupResult(key_configured=True, records=found, not_found=missing)


@router.post("/api/farms/{farm_id}/shipments/ekape", response_model=SaveResult)
def save_ekape(farm_id: int, body: SaveDraftsRequest, conn=Depends(get_db)):
    get_farm(conn, farm_id)
    if not body.records:
        raise HTTPException(status_code=422, detail="저장할 데이터가 없습니다.")
    try:
        saved = shipments.save_ekape_records(conn, farm_id, [r.model_dump() for r in body.records])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    log.info("이력제 출하성적 저장: 농가 %s, %d두", farm_id, saved)
    return SaveResult(saved=saved, backup=persist_db("출하성적 API 저장").model_dump())


# ---------------------------------------------------------------- 엑셀
async def _read_upload(file: UploadFile):
    data = await file.read()
    if len(data) > MAX_EXCEL_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (10MB 까지).")
    try:
        return shipments.read_excel(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀 읽기 오류: {e}")


@router.post("/api/farms/{farm_id}/shipments/excel/preview", response_model=ExcelPreview)
async def excel_preview(farm_id: int, file: UploadFile = File(...), conn=Depends(get_db)):
    farm = get_farm(conn, farm_id)
    df = await _read_upload(file)
    return ExcelPreview(**shipments.excel_preview(df, farm["farm_name"]))


@router.post("/api/farms/{farm_id}/shipments/excel", response_model=SaveResult)
async def excel_save(farm_id: int, file: UploadFile = File(...), confirm_name_mismatch: bool = Form(False),
                     conn=Depends(get_db)):
    farm = get_farm(conn, farm_id)
    df = await _read_upload(file)
    preview = shipments.excel_preview(df, farm["farm_name"])
    if preview["mismatched_names"] and not confirm_name_mismatch:
        return JSONResponse(status_code=409, content={"detail": (
            f"파일 안의 이름({', '.join(preview['mismatched_names'])})이 현재 선택된 농가 {farm['farm_name']}와(과) 다릅니다."
            " 다른 농가 파일을 잘못 올린 건 아닌지 확인해주세요.")})
    try:
        saved = shipments.save_excel(conn, farm_id, df)
        conn.commit()
    except Exception as e:
        # 한 행이라도 실패하면 아무것도 저장하지 않는다 (기존과 같음: 끝에서 한 번에 commit)
        conn.rollback()
        log.exception("엑셀 적재 실패: 농가 %s", farm_id)
        raise HTTPException(status_code=400, detail=f"엑셀 처리 오류: {e}")
    log.info("엑셀 출하성적 저장: 농가 %s, %d두", farm_id, saved)
    return SaveResult(saved=saved, backup=persist_db("출하성적 엑셀 저장").model_dump())


# ---------------------------------------------------------------- 비교·리포트
@router.get("/api/farms/{farm_id}/comparison", response_model=Comparison)
def comparison(farm_id: int, year: int | None = Query(None, ge=2000, le=2100),
               gender: Literal["거세", "암"] | None = None, conn=Depends(get_db)):
    """전국 1:1 비교분석표, 수익성 추정, 최근 3년 추이, 개체별 성적. year 가 없으면 전체 누적."""
    get_farm(conn, farm_id)
    return shipments.comparison(conn, farm_id, year, gender)


@router.get("/api/farms/{farm_id}/print-report", response_class=Response)
def print_report_html(farm_id: int, conn=Depends(get_db)):
    """방문용 A4 3페이지 인쇄 리포트 (.html 내려받기)."""
    farm = get_farm(conn, farm_id)
    html = print_report.build_print_comparison_report_html(farm["farm_name"], farm_id, conn, national_stats.national_stats())
    filename = f"{farm['farm_name']}_출하성적_비교_리포트.html"
    return Response(content=html, media_type="text/html; charset=utf-8", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"})
