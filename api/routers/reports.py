"""3단계 · AI 리포트 API — 만들기(백그라운드 작업)·진행 보기·취소, 저장된 리포트 보기·내려받기."""
import urllib.parse
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from .. import backup
from ..auth import require_login
from ..db import get_conn
from ..services import ai_report, report_data, shipments
from ..services.ai_report import ReportError

router = APIRouter(prefix="/api", tags=["AI 리포트"], dependencies=[Depends(require_login)])


def _farm(conn, farm_id: int) -> dict:
    farm = shipments.farm_info(conn, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="농가를 찾을 수 없습니다. 농가 목록을 새로 고쳐주세요.")
    return farm


def _job(job_id: str) -> dict:
    job = ai_report.JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="리포트 작업을 찾을 수 없습니다. 서버가 다시 시작되었을 수 있습니다.")
    return job


@router.get("/farms/{farm_id}/reports")
def report_list(farm_id: int, conn=Depends(get_conn)):
    farm = _farm(conn, farm_id)
    visit = report_data.last_visit(conn, farm_id)
    running = ai_report.running_for(farm_id)
    return {"farm": farm, "last_visit": {k: visit[k] for k in ("id", "visit_number", "visit_date")} if visit else None,
            "reports": ai_report.list_reports(conn, farm_id), "running_job": running["id"] if running else None,
            "api_key": ai_report.has_api_key(), "knowledge": ai_report.knowledge_ready(), "model": ai_report.MODEL}


class StartIn(BaseModel):
    mode: Literal["전문", "일반"]


@router.post("/farms/{farm_id}/reports")
def report_start(farm_id: int, body: StartIn, conn=Depends(get_conn)):
    farm = _farm(conn, farm_id)
    if not ai_report.has_api_key():
        raise HTTPException(status_code=503, detail="Anthropic API 키(ANTHROPIC_API_KEY)가 서버에 설정되지 않았습니다.")
    try:
        job = ai_report.start(farm_id, farm["name"], body.mode)
    except ReportError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return {"job_id": job["id"]}


@router.get("/report-jobs/{job_id}")
def job_view(job_id: str, offset: int = Query(0, ge=0)):
    return ai_report.view(_job(job_id), offset)


@router.post("/report-jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    job = _job(job_id)
    if job["status"] == "running":
        job["cancel"] = True
    return {"ok": True}


@router.get("/reports/{report_id}")
def report_read(report_id: int, conn=Depends(get_conn)):
    r = ai_report.get_report(conn, report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    return {**{k: v for k, v in r.items() if k != "markdown"}, "html": ai_report.to_html(r["markdown"]), "length": len(r["markdown"])}


@router.get("/reports/{report_id}/source")
def report_source(report_id: int, conn=Depends(get_conn)):
    """고치기용 마크다운 원문."""
    r = ai_report.get_report(conn, report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    return {"id": r["id"], "markdown": r["markdown"]}


class EditIn(BaseModel):
    markdown: str


@router.put("/reports/{report_id}")
def report_edit(report_id: int, body: EditIn, conn=Depends(get_conn)):
    try:
        found = ai_report.update_text(conn, report_id, body.markdown)
    except ReportError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if not found:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다. 목록을 새로 고쳐주세요.")
    return {"id": report_id, "length": len(body.markdown), "backup": backup.run("AI 리포트 수정 저장")}


@router.get("/reports/{report_id}/download")
def report_download(report_id: int, fmt: Literal["md", "html"] = "html", inline: bool = False, conn=Depends(get_conn)):
    """inline=1 이면 내려받지 않고 브라우저 새 탭에서 바로 연다 (HTML)."""
    r = ai_report.get_report(conn, report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    name = f"{r['farm']}_AI컨설팅리포트_{r['mode']}.{fmt}"
    body = r["markdown"] if fmt == "md" else ai_report.html_document(r["farm"], r["markdown"], r["mode"])
    media = "text/markdown; charset=utf-8" if fmt == "md" else "text/html; charset=utf-8"
    how = "inline" if inline and fmt == "html" else "attachment"
    headers = {"Content-Disposition": f"{how}; filename*=UTF-8''{urllib.parse.quote(name)}"}
    if how == "inline":   # 리포트 글은 화면에 그대로 넣지 않고 마크다운에서 만든 것이지만, 스크립트는 막아 둔다
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return Response(body, media_type=media, headers=headers)
