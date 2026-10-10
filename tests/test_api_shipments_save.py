"""출하성적 저장 쪽(이력제 조회분 저장·엑셀 적재) 시험.

같은 입력을 두 시험 DB 에 넣어
  1) 새 API 로 저장한 결과와
  2) streamlit_app.py 의 저장 반복문을 소스에서 그대로 꺼내 실행한 결과가
행 단위로 같은지 본다. 빈 행·중복 이력번호·앞자리 0 이 빠진 숫자 이력번호·'-' 같은 글자·
다른 농가 파일(이름 불일치)을 섞는다. 실제 축평원·GitHub 는 부르지 않는다.
실행: python -m unittest tests.test_api_shipments_save
"""
import io
import re
import textwrap
import unittest
from unittest import mock

import pandas as pd

from test_api_dashboard import APP_SOURCE, ApiTestBase, make_db  # noqa: E402

from api.services import backup, shipments  # noqa: E402

FARM_ID, FARM_NAME = 1, "가농장"
OTHER_FARM_ID = 2
COLS = ("farm_id, animal_no, gender, slaughter_date, slaughter_year, month_age, carcass_weight, grade_quality,"
        " grade_yield, bms, backfat, ribeye, price_per_kg, total_price, data_source")


def legacy_block(pattern: str) -> str:
    m = re.search(pattern, APP_SOURCE, re.DOTALL)
    if not m:
        raise AssertionError(f"streamlit_app.py 에서 저장 코드를 찾지 못함: {pattern[:60]}")
    return textwrap.dedent(m.group(1))


# 기존 앱의 코드 조각 (바뀌면 이 시험이 먼저 깨진다)
LEGACY_NORMALIZE = legacy_block(r"\n(def normalize_animal_no\(value\):.*?\n    return s\n)")
LEGACY_EKAPE = legacy_block(
    r"\n([ \t]*conn = get_db\(\)\n[ \t]*cur = conn\.cursor\(\)\n[ \t]*saved = 0\n"
    r"[ \t]*for _, row in edited_df\.iterrows\(\):.*?saved \+= 1)\n")
LEGACY_EXCEL = legacy_block(r"\n([ \t]*col_map = \{.*?saved_cnt \+= 1)\n")


class _NoClose:
    def __init__(self, conn):
        self._c = conn

    def __getattr__(self, k):
        return getattr(self._c, k)

    def close(self):
        pass


def run_legacy(code: str, conn, **names) -> dict:
    ns = {"pd": pd, "re": re, "get_db": lambda: _NoClose(conn), "selected_farm_id": FARM_ID, **names}
    exec(LEGACY_NORMALIZE, ns)
    exec(code, ns)
    conn.commit()
    return ns


def table(conn):
    return [tuple(r) for r in conn.execute(f"SELECT {COLS} FROM shipment_records ORDER BY animal_no").fetchall()]


def seed(conn):
    """이미 저장돼 있던 개체 두 마리: 하나는 이 농가(단가 있음), 하나는 다른 농가."""
    conn.execute("INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_date, slaughter_year,"
                 " carcass_weight, price_per_kg, total_price, data_source)"
                 " VALUES (?, '002000000001', '거세', '2024-01-10', 2024, 450, 20000, 9000000, 'ekape_api')", (FARM_ID,))
    conn.execute("INSERT INTO shipment_records (farm_id, animal_no, gender, slaughter_date, slaughter_year,"
                 " carcass_weight, data_source) VALUES (?, '002000000002', '암', '2024-02-10', 2024, 380, 'excel')",
                 (OTHER_FARM_ID,))
    conn.commit()


# ---------------------------------------------------------------- 시험 입력
def draft(no, **v):
    base = dict(animal_no=no, gender="거세", costAmt=21000.0, carcass_weight=480.0, grade_quality="1+",
                grade_yield="A", bms=7.0, backfat=12.0, ribeye=95.0, month_age=30.0, slaughter_date="2025-03-04")
    base.update(v)
    return base


EKAPE_DRAFTS = [
    draft("002000000010"),
    draft(None),                                    # 표에 행만 추가하고 비워 둔 경우
    draft("   "),                                   # 공백뿐인 이력번호
    draft("002 0000 0001 1", gender=None),          # 띄어 쓴 번호, 성별 없음 → 거세
    draft("002-0000-0001-2", gender="암", slaughter_date=None, costAmt=None),   # 날짜 없음 → 2025-01-01, 단가 없음 → 0원
    draft("002000000010", carcass_weight=500.0, grade_quality="1++"),        # 같은 번호 두 번 → 뒤의 값
    draft("002000000002", gender="암", carcass_weight=390.0),                # 다른 농가에 있던 개체 → 이 농가로 옮겨짐
    draft("002000000013", carcass_weight=None, month_age=None, bms=None),    # 빈 숫자
]


def excel_frame(names=None):
    """'데이터' 시트와 같은 모양: 이력번호가 숫자형(앞자리 0 빠짐), 이름 열 이름은 바꿔 가며 쓴다."""
    rows = [
        # 이력번호, 성별, 도축일자, 도체중, 육질, 육량, 근내지방도, 등지방두께, 등심단면적, 도축개월령
        (2000000101, "거세", "2025-02-01", 480, "1+", "A", 7, 12, 95, 30),
        (2000000102, "암", "2025-02-02", 380, "1", "B", 5, 13, 88, 62),
        (2000000103, "수", "2024-12-30", 420, "2", "C", 3, 9, 85, 26),
        (2000000104, "미상", "2025-01-15", 400, "1", "B", 4, 10, 90, 28),     # 그 밖의 글자 → 암
        (2000000105, None, "2025-01-16", 470, "1++", "A", 9, 11, 100, 31),     # 성별 빈 칸 → 거세
        (2000000106, "거세우", "2025-01-17", "-", None, None, "-", "", None, 30),  # '-'·빈 칸 → NULL
        (2000000101, "거세", "2025-02-01", 485, "1++", "A", 8, 12, 96, 30),   # 파일 안 중복 → 뒤의 값
        (None, "거세", "2025-01-01", 450, "1", "A", 5, 10, 90, 30),            # 이력번호 빈 칸 → 건너뜀
        (1234567, "거세", "2025-01-01", 450, "1", "A", 5, 10, 90, 30),         # 7자리 → 12자리로 채워져 저장됨
        ("확인중", "거세", "2025-01-01", 450, "1", "A", 5, 10, 90, 30),        # 숫자 아닌 8자 미만 → 건너뜀
        (2000000001, "거세", "2025-03-01", 455, "1+", "B", 6, 11, 92, 31),    # 이미 있는 개체: 단가는 그대로 둬야 함
        (2000000107, "거세", None, 460, "1", "B", 5, 10, 90, 30),              # 도축일자 빈 칸 → 'nan' / 2025 (기존과 같음)
    ]
    df = pd.DataFrame(rows, columns=["이력번호", "성별", "도축일자", "도체중", "육질등급", "육량등급",
                                     "근내지방도", "등지방두께", "등심단면적", "도축개월령"])
    if names is not None:
        df.insert(1, "농가명", names)
    return df


def xlsx(df) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def reread(df):
    """앱이 받는 것과 같게: 엑셀 파일로 썼다가 pandas 로 다시 읽는다 (빈 칸 → NaN, 숫자형 이력번호 등)."""
    return shipments.read_excel(xlsx(df))


# ---------------------------------------------------------------- 기존 앱과 행 단위 대조
class LegacyParityTest(unittest.TestCase):
    def setUp(self):
        self.new, self.old = make_db(), make_db()
        seed(self.new)
        seed(self.old)

    def tearDown(self):
        self.new.close()
        self.old.close()

    def test_legacy_code_found(self):
        self.assertIn("ekape_api", LEGACY_EKAPE)
        self.assertIn("'excel'", LEGACY_EXCEL)

    def test_ekape_save_matches_legacy(self):
        saved = shipments.save_ekape_records(self.new, FARM_ID, [dict(d) for d in EKAPE_DRAFTS])
        self.new.commit()
        ns = run_legacy(LEGACY_EKAPE, self.old, edited_df=pd.DataFrame(EKAPE_DRAFTS))
        self.assertEqual(saved, ns["saved"])
        self.assertEqual(table(self.new), table(self.old))

    def test_excel_save_matches_legacy(self):
        df = reread(excel_frame())
        saved = shipments.save_excel(self.new, FARM_ID, df)
        self.new.commit()
        ns = run_legacy(LEGACY_EXCEL, self.old, df=df)
        self.assertEqual(saved, ns["saved_cnt"])
        self.assertEqual(table(self.new), table(self.old))


# ---------------------------------------------------------------- 값 하나하나 (손으로 정한 기대값)
class EkapeSaveRulesTest(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        seed(self.conn)
        self.saved = shipments.save_ekape_records(self.conn, FARM_ID, [dict(d) for d in EKAPE_DRAFTS])
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def row(self, no):
        return self.conn.execute(f"SELECT {COLS} FROM shipment_records WHERE animal_no = ?", (no,)).fetchone()

    def test_blank_rows_skipped_duplicates_counted(self):
        # 8행 중 빈 행 2개 건너뜀, 같은 번호 두 번은 두 번 다 센다 (기존 앱 안내 문구와 같은 숫자)
        self.assertEqual(self.saved, 6)
        self.assertIsNone(self.row(""))
        n = self.conn.execute("SELECT COUNT(*) FROM shipment_records WHERE farm_id = ? AND animal_no LIKE '0020000000%'",
                              (FARM_ID,)).fetchone()[0]
        self.assertEqual(n, 6)   # 기존 1 + 새 5 (002000000010 은 한 행)

    def test_duplicate_keeps_last(self):
        r = self.row("002000000010")
        self.assertEqual((r["carcass_weight"], r["grade_quality"], r["total_price"]), (500.0, "1++", 500 * 21000))

    def test_spaced_number_and_default_gender(self):
        self.assertEqual(self.row("002000000011")["gender"], "거세")

    def test_missing_date_and_price(self):
        r = self.row("002000000012")
        self.assertEqual((r["slaughter_date"], r["slaughter_year"], r["price_per_kg"], r["total_price"]),
                         ("2025-01-01", 2025, 0, 0))

    def test_moves_animal_from_other_farm(self):
        r = self.row("002000000002")
        self.assertEqual((r["farm_id"], r["carcass_weight"], r["data_source"]), (FARM_ID, 390.0, "ekape_api"))

    def test_empty_numbers_stay_null(self):
        r = self.row("002000000013")
        self.assertEqual((r["carcass_weight"], r["month_age"], r["bms"], r["total_price"]), (None, None, None, 0))


class ExcelSaveRulesTest(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        seed(self.conn)
        self.df = reread(excel_frame())
        self.saved = shipments.save_excel(self.conn, FARM_ID, self.df)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def row(self, no):
        return self.conn.execute(f"SELECT {COLS} FROM shipment_records WHERE animal_no = ?", (no,)).fetchone()

    def test_counts_match_preview(self):
        p = shipments.excel_preview(self.df, FARM_NAME)
        self.assertEqual((p["rows"], p["will_skip"], p["missing_date"]), (12, 2, 1))
        self.assertEqual(self.saved, p["rows"] - p["will_skip"])   # 미리보기 숫자 = 실제 저장 두수

    def test_numeric_animal_no_restored_to_12_digits(self):
        self.assertIsNotNone(self.row("002000000101"))
        self.assertIsNotNone(self.row("000001234567"))
        self.assertIsNone(self.row("확인중"))

    def test_gender_mapping(self):
        got = {no: self.row(no)["gender"] for no in
               ["002000000101", "002000000102", "002000000103", "002000000104", "002000000105", "002000000106"]}
        self.assertEqual(list(got.values()), ["거세", "암", "수", "암", "거세", "거세"])

    def test_duplicate_in_file_keeps_last(self):
        r = self.row("002000000101")
        self.assertEqual((r["carcass_weight"], r["grade_quality"], r["bms"]), (485.0, "1++", 8.0))

    def test_text_in_number_cells_and_blank_grades_are_null(self):
        r = self.row("002000000106")
        self.assertEqual((r["carcass_weight"], r["bms"], r["backfat"], r["ribeye"], r["grade_quality"], r["grade_yield"]),
                         (None, None, None, None, None, None))
        self.assertEqual(r["month_age"], 30.0)

    def test_existing_price_kept(self):
        r = self.row("002000000001")
        self.assertEqual((r["carcass_weight"], r["price_per_kg"], r["total_price"], r["data_source"]),
                         (455.0, 20000, 9000000, "excel"))

    def test_unreadable_date_goes_to_2025(self):
        # 기존 앱과 같게 둔 동작 (고칠지는 아직 정하지 않음): 날짜 글자는 'nan', 연도는 2025
        r = self.row("002000000107")
        self.assertEqual((r["slaughter_date"], r["slaughter_year"]), ("nan", 2025))


# ---------------------------------------------------------------- API (요청 → 저장 → 백업 호출)
class ShipmentSaveApiTest(ApiTestBase):
    def setUp(self):
        super().setUp()
        seed(self.conn)
        self.patches = [
            mock.patch("api.config.app_password", return_value=None),
            mock.patch("api.routers.shipments.persist_db",
                       return_value=backup.BackupResult(ok=True, message="GitHub 에 자동 백업되었습니다.")),
        ]
        self.patches[0].start()
        self.backup_mock = self.patches[1].start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def count(self, farm_id=FARM_ID):
        return self.conn.execute("SELECT COUNT(*) FROM shipment_records WHERE farm_id = ?", (farm_id,)).fetchone()[0]

    def upload(self, df, confirm=None, path="excel"):
        data = {} if confirm is None else {"confirm_name_mismatch": "true" if confirm else "false"}
        return self.client.post(f"/api/farms/{FARM_ID}/shipments/{path}", data=data,
                                files={"file": ("출하.xlsx", xlsx(df), "application/octet-stream")})

    # 이력제
    def test_ekape_save(self):
        before = self.count()
        r = self.client.post(f"/api/farms/{FARM_ID}/shipments/ekape", json={"records": EKAPE_DRAFTS})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["saved"], 6)
        self.assertEqual(r.json()["backup"]["ok"], True)
        self.assertEqual(self.count(), before + 5)   # 새 4 + 다른 농가에서 옮겨 온 1
        self.backup_mock.assert_called_once_with("출하성적 API 저장")

    def test_ekape_empty_and_unknown_farm(self):
        self.assertEqual(self.client.post(f"/api/farms/{FARM_ID}/shipments/ekape", json={"records": []}).status_code, 422)
        self.assertEqual(self.client.post("/api/farms/999/shipments/ekape", json={"records": EKAPE_DRAFTS}).status_code, 404)
        self.backup_mock.assert_not_called()

    def test_ekape_only_blank_rows(self):
        # 기존 앱과 같이 오류가 아니라 0두 저장으로 끝난다
        r = self.client.post(f"/api/farms/{FARM_ID}/shipments/ekape", json={"records": [draft(None), draft("")]})
        self.assertEqual((r.status_code, r.json()["saved"]), (200, 0))

    # 엑셀: 미리보기
    def test_preview(self):
        df = excel_frame(names=[FARM_NAME] * 6 + ["딴농장"] * 6)
        r = self.upload(df, path="excel/preview")
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        self.assertEqual((p["rows"], p["will_skip"], p["missing_date"], p["name_column"], p["mismatched_names"]),
                         (12, 2, 1, "농가명", ["딴농장"]))
        self.assertEqual(self.count(), 5)   # 미리보기는 저장하지 않는다
        self.backup_mock.assert_not_called()

    def test_preview_reports_missing_animal_no_column(self):
        df = excel_frame().rename(columns={"이력번호": "번호"})
        p = self.upload(df, path="excel/preview").json()
        self.assertIsNone(p["animal_no_column"])
        self.assertIn("이력번호", p["missing_columns"])
        self.assertEqual(p["will_skip"], 12)

    # 엑셀: 이름 대조
    def test_name_mismatch_blocks_until_confirmed(self):
        df = excel_frame(names=["딴농장"] * 12)
        r = self.upload(df)
        self.assertEqual(r.status_code, 409)
        self.assertIn("딴농장", r.json()["detail"])
        self.assertEqual(self.count(), 5)
        self.backup_mock.assert_not_called()

        r = self.upload(df, confirm=False)
        self.assertEqual(r.status_code, 409)

        r = self.upload(df, confirm=True)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["saved"], 10)
        self.backup_mock.assert_called_once_with("출하성적 엑셀 저장")

    def test_matching_name_needs_no_confirmation(self):
        r = self.upload(excel_frame(names=[f" {FARM_NAME} "] * 12))   # 앞뒤 공백은 무시
        self.assertEqual((r.status_code, r.json()["saved"]), (200, 10))

    def test_file_without_name_column_saves(self):
        r = self.upload(excel_frame())
        self.assertEqual((r.status_code, r.json()["saved"]), (200, 10))
        self.assertEqual(self.count(), 5 + 8)   # 이미 있던 5 + 새 8 (중복 1행은 한 번, 002000000001 은 고쳐 쓰기)

    # 엑셀: 실패 처리
    def test_failure_midway_saves_nothing(self):
        real_num = shipments._num

        def boom(v):
            if real_num(v) == 485:     # 7번째 행(중복 이력번호의 두 번째)에서 실패시킨다
                raise RuntimeError("시험용 실패")
            return real_num(v)

        before = table(self.conn)
        with mock.patch.object(shipments, "_num", side_effect=boom):
            r = self.upload(excel_frame())
        self.assertEqual(r.status_code, 400)
        self.assertIn("엑셀 처리 오류", r.json()["detail"])
        self.assertEqual(table(self.conn), before)   # 앞의 행들도 남지 않는다
        self.backup_mock.assert_not_called()

    def test_not_an_excel_file(self):
        r = self.client.post(f"/api/farms/{FARM_ID}/shipments/excel",
                             files={"file": ("x.xlsx", b"not excel", "application/octet-stream")})
        self.assertEqual(r.status_code, 400)
        self.assertIn("엑셀 읽기 오류", r.json()["detail"])

    def test_too_large(self):
        with mock.patch("api.routers.shipments.MAX_EXCEL_BYTES", 100):
            r = self.upload(excel_frame())
        self.assertEqual(r.status_code, 413)


if __name__ == "__main__":
    unittest.main()
