"""수기용 현장조사표(인쇄 양식) 검사 — 양식 항목이 빠짐없이 나오는지, 농가 정보가 미리 적히는지, 다운로드 API.
실행: python -m unittest tests.test_survey_sheet
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_surveys import SurveyApiTest as _Base  # noqa: E402  (임시 DB·로그인 준비를 같이 쓴다)

from api.services import survey_sheet, surveys  # noqa: E402


class SheetHtmlTest(unittest.TestCase):
    def test_blank_sheet_has_every_form_field_and_option(self):
        html = survey_sheet.build_html()
        for s in surveys.FORM:
            for f in s["fields"]:
                if f["kind"] == "date" or f["key"] in surveys.WEATHER_FIELDS:   # 날씨는 지역을 고르면 앱이 채워서 칸이 없다
                    continue
                self.assertIn(survey_sheet._plain(f["label"]), html.replace("&amp;", "&"), f["key"])
                for o in f.get("options", []):
                    self.assertIn(o.replace("&", "&amp;"), html, f"{f['key']}: {o}")
        for stage in surveys.FEED_STAGES:
            self.assertIn(stage, html)
        for row in surveys.FEED_ROWS:
            self.assertIn(row, html)
        self.assertNotIn("☑", html)                      # 빈 양식에는 체크된 칸이 없다

    def test_prefill_farm_name_code_region_and_weather(self):
        html = survey_sheet.build_html({"id": 1, "name": "가농가", "code": "M123", "region": "영천"})
        self.assertIn("가농가", html)
        self.assertIn("M123", html)
        self.assertIn("☑ 영천", html)
        self.assertEqual(html.count("☑"), 1)
        self.assertIn("1047.7", html)                    # 영천 연강수량
        self.assertIn("영천 관측소 (직접)", html)

    def test_unknown_region_is_not_checked_and_no_weather_values(self):
        html = survey_sheet.build_html({"id": 1, "name": "나농가", "code": "", "region": "서울"})
        self.assertNotIn("☑", html)
        self.assertNotIn("1047.7", html)

    def test_html_is_escaped(self):
        html = survey_sheet.build_html({"id": 1, "name": "<script>alert(1)</script>", "code": "", "region": ""})
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_emoji_labels_are_plain(self):
        self.assertEqual(survey_sheet._plain("🎯 농가 경영 목표 (출하 전략)"), "농가 경영 목표 (출하 전략)")
        self.assertEqual(survey_sheet._plain("연평균기온 (℃)"), "연평균기온 (℃)")


class SheetApiTest(_Base):
    def test_blank_download_and_inline(self):
        r = self.client.get("/api/surveys/sheet")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertIn("text/html", r.headers["content-type"])
        r = self.client.get("/api/surveys/sheet", params={"inline": 1})
        self.assertTrue(r.headers["content-disposition"].startswith("inline"))
        self.assertIn("현장 점검 소견", r.text)

    def test_farm_sheet_prefilled_and_unknown_farm_404(self):
        farm = self.client.get("/api/farms").json()["farms"][0]
        r = self.client.get("/api/surveys/sheet", params={"farm_id": farm["id"], "inline": 1})
        self.assertEqual(r.status_code, 200)
        self.assertIn(farm["name"], r.text)
        self.assertEqual(self.client.get("/api/surveys/sheet", params={"farm_id": 99999}).status_code, 404)

    def test_login_required(self):
        from fastapi.testclient import TestClient
        from api.main import app
        self.assertEqual(TestClient(app).get("/api/surveys/sheet").status_code, 401)


if __name__ == "__main__":
    unittest.main()
