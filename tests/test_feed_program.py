"""대구축협 사료 프로그램 — 엑셀 읽기, 품목 판정, 단계별 기준, AI 리포트 프롬프트 연결.

실제 프로그램 표는 대구축협 내부 자료라 이 공개 저장소에 넣지 않는다. 여기서는 모양만 같은 가짜 표를 쓴다.
실행: python -m unittest tests.test_feed_program
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ["CONSULTING_LOCAL_ONLY"] = "1"
for k in ("GITHUB_TOKEN", "ANTHROPIC_API_KEY"):
    os.environ.pop(k, None)

import openpyxl  # noqa: E402

import build_feed_program  # noqa: E402
from api.services import ai_report, feed_program as fp  # noqa: E402


def fake_program() -> dict:
    """1~29개월 가짜 표: 1–3 송아지A / 4–10 팔공육성B / 11–16 육성C(고단백 C500) / 17–23 비육D(고단백 E800) / 24–29 비육F(고단백 E800)"""
    def feed(m):
        return ("송아지A(펠렛)", "송아지A(펠렛)") if m <= 3 else ("팔공육성B(후레이크)", "팔공육성B(후레이크)") if m <= 10 else \
               ("육성C(후레이크)", "C500(후레이크)") if m <= 16 else ("비육D(후레이크)", "E800(후레이크)") if m <= 23 else ("비육F(후레이크)", "E800(후레이크)")
    months = [{"month": m, "target_weight": 50.0 + 25 * m, "feed": feed(m)[0], "high_protein_feed": feed(m)[1],
               "feed_kg": [m / 3, m / 3 + (0.5 if m >= 9 else 0)], "roughage_kg": [0.1 * m, 0.1 * m]} for m in range(1, 30)]
    return {"name": "가짜 프로그램", "applies_to": "거세우 비육", "source_modified": "2026-11-06", "notes": ["메모"], "months": months}


class JudgeTest(unittest.TestCase):
    def setUp(self):
        self.p = fake_program()

    def verdicts(self, text, stage):
        return [v["판정"].split(" (")[0] for v in fp.judge(text, stage, self.p)]

    def test_exact_spaced_and_bracketed_names_match(self):
        self.assertEqual(self.verdicts("송아지 A", "송아지"), ["이 단계 프로그램 사료"])
        self.assertEqual(self.verdicts("비육D(후레이크)", "비육전기"), ["이 단계 프로그램 사료"])

    def test_name_without_palgong_prefix_matches(self):
        self.assertEqual(fp.match_product("육성B", self.p)["name"], "팔공육성B(후레이크)")

    def test_unique_prefix_matches_but_ambiguous_does_not(self):
        self.assertEqual(fp.match_product("송아지", self.p)["name"], "송아지A(펠렛)")
        self.assertIsNone(fp.match_product("비육", self.p))             # 너무 짧고 비육D·비육F 둘 다 맞음 → 정하지 않는다

    def test_high_protein_is_farm_choice(self):
        self.assertEqual(self.verdicts("E800", "비육후기"), ["이 단계 단백질 높은 사료 — 농가 선택 사항"])

    def test_other_stage_and_unknown(self):
        self.assertEqual(self.verdicts("비육F", "비육전기"), ["프로그램 사료지만 다른 개월령용"])
        self.assertEqual(self.verdicts("다른회사사료", "육성우"), ["프로그램에 없는 사료"])

    def test_several_feeds_in_one_cell(self):
        self.assertEqual(self.verdicts("육성B→육성C", "육성우"), ["이 단계 프로그램 사료", "이 단계 프로그램 사료"])
        self.assertEqual(fp.judge("", "육성우", self.p), [])


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.p = fake_program()

    def test_stage_groups_months_with_same_feed(self):
        plan = fp.stage_plan(self.p, "육성우")
        self.assertEqual([g["개월령"] for g in plan], ["4~10개월", "11~16개월"])
        self.assertEqual(plan[0]["단백질_높은_사료(농가_선택)"], "없음(같은 사료)")
        self.assertEqual(plan[1]["단백질_높은_사료(농가_선택)"], "C500(후레이크)")
        self.assertEqual(plan[1]["목표체중_kg"], "325~450")
        self.assertEqual(plan[1]["조사료_kg_두_일"], "1.1~1.6")

    def test_last_stage_runs_to_shipment(self):
        self.assertEqual(fp.stage_plan(self.p, "비육후기")[-1]["개월령"], "24개월~출하 (29개월 뒤는 29개월 급여 유지)")

    def test_compare_keeps_record_and_marks_missing(self):
        c = fp.compare(self.p, {"육성우": {"배합사료 품목": "육성B", "배합사료 급여수준": "적정", "조사료 품목": ""}})
        st = {s["단계"]: s for s in c["단계별_비교"]}
        self.assertEqual(list(st), ["송아지", "육성우", "비육전기", "비육후기"])
        self.assertEqual(st["육성우"]["농가_현장조사_기록"], {"배합사료 품목": "육성B", "배합사료 급여수준": "적정"})
        self.assertEqual(st["송아지"]["농가_현장조사_기록"], "기록 없음")
        self.assertEqual(st["송아지"]["배합사료_품목_판정"], "품목 기록 없음")
        self.assertIn("번식우", c["프로그램_대상_아님"])
        self.assertEqual(fp.compare(self.p, None)["단계별_비교"][0]["농가_현장조사_기록"], "기록 없음")

    def test_program_text_has_one_line_per_month(self):
        t = fp.program_text(self.p)
        self.assertEqual(sum(1 for l in t.splitlines() if l[:2].strip().isdigit()), 29)
        self.assertIn("메모", t)


class LoadTest(unittest.TestCase):
    def setUp(self):
        fp._cache.update(prog=None, at=0.0)
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        fp._cache.update(prog=None, at=0.0)
        self.tmp.cleanup()

    def test_reads_local_file_and_caches(self):
        (self.dir / fp.FILE_NAME).write_text(json.dumps(fake_program(), ensure_ascii=False), encoding="utf-8")
        with mock.patch.object(fp, "LOCAL_DIR", self.dir):
            self.assertEqual(fp.load()["name"], "가짜 프로그램")
            (self.dir / fp.FILE_NAME).unlink()
            self.assertEqual(fp.load()["name"], "가짜 프로그램")          # 10분 안에는 다시 읽지 않는다

    def test_missing_or_broken_file_gives_none_or_last_value(self):
        with mock.patch.object(fp, "LOCAL_DIR", self.dir), self.assertLogs("consulting.feed_program", "WARNING"):
            self.assertIsNone(fp.load())
        bad = fake_program()
        bad["months"].pop(3)                                              # 4개월 줄이 빠짐
        (self.dir / fp.FILE_NAME).write_text(json.dumps(bad), encoding="utf-8")
        fp._cache.update(prog=fake_program(), at=0.0)                     # 지난 값은 있고 오래됨
        with mock.patch.object(fp, "LOCAL_DIR", self.dir), self.assertLogs("consulting.feed_program", "WARNING"):
            self.assertEqual(fp.load()["name"], "가짜 프로그램")


class PromptTest(unittest.TestCase):
    def test_feed_adds_rules_table_and_comparison_in_both_modes(self):
        p = fake_program()
        feed = {"program": fp.program_text(p), "comparison": fp.compare(p, {})}
        for kb in ("", "자료 본문"):
            system, prompt = ai_report.build_request("가농가", {}, {}, kb, "", feed)
            self.assertIn("대구축협 고급육생산프로그램 기준", system[0]["text"])
            self.assertIn("암소 비육 프로그램은 없습니다", system[0]["text"])
            self.assertEqual(system[-1]["text"], feed["program"])
            self.assertNotIn("cache_control", system[-1])
            self.assertIn("프로그램 대비 현장 사료 급여 비교", prompt)
            self.assertIn("대구축협 고급육생산프로그램, 농촌진흥청", prompt)

    def test_without_feed_prompt_is_unchanged(self):
        system, prompt = ai_report.build_request("가농가", {}, {}, "")
        self.assertNotIn("대구축협", system[0]["text"] + prompt)
        self.assertIn("(농촌진흥청 국립축산과학원 사양표준 인용 및 축협", prompt)

    def test_feed_failure_does_not_stop_report(self):
        with mock.patch.object(fp, "load", side_effect=RuntimeError("x")), self.assertLogs("consulting.ai_report", "ERROR"):
            self.assertIsNone(ai_report._feed({"survey_data": {}}))
        with mock.patch.object(fp, "load", return_value=None):
            self.assertIsNone(ai_report._feed(None))
        with mock.patch.object(fp, "load", return_value=fake_program()):
            f = ai_report._feed({"survey_data": {"feed_matrix": {"비육전기": {"배합사료 품목": "비육D"}}}})
            self.assertEqual(f["comparison"]["단계별_비교"][2]["배합사료_품목_판정"][0]["품목"], "비육D")


class BuildToolTest(unittest.TestCase):
    def test_reads_merged_cells_and_ranges(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(build_feed_program.HEADER)
        for m in range(1, 5):
            ws.append([m, 50 * m, "송아지A\n(펠렛)" if m == 1 else ("육성B" if m == 3 else None), "4.5-5" if m == 4 else m,
                       "고단백B" if m == 3 else ("송아지A\n(펠렛)" if m == 1 else None), 0.5])
        ws.merge_cells("C2:C3")
        ws.merge_cells("E2:E3")
        ws.merge_cells("C4:C5")
        ws.merge_cells("E4:E5")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.xlsx"
            wb.save(path)
            prog = build_feed_program.parse(path)
        ms = prog["months"]
        self.assertEqual([m["feed"] for m in ms], ["송아지A(펠렛)", "송아지A(펠렛)", "육성B", "육성B"])
        self.assertEqual(ms[3]["high_protein_feed"], "고단백B")
        self.assertEqual(ms[3]["feed_kg"], [4.5, 5.0])
        self.assertEqual(ms[0]["feed_kg"], [1.0, 1.0])

    def test_rejects_wrong_header_and_gaps(self):
        wb = openpyxl.Workbook()
        wb.active.append(["월령", "체중"])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.xlsx"
            wb.save(path)
            with self.assertRaises(ValueError):
                build_feed_program.parse(path)


if __name__ == "__main__":
    unittest.main()
