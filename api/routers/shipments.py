from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_login
from ..db import get_conn
from ..services import shipments

router = APIRouter(prefix="/api", tags=["출하성적"], dependencies=[Depends(require_login)])


@router.get("/farms/{farm_id}/shipments")
def farm_shipments(farm_id: int, year: int | None = Query(None, ge=1990, le=2100),
                   gender: str | None = Query(None, pattern="^(거세|암)$"), conn=Depends(get_conn)):
    """농가 한 곳의 출하성적 전국 1:1 비교분석 (연도·성별은 선택). 조회만 한다."""
    farm = shipments.farm_info(conn, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="농가를 찾을 수 없습니다. 농가 목록을 새로 고쳐주세요.")
    return {"farm": farm, **shipments.build(conn, farm_id, year, gender)}
