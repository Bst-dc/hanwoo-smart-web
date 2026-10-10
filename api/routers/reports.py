"""메뉴 4: 3단계 · AI 리포트 — Claude 로 컨설팅 리포트를 만들어 화면에 흘려 보내고, 성공하면 저장한다."""
import json
import logging
import urllib.parse

from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse

from .. import db
from ..auth import require_auth
from ..db import get_db
from ..models import ReportHtmlRequest, ReportRequest, ReportStatus
from ..services import ai_report
from ..services.backup import persist_db
from .shipments import get_farm

log = logging.getLogger(__name__)
router = APIRouter(tags=["3단계 · AI 리포트"], dependencies=[Depends(require_auth)])

# 리포트는 몇 분 걸려서, 응답을 흘려 보내는 동안 쓸 연결은 요청 의존성과 따로 연다 (시험에서는 바꿔 끼운다)
connect = db.connect


@router.get("/api/report/status", response_model=ReportStatus)
def status():
    return ReportStatus(key_configured=bool(ai_report.api_key()), knowledge_ready=bool(ai_report.load_knowledge_base()),
                        model=ai_report.MODEL)


def _line(obj) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _report_events(farm_id: int, mode: str):
    """한 줄에 JSON 하나: {"text": 조각} 이 이어지고, 마지막 줄은 {"done": ...} 또는 {"error": ...}.
    실패·잘림·빈 응답은 저장하지 않는다 → 기존에 저장된 리포트가 그대로 남는다 (기존과 같음)."""
    conn = connect()
    try:
        inp = ai_report.gather_inputs(conn, farm_id)
        yield _line({"start": True, "farm_name": inp["farm_name"], "mode": mode})
        system, prompt = ai_report.build_request(inp["farm_name"], inp["gender_data"], inp["survey"], mode == "전문")
        text = ""
        try:
            for chunk in ai_report.stream_report(system, prompt):
                text += chunk
                yield _line({"text": chunk})
        except ai_report.ReportError as e:
            log.warning("AI 리포트 실패: 농가 %s, %s", farm_id, e)
            yield _line({"error": str(e)})
            return
        if not text.strip():
            yield _line({"error": "Claude 가 빈 응답을 보냈습니다. 잠시 후 다시 시도해주세요. (저장하지 않았습니다)"})
            return
        if inp["visit_id"] is None:
            yield _line({"done": True, "saved": False, "visit_id": None, "backup": None,
                         "message": "이 농가는 방문 기록이 없어 리포트를 DB 에 저장하지 않았습니다. 필요하면 파일로 내려받으세요."})
            return
        try:
            ai_report.save_report(conn, inp["visit_id"], mode, text)
            conn.commit()
        except Exception:
            conn.rollback()
            log.exception("AI 리포트 저장 실패: 농가 %s", farm_id)
            yield _line({"error": "리포트는 만들어졌지만 DB 에 저장하지 못했습니다. 아래에서 파일로 내려받아 두세요."})
            return
        log.info("AI 리포트 저장: 농가 %s, 방문 %s, %s, %d자", farm_id, inp["visit_id"], mode, len(text))
        yield _line({"done": True, "saved": True, "visit_id": inp["visit_id"],
                     "backup": persist_db("AI 리포트 저장").model_dump(), "message": "AI 리포트가 DB에 저장되었습니다."})
    except Exception:
        log.exception("AI 리포트 처리 중 오류: 농가 %s", farm_id)
        yield _line({"error": "리포트를 만드는 중 서버 오류가 났습니다. 잠시 후 다시 시도해주세요."})
    finally:
        conn.close()


@router.post("/api/farms/{farm_id}/report")
def generate(farm_id: int, body: ReportRequest, conn=Depends(get_db)):
    get_farm(conn, farm_id)
    return StreamingResponse(_report_events(farm_id, body.mode), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/report/html", response_class=Response)
def report_html(body: ReportHtmlRequest, conn=Depends(get_db)):
    farm = get_farm(conn, body.farm_id)
    html = ai_report.build_report_html(farm["farm_name"], body.markdown, body.mode)
    filename = f"{farm['farm_name']}_AI컨설팅리포트_{body.mode}.html"
    return Response(content=html, media_type="text/html; charset=utf-8", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"})
