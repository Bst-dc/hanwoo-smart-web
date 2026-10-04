"""Tests for the dashboard changes in commit 63287a1:
- the "farms with shipments but no field survey" KPI query
- the owner_name fallback used in the AI report farm picker

streamlit_app.py is a top-level Streamlit script (it renders UI as soon as
it's imported), so it can't be imported directly in a test process. Instead,
the KPI query is extracted verbatim from the source file and executed
against a throwaway in-memory database that mirrors the real schema, so the
test exercises the actual SQL rather than a hand-copied duplicate that could
drift out of sync.
"""
import re
import sqlite3
import unittest
from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "streamlit_app.py"

SCHEMA = """
CREATE TABLE farms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_name TEXT,
    owner_name TEXT
);
CREATE TABLE visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL
);
CREATE TABLE field_surveys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id INTEGER UNIQUE NOT NULL,
    survey_data TEXT
);
CREATE TABLE shipment_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL,
    animal_no TEXT
);
"""


def _extract_missing_survey_query() -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    match = re.search(
        r'farms_missing_survey_list = conn\.execute\("""(.*?)"""\)\.fetchall\(\)',
        source,
        re.DOTALL,
    )
    if not match:
        raise AssertionError(
            "Could not find the farms_missing_survey query in streamlit_app.py "
            "(it may have been renamed or refactored) - update this test to match."
        )
    return match.group(1)


class FarmsMissingSurveyQueryTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(SCHEMA)
        self.query = _extract_missing_survey_query()

    def tearDown(self):
        self.conn.close()

    def _add_farm(self, name="farm"):
        cur = self.conn.execute("INSERT INTO farms (farm_name) VALUES (?)", (name,))
        return cur.lastrowid

    def _add_shipment(self, farm_id, animal_no="1"):
        self.conn.execute(
            "INSERT INTO shipment_records (farm_id, animal_no) VALUES (?, ?)",
            (farm_id, animal_no),
        )

    def _add_visit(self, farm_id):
        cur = self.conn.execute("INSERT INTO visits (farm_id) VALUES (?)", (farm_id,))
        return cur.lastrowid

    def _add_survey(self, visit_id, survey_data="{}"):
        self.conn.execute(
            "INSERT INTO field_surveys (visit_id, survey_data) VALUES (?, ?)",
            (visit_id, survey_data),
        )

    def _count(self):
        # 앱은 이 쿼리로 농가명 목록을 받아 len()으로 개수를 센다 (farms_missing_survey = len(...))
        return len(self.conn.execute(self.query).fetchall())

    def test_counts_farm_with_shipment_and_no_survey(self):
        farm_id = self._add_farm()
        self._add_shipment(farm_id)
        self.assertEqual(self._count(), 1)

    def test_excludes_farm_with_completed_survey(self):
        farm_id = self._add_farm()
        self._add_shipment(farm_id)
        visit_id = self._add_visit(farm_id)
        self._add_survey(visit_id, survey_data="{}")
        self.assertEqual(self._count(), 0)

    def test_excludes_farm_without_any_shipment(self):
        farm_id = self._add_farm()
        self._add_visit(farm_id)
        self.assertEqual(self._count(), 0)

    def test_still_counts_farm_whose_survey_row_has_null_survey_data(self):
        # A visit can get a field_surveys row before the survey is filled in
        # (survey_data left NULL) - that farm should still be flagged.
        farm_id = self._add_farm()
        self._add_shipment(farm_id)
        visit_id = self._add_visit(farm_id)
        self._add_survey(visit_id, survey_data=None)
        self.assertEqual(self._count(), 1)

    def test_counts_each_qualifying_farm_once_even_with_multiple_shipments(self):
        farm_id = self._add_farm()
        self._add_shipment(farm_id, animal_no="1")
        self._add_shipment(farm_id, animal_no="2")
        self.assertEqual(self._count(), 1)


class OwnerNameFallbackTest(unittest.TestCase):
    """Mirrors the AI report farm picker's fallback (streamlit_app.py ~line 1412):
    f"{row['farm_name']} ({row['owner_name'] or '대표자'})" - previously this
    showed a literal "(None)" for farms with no owner_name.
    """

    @staticmethod
    def _label(farm_name, owner_name):
        return f"{farm_name} ({owner_name or '대표자'})"

    def test_uses_placeholder_when_owner_name_is_none(self):
        self.assertEqual(self._label("행복목장", None), "행복목장 (대표자)")

    def test_uses_placeholder_when_owner_name_is_empty_string(self):
        self.assertEqual(self._label("행복목장", ""), "행복목장 (대표자)")

    def test_uses_actual_owner_name_when_present(self):
        self.assertEqual(self._label("행복목장", "홍길동"), "행복목장 (홍길동)")


if __name__ == "__main__":
    unittest.main()
