"""2단계 · 현장방문조사 API — 양식, 방문 목록, 조사표 읽기·새로 쓰기·고치기. 저장 뒤 GitHub 백업."""
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import backup
from ..auth import require_login
from ..db import get_conn
from ..services import shipments, surveys
from ..services.surveys import SurveyError

router = APIRouter(prefix="/api", tags=["현장조사"], dependencies=[Depends(require_login)])


def _farm(conn, farm_id: int) -> dict:
    farm = shipments.farm_info(conn, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="농가를 찾을 수 없습니다. 농가 목록을 새로 고쳐주세요.")
    return farm


class SurveyIn(BaseModel):
    values: dict[str, Any]


@router.get("/surveys/form")
def form():
    """조사표 양식(항목·선택지·기본값)과 지역 날씨. 화면이 이것으로 양식을 그린다."""
    return surveys.form_schema()


@router.get("/farms/{farm_id}/visits")
def visit_list(farm_id: int, conn=Depends(get_conn)):
    farm = _farm(conn, farm_id)
    return {"farm": farm, "visits": surveys.visits(conn, farm_id), "blank": surveys.blank(date.today())}


@router.get("/farms/{farm_id}/visits/{visit_id}")
def visit_read(farm_id: int, visit_id: int, conn=Depends(get_conn)):
    _farm(conn, farm_id)
    d = surveys.read(conn, farm_id, visit_id, date.today())
    if d is None:
        raise HTTPException(status_code=404, detail="이 농가의 방문 기록이 아닙니다. 목록을 새로 고쳐주세요.")
    return d


@router.post("/farms/{farm_id}/visits")
def visit_create(farm_id: int, body: SurveyIn, conn=Depends(get_conn)):
    farm = _farm(conn, farm_id)
    try:
        r = surveys.create(conn, farm_id, body.values)
    except SurveyError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return {**r, "farm": farm["name"], "backup": backup.run("현장조사 신규 저장")}


@router.put("/farms/{farm_id}/visits/{visit_id}")
def visit_update(farm_id: int, visit_id: int, body: SurveyIn, conn=Depends(get_conn)):
    farm = _farm(conn, farm_id)
    try:
        r = surveys.update(conn, farm_id, visit_id, body.values)
    except SurveyError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if r is None:
        raise HTTPException(status_code=404, detail="이 농가의 방문 기록이 아닙니다. 목록을 새로 고쳐주세요.")
    return {**r, "farm": farm["name"], "backup": backup.run("현장조사 수정 저장")}
