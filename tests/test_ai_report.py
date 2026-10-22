"""3단계 · AI 리포트 검사 — 작은 데이터로 기대값을 손으로 적고, Claude 호출은 가짜로 바꿔 끼운다 (비용·외부 호출 없음).
실행: python -m unittest tests.test_ai_report
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CONSULTING_LOCAL_ONLY"] = "1"
os.environ.setdefault("APP_PASSWORD", "test-pass")
for k in ("GITHUB_TOKEN", "EKAPE_API_KEY", "KOSIS_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ.pop(k, None)

import db_schema  # noqa: E402
from api import national_stats  # noqa: E402
from api.services import ai_report, report_data  # noqa: E402

STATS = national_stats.merge(national_stats.BASELINE, None)


class KeepOpen:
    def __init__(self, conn):
        self._c = conn

    def __getattr__(self, n):
        return getattr(self._c, n)

    def close(self):
        pass


def memory_db(with_visit=True):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(db_schema.SQLITE_DDL)
    conn.executemany("INSERT INTO farms (id, farm_name) VALUES (?, ?)", [(1, "가농가"), (2, "나농가")])
    rows = [  # (번호, 성별, 연도, 도체중, 육질, 육량, BMS, 등지방, 단면적, 월령)
        ("s1", "거세", 2025, 500, "1++", "A", 9, 12, 100, 30),
        ("s2", "거세", 2025, 440, "1", "C", 4, 16, 90, 32),
        ("c1", "암", 2026, 400, "1+", "B", 6, 13, 95, 50),
    ]
    conn.executemany("""INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_year, carcass_weight, grade_quality,
                        grade_yield, bms, backfat, ribeye, month_age) VALUES (1,?,?,?,?,?,?,?,?,?,?)""", rows)
    if with_visit:
        conn.execute("INSERT INTO visits (id, farm_id, visit_number, visit_date) VALUES (7, 1, 1, '2026-06-01')")
        conn.execute("INSERT INTO visits (id, farm_id, visit_number, visit_date) VALUES (8, 1, 2, '2026-09-01')")
        conn.execute("INSERT INTO field_surveys (visit_id, survey_data) VALUES (8, ?)",
                     (json.dumps({"region": "영천", "tmr": "부", "_extra": {"zone": "A"}}, ensure_ascii=False),))
    conn.commit()
    return conn


class DataTest(unittest.TestCase):
    def setUp(self):
        self.conn = memory_db()

    def test_report_years_follow_the_calendar(self):
        from datetime import date
        self.assertEqual(report_data.report_years(date(2026, 10, 22)), [2023, 2024, 2025, 2026])
        self.assertEqual(report_data.report_years(date(2027, 1, 5)), [2024, 2025, 2026, 2027])    # 해가 바뀌면 창이 따라 움직인다

    def test_new_year_records_appear_and_empty_years_are_skipped(self):
        self.conn.execute("""INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_year, carcass_weight, grade_quality,
                             grade_yield, bms, backfat, ribeye, month_age) VALUES (1, 'n1', '거세', 2027, 510, '1++', 'A', 8, 12, 100, 30)""")
        y = report_data.gender_data(self.conn, 1, STATS, prices={}, years=[2024, 2025, 2026, 2027])["거세우"]["yearly_breakdown"]
        self.assertEqual([r["year"] for r in y], [2025, 2027])           # 기록 없는 2024·2026 은 건너뛴다
        self.assertEqual(y[1]["carcass_weight_kg"]["전국"], None)         # 전국 통계에 없는 해는 None (지어내지 않음)

    def test_stats_and_yearly_breakdown(self):
        g = report_data.gender_data(self.conn, 1, STATS, prices={}, years=[2023, 2024, 2025, 2026])
        self.assertEqual(list(g), ["거세우", "암소"])
        s = g["거세우"]["shipment_stats"]
        self.assertEqual((s["total_count"], s["avg_weight"], s["avg_bms"], s["rate_1plus_above"], s["rate_c_grade"]), (2, 470.0, 6.5, 50.0, 50.0))
        y = g["거세우"]["yearly_breakdown"]
        self.assertEqual([r["year"] for r in y], [2025])
        self.assertEqual(y[0]["carcass_weight_kg"], {"농가": 470.0, "전국": 478.1})
        self.assertEqual(y[0]["grade_quality_pct"]["농가"], {"1++": 50.0, "1+": 0.0, "1": 50.0, "2": 0.0, "3": 0.0, "1+이상": 50.0})
        self.assertEqual(y[0]["grade_yield_pct"]["농가"], {"A": 50.0, "B": 0.0, "C": 50.0})
        self.assertEqual(g["암소"]["yearly_breakdown"][0]["grade_yield_pct"]["전국"], None)   # 암소 2026 육량 전국 통계 없음

    def test_profit_estimate_with_fixed_prices(self):
        p = report_data.profit_estimate(self.conn, 1, "거세", STATS, prices={})
        # 농가: 470kg × (23038 + 18165)/2,  전국 2026: 490.4kg × Σ(등급단가 × 비율)
        farm = 470.0 * (23038 + 18165) / 2
        nat_kg = 23038 * .455 + 19590 * .287 + 18165 * .19 + 14969 * .061 + 12735 * .008
        nat = 490.4 * nat_kg
        self.assertEqual(p["farm_revenue_per_head_est"], int(round(farm)))
        self.assertEqual(p["national_revenue_per_head_est"], int(round(nat)))
        self.assertEqual(p["total_diff_revenue"], round(farm - nat) * 2)
        self.assertIn("고정값", p["가격_기준"])

    def test_gender_without_records_is_left_out(self):
        self.assertEqual(report_data.gender_data(self.conn, 2, STATS, prices={}), {})

    def test_survey_keys_are_relabelled_inside_too(self):
        s = report_data.survey_for_prompt(report_data.last_visit(self.conn, 1))
        self.assertEqual(s["visit_number"], 2)                            # 마지막 방문
        self.assertEqual(s["survey_data"]["지역"], "영천")
        self.assertEqual(s["survey_data"]["TMR 급여"], "부")
        self.assertEqual(s["survey_data"]["_extra"], {"zone": "A"})


class PromptTest(unittest.TestCase):
    def test_knowledge_block_is_cached_and_last(self):
        sys_blocks, prompt = ai_report.build_request("가농가", {}, {}, "자료 본문")
        self.assertEqual(len(sys_blocks), 2)
        self.assertEqual(sys_blocks[1]["cache_control"], {"type": "ephemeral", "ttl": "1h"})
        self.assertIn("[농가명]: 가농가", prompt)
        self.assertIn("(이 농가는 등록된 출하성적이 없습니다)", prompt)
        self.assertEqual(len(ai_report.build_request("가농가", {}, {}, "")[0]), 1)

    def test_html_does_not_pass_tags_through(self):
        h = ai_report.to_html("# 제목\n\n<script>alert(1)</script>\n\n| a | b |\n|---|---|\n| 1 | 2 |")
        self.assertNotIn("<script>", h)
        self.assertIn("<table>", h)


def fake_stream(chunks, stop="end_turn", delay=0.0):
    def run(system, prompt, on_text, should_stop):
        for c in chunks:
            if should_stop():
                return "cancelled"
            time.sleep(delay)
            on_text(c)
        return stop
    return run


class JobTest(unittest.TestCase):
    def setUp(self):
        ai_report.JOBS.clear()
        self.conn = memory_db()
        self.connect = lambda: KeepOpen(self.conn)
        p = mock.patch.object(report_data, "eumseong_prices", lambda year, get=None: None)
        p.start()
        self.addCleanup(p.stop)

    def run_job(self, stream, mode="일반", farm=1):
        job = ai_report.start(farm, "가농가", mode, stream_fn=stream, connect=self.connect)
        for _ in range(200):
            if job["status"] != "running":
                break
            time.sleep(0.02)
        return job

    def reports(self):
        return [tuple(r) for r in self.conn.execute("SELECT visit_id, report_mode, full_markdown FROM ai_reports ORDER BY report_mode")]

    def test_complete_report_is_saved_to_last_visit_per_mode(self):
        j = self.run_job(fake_stream(["# 리포트", " 본문"]))
        self.assertEqual((j["status"], j["text"]), ("done", "# 리포트 본문"))
        self.assertEqual(self.reports(), [(8, "일반", "# 리포트 본문")])
        self.assertEqual(j["backup"]["ok"], None)
        self.run_job(fake_stream(["새 일반"]))                               # 같은 방식은 덮어쓴다
        with mock.patch.object(ai_report, "knowledge", lambda: "자료"):
            self.run_job(fake_stream(["전문 본문"]), mode="전문")
        self.assertEqual(self.reports(), [(8, "일반", "새 일반"), (8, "전문", "전문 본문")])
        self.assertEqual([r["mode"] for r in ai_report.list_reports(self.conn, 1)], ["일반", "전문"])

    def test_cut_off_empty_or_failed_reports_are_not_saved(self):
        self.assertEqual(self.run_job(fake_stream(["앞부분"], stop="max_tokens"))["status"], "error")
        self.assertEqual(self.run_job(fake_stream(["  "]))["status"], "error")

        def boom(*a):
            raise ai_report.ReportError("API 키가 올바르지 않습니다.")
        j = self.run_job(boom)
        self.assertEqual((j["status"], j["error"]), ("error", "API 키가 올바르지 않습니다."))
        self.assertEqual(self.reports(), [])

    def test_expert_mode_without_knowledge_fails_before_calling_claude(self):
        called = []
        with mock.patch.object(ai_report, "knowledge", lambda: ""):
            j = self.run_job(lambda *a: called.append(1) or "end_turn", mode="전문")
        self.assertEqual((j["status"], called), ("error", []))

    def test_cancel_stops_and_saves_nothing(self):
        job = ai_report.start(1, "가농가", "일반", stream_fn=fake_stream(["가"] * 50, delay=0.02), connect=self.connect)
        time.sleep(0.1)
        job["cancel"] = True
        for _ in range(200):
            if job["status"] != "running":
                break
            time.sleep(0.02)
        self.assertEqual(job["status"], "cancelled")
        self.assertEqual(self.reports(), [])

    def test_farm_without_visit_is_not_saved_and_one_job_per_farm(self):
        self.conn = memory_db(with_visit=False)
        j = self.run_job(fake_stream(["본문"]))
        self.assertEqual(j["status"], "done")
        self.assertIn("방문 기록이 없어", j["saved_note"])
        self.assertEqual(self.reports(), [])
        slow = ai_report.start(1, "가농가", "일반", stream_fn=fake_stream(["가"] * 20, delay=0.02), connect=self.connect)
        with self.assertRaisesRegex(ai_report.ReportError, "이미 만들고"):
            ai_report.start(1, "가농가", "전문", stream_fn=fake_stream(["x"]), connect=self.connect)
        slow["cancel"] = True


class ReportApiTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from api import config
        from api.main import app
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "consulting.db"
        conn = memory_db()
        conn.execute("INSERT INTO ai_reports (visit_id, report_mode, full_markdown) VALUES (8, '일반', '# 가농가 리포트')")
        conn.commit()
        disk = sqlite3.connect(path)
        conn.backup(disk)
        disk.close()
        p = mock.patch.object(config, "DB_PATH", path)
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(app)
        self.client.post("/api/auth/login", json={"password": os.environ["APP_PASSWORD"]})

    def test_list_read_download_and_no_key(self):
        d = self.client.get("/api/farms/1/reports").json()
        self.assertEqual((d["last_visit"]["visit_number"], d["api_key"], [r["mode"] for r in d["reports"]]), (2, False, ["일반"]))
        rid = d["reports"][0]["id"]
        self.assertIn("<h1>가농가 리포트</h1>", self.client.get(f"/api/reports/{rid}").json()["html"])
        r = self.client.get(f"/api/reports/{rid}/download?fmt=md")
        self.assertEqual(r.text, "# 가농가 리포트")
        self.assertIn("filename*=UTF-8''", r.headers["content-disposition"])
        self.assertEqual(self.client.post("/api/farms/1/reports", json={"mode": "일반"}).status_code, 503)
        self.assertEqual(self.client.get("/api/report-jobs/없음").status_code, 404)


if __name__ == "__main__":
    unittest.main()
