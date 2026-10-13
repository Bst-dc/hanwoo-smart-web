"""출하성적 입력(축평원 조회·엑셀 업로드) 검사 — 손으로 기대값을 적을 수 있는 소량 데이터만 쓴다.

축평원·GitHub 에는 붙지 않는다 (가짜 응답, 로컬 임시 DB). 운영 DB 에도 붙지 않는다.
실행: python -m unittest tests.test_shipment_input
"""
import io
import os
import sqlite3
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CONSULTING_LOCAL_ONLY"] = "1"
os.environ.setdefault("APP_PASSWORD", "test-pass")
for k in ("EKAPE_API_KEY", "GITHUB_TOKEN"):
    os.environ.pop(k, None)

import db_schema  # noqa: E402
from api.services import ekape, shipment_input as si  # noqa: E402

ISSUE_XML = ("<response><body><items><item><issueNo>{}     </issueNo><issueDate>2026-01-14</issueDate>"
             "<abattDate>2026-01-13</abattDate></item></items></body></response>")
GRADE_XML = """<response><body><items><item>
<judgeSexNm>{sex}</judgeSexNm><costAmt>{cost}</costAmt><weight>458</weight><qgrade>1+</qgrade><wgrade>A</wgrade>
<insfat>7</insfat><backfat>10</backfat><rea>99</rea><birthmonth>31</birthmonth><abattDate>2026-01-13</abattDate>
<judgeDate>2026-01-14</judgeDate></item></items></body></response>"""


def fake_get(responses):
    """URL 에 들어 있는 번호로 가짜 응답을 고른다. 값이 Exception 이면 던진다."""
    def get(url):
        for key, val in responses.items():
            if key in url:
                if isinstance(val, Exception):
                    raise val
                return val
        return "<response><body><items/></body></response>"
    return get


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db_schema.SQLITE_DDL)
    conn.executemany("INSERT INTO farms (id, farm_name) VALUES (?, ?)", [(1, "가농가"), (2, "나농가")])
    conn.execute("""INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_date, slaughter_year,
                    carcass_weight, price_per_kg, total_price, data_source)
                    VALUES (1, '002000000001', '거세', '2024-01-01', 2024, 400, 20000, 8000000, 'ekape_api')""")
    conn.execute("""INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_date, slaughter_year, carcass_weight)
                    VALUES (2, '002000000002', '암', '2024-02-02', 2024, 350)""")
    conn.commit()
    return conn


def xlsx(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    return buf.getvalue()


# 실제 '농가출하데이터.xlsx' 와 같은 모양: 첫 시트는 작업 기록, 이력번호는 앞 '00' 이 떨어진 숫자, 이름 칸은 '최종농장주'
EXCEL_ROWS = pd.DataFrame({
    "이력번호": [2000000001, 2000000002, 2000000003, 2000000004, None, 2000000003],   # 빈 칸이 있어 소수(.0)로 읽힌다
    "성별": ["거세", "암", None, "수", "거세", "거세"],
    "도축일자": ["2026-03-01", "2026-03-02", None, 20260304, "2026-03-05", "2026.3.6"],
    "최종농장주": ["가농가", "나농가", "가농가", "가농가", "가농가", "가농가"],
    "도체중": [500, 380, "-", 610, 1, 505],
    "육질등급": ["1++", "1", None, "2", "1", "1+"],
    "육량등급": ["A", "B", "C", None, "A", "B"],
    "근내지방도": [9, 4, 5, 2, 1, 7],
    "등지방두께": [12, 13, 14, 6, 1, 11],
    "등심단면적": [101, 92, 95, 99, 1, 100],
    "도축개월령": [30, 58, 31, 27, 1, 30],
})
EXCEL = xlsx({"Claude Log": pd.DataFrame({"Turn #": [1], "Details": ["기록"]}), "데이터": EXCEL_ROWS})


class EkapeTest(unittest.TestCase):
    def test_normalize_animal_no(self):
        n = ekape.normalize_animal_no
        self.assertEqual(n("002 1531 7717 0"), "002153177170")
        self.assertEqual(n("002-1531-7717-0"), "002153177170")
        self.assertEqual(n(2019416036), "002019416036")
        self.assertEqual(n(2019416036.0), "002019416036")
        self.assertEqual(n("2019416036.0"), "002019416036")
        self.assertEqual((n(None), n(float("nan"))), ("", ""))
        self.assertEqual(n("KOR123"), "KOR123")

    def test_split_input_drops_short_and_duplicates(self):
        nos, dup = ekape.split_input("002000000001, 2000000001\n123\n\n002-0000-0000-2\n")
        self.assertEqual(nos, ["002000000001", "002000000002"])
        self.assertEqual(dup, 1)

    def test_parse_grade_maps_fields_and_gender(self):
        r = ekape.parse_grade(GRADE_XML.format(sex="거세", cost="21000"), "002000000009")
        self.assertEqual(r, {"animal_no": "002000000009", "gender": "거세", "costAmt": 21000.0, "carcass_weight": 458.0,
                             "grade_quality": "1+", "grade_yield": "A", "bms": 7.0, "backfat": 10.0, "ribeye": 99.0,
                             "month_age": 31.0, "slaughter_date": "2026-01-13"})
        self.assertEqual(ekape.parse_grade(GRADE_XML.format(sex="암", cost=""), "x")["gender"], "암")
        self.assertIsNone(ekape.parse_grade(GRADE_XML.format(sex="", cost=""), "x")["gender"])
        self.assertIsNone(ekape.parse_grade("<r/>", "x"))                       # item 없음

    def test_fetch_one_reasons(self):
        ok = fake_get({"animalNo=002000000009": ISSUE_XML.format("A-1"), "issueNo=A-1": GRADE_XML.format(sex="수", cost="1")})
        rec, why = ekape.fetch_one("002000000009", "KEY", ok)
        self.assertEqual((rec["gender"], why), ("수", ""))
        self.assertIn("등급판정 기록 없음", ekape.fetch_one("002000000008", "KEY", fake_get({}))[1])
        self.assertIn("형식 오류", ekape.fetch_one("1", "KEY", fake_get({"animalNo=1": "<<not xml"}))[1])
        self.assertIn("연결 실패 (TimeoutError)", ekape.fetch_one("1", "KEY", fake_get({"animalNo=1": TimeoutError()}))[1])

    def test_second_call_sends_issue_date(self):
        """확인서 번호는 다시 쓰인다 → 발급일을 같이 보내야 이 소의 성적이 나온다 (실제 응답 모양)."""
        urls = []
        issue = ("<response><body><items><item><abattDate>2023-08-31</abattDate><animalNo>002158963731</animalNo>"
                 "<issueDate>2023-09-01</issueDate><issueNo>0905-50642     </issueNo><judgeSexNm>거세</judgeSexNm></item></items></body></response>")
        grade = GRADE_XML.format(sex="거세", cost="").replace("2026-01-13", "2023-08-31").replace("<item>", "<item><cattleNo>002158963731</cattleNo>")

        def get(url):
            urls.append(url)
            return issue if "animalNo=" in url else grade
        rec, why = ekape.fetch_one("002158963731", "KEY", get)
        self.assertEqual((why, rec["slaughter_date"]), ("", "2023-08-31"))
        self.assertIn("issueNo=0905-50642&issueDate=2023-09-01&", urls[1])

    def test_rejects_grade_of_another_cow(self):
        """번호만으로 조회돼 다른 소의 성적이 오면 저장하지 않게 실패로 돌린다."""
        other_no = fake_get({"animalNo=002000000009": ISSUE_XML.format("A-9"),
                             "issueNo=A-9": GRADE_XML.format(sex="암", cost="").replace("<item>", "<item><cattleNo>002999999999</cattleNo>")})
        self.assertIn("다른 소", ekape.fetch_one("002000000009", "KEY", other_no)[1])
        other_day = fake_get({"animalNo=002000000009": ISSUE_XML.format("A-9"),
                              "issueNo=A-9": GRADE_XML.format(sex="암", cost="").replace("2026-01-13", "2026-09-02")})
        self.assertIn("다른 소", ekape.fetch_one("002000000009", "KEY", other_day)[1])

    def test_fetch_many_keeps_input_order(self):
        resp = {"animalNo=002000000009": ISSUE_XML.format("A-9"), "issueNo=A-9": GRADE_XML.format(sex="거세", cost="1"),
                "animalNo=002000000007": ISSUE_XML.format("A-7"), "issueNo=A-7": GRADE_XML.format(sex="암", cost="1")}
        found, failed = ekape.fetch_many(["002000000009", "002000000008", "002000000007"], "KEY", fake_get(resp))
        self.assertEqual([r["animal_no"] for r in found], ["002000000009", "002000000007"])
        self.assertEqual([f["animal_no"] for f in failed], ["002000000008"])


class SaveApiTest(unittest.TestCase):
    def test_api_params_follow_old_rules(self):
        p = si.api_params(1, {"animal_no": "2000000005", "gender": None, "slaughter_date": "", "carcass_weight": 450.5,
                              "costAmt": 20000.0, "month_age": 30.0})
        self.assertEqual(p[:5], (1, "002000000005", "거세", "2025-01-01", 2025))     # 성별·날짜 기본값
        self.assertEqual(p[-2:], (20000.0, 9010000))                                  # 단가, int(450.5*20000)
        p = si.api_params(1, {"animal_no": "002000000006", "gender": " 암 ", "slaughter_date": "2026-01-13", "costAmt": None})
        self.assertEqual((p[2], p[4], p[-2], p[-1]), ("암", 2026, 0, 0))             # 단가 없으면 0
        self.assertIsNone(si.api_params(1, {"animal_no": "  "}))

    def test_save_api_upserts_including_price_and_moves_farm(self):
        conn = memory_db()
        recs = [{"animal_no": "002000000001", "gender": "거세", "slaughter_date": "2026-01-13", "carcass_weight": 470.0,
                 "costAmt": 21000.0, "grade_quality": "1++", "bms": 9.0},
                {"animal_no": "002000000002", "gender": "암", "slaughter_date": "2026-01-14", "carcass_weight": 360.0, "costAmt": None},
                {"animal_no": "", "gender": "암"}]
        own = si.ownership(conn, 1, [r["animal_no"] for r in recs[:2]] + ["002000000099"])
        self.assertEqual((own["new"], own["update"], own["move"], own["moved_from"]), (1, 1, 1, [{"farm": "나농가", "count": 1}]))
        self.assertEqual(si.save_api(conn, 1, recs), {"saved": 2, "skipped": 1})
        rows = {r["animal_no"]: dict(r) for r in conn.execute("SELECT * FROM shipment_records")}
        a, b = rows["002000000001"], rows["002000000002"]
        self.assertEqual((a["carcass_weight"], a["price_per_kg"], a["total_price"], a["data_source"], a["slaughter_year"]),
                         (470.0, 21000, 9870000, "ekape_api", 2026))
        self.assertEqual((b["farm_id"], b["price_per_kg"], b["total_price"]), (1, 0, 0))   # 나농가 → 가농가로 옮겨짐
        self.assertEqual(len(rows), 2)

    def test_save_rolls_back_everything_on_error(self):
        conn = memory_db()
        bad = [{"animal_no": "002000000003", "carcass_weight": 1.0}, {"animal_no": "002000000004"}]
        params = [si.api_params(1, r) for r in bad]
        params[1] = params[1][:-1]                      # 값 개수가 틀린 두 번째 행 → 오류
        with self.assertRaises(Exception):
            si._save(conn, si.API_SQL, params)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM shipment_records").fetchone()[0], 2)   # 첫 행도 안 들어감


class ExcelTest(unittest.TestCase):
    def test_finds_data_sheet_and_cleans_values(self):
        p = si.parse_excel(EXCEL)
        self.assertEqual((p["sheet"], p["total_rows"], p["invalid"], p["name_col"]), ("데이터", 6, 1, "최종농장주"))
        r = {x["animal_no"]: x for x in p["rows"]}
        self.assertEqual(list(r), ["002000000001", "002000000002", "002000000003", "002000000004"])
        self.assertEqual((r["002000000001"]["carcass_weight"], r["002000000001"]["grade_quality"]), (500.0, "1++"))
        third = p["rows"][2]                                       # 이력번호 3 의 첫 행
        self.assertEqual((third["gender"], third["slaughter_date"], third["date_missing"], third["carcass_weight"], third["grade_quality"]),
                         ("거세", "2025-01-01", True, None, None))  # 빈 성별→거세, 빈 날짜→기본값, '-'→빈 값
        self.assertEqual((r["002000000004"]["gender"], r["002000000004"]["slaughter_date"], r["002000000004"]["grade_yield"]),
                         ("수", "2026-03-04", None))
        self.assertEqual(p["rows"][-1]["slaughter_date"], "2026-03-06")    # 2026.3.6 → 2026-03-06

    def test_excel_gender_and_date_rules(self):
        self.assertEqual([si.excel_gender(v) for v in ["거세우", "암소", "수소", "", "기타"]], ["거세", "암", "수", "거세", "암"])
        self.assertEqual(si.excel_date(pd.Timestamp("2026-05-07")), ("2026-05-07", 2026, False))
        self.assertEqual(si.excel_date("20260507.0"), ("2026-05-07", 2026, False))
        self.assertEqual(si.excel_date(pd.NaT), ("2025-01-01", 2025, True))

    def test_match_mode_keeps_only_this_farms_rows(self):
        p = si.parse_excel(EXCEL)
        self.assertEqual(si.name_summary(p, "가농가"), {"col": "최종농장주", "match": 4, "blank": 0, "others": [{"name": "나농가", "count": 1}]})
        self.assertEqual(len(si.choose_rows(p, "가농가", "match")), 4)
        self.assertEqual(len(si.choose_rows(p, "가농가", "all")), 5)

    def test_no_id_column_is_an_error(self):
        with self.assertRaisesRegex(si.InputError, "이력번호"):
            si.parse_excel(xlsx({"시트": pd.DataFrame({"번호": [1]})}))
        with self.assertRaisesRegex(si.InputError, "읽지 못했습니다"):
            si.parse_excel(b"not an excel file")

    def test_save_excel_keeps_price_columns(self):
        conn = memory_db()
        rows = si.choose_rows(si.parse_excel(EXCEL), "가농가", "match")
        self.assertEqual(si.save_excel(conn, 1, rows), {"saved": 3, "rows": 4})          # 3번 개체가 두 줄
        a = dict(conn.execute("SELECT * FROM shipment_records WHERE animal_no='002000000001'").fetchone())
        self.assertEqual((a["carcass_weight"], a["price_per_kg"], a["total_price"], a["data_source"]), (500.0, 20000, 8000000, "excel"))
        c = dict(conn.execute("SELECT * FROM shipment_records WHERE animal_no='002000000003'").fetchone())
        self.assertEqual((c["slaughter_date"], c["carcass_weight"], c["grade_quality"]), ("2026-03-06", 505.0, "1+"))  # 나중 행이 남는다
        self.assertEqual(conn.execute("SELECT farm_id FROM shipment_records WHERE animal_no='002000000002'").fetchone()[0], 2)  # 나농가 행은 안 건드림


class InputApiTest(unittest.TestCase):
    """HTTP 경로: 조회·미리보기는 쓰지 않고, 옮겨짐·이름 불일치는 확인을 받아야 저장된다."""

    def setUp(self):
        from fastapi.testclient import TestClient
        from api import config
        from api.main import app
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        path = Path(self._tmp.name) / "consulting.db"
        conn = sqlite3.connect(path)
        conn.executescript(db_schema.SQLITE_DDL)
        conn.executemany("INSERT INTO farms (id, farm_name) VALUES (?, ?)", [(1, "가농가"), (2, "나농가")])
        conn.execute("INSERT INTO shipment_records (farm_id, animal_no, gender) VALUES (2, '002000000002', '암')")
        conn.commit()
        conn.close()
        patcher = mock.patch.object(config, "DB_PATH", path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = path
        self.client = TestClient(app)
        self.client.post("/api/auth/login", json={"password": os.environ["APP_PASSWORD"]})

    def count(self):
        c = sqlite3.connect(self.path)
        try:
            return c.execute("SELECT COUNT(*) FROM shipment_records").fetchone()[0]
        finally:
            c.close()

    def upload(self, url, mode="match", confirm=None, data=EXCEL, name="농가출하데이터.xlsx"):
        form = {"mode": mode}
        if confirm is not None:
            form["confirm"] = "true" if confirm else "false"
        return self.client.post(url, files={"file": (name, data)}, data=form)

    def test_lookup_without_key_is_503(self):
        r = self.client.post("/api/farms/1/shipments/lookup", json={"text": "002000000001"})
        self.assertEqual(r.status_code, 503)

    def test_lookup_returns_status_and_does_not_write(self):
        found = [{"animal_no": "002000000002", "gender": "암"}, {"animal_no": "002000000005", "gender": "거세"}]
        with mock.patch.object(ekape, "api_key", return_value="KEY"), \
                mock.patch.object(ekape, "fetch_many", return_value=(found, [{"animal_no": "002000000006", "reason": "x"}])):
            r = self.client.post("/api/farms/1/shipments/lookup", json={"text": "002000000002\n002000000005\n002000000006"})
        d = r.json()
        self.assertEqual([x["status"] for x in d["records"]], ["move", "new"])
        self.assertEqual(d["ownership"]["moved_from"], [{"farm": "나농가", "count": 1}])
        self.assertEqual(self.count(), 1)

    def test_save_api_needs_confirm_to_move(self):
        body = {"records": [{"animal_no": "002000000002", "gender": "암", "carcass_weight": 360}]}
        self.assertEqual(self.client.post("/api/farms/1/shipments/save-api", json=body).status_code, 409)
        r = self.client.post("/api/farms/1/shipments/save-api", json={**body, "confirm": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["saved"], r.json()["backup"]["ok"]), (1, None))     # 로컬 모드라 백업 안 함
        self.assertEqual(self.count(), 1)

    def test_save_api_rejects_text_in_number_field(self):
        r = self.client.post("/api/farms/1/shipments/save-api", json={"records": [{"animal_no": "002000000009", "bms": "많음"}]})
        self.assertEqual(r.status_code, 422)

    def test_excel_preview_writes_nothing(self):
        r = self.upload("/api/farms/1/shipments/excel/preview")
        d = r.json()
        self.assertEqual((d["sheet"], d["mode"], d["selected_rows"], d["unique"], d["duplicates"], d["date_missing"]), ("데이터", "match", 4, 3, 1, 1))
        self.assertEqual((d["ownership"]["new"], d["needs_confirm"]), (3, False))
        all_ = self.upload("/api/farms/1/shipments/excel/preview", mode="all").json()
        self.assertEqual((all_["selected_rows"], all_["ownership"]["move"], all_["needs_confirm"]), (5, 1, True))
        self.assertEqual(self.count(), 1)

    def test_excel_save_match_then_all_needs_confirm(self):
        r = self.upload("/api/farms/1/shipments/excel/save")
        self.assertEqual((r.status_code, r.json()["saved"]), (200, 3))
        self.assertEqual(self.count(), 4)
        self.assertEqual(self.upload("/api/farms/1/shipments/excel/save", mode="all").status_code, 409)
        self.assertEqual(self.upload("/api/farms/1/shipments/excel/save", mode="all", confirm=True).status_code, 200)
        self.assertEqual(self.count(), 4)                            # 나농가 개체가 가농가로 옮겨졌을 뿐 행 수는 같다

    def test_excel_rejects_non_xlsx(self):
        self.assertEqual(self.upload("/api/farms/1/shipments/excel/preview", name="a.csv").status_code, 422)
        self.assertEqual(self.upload("/api/farms/1/shipments/excel/preview", data=b"junk").status_code, 422)
        self.assertEqual(self.upload("/api/farms/99/shipments/excel/preview").status_code, 404)


if __name__ == "__main__":
    unittest.main()
