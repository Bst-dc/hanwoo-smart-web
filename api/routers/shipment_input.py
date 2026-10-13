"""출하성적 입력 — 축평원 이력번호 조회(저장 안 함) → 검토 → 저장, 엑셀 미리보기 → 저장.

조회·미리보기는 DB 에 쓰지 않는다. 저장만 운영 DB 에 쓰고, 저장 뒤 GitHub 백업을 한다.
다른 농가에 있던 이력번호를 옮기거나, 이름이 다른 행까지 저장할 때는 confirm=true 가 있어야 한다.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import backup
from ..auth import require_login
from ..db import get_conn
from ..services import ekape, shipment_input, shipments
from ..services.shipment_input import InputError

router = APIRouter(prefix="/api/farms/{farm_id}/shipments", tags=["출하성적 입력"], dependencies=[Depends(require_login)])

SAMPLE_ROWS = 30
MAX_EXCEL_BYTES = 10 * 1024 * 1024
Num = Annotated[float | None, Field(default=None, allow_inf_nan=False)]
Text = Annotated[str | None, Field(default=None, max_length=40)]


def _farm(conn, farm_id: int) -> dict:
    farm = shipments.farm_info(conn, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="농가를 찾을 수 없습니다. 농가 목록을 새로 고쳐주세요.")
    return farm


def _confirm_needed(detail: str):
    raise HTTPException(status_code=409, detail=detail)


# ---------------------------------------------------------------- 축평원
class LookupIn(BaseModel):
    text: str = Field(max_length=20000)


@router.post("/lookup")
def lookup(farm_id: int, body: LookupIn, conn=Depends(get_conn)):
    """이력번호로 축평원 성적을 받아 온다. 저장은 하지 않는다."""
    _farm(conn, farm_id)
    key = ekape.api_key()
    if not key:
        raise HTTPException(status_code=503, detail="축평원 API 키(EKAPE_API_KEY)가 서버에 설정되지 않았습니다.")
    nos, dup = ekape.split_input(body.text)
    if not nos:
        raise HTTPException(status_code=422, detail="올바른 이력번호를 입력해주세요. (한 줄에 하나, 8자리 이상)")
    if len(nos) > ekape.MAX_LOOKUP:
        raise HTTPException(status_code=422, detail=f"한 번에 {ekape.MAX_LOOKUP}두까지 조회할 수 있습니다. 나눠서 조회해주세요. (입력 {len(nos)}두)")
    found, failed = ekape.fetch_many(nos, key)
    own = shipment_input.ownership(conn, farm_id, [r["animal_no"] for r in found])
    return {"records": [{**r, "status": own["status"][r["animal_no"]]} for r in found], "failed": failed,
            "duplicates": dup, "ownership": {k: v for k, v in own.items() if k != "status"}}


class ApiRecord(BaseModel):
    animal_no: str = Field(max_length=30)
    gender: Text
    costAmt: Num
    carcass_weight: Num
    grade_quality: Text
    grade_yield: Text
    bms: Num
    backfat: Num
    ribeye: Num
    month_age: Num
    slaughter_date: Text


class SaveApiIn(BaseModel):
    records: list[ApiRecord] = Field(max_length=ekape.MAX_LOOKUP)
    confirm: bool = False


@router.post("/save-api")
def save_api(farm_id: int, body: SaveApiIn, conn=Depends(get_conn)):
    """검토한 축평원 성적을 저장한다 (같은 이력번호는 새 값으로 고친다)."""
    farm = _farm(conn, farm_id)
    records = [r.model_dump() for r in body.records]
    if not records:
        raise HTTPException(status_code=422, detail="저장할 성적이 없습니다.")
    own = shipment_input.ownership(conn, farm_id, [ekape.normalize_animal_no(r["animal_no"]) for r in records])
    if own["move"] and not body.confirm:
        _confirm_needed(f"{own['move']}두는 다른 농가에 이미 등록된 개체입니다. 저장하면 {farm['name']} 농가로 옮겨집니다. 확인 후 다시 저장해주세요.")
    result = shipment_input.save_api(conn, farm_id, records)
    return {**result, "farm": farm["name"], "backup": backup.run("출하성적 API 저장")}


# ---------------------------------------------------------------- 엑셀
def _read_upload(file: UploadFile) -> bytes:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="엑셀(.xlsx) 파일만 올릴 수 있습니다.")
    data = file.file.read(MAX_EXCEL_BYTES + 1)
    if len(data) > MAX_EXCEL_BYTES:
        raise HTTPException(status_code=413, detail="엑셀 파일이 너무 큽니다 (최대 10MB).")
    return data


def _excel_plan(conn, farm: dict, data: bytes, mode: str) -> tuple[dict, list[dict]]:
    """미리보기와 저장이 같이 쓴다: 무엇을 저장하게 되는지 계산 (DB 에는 쓰지 않는다)."""
    try:
        parsed = shipment_input.parse_excel(data)
    except InputError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    names = shipment_input.name_summary(parsed, farm["name"])
    mode = mode if names else "all"
    rows = shipment_input.choose_rows(parsed, farm["name"], mode)
    own = shipment_input.ownership(conn, farm["id"], [r["animal_no"] for r in rows])
    unique = len(own["status"])
    plan = {
        "sheet": parsed["sheet"], "total_rows": parsed["total_rows"], "invalid": parsed["invalid"],
        "missing_cols": parsed["missing_cols"], "names": names, "mode": mode,
        "selected_rows": len(rows), "unique": unique, "duplicates": len(rows) - unique,
        "date_missing": sum(r["date_missing"] for r in rows),
        "ownership": {k: v for k, v in own.items() if k != "status"},
        "needs_confirm": bool(own["move"] or (names and mode == "all" and names["others"])),
        "sample": [{**{k: v for k, v in r.items() if k != "date_missing"}, "status": own["status"][r["animal_no"]]}
                   for r in rows[:SAMPLE_ROWS]],
    }
    return plan, rows


@router.post("/excel/preview")
def excel_preview(farm_id: int, file: UploadFile = File(...), mode: Literal["match", "all"] = Form("match"),
                  conn=Depends(get_conn)):
    """엑셀을 해석해 무엇이 저장될지 보여 준다. 저장은 하지 않는다."""
    farm = _farm(conn, farm_id)
    plan, _ = _excel_plan(conn, farm, _read_upload(file), mode)
    return plan


@router.post("/excel/save")
def excel_save(farm_id: int, file: UploadFile = File(...), mode: Literal["match", "all"] = Form("match"),
               confirm: bool = Form(False), conn=Depends(get_conn)):
    """미리보기와 같은 파일·같은 방식으로 다시 해석해서 저장한다 (단가·금액 칸은 건드리지 않는다)."""
    farm = _farm(conn, farm_id)
    plan, rows = _excel_plan(conn, farm, _read_upload(file), mode)
    if not rows:
        raise HTTPException(status_code=422, detail="저장할 행이 없습니다. 미리보기를 확인해주세요.")
    if plan["needs_confirm"] and not confirm:
        _confirm_needed("다른 농가 이름의 행이나 다른 농가에 등록된 개체가 있습니다. 미리보기를 확인하고 '확인' 에 체크한 뒤 저장해주세요.")
    result = shipment_input.save_excel(conn, farm_id, rows)
    return {**result, "farm": farm["name"], "backup": backup.run("출하성적 엑셀 저장")}
