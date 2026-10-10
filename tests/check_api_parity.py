"""운영 DB 전체로 새 API 와 기존 Streamlit 앱의 숫자를 대조한다 (읽기 전용, 이름은 출력하지 않음).

화면을 하나 옮길 때마다 돌려 '불일치 0건' 을 확인한다. 테스트가 아니라 점검 스크립트다(unittest 가 줍지 않는 이름).
실행: python tests/check_api_parity.py   (DATABASE_URL 이 secrets.toml 에 있어야 실제 DB 를 본다)
"""
import os
import sys
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP); sys.path.insert(0, os.path.join(APP, "tests")); os.chdir(APP)
from unittest import mock
from fastapi.testclient import TestClient
from api.main import app
from api import db
import test_api_dashboard as T
c = TestClient(app)
conn = db.connect()
diffs = 0
def check(name, got, want):
    global diffs
    ok = got == want
    diffs += not ok
    print(f"  {'OK ' if ok else 'DIFF'} {name}" + ("" if ok else f": api={got} legacy={want}"))
with mock.patch("api.config.app_password", return_value=None):
    s = c.get("/api/dashboard/summary").json()
    check("거세 1+이상", s["steer_plus1"]["value"], float(conn.execute(T.LEGACY["steer"]).fetchone()[0]))
    check("암 1+이상", s["cow_plus1"]["value"], float(conn.execute(T.LEGACY["cow"]).fetchone()[0]))
    check("출하만 있는 농가 명단", sorted(s["farms_missing_survey"]), sorted(r[0] for r in conn.execute(T.LEGACY["missing_survey"]).fetchall()))
    check("조사표만 있는 농가 명단", sorted(s["farms_missing_shipment"]), sorted(r[0] for r in conn.execute(T.LEGACY["missing_shipment"]).fetchall()))
    print(f"  (요약) 농가 {s['total_farms']} 방문 {s['total_visits']} 출하 {s['total_shipments']} | 거세 1+ {s['steer_plus1']} | 암 1+ {s['cow_plus1']} | 명단 {len(s['farms_missing_survey'])}/{len(s['farms_missing_shipment'])}곳")
    cells = 0
    for g in ["거세", "암"]:
        legacy = {r[0]: [float(x) if x is not None else None for x in list(r)[1:]] for r in conn.execute(T.LEGACY["yearly"], (g,)).fetchall()}
        rows = c.get("/api/dashboard/yearly", params={"gender": g}).json()["rows"]
        api = {r["year"]: [r["farms"], r["heads"]] + [r["farm"][k] for k in T.YearlyTest.KEYS[2:]] for r in rows if r["heads"] is not None}
        cells += sum(len(v) for v in legacy.values())
        check(f"연도별 {g} ({len(legacy)}개 연도)", api, legacy)
    print(f"  연도별 대조 칸 수: {cells}")
    cmp_api = [[r["gender"], r["heads"], r["carcass_weight"], r["bms"], r["ribeye"], r["backfat"], r["plus1_rate"], r["month_age"]] for r in c.get("/api/dashboard/gender-compare").json()]
    cmp_legacy = [[r[0]] + [float(x) if x is not None else None for x in list(r)[1:]] for r in conn.execute(T.LEGACY["compare"]).fetchall()]
    check("거세 vs 암 비교", cmp_api, cmp_legacy)
    for r in cmp_api: print("   ", r)
print(f"\n불일치 {diffs}건")
