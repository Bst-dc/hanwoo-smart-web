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

# ---------------------------------------------------------------- 1단계 · 출하성적 비교 (모든 농가 × 연도 × 성별)
import ast, re, json as _json
import pandas as pd
from api.services import national_stats as _ns
SRC = T.APP_SOURCE
def grab(pattern):
    m = re.search(pattern, SRC, re.DOTALL)
    assert m, pattern
    return m.group(1)
L_STATS_YEAR = grab(r'stats_row = conn\.execute\(f"""((?:(?!""").)*)""", \(selected_farm_id, selected_year\)\)')
L_STATS_ALL = grab(r'stats_row = conn\.execute\(f"""((?:(?!""").)*)""", \(selected_farm_id,\)\)')
L_REC_YEAR = grab(r'records_df = pd\.read_sql_query\(f"""((?:(?!""").)*)""", conn, params=\(selected_farm_id, selected_year\)\)')
L_REC_ALL = grab(r'records_df = pd\.read_sql_query\(f"""((?:(?!""").)*)""", conn, params=\(selected_farm_id,\)\)')
L_RECENT = grab(r'yearly_rows = conn3\.execute\(f"""((?:(?!""").)*)""", \(selected_farm_id, \*recent_years\)\)')
num = lambda v: None if v is None or (isinstance(v, float) and v != v) else float(v)
TEXT_COLS = ("animal_no", "gender", "slaughter_date", "grade_quality", "grade_yield")
REC_COLS = ["animal_no", "gender", "slaughter_date", "carcass_weight", "grade_quality", "grade_yield", "bms", "backfat", "ribeye", "month_age"]
combos = mismatch = 0
farm_ids = [r[0] for r in conn.execute("SELECT id FROM farms ORDER BY id").fetchall()]
with mock.patch("api.config.app_password", return_value=None):
    for fid in farm_ids:
        years = [r[0] for r in conn.execute("SELECT DISTINCT slaughter_year FROM shipment_records WHERE farm_id = ? AND slaughter_year IS NOT NULL ORDER BY slaughter_year DESC", (fid,)).fetchall()]
        for year in [None] + years:
            for gender in [None, "거세", "암"]:
                combos += 1
                q = {k: v for k, v in {"year": year, "gender": gender}.items() if v is not None}
                api = c.get(f"/api/farms/{fid}/comparison", params=q).json()
                cmp_g = gender
                if not cmp_g:
                    n = conn.execute("SELECT COUNT(*) FROM shipment_records WHERE farm_id = ? AND gender = '거세'" + (" AND slaughter_year = ?" if year else ""), (fid, year) if year else (fid,)).fetchone()[0]
                    cmp_g = "거세" if n > 0 else "암"
                cg_sql, g_sql = f" AND gender = '{cmp_g}'", (f" AND gender = '{gender}'" if gender else "")
                srow = conn.execute((L_STATS_YEAR if year else L_STATS_ALL).replace("{cmp_gender_sql}", cg_sql), (fid, year) if year else (fid,)).fetchone()
                if srow["total_count"]:
                    want = [srow["total_count"]] + [num(srow[k]) for k in ["avg_weight", "avg_bms", "avg_ribeye", "avg_backfat", "rate_1plus_above", "rate_c_grade", "avg_month_age"]]
                    got = [api["total_count"]] + [r["farm"] for r in api["rows"]]
                else:
                    want, got = [0, []], [api["total_count"], api["rows"]]
                rec_sql = (L_REC_YEAR if year else L_REC_ALL).replace("{gender_sql}", g_sql)
                lrec = [[v if k in TEXT_COLS else num(v) for k, v in zip(REC_COLS, r)] for r in conn.execute(rec_sql, (fid, year) if year else (fid,)).fetchall()]
                arec = [[r[k] if k in TEXT_COLS else num(r[k]) for k in REC_COLS] for r in api["records"]]
                lrecent = []
                if srow["total_count"] and years:
                    ry = sorted(sorted(years, reverse=True)[:3])
                    rsql = L_RECENT.replace("{cmp_gender_sql}", cg_sql).replace("{placeholders}", ",".join("?" * len(ry)))
                    found = {r[0]: [num(x) for x in list(r)[1:]] for r in conn.execute(rsql, (fid, *ry)).fetchall()}
                    lrecent = [[y] + found.get(y, [None] * 7) for y in ry]
                arecent = [[r["year"]] + [r["farm"][k] for k in ["carcass_weight", "bms", "ribeye", "backfat", "plus1_rate", "c_rate", "month_age"]] for r in api["recent"]]
                if (want, lrec, lrecent, cmp_g) != (got, arec, arecent, api["cmp_gender"]):
                    mismatch += 1
                    if mismatch <= 3:
                        print(f"  DIFF 농가 {fid} 연도 {year} 성별 {gender}: 통계 {want == got}, 개체 {lrec == arec}, 추이 {lrecent == arecent}")
check(f"출하성적 비교 ({len(farm_ids)}농가 × 연도 × 성별 = {combos}조합)", mismatch, 0)

# 인쇄 리포트: 기존 함수를 그대로 실행해 HTML 이 글자까지 같은지
tree = ast.parse(SRC)
names = ["_fmt1", "_diff_cell", "_build_page1_table", "_build_page2_table", "build_print_comparison_report_html"]
code = "\n\n".join(ast.get_source_segment(SRC, n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names)
class _NoClose:
    def __init__(self, conn): self._c = conn
    def __getattr__(self, k): return getattr(self._c, k)
    def close(self): pass
legacy_ns = {"pd": pd, "json": _json, "NATIONAL_STATS": _ns.national_stats(), "PRINT_REPORT_YEARS": [2023, 2024, 2025, 2026],
             "PRINT_REPORT_GENDERS": [("거세", "거세우"), ("암", "암소")], "get_db": lambda: _NoClose(db.connect())}
exec(code, legacy_ns)
html_diff = 0
with mock.patch("api.config.app_password", return_value=None):
    for fid in farm_ids:
        name = conn.execute("SELECT farm_name FROM farms WHERE id = ?", (fid,)).fetchone()[0]
        r = c.get(f"/api/farms/{fid}/print-report")
        html_diff += r.text != legacy_ns["build_print_comparison_report_html"](name, fid)
check(f"인쇄 리포트 HTML ({len(farm_ids)}농가, 글자 단위)", html_diff, 0)

print(f"\n불일치 {diffs}건")
