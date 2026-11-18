"""매일 정기 백업 작업 — 종료 코드가 결과를 그대로 알리는지."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# api 를 불러오기 전에 로컬 모드로 고정한다(운영 DB 에 붙지 않게, 다른 시험의 불러오기 순서에 영향을 주지 않게).
_tmp = tempfile.TemporaryDirectory()
os.environ.setdefault("CONSULTING_LOCAL_ONLY", "1")
os.environ.setdefault("CONSULTING_DB_PATH", str(Path(_tmp.name) / "consulting.db"))
os.environ.setdefault("APP_PASSWORD", "test-pass")

from api import backup_job  # noqa: E402


class BackupJobTest(unittest.TestCase):
    def _code(self, result):
        with mock.patch.object(backup_job.backup, "run", return_value=result) as run:
            code = backup_job.main()
        run.assert_called_once_with("매일 정기 백업")
        return code

    def test_ok(self):
        self.assertEqual(self._code({"ok": True, "message": "x"}), 0)

    def test_failure_is_nonzero(self):
        self.assertEqual(self._code({"ok": False, "message": "x"}), 1)

    def test_not_configured_is_nonzero(self):
        self.assertEqual(self._code({"ok": None, "message": "x"}), 1)


if __name__ == "__main__":
    unittest.main()
