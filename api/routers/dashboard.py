from fastapi import APIRouter, Depends

from ..auth import require_login
from ..db import get_conn
from ..services import dashboard

router = APIRouter(prefix="/api", tags=["대시보드"], dependencies=[Depends(require_login)])


@router.get("/dashboard")
def get_dashboard(conn=Depends(get_conn)):
    """종합 현황 대시보드 한 화면에 필요한 값 전부 (KPI · 연도별 추이 · 거세우/암소 비교 · 전국 평균 출처)."""
    return dashboard.build(conn)
