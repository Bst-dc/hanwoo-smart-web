"""메뉴 3: 2단계 · 현장방문조사 — 조사표 신규 작성·수정."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_auth
from ..db import get_db
from ..models import SurveyData, VisitDetail, VisitSaved, VisitSummary
from ..services import survey
from ..services.backup import persist_db
from .shipments import get_farm

log = logging.getLogger(__name__)
router = APIRouter(tags=["2단계 · 현장방문조사"], dependencies=[Depends(require_auth)])


def _survey_dict(body: SurveyData) -> dict:
    data = body.model_dump(mode="json")          # visitDate → 'YYYY-MM-DD' (기존 str(date) 와 같음)
    data["feed_matrix"] = survey.full_feed_matrix(data["feed_matrix"])
    return data


@router.get("/api/survey/options")
def form_options():
    """양식 선택지·지역별 날씨(2025년 기준)·사료 표의 행과 열."""
    return survey.form_options()


@router.get("/api/farms/{farm_id}/visits", response_model=list[VisitSummary])
def list_visits(farm_id: int, conn=Depends(get_db)):
    get_farm(conn, farm_id)
    return survey.list_visits(conn, farm_id)


@router.get("/api/visits/{visit_id}", response_model=VisitDetail)
def get_visit(visit_id: int, conn=Depends(get_db)):
    v = survey.get_visit(conn, visit_id)
    if v is None:
        raise HTTPException(status_code=404, detail="방문 기록을 찾을 수 없습니다. 목록을 새로 고쳐주세요.")
    return v


@router.post("/api/farms/{farm_id}/visits", response_model=VisitSaved, status_code=201)
def create_visit(farm_id: int, body: SurveyData, conn=Depends(get_db)):
    get_farm(conn, farm_id)
    try:
        v_id, v_no = survey.create_visit(conn, farm_id, _survey_dict(body))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    log.info("현장조사 신규 저장: 농가 %s, %d차 (방문 %s)", farm_id, v_no, v_id)
    return VisitSaved(visit_id=v_id, visit_number=v_no, backup=persist_db("현장조사 신규 저장").model_dump())


@router.put("/api/visits/{visit_id}", response_model=VisitSaved)
def update_visit(visit_id: int, body: SurveyData, conn=Depends(get_db)):
    v = survey.get_visit(conn, visit_id)
    if v is None:
        raise HTTPException(status_code=404, detail="방문 기록을 찾을 수 없습니다. 목록을 새로 고쳐주세요.")
    try:
        survey.update_visit(conn, visit_id, _survey_dict(body))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    log.info("현장조사 수정 저장: 방문 %s", visit_id)
    return VisitSaved(visit_id=visit_id, visit_number=v["visit_number"], backup=persist_db("현장조사 수정 저장").model_dump())
