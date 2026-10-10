"""3단계 · AI 리포트 시험 — 실제 Claude API 는 부르지 않는다.

기존 streamlit_app.py 의 리포트 코드(성별 집계·연도별 추이·수익성 추정·generate_claude_report)를 소스에서 꺼내
가짜 Anthropic 클라이언트로 실행하고, 새 API 가 Claude 에 보내는 요청(system 블록·프롬프트·모델·max_tokens)이
글자 하나까지 같은지 본다. 저장 규칙(성공만 저장, 같은 방식만 덮어쓰기, 방문 없으면 저장 안 함)도 본다.
실행: python -m unittest tests.test_api_ai_report
"""
import ast
from datetime import datetime, timezone
import json
import re
import textwrap
import warnings
import types
import unittest
from unittest import mock

import pandas as pd

from test_api_dashboard import APP_SOURCE, ApiTestBase, make_db  # noqa: E402

from api.services import ai_report, backup  # noqa: E402
from api.services import national_stats as ns  # noqa: E402

KNOWLEDGE = '<문서 제목="시험자료">\n시험용 전문자료 본문\n</문서>'
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")   # 기존 코드에 넘기는 시험용 연결 래퍼 때문
LEGACY_TREE = ast.parse(APP_SOURCE)
APP_LINES = APP_SOURCE.splitlines()
LIVE_PRICES = {"1++": 24000.0, "1+": 20000.0, "D": 9000.0}   # 일부 등급만 온 실시간 단가 (고정표와 섞이는 경로)


def legacy_def(name: str) -> str:
    """streamlit_app.py 의 최상위 함수 소스 (데코레이터 제외). 프롬프트 f-string 이 줄 맨 앞에서 시작해서 ast 로 찾는다."""
    for node in LEGACY_TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "\n".join(APP_LINES[node.lineno - 1:node.end_lineno]) + "\n"
    raise AssertionError(f"streamlit_app.py 에서 {name} 을 찾지 못함")


def legacy_gather_block() -> str:
    """메뉴 4 의 '성별마다 집계' 부분 — gender_data = {} 부터 conn.close() 직전까지."""
    sec = APP_SOURCE[APP_SOURCE.index('elif menu == "3단계 · AI 리포트":'):APP_SOURCE.index('elif menu == "데이터 관리 · 백업":')]
    m = re.search(r"\n([ \t]*gender_data = \{\}\n.*?)\n[ \t]*conn\.close\(\)\n", sec, re.DOTALL)
    if not m:
        raise AssertionError("AI 리포트 화면에서 성별 집계 코드를 찾지 못함")
    return textwrap.dedent(m.group(1))


class _NoClose:
    def __init__(self, conn):
        self._c = conn

    def __getattr__(self, k):
        return getattr(self._c, k)

    def close(self):
        pass


class FakeStream:
    def __init__(self, calls, text, stop_reason):
        self.calls, self.text, self.stop_reason = calls, text, stop_reason
        self.text_stream = iter([text[: len(text) // 2], text[len(text) // 2:]])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        usage = types.SimpleNamespace(input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1)
        return types.SimpleNamespace(stop_reason=self.stop_reason, usage=usage)


def fake_anthropic(calls, text="# 리포트\n본문", stop_reason="end_turn"):
    """anthropic 모듈 흉내: messages.stream(**kwargs) 를 기록하고 정해 둔 글을 돌려준다. 예외 클래스는 진짜를 쓴다."""
    import anthropic as real

    class Client:
        def __init__(self, api_key=None):
            self.messages = types.SimpleNamespace(stream=lambda **kw: (calls.append(kw), FakeStream(calls, text, stop_reason))[1])

    mod = types.SimpleNamespace(**{k: getattr(real, k) for k in dir(real) if k.endswith("Error")})
    mod.Anthropic = Client
    return mod


def legacy_namespace(conn, stats):
    ns_ = {"pd": pd, "json": json, "re": re, "datetime": datetime, "timezone": timezone, "get_db": lambda: _NoClose(conn), "NATIONAL_STATS": stats,
           "PRINT_REPORT_YEARS": [2023, 2024, 2025, 2026], "PRINT_REPORT_GENDERS": [("거세", "거세우"), ("암", "암소")],
           "fetch_eumseong_grade_prices": lambda year: dict(LIVE_PRICES), "get_claude_api_key": lambda: "test-key",
           "load_knowledge_base": lambda: KNOWLEDGE}
    exec(re.search(r"^EUMSEONG_PRICES_2025 = \{.*?\n\}\n", APP_SOURCE, re.S | re.M).group(0), ns_)
    exec(re.search(r"^SURVEY_FIELD_LABELS = \{.*?\n\}\n", APP_SOURCE, re.S | re.M).group(0), ns_)
    for name in ["nat_latest_year", "relabel_survey_data", "build_ai_report_yearly_breakdown",
                 "build_ai_report_profit_estimate", "generate_claude_report"]:
        exec(legacy_def(name), ns_)
    exec(re.search(r"^class ClaudeReportError\(Exception\):\n.*?\n\n", APP_SOURCE, re.S | re.M).group(0), ns_)
    return ns_


def legacy_request(conn, stats, farm_id, use_knowledge):
    """기존 화면이 리포트 버튼을 눌렀을 때 Claude 에 보내던 요청 그대로."""
    lg = legacy_namespace(conn, stats)
    cur = conn.cursor()
    lg.update(cur=cur, ai_target_farm_id=farm_id)
    exec(legacy_gather_block(), lg)
    farm = conn.execute("SELECT * FROM farms WHERE id = ?", (farm_id,)).fetchone()
    last_visit = conn.execute("""SELECT v.id, v.visit_number, v.visit_date, s.survey_data, s.consult_notes
        FROM visits v LEFT JOIN field_surveys s ON s.visit_id = v.id WHERE v.farm_id = ? ORDER BY v.visit_number DESC LIMIT 1""",
                              (farm_id,)).fetchone()
    survey_dict = dict(last_visit) if last_visit else {}
    if isinstance(survey_dict.get("survey_data"), str):
        try:
            survey_dict["survey_data"] = json.loads(survey_dict["survey_data"])
        except ValueError:
            pass
    calls = []
    lg["anthropic"] = fake_anthropic(calls)
    text = "".join(lg["generate_claude_report"](farm["farm_name"] if farm else "농가", lg["gender_data"], survey_dict, use_knowledge))
    return calls[0], text


def new_request(conn, farm_id, use_knowledge):
    calls = []
    with mock.patch.object(ai_report, "anthropic", fake_anthropic(calls)), \
         mock.patch.object(ai_report, "api_key", return_value="test-key"):
        inp = ai_report.gather_inputs(conn, farm_id)
        system, prompt = ai_report.build_request(inp["farm_name"], inp["gender_data"], inp["survey"], use_knowledge)
        text = "".join(ai_report.stream_report(system, prompt))
    return calls[0], text


def add_rich_data(conn):
    """연도 여러 개·암소·실측 정산액·등급 빈 칸·조사표(한글로 바뀌는 키 + _extra) 를 더한다."""
    rows = [  # 농가, 이력번호, 성별, 연도, 육질, 육량, 도체중, BMS, 단면적, 등지방, 월령, 정산액
        (1, "A1", "거세", 2023, "1+", "A", 470, 7, 98, 12, 31, None),
        (1, "A2", "거세", 2024, "1++", "B", 490, 9, 101, 13, 30, None),
        (1, "A3", "거세", 2026, None, "C", 510, None, 105, 14, 32, None),
        (1, "A4", "암", 2024, "2", None, 360, 4, 85, 11, 70, None),
        (2, "B1", "거세", 2024, "1+", "A", 480, 7, 100, 12, 30, 10500000),
        (2, "B2", "거세", 2024, "1", "B", 470, 5, 95, 13, 31, 9800000),
        (2, "B3", "거세", 2025, "1++", "A", 500, 8, 104, 12, 30, 11800000),
    ]
    for fid, no, g, y, q, yl, cw, bms, rib, bf, age, total in rows:
        conn.execute("INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_date, slaughter_year, grade_quality,"
                     " grade_yield, carcass_weight, bms, ribeye, backfat, month_age, total_price) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (fid, no, g, f"{y}-03-01", y, q, yl, cw, bms, rib, bf, age, total))
    survey = {"investigator": "조사자", "region": "영천", "manureScore": "", "feed_matrix": {"송아지": {"배합사료 품목": "입붙이기"}},
              "_extra": {"waterSource": "지하수"}}
    conn.execute("INSERT INTO visits (id, farm_id, visit_number, visit_date) VALUES (10, 1, 2, '2026-09-01')")
    conn.execute("INSERT INTO field_surveys (visit_id, survey_data, consult_notes) VALUES (10, ?, '메모')",
                 (json.dumps(survey, ensure_ascii=False),))
    conn.commit()


class LegacyParityTest(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        add_rich_data(self.conn)
        self.kosis = mock.patch.object(ns, "_kosis_cached", return_value=None)
        self.kosis.start()
        self.stats = ns.national_stats()
        self.patches = [mock.patch.object(ai_report, "fetch_eumseong_grade_prices", side_effect=lambda y: dict(LIVE_PRICES)),
                        mock.patch.object(ai_report, "load_knowledge_base", return_value=KNOWLEDGE)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.kosis.stop()
        self.conn.close()

    def test_legacy_code_found(self):
        self.assertIn("build_ai_report_yearly_breakdown", legacy_gather_block())
        self.assertIn('model="claude-sonnet-5"', legacy_def("generate_claude_report"))

    def test_request_matches_legacy_every_farm_both_modes(self):
        # 농가 1: 거세+암, 연도 여러 개, 최근 방문 2차 / 2: 실측 정산액 / 3: 조사표만 / 4: 방문만 / 5: 아무것도 없음 / 999: 없는 농가
        for farm_id in [1, 2, 3, 4, 5, 999]:
            for use_knowledge in (True, False):
                with self.subTest(farm=farm_id, knowledge=use_knowledge):
                    old_call, old_text = legacy_request(self.conn, self.stats, farm_id, use_knowledge)
                    new_call, new_text = new_request(self.conn, farm_id, use_knowledge)
                    self.assertEqual(new_call, old_call)
                    self.assertEqual(new_text, old_text)

    def test_parity_check_sees_differences(self):
        # 대조가 헛돌지 않는지: 단가 하나만 바꿔도 요청이 달라져야 한다
        old_call, _ = legacy_request(self.conn, self.stats, 1, False)
        with mock.patch.dict(ai_report.EUMSEONG_PRICES_2025, {"2": 1}):
            new_call, _ = new_request(self.conn, 1, False)
        self.assertNotEqual(new_call["messages"], old_call["messages"])

    def test_prompt_contents(self):
        inp = ai_report.gather_inputs(self.conn, 1)
        self.assertEqual(list(inp["gender_data"]), ["거세우", "암소"])
        self.assertEqual(inp["visit_id"], 10)
        system, prompt = ai_report.build_request(inp["farm_name"], inp["gender_data"], inp["survey"], True)
        self.assertEqual(system[1]["cache_control"], {"type": "ephemeral", "ttl": "1h"})
        # 기존 앱은 relabel_survey_data 를 방문 기록 dict(바깥)에 적용해서, 조사표 안의 키는 영문 그대로 간다 (그대로 옮김)
        self.assertIn('"manureScore": ""', prompt)
        self.assertNotIn("소 분변 상태", prompt)
        self.assertIn('"_extra"', prompt)
        steer = inp["gender_data"]["거세우"]["profit_data"]
        self.assertIn("등급분포 가중평균 추정", steer["계산_방식"])
        self.assertIn("실측", ai_report.gather_inputs(self.conn, 2)["gender_data"]["거세우"]["profit_data"]["계산_방식"])


class StreamErrorsTest(unittest.TestCase):
    def run_stream(self, **fake):
        calls = []
        with mock.patch.object(ai_report, "anthropic", fake_anthropic(calls, **fake)), \
             mock.patch.object(ai_report, "api_key", return_value="k"):
            return "".join(ai_report.stream_report([{"type": "text", "text": "s"}], "p"))

    def test_truncated_and_refused_raise(self):
        with self.assertRaisesRegex(ai_report.ReportError, "잘렸"):
            self.run_stream(stop_reason="max_tokens")
        with self.assertRaisesRegex(ai_report.ReportError, "거절"):
            self.run_stream(stop_reason="refusal")

    def test_no_key(self):
        with mock.patch.object(ai_report, "api_key", return_value=""):
            with self.assertRaisesRegex(ai_report.ReportError, "API 키"):
                list(ai_report.stream_report([], "p"))


class ReportApiTest(ApiTestBase):
    def setUp(self):
        super().setUp()
        add_rich_data(self.conn)
        self.calls = []
        self.patches = [
            mock.patch("api.config.app_password", return_value=None),
            mock.patch("api.routers.reports.persist_db", return_value=backup.BackupResult(ok=True, message="백업됨")),
            mock.patch.object(ai_report, "fetch_eumseong_grade_prices", return_value=None),
            mock.patch.object(ai_report, "load_knowledge_base", return_value=KNOWLEDGE),
            mock.patch.object(ai_report, "api_key", return_value="k"),
            mock.patch("api.routers.reports.connect", return_value=_NoClose(self.conn)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def generate(self, farm_id, mode="전문", **fake):
        with mock.patch.object(ai_report, "anthropic", fake_anthropic(self.calls, **fake)):
            r = self.client.post(f"/api/farms/{farm_id}/report", json={"mode": mode})
        self.assertEqual(r.status_code, 200, r.text)
        return [json.loads(line) for line in r.text.splitlines() if line.strip()]

    def saved(self):
        return [tuple(r) for r in self.conn.execute("SELECT visit_id, report_mode, full_markdown FROM ai_reports ORDER BY report_mode")]

    def test_status(self):
        s = self.client.get("/api/report/status").json()
        self.assertEqual((s["key_configured"], s["knowledge_ready"], s["model"]), (True, True, "claude-sonnet-5"))

    def test_generate_and_save(self):
        events = self.generate(1)
        self.assertEqual("".join(e.get("text", "") for e in events), "# 리포트\n본문")
        done = events[-1]
        self.assertEqual((done["done"], done["saved"], done["visit_id"]), (True, True, 10))
        self.assertEqual(self.saved(), [(10, "전문", "# 리포트\n본문")])
        self.generate(1, "일반", text="일반 리포트")          # 다른 방식은 따로 남는다
        self.generate(1, "전문", text="새 전문 리포트")       # 같은 방식은 덮어쓴다
        self.assertEqual(self.saved(), [(10, "일반", "일반 리포트"), (10, "전문", "새 전문 리포트")])
        self.assertEqual(len(self.calls[1]["system"]), 1)    # 일반 모드엔 전문자료 블록이 없다

    def test_failure_is_not_saved(self):
        events = self.generate(1, stop_reason="max_tokens")
        self.assertIn("잘렸", events[-1]["error"])
        self.assertEqual("".join(e.get("text", "") for e in events), "# 리포트\n본문")   # 중간까지 온 글은 보여 준다
        self.assertEqual(self.saved(), [])

    def test_empty_answer_is_not_saved(self):
        events = self.generate(1, text="   ")
        self.assertIn("빈 응답", events[-1]["error"])
        self.assertEqual(self.saved(), [])

    def test_farm_without_visit_is_not_saved(self):
        events = self.generate(5)
        self.assertEqual((events[-1]["done"], events[-1]["saved"]), (True, False))
        self.assertEqual(self.saved(), [])

    def test_bad_mode_and_unknown_farm(self):
        self.assertEqual(self.client.post("/api/farms/1/report", json={"mode": "아무거나"}).status_code, 422)
        self.assertEqual(self.client.post("/api/farms/999/report", json={"mode": "일반"}).status_code, 404)

    def test_html_download(self):
        r = self.client.post("/api/report/html", json={"farm_id": 1, "markdown": "# 제목\n\n| a | b |\n|---|---|\n| 1 | 2 |", "mode": "전문"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("<table>", r.text)
        self.assertIn("가농장 AI 컨설팅 리포트 (전문)", r.text)
        self.assertIn("attachment", r.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
