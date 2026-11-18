"""헬스 점검 시험 — /api/health(생존), /api/health/deep(DB 까지).

운영 DB 에는 붙지 않는다 (CONSULTING_LOCAL_ONLY=1, 실패·시간 초과는 가짜 함수로 흉내 낸다).
실행: python -m unittest tests.test_api_health
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
os.environ["CONSULTING_LOCAL_ONLY"] = "1"
os.environ["CONSULTING_DB_PATH"] = str(Path(_tmp.name) / "consulting.db")
os.environ["APP_PASSWORD"] = "test-pass"

from fastapi.testclient import TestClient  # noqa: E402

from api import health  # noqa: E402
from api.main import app  # noqa: E402


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        health._expires = 0.0            # 시험마다 캐시를 비운다
        health._last = False

    def test_liveness_accepts_head_and_get(self):
        for method in ("get", "head"):
            r = getattr(self.client, method)("/api/health")
            self.assertEqual(r.status_code, 200, method)
        self.assertEqual(self.client.get("/api/health").json(), {"ok": True, "db": "sqlite"})

    def test_deep_needs_no_login_and_is_ok_in_local_mode(self):
        r = self.client.get("/api/health/deep")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True, "db": "up"})
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_deep_reports_503_when_db_unreachable_without_leaking_details(self):
        secret = "postgresql://user:SECRET-PW@db.example:5432/x"
        with mock.patch.object(health.db, "using_supabase", return_value=True), \
                mock.patch.object(health, "_select_one", side_effect=RuntimeError(secret)):
            for method in ("get", "head"):
                health._expires = 0.0
                r = getattr(self.client, method)("/api/health/deep")
                self.assertEqual(r.status_code, 503, method)
            body = self.client.get("/api/health/deep").text
        self.assertEqual(body, '{"ok":false,"db":"down"}')
        self.assertNotIn("SECRET", body)

    def test_deep_gives_up_after_timeout(self):
        with mock.patch.object(health.db, "using_supabase", return_value=True), \
                mock.patch.object(health, "TIMEOUT_SECONDS", 0.2), \
                mock.patch.object(health, "_select_one", side_effect=lambda: time.sleep(3.0) or True):
            started = time.monotonic()
            r = self.client.get("/api/health/deep")
            elapsed = time.monotonic() - started
        self.assertEqual(r.status_code, 503)
        self.assertLess(elapsed, 2.0)    # 3초 걸리는 DB 를 끝까지 기다리지 않는다 (제한 0.2초)

    def test_deep_result_is_cached_so_public_url_cannot_hammer_db(self):
        with mock.patch.object(health.db, "using_supabase", return_value=True), \
                mock.patch.object(health, "_select_one", return_value=True) as probe:
            for _ in range(5):
                self.assertEqual(self.client.get("/api/health/deep").status_code, 200)
            self.assertEqual(probe.call_count, 1)
            health._expires = 0.0        # 캐시 기간이 지났다고 치면 다시 점검한다
            self.client.get("/api/health/deep")
            self.assertEqual(probe.call_count, 2)

    def test_deep_does_not_use_adapter_query_cache(self):
        # db_adapter 의 조회 캐시(600초)를 거치면 DB 가 죽어도 정상으로 보인다 — 점검은 일회용 연결을 직접 연다
        import inspect
        src = inspect.getsource(health._select_one)
        self.assertIn("psycopg2.connect", src)
        self.assertNotIn("db_adapter.connect", src)
        self.assertNotIn("db.connect", src)


if __name__ == "__main__":
    unittest.main()
