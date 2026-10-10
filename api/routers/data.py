"""메뉴 5: 데이터 관리 · 백업 — 누적 DB 표 조회, CSV·리포트 내려받기, DB 파일 백업."""
import logging
import urllib.parse
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..auth import require_auth
from ..db import get_db
from ..services import ai_report, backup, data_export
from .shipments import get_farm

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/data", tags=["데이터 관리 · 백업"], dependencies=[Depends(require_auth)])


def _attachment(filename: str) -> dict:
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"}


@router.get("/tables")
def tables(farm_id: int | None = Query(None), conn=Depends(get_db)):
    """농가 마스터·출하성적·방문 이력·AI 리포트 목록. farm_id 가 없으면 전체."""
    if farm_id is not None:
        get_farm(conn, farm_id)
    return {name: data_export.table(conn, name, farm_id) for name in data_export.TABLES}


@router.get("/export/{name}.csv", response_class=Response)
def export_csv(name: Literal["farms", "shipments", "visits"], farm_id: int | None = Query(None), conn=Depends(get_db)):
    if farm_id is not None:
        get_farm(conn, farm_id)
    return Response(content=data_export.csv_bytes(conn, name, farm_id), media_type="text/csv; charset=utf-8",
                    headers=_attachment(data_export.CSV_NAMES[name]))


@router.get("/reports/{report_id}")
def report(report_id: int, conn=Depends(get_db)):
    r = data_export.get_report(conn, report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다. 목록을 새로 고쳐주세요.")
    return r


@router.get("/reports/{report_id}/html", response_class=Response)
def report_html(report_id: int, conn=Depends(get_db)):
    r = data_export.get_report(conn, report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다. 목록을 새로 고쳐주세요.")
    html = ai_report.build_report_html(r["farm_name"], r["markdown"], r["report_mode"])
    return Response(content=html, media_type="text/html; charset=utf-8",
                    headers=_attachment(f"{r['farm_name']}_AI리포트_{r['report_mode']}_{r['id']}.html"))


@router.get("/db-file", response_class=Response)
def db_file():
    """DB 전체(농가·방문·조사표·출하성적·AI 리포트)를 SQLite 파일 하나로. 몇 초 걸려서 버튼을 눌렀을 때만 만든다."""
    data, err = backup.db_file_bytes()
    if err:
        raise HTTPException(status_code=500, detail=err)
    log.info("DB 파일 내려받기: %d KB", len(data) // 1024)
    return Response(content=data, media_type="application/octet-stream",
                    headers=_attachment(f"consulting_{datetime.now().strftime('%Y%m%d_%H%M')}.db"))
