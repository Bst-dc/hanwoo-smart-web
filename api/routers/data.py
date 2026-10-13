"""데이터 관리 · 백업 API, 신규 농가 등록."""
import urllib.parse
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import backup
from ..auth import require_login
from ..db import get_conn
from ..services import datamgmt
from ..services.datamgmt import FarmError

router = APIRouter(prefix="/api", tags=["데이터 관리"], dependencies=[Depends(require_login)])


def _attachment(name: str) -> dict:
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(name)}"}


@router.get("/data/summary")
def data_summary(farm_id: int | None = Query(None, ge=1), conn=Depends(get_conn)):
    """표 미리보기(앞 30행)와 전체 행 수. farm_id 가 있으면 그 농가만."""
    return datamgmt.summary(conn, farm_id)


@router.get("/data/export/{kind}")
def data_export(kind: Literal["farms", "shipments", "visits"], farm_id: int | None = Query(None, ge=1), conn=Depends(get_conn)):
    return Response(datamgmt.csv_bytes(conn, kind, farm_id), media_type="text/csv; charset=utf-8",
                    headers=_attachment(datamgmt.CSV_NAMES[kind]))


@router.get("/data/db-file")
def data_db_file():
    """DB 전체(.db). 조합원 정보가 들어 있다."""
    try:
        data, name = datamgmt.db_file()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 파일을 만들지 못했습니다 ({type(e).__name__}). 저장된 데이터는 그대로입니다.") from None
    return Response(data, media_type="application/octet-stream", headers=_attachment(name))


class FarmIn(BaseModel):
    code: str = Field("", max_length=30)
    name: str = Field(max_length=60)
    owner: str = Field("", max_length=30)
    region: str = Field("", max_length=30)
    breeding_type: Literal["비육우", "일관사육", "번식우"] = "비육우"
    total_heads: int = Field(100, ge=0, le=100000)
    confirm_duplicate: bool = False


@router.get("/farms/duplicate")
def farm_duplicate(name: str = Query("", max_length=60), code: str = Query("", max_length=30), conn=Depends(get_conn)):
    return {"match": datamgmt.find_duplicate(conn, name, code)}


@router.post("/farms")
def farm_create(body: FarmIn, conn=Depends(get_conn)):
    dup = datamgmt.find_duplicate(conn, body.name, body.code)
    if dup and not body.confirm_duplicate:
        raise HTTPException(status_code=409, detail=f"이미 등록된 농가와 일치합니다: {dup['name']} (조합원번호 {dup['code'] or '미입력'}). "
                                                    "같은 농가라면 새로 등록하지 말고 위쪽에서 그 농가를 고르세요.")
    try:
        new_id = datamgmt.create_farm(conn, body.model_dump())
    except FarmError as e:
        raise HTTPException(status_code=409 if "이미" in str(e) else 422, detail=str(e)) from None
    return {"id": new_id, "name": body.name.strip(), "backup": backup.run("신규 농가 등록")}
