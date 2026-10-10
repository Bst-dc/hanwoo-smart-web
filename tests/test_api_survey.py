"""2단계 · 현장방문조사 API 시험.

1) 지역·날씨·선택지 상수와 조사표 키 순서·값 종류(int/float)가 streamlit_app.py 소스와 같은지,
2) 신규 저장·수정 저장이 기존 앱과 같은 행·JSON 을 남기는지, 수정할 때 양식 밖 키('_extra')를 지키는지 본다.
실행: python -m unittest tests.test_api_survey
"""
import ast
import json
import re
import unittest
from unittest import mock

from test_api_dashboard import APP_SOURCE, ApiTestBase  # noqa: E402

from api.models import SurveyData  # noqa: E402
from api.services import backup, survey  # noqa: E402

SECTION = APP_SOURCE[APP_SOURCE.index('elif menu == "2단계 · 현장방문조사":'):APP_SOURCE.index('elif menu == "3단계 · AI 리포트":')]


def legacy_literal(name: str):
    m = re.search(rf"^{name} = (\[.*?\]|\{{.*?\n\}}|[\d.]+)\n", APP_SOURCE, re.DOTALL | re.MULTILINE)
    if not m:
        raise AssertionError(f"streamlit_app.py 에서 {name} 을 찾지 못함")
    return ast.literal_eval(m.group(1))


def section_list(var: str):
    m = re.search(rf"\b{var} = (\[[^\]]*\])", SECTION)
    if not m:
        raise AssertionError(f"조사표 화면에서 {var} 를 찾지 못함")
    return ast.literal_eval(m.group(1))


def form(**over):
    """화면이 보내는 것과 같은 조사표 (모든 항목)."""
    d = {k: (f.default if f.default is not None and not callable(f.default) else None) for k, f in SurveyData.model_fields.items()}
    d.update(investigator="컨설턴트", visitDate="2026-10-11", memberName="조합원", memberId="M1", region="영천",
             farmType="전업", bizGoal="복합", dailyAvgTemp=14.0, highTemp=36.7, lowTemp=-11.8, annualPrecip=1047.7,
             avgWindSpeed=1.7, avgHumidity=67.3, breedingType="일관사육", feed_matrix={"송아지": {"배합사료 품목": "입붙이기"}},
             castrationAge=7, dewormingCount=2, feedFrequency=3, countSteer=40, calvingInterval=13.5, consultingNotes="소견")
    d.update(over)
    return d


class LegacyConstantsTest(unittest.TestCase):
    def test_weather_regions_feed(self):
        self.assertEqual(survey.WEATHER_DATA, legacy_literal("WEATHER_DATA"))
        self.assertEqual(survey.REGION_OPTIONS, list(legacy_literal("WEATHER_DATA")) + ["기타"])
        self.assertEqual(survey.FEED_CATS, legacy_literal("FEED_CATS"))
        self.assertEqual(survey.NATIONAL_PRECIP_2025, legacy_literal("NATIONAL_PRECIP_2025"))
        self.assertEqual(survey.FEED_ROWS, section_list("feed_index"))

    def test_choices(self):
        for key, var in [("bizGoal", "biz_opts"), ("breedingType", "breeding_opts"), ("penSize", "pen_size_opts"),
                         ("penDensity", "pen_density_opts"), ("yesNo", "yes_no_opts"), ("floorCondition", "floor_opts"),
                         ("waterQuality", "water_opts"), ("manureScore", "manure_opts"), ("yesNo2", "yes_no2_opts"),
                         ("forageQuality", "forage_opts"), ("aiMethod", "ai_opts")]:
            self.assertEqual(survey.CHOICES[key], section_list(var), key)
        self.assertIn('["전업", "겸업"]', SECTION)
        self.assertIn('["무혈","유혈"]', SECTION)

    def test_keys_in_legacy_order(self):
        legacy_keys = list(dict.fromkeys(re.findall(r"s_dict\['(\w+)'\]", SECTION)))
        self.assertEqual(list(SurveyData.model_fields), legacy_keys)

    def test_number_types_match_legacy(self):
        # 기존 화면: value=int(...) 는 정수로, float(...)·날씨(wv) 는 실수로 저장된다
        for key, kind in re.findall(r"s_dict\['(\w+)'\] = [\w.]+\.number_input\([^\n]*?value=(int|float|wv)\(", SECTION):
            want = int if kind == "int" else float
            self.assertIs(SurveyData.model_fields[key].annotation, want, key)


class SurveyApiTest(ApiTestBase):
    def setUp(self):
        super().setUp()
        self.patches = [
            mock.patch("api.config.app_password", return_value=None),
            mock.patch("api.routers.surveys.persist_db",
                       return_value=backup.BackupResult(ok=True, message="GitHub 에 자동 백업되었습니다.")),
        ]
        self.patches[0].start()
        self.backup_mock = self.patches[1].start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def stored(self, visit_id):
        return json.loads(self.conn.execute("SELECT survey_data FROM field_surveys WHERE visit_id = ?", (visit_id,)).fetchone()[0])

    def test_options(self):
        o = self.client.get("/api/survey/options").json()
        self.assertEqual(o["regions"][-1], "기타")
        self.assertEqual(o["weather"]["영천"]["avgTemp"], 14.0)
        self.assertEqual(o["feed_cols"], ["송아지", "육성우", "비육전기", "비육후기", "번식우"])

    def test_list_visits(self):
        self.assertEqual(self.client.get("/api/farms/1/visits").json(),
                         [{"id": 1, "visit_number": 1, "visit_date": "2026-01-01", "consultant_name": None, "has_survey": True}])
        self.assertFalse(self.client.get("/api/farms/4/visits").json()[0]["has_survey"])   # 조사표 내용 없음
        self.assertEqual(self.client.get("/api/farms/2/visits").json(), [])
        self.assertEqual(self.client.get("/api/farms/999/visits").status_code, 404)

    def test_create(self):
        r = self.client.post("/api/farms/1/visits", json=form())
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual(body["visit_number"], 2)            # 1차가 이미 있다
        v = self.conn.execute("SELECT * FROM visits WHERE id = ?", (body["visit_id"],)).fetchone()
        self.assertEqual((v["farm_id"], v["visit_number"], v["visit_date"], v["consultant_name"]), (1, 2, "2026-10-11", "컨설턴트"))
        s = self.stored(body["visit_id"])
        self.assertEqual(list(s), list(SurveyData.model_fields))
        self.assertEqual((s["castrationAge"], s["calvingInterval"], s["dailyAvgTemp"]), (7, 13.5, 14.0))
        self.assertIsInstance(s["castrationAge"], int)
        self.assertIsInstance(s["mortalityRate"], float)
        # 사료 표는 5개 성장단계 × 6행이 모두 채워진 모양으로 저장된다 (빈 칸은 '')
        self.assertEqual(list(s["feed_matrix"]), survey.FEED_COLS)
        self.assertEqual(s["feed_matrix"]["송아지"]["배합사료 품목"], "입붙이기")
        self.assertEqual(s["feed_matrix"]["번식우"], {row: "" for row in survey.FEED_ROWS})
        # 저장 형식: 한글을 그대로 둔 JSON (기존 json.dumps(ensure_ascii=False))
        raw = self.conn.execute("SELECT survey_data FROM field_surveys WHERE visit_id = ?", (body["visit_id"],)).fetchone()[0]
        self.assertIn('"region": "영천"', raw)
        self.backup_mock.assert_called_once_with("현장조사 신규 저장")

    def test_first_visit_of_farm_is_number_one(self):
        self.assertEqual(self.client.post("/api/farms/2/visits", json=form()).json()["visit_number"], 1)
        self.assertEqual(self.client.post("/api/farms/2/visits", json=form()).json()["visit_number"], 2)

    def test_update_keeps_extra_keys(self):
        self.conn.execute("UPDATE field_surveys SET survey_data = ? WHERE visit_id = 1",
                          (json.dumps({"region": "영천", "countSteer": 10, "_extra": {"waterSource": "지하수"}}, ensure_ascii=False),))
        self.conn.commit()
        r = self.client.put("/api/visits/1", json=form(region="대구", countSteer=55, visitDate="2026-02-03", investigator="조사자2"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["visit_number"], 1)
        s = self.stored(1)
        self.assertEqual((s["region"], s["countSteer"]), ("대구", 55))
        self.assertEqual(s["_extra"], {"waterSource": "지하수"})
        v = self.conn.execute("SELECT visit_date, consultant_name FROM visits WHERE id = 1").fetchone()
        self.assertEqual(tuple(v), ("2026-02-03", "조사자2"))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0], 3)   # 새 방문이 생기지 않음
        self.backup_mock.assert_called_once_with("현장조사 수정 저장")

    def test_update_visit_without_survey_row(self):
        self.conn.execute("DELETE FROM field_surveys WHERE visit_id = 3")
        self.conn.commit()
        self.assertEqual(self.client.get("/api/visits/3").json()["survey"], {})
        self.assertEqual(self.client.put("/api/visits/3", json=form()).status_code, 200)
        self.assertEqual(self.stored(3)["region"], "영천")

    def test_broken_json_opens_empty(self):
        self.conn.execute("UPDATE field_surveys SET survey_data = '{깨짐' WHERE visit_id = 1")
        self.conn.commit()
        r = self.client.get("/api/visits/1")
        self.assertEqual((r.status_code, r.json()["survey"]), (200, {}))

    def test_rejects_bad_input(self):
        cases = [form(visitDate="2026-13-01"), form(countCow=-1), form(castrationAge=7.5), form(unknown="x"),
                 form(avgHumidity=120), form(consultingNotes="가" * 5001)]
        for body in cases:
            self.assertEqual(self.client.post("/api/farms/1/visits", json=body).status_code, 422)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0], 3)
        self.backup_mock.assert_not_called()

    def test_not_found(self):
        self.assertEqual(self.client.get("/api/visits/999").status_code, 404)
        self.assertEqual(self.client.put("/api/visits/999", json=form()).status_code, 404)
        self.assertEqual(self.client.post("/api/farms/999/visits", json=form()).status_code, 404)


if __name__ == "__main__":
    unittest.main()
