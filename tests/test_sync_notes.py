"""tools/sync_notes.py 의 올리기 전 가드 검사 — 네트워크·실제 보관함 없이 순수 함수만."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import sync_notes  # noqa: E402


class FindPiiTest(unittest.TestCase):
    def kinds(self, text, names=()):
        return [(kind, hit) for _, kind, hit in sync_notes.find_pii({"a.md": text}, set(names))]

    def test_clean_note_has_no_findings(self):
        self.assertEqual(self.kinds("BMS 하락 원인은 비타민A, 출하월령 30개월, 2026-10, 농가-2026-001 사례"), [])

    def test_phone_numbers_in_common_formats(self):
        for t in ("010-1234-5678", "연락처 01012345678", "010 123 4567", "011.123.4567"):
            self.assertEqual([k for k, _ in self.kinds(t)], ["전화번호"], t)

    def test_resident_number_and_twelve_digit_id(self):
        self.assertEqual([k for k, _ in self.kinds("900101-1234567")], ["주민등록번호"])
        self.assertEqual([k for k, _ in self.kinds("이력번호 002123456789")], ["12자리 번호(이력번호?)"])

    def test_numbers_inside_longer_digit_runs_are_not_flagged(self):
        self.assertEqual(self.kinds("코드 1234567890123456"), [])      # 16자리: 12자리 번호가 아님

    def test_farm_and_owner_names_from_the_db(self):
        got = self.kinds("김철수 농가는 BMS가 낮다", {"김철수", "박영희"})
        self.assertEqual(got, [("농가·농장주 이름", "김철수")])


class FarmNamesTest(unittest.TestCase):
    def test_reads_names_of_three_or_more_chars_and_survives_missing_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "c.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE farms (farm_name TEXT, owner_name TEXT)")
            con.execute("INSERT INTO farms VALUES ('가나다농장', '김철'), ('라마바', NULL)")
            con.commit()
            con.close()
            with mock.patch.object(sync_notes, "LOCAL_DB", db):
                self.assertEqual(sync_notes.farm_names(), {"가나다농장", "라마바"})   # '김철' 은 2글자라 제외
            with mock.patch.object(sync_notes, "LOCAL_DB", Path(tmp) / "없음.db"):
                self.assertEqual(sync_notes.farm_names(), set())


class CheckRemoteTest(unittest.TestCase):
    def test_same_url_as_origin_is_refused_even_with_dot_git_or_case_differences(self):
        with mock.patch.object(sync_notes, "is_public", lambda u: False):
            self.assertIn("origin", sync_notes.check_remote("https://github.com/A/Repo.git", "https://github.com/a/repo/"))

    def test_publicly_readable_remote_is_refused(self):
        with mock.patch.object(sync_notes, "is_public", lambda u: True):
            self.assertIn("공개", sync_notes.check_remote("https://github.com/A/private", "https://github.com/A/web"))

    def test_private_separate_remote_is_allowed(self):
        with mock.patch.object(sync_notes, "is_public", lambda u: False):
            self.assertIsNone(sync_notes.check_remote("https://github.com/A/private", "https://github.com/A/web"))


if __name__ == "__main__":
    unittest.main()
