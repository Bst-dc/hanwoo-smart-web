"""2단계 · 현장방문조사 API — 양식, 방문 목록, 조사표 읽기·새로 쓰기·고치기. 저장 뒤 GitHub 백업."""
import urllib.parse
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from .. import backup
from ..auth import require_login
from ..db import get_conn
from ..services import shipments, survey_sheet, surveys
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


@router.get("/surveys/sheet")
def sheet(farm_id: int | None = Query(None, ge=1), inline: bool = False, conn=Depends(get_conn)):
    """수기용 현장조사표(A4 인쇄 양식). farm_id 가 있으면 그 농가의 이름·번호·지역을 미리 적는다.
    inline=1 이면 새 탭에서 바로 열고(인쇄), 아니면 HTML 파일로 내려받는다."""
    farm = _farm(conn, farm_id) if farm_id else None
    name = f"현장조사표_수기용{'_' + farm['name'] if farm else '_빈양식'}.html"
    headers = {"Content-Disposition": f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{urllib.parse.quote(name)}",
               "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"}
    return Response(survey_sheet.build_html(farm), media_type="text/html; charset=utf-8", headers=headers)


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
