from fastapi import APIRouter, Depends

from ..auth import require_login
from ..db import get_conn
from ..services import datamgmt

router = APIRouter(prefix="/api", tags=["농가"], dependencies=[Depends(require_login)])

# 농가마다 방문 횟수와 출하성적 두수를 같이 센다. 서브쿼리만 써서 SQLite·Postgres(어댑터)에서 같게 동작한다.
FARMS_SQL = """
SELECT f.id, f.farm_name, f.owner_name, f.region, f.breeding_type,
       (SELECT COUNT(*) FROM visits v WHERE v.farm_id = f.id) AS visit_cnt,
       (SELECT COUNT(*) FROM shipment_records s WHERE s.farm_id = f.id) AS ship_cnt
FROM farms f
ORDER BY f.farm_name
"""


@router.get("/farms")
def list_farms(conn=Depends(get_conn)):
    rows = conn.execute(FARMS_SQL).fetchall()
    survey_region = datamgmt.region_from_surveys(conn)      # 기존 앱처럼 조사표의 최근 지역을 우선
    farms = [
        {"id": r["id"], "name": r["farm_name"], "owner": r["owner_name"] or "", "region": survey_region.get(r["id"]) or r["region"] or "",
         "breeding_type": r["breeding_type"] or "", "visits": int(r["visit_cnt"] or 0), "shipments": int(r["ship_cnt"] or 0)}
        for r in rows
    ]
    return {"farms": farms}
