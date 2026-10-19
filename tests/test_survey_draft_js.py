"""현장조사 임시 저장 로직(web/survey_draft.js)의 Node 시험을 unittest 에서도 돌린다. node 가 없으면 건너뛴다."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node 가 없어 건너뜀")
class SurveyDraftJs(unittest.TestCase):
    def test_node_suite(self):
        r = subprocess.run(["node", "--test", "tests/js/survey_draft.test.mjs"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-1000:])


if __name__ == "__main__":
    unittest.main()
