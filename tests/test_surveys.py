"""2단계 · 현장방문조사 검사 — 손으로 기대값을 적을 수 있는 작은 데이터, 임시 DB. 운영 DB 에는 붙지 않는다.
실행: python -m unittest tests.test_surveys
"""
import copy
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CONSULTING_LOCAL_ONLY"] = "1"
os.environ.setdefault("APP_PASSWORD", "test-pass")
os.environ.pop("GITHUB_TOKEN", None)

import db_schema  # noqa: E402
from api.services import surveys as sv  # noqa: E402

TODAY = date(2026, 10, 13)

# 엑셀에서 옮긴 실제 조사표와 같은 모양: 빈 선택 항목('')과 양식에 없는 _extra 가 있다
STORED = {
    "investigator": "조사자", "visitDate": "2026-06-22", "memberName": "", "memberId": "", "region": "영천",
    "farmType": "겸업", "bizGoal": "", "dailyAvgTemp": 14.0, "highTemp": 36.7, "lowTemp": -11.8, "annualPrecip": 1047.7,
    "avgWindSpeed": 1.7, "avgHumidity": 67.3, "breedingType": "일관사육", "fatteningPenSize": "5X10",
    "fatteningPenDensity": "적정", "breedingPenSize": "", "breedingPenDensity": "적정", "calfPenSize": "기타",
    "calfPenDensity": "높음", "bulkBin": "여", "autoFeeder": "부", "tmr": "부", "selfMix": "부", "castrationAge": 8,
    "castrationMethod": "무혈", "floorCondition": "미흡", "dewormingCount": 0, "waterQuality": "", "manureScore": "",
    "troughCleaning": "", "feedOrder": "조사료 → 배합사료", "feedFrequency": 2, "forageQuality": "",
    "feed_matrix": {st: {row: ("적정" if "수준" in row else "") for row in sv.FEED_ROWS} for st in sv.FEED_STAGES},
    "countCow": 0, "countSteer": 0, "countGrowing": 0, "countCalf": 0, "countOptimal": 0, "aiMethod": "자가 수정",
    "calvingInterval": 13.0, "mortalityRate": 0.0, "weaningAge": 4.0, "artificialRearing": "아니오",
    "consultingNotes": "소견", "_extra": {"solarPower": "부", "zone": "A"},
}


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db_schema.SQLITE_DDL)
    conn.executemany("INSERT INTO farms (id, farm_name) VALUES (?, ?)", [(1, "가농가"), (2, "나농가")])
    conn.execute("INSERT INTO visits (id, farm_id, visit_number, visit_date, consultant_name) VALUES (10, 1, 1, '2026-06-22', '조사자')")
    conn.execute("INSERT INTO field_surveys (visit_id, facility_info, survey_data) VALUES (10, '{\"steer_pen\":\"5X10\"}', ?)",
                 (json.dumps(STORED, ensure_ascii=False),))
    conn.commit()
    return conn


def stored(conn, visit_id):
    return json.loads(conn.execute("SELECT survey_data FROM field_surveys WHERE visit_id = ?", (visit_id,)).fetchone()[0])


class FormValuesTest(unittest.TestCase):
    def test_blank_form_uses_old_app_defaults(self):
        v = sv.blank(TODAY)["values"]
        self.assertEqual((v["region"], v["farmType"], v["fatteningPenDensity"], v["manureScore"], v["feedFrequency"]),
                         ("대구", "전업", "적정", "적정(모양 유지)", 2))
        self.assertEqual((v["visitDate"], v["investigator"], v["dailyAvgTemp"], v["avgHumidity"]), ("2026-10-13", "컨설턴트 배성태", 15.2, 61.1))
        self.assertEqual(v["feed_matrix"]["번식우"]["조사료 급여수준"], "")

    def test_saved_blank_option_opens_unselected(self):
        v = sv.form_values(STORED, TODAY)
        self.assertIsNone(v["bizGoal"])            # 저장된 '' → 선택 안 함
        self.assertIsNone(v["breedingPenSize"])
        self.assertEqual(v["calfPenSize"], "기타")
        self.assertEqual(v["visitDate"], "2026-06-22")

    def test_missing_key_gets_default_and_zero_weather_gets_region_value(self):
        s = {k: v for k, v in STORED.items() if k != "floorCondition"}
        s["highTemp"] = 0.0
        v = sv.form_values(s, TODAY)
        self.assertEqual(v["floorCondition"], "양호")      # 키가 없으면 기본값
        self.assertEqual((v["highTemp"], v["lowTemp"]), (36.7, -11.8))   # 0 → 영천 값, 저장값은 그대로


class SaveTest(unittest.TestCase):
    def test_round_trip_without_changes_keeps_everything(self):
        conn = memory_db()
        values = sv.read(conn, 1, 10, TODAY)["values"]
        sv.update(conn, 1, 10, values)
        self.assertEqual(stored(conn, 10), STORED)                           # '' · _extra · 숫자 타입까지 같다
        self.assertEqual(conn.execute("SELECT facility_info FROM field_surveys WHERE visit_id=10").fetchone()[0], '{"steer_pen":"5X10"}')

    def test_update_changes_fields_and_visit_row(self):
        conn = memory_db()
        values = sv.read(conn, 1, 10, TODAY)["values"]
        values.update(bizGoal="복합", visitDate="2026-07-01", investigator="새 조사자", castrationAge="9", calvingInterval="12.5")
        values["feed_matrix"]["송아지"]["배합사료 품목"] = "  어린소용  "
        r = sv.update(conn, 1, 10, values)
        s = stored(conn, 10)
        self.assertEqual(r, {"visit_id": 10, "visit_number": 1})
        self.assertEqual((s["bizGoal"], s["castrationAge"], s["calvingInterval"], s["breedingPenSize"]), ("복합", 9, 12.5, ""))
        self.assertEqual(s["feed_matrix"]["송아지"]["배합사료 품목"], "어린소용")
        self.assertEqual(s["_extra"], STORED["_extra"])
        v = conn.execute("SELECT visit_date, consultant_name FROM visits WHERE id=10").fetchone()
        self.assertEqual(tuple(v), ("2026-07-01", "새 조사자"))

    def test_create_numbers_visits_per_farm(self):
        conn = memory_db()
        a = sv.create(conn, 1, sv.blank(TODAY)["values"])
        b = sv.create(conn, 2, sv.blank(TODAY)["values"])
        self.assertEqual((a["visit_number"], b["visit_number"]), (2, 1))
        s = stored(conn, a["visit_id"])
        self.assertEqual((s["region"], s["dailyAvgTemp"], s["visitDate"]), ("대구", 15.2, "2026-10-13"))
        self.assertEqual(len(s), len(sv.FIELDS))

    def test_other_farms_visit_is_not_found(self):
        conn = memory_db()
        self.assertIsNone(sv.read(conn, 2, 10, TODAY))
        self.assertIsNone(sv.update(conn, 2, 10, sv.blank(TODAY)["values"]))

    def test_bad_values_are_rejected(self):
        base = sv.blank(TODAY)["values"]
        for change, msg in [({"region": "서울"}, "선택지"), ({"castrationAge": "8.5"}, "정수"), ({"mortalityRate": "많음"}, "숫자"),
                            ({"visitDate": "6월 22일"}, "조사일자"), ({"consultingNotes": "가" * 5001}, "너무 깁니다")]:
            with self.assertRaisesRegex(sv.SurveyError, msg):
                sv.clean({**base, **change})
        bad_feed = copy.deepcopy(base["feed_matrix"])
        bad_feed["송아지"]["조사료 급여수준"] = "많이"
        with self.assertRaisesRegex(sv.SurveyError, "낮음/적정/높음"):
            sv.clean({**base, "feed_matrix": bad_feed})
        with self.assertRaisesRegex(sv.SurveyError, "빠졌습니다"):
            sv.clean({k: v for k, v in base.items() if k != "tmr"})


class SurveyApiTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from api import config
        from api.main import app
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "consulting.db"
        conn = memory_db()
        disk = sqlite3.connect(path)
        conn.backup(disk)
        disk.close()
        p = mock.patch.object(config, "DB_PATH", path)
        p.start()
        self.addCleanup(p.stop)
        self.path = path
        self.client = TestClient(app)
        self.client.post("/api/auth/login", json={"password": os.environ["APP_PASSWORD"]})

    def test_form_list_read_create_update(self):
        f = self.client.get("/api/surveys/form").json()
        self.assertEqual([s["title"][:2] for s in f["sections"]], ["1.", "2.", "3.", "4.", "5.", "6."])
        lst = self.client.get("/api/farms/1/visits").json()
        self.assertEqual([(v["visit_number"], v["has_survey"]) for v in lst["visits"]], [(1, True)])
        d = self.client.get("/api/farms/1/visits/10").json()
        self.assertEqual(d["extra_keys"], ["_extra"])
        r = self.client.put("/api/farms/1/visits/10", json={"values": d["values"]})
        self.assertEqual((r.status_code, r.json()["backup"]["ok"]), (200, None))
        r = self.client.post("/api/farms/1/visits", json={"values": lst["blank"]["values"]})
        self.assertEqual((r.status_code, r.json()["visit_number"]), (200, 2))

    def test_errors(self):
        self.assertEqual(self.client.get("/api/farms/2/visits/10").status_code, 404)
        self.assertEqual(self.client.get("/api/farms/99/visits").status_code, 404)
        vals = self.client.get("/api/farms/1/visits").json()["blank"]["values"]
        r = self.client.post("/api/farms/1/visits", json={"values": {**vals, "region": "서울"}})
        self.assertEqual(r.status_code, 422)
        c = sqlite3.connect(self.path)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM visits").fetchone()[0], 1)    # 실패하면 아무것도 안 들어감
        c.close()


if __name__ == "__main__":
    unittest.main()
