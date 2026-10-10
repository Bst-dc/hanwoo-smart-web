"""농가 신규 등록 API 와 GitHub 자동 백업(services/backup.py) 시험.

GitHub 는 실제로 부르지 않는다 — _github() 를 가짜로 바꿔 요청 내용과 응답을 확인한다.
실행: python -m unittest tests.test_api_farms_backup
"""
import base64
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from test_api_dashboard import ApiTestBase  # noqa: E402  (같은 시험 DB·클라이언트를 쓴다)

from api.services import backup  # noqa: E402

FAKE_DB = b"SQLite format 3\x00 fake snapshot"


def secrets(**values):
    return lambda name, default="": values.get(name, default)


def http_error(code):
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", {}, None)


class FakeGitHub:
    """GET 은 remote_sha 를 돌려주고(None 이면 404), PUT 은 기록해 두고 새 sha 를 돌려준다."""

    def __init__(self, remote_sha=None, put_error=None, get_error=None):
        self.remote_sha, self.put_error, self.get_error = remote_sha, put_error, get_error
        self.puts = []

    def __call__(self, url, token, body=None, method="GET", timeout=20):
        if method == "GET":
            if self.get_error:
                raise http_error(self.get_error)
            if self.remote_sha is None:
                raise http_error(404)
            return {"sha": self.remote_sha}
        if self.put_error:
            raise http_error(self.put_error)
        self.puts.append(body)
        return {"content": {"sha": "newsha"}}


class PersistDbTest(unittest.TestCase):
    def run_backup(self, gh, cloud=True, base_sha=None):
        with mock.patch.object(backup.config, "secret", secrets(GITHUB_TOKEN="tok")), \
             mock.patch.object(backup, "_github", gh), \
             mock.patch.object(backup, "db_file_bytes", return_value=(FAKE_DB, None)), \
             mock.patch.object(backup.db, "using_supabase", return_value=cloud), \
             mock.patch.object(backup, "_read_base_sha", return_value=base_sha), \
             mock.patch.object(backup, "_write_base_sha") as write_base:
            result = backup.persist_db("시험 저장")
        return result, write_base

    def test_no_token_means_not_configured(self):
        with mock.patch.object(backup.config, "secret", secrets()):
            r = backup.persist_db("x")
        self.assertIsNone(r.ok)

    def test_first_upload_without_sha(self):
        gh = FakeGitHub(remote_sha=None)
        r, _ = self.run_backup(gh)
        self.assertTrue(r.ok)
        self.assertEqual(len(gh.puts), 1)
        self.assertNotIn("sha", gh.puts[0])
        self.assertEqual(base64.b64decode(gh.puts[0]["content"]), FAKE_DB)
        self.assertIn("시험 저장", gh.puts[0]["message"])

    def test_update_sends_remote_sha(self):
        gh = FakeGitHub(remote_sha="abc")
        r, _ = self.run_backup(gh)
        self.assertTrue(r.ok)
        self.assertEqual(gh.puts[0]["sha"], "abc")

    def test_identical_content_is_not_uploaded(self):
        gh = FakeGitHub(remote_sha=backup.git_blob_sha(FAKE_DB))
        r, _ = self.run_backup(gh)
        self.assertTrue(r.ok)
        self.assertEqual(gh.puts, [])

    def test_cloud_mode_ignores_base_sha(self):
        # 앱이 둘 이상 같은 백업 파일에 올려도 서로를 막지 않는다 (클라우드 백업은 늘 DB 전체의 최신 사본)
        gh = FakeGitHub(remote_sha="other-app-sha")
        r, write_base = self.run_backup(gh, cloud=True, base_sha="my-last-sha")
        self.assertTrue(r.ok)
        self.assertEqual(len(gh.puts), 1)
        write_base.assert_not_called()

    def test_local_mode_keeps_overwrite_guard(self):
        gh = FakeGitHub(remote_sha="changed-elsewhere")
        r, _ = self.run_backup(gh, cloud=False, base_sha="my-base")
        self.assertFalse(r.ok)
        self.assertEqual(gh.puts, [])

    def test_local_mode_records_new_base(self):
        gh = FakeGitHub(remote_sha="my-base")
        r, write_base = self.run_backup(gh, cloud=False, base_sha="my-base")
        self.assertTrue(r.ok)
        write_base.assert_called_once_with("newsha")

    def test_conflict_and_server_errors_are_reported_not_raised(self):
        for gh in [FakeGitHub(remote_sha="a", put_error=409), FakeGitHub(remote_sha="a", put_error=500),
                   FakeGitHub(get_error=500)]:
            r, _ = self.run_backup(gh)
            self.assertFalse(r.ok)
            self.assertIn("저장", r.message)   # 데이터는 저장됐다는 안내가 들어 있어야 한다

    def test_snapshot_failure_is_reported(self):
        with mock.patch.object(backup.config, "secret", secrets(GITHUB_TOKEN="tok")), \
             mock.patch.object(backup, "_github", FakeGitHub()), \
             mock.patch.object(backup, "db_file_bytes", return_value=(None, "스냅샷 실패")):
            r = backup.persist_db("x")
        self.assertEqual((r.ok, r.message), (False, "스냅샷 실패"))

    def test_local_db_file_bytes_is_a_consistent_copy(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "consulting.db"
            c = sqlite3.connect(path)
            c.execute("CREATE TABLE t (x)")
            c.execute("INSERT INTO t VALUES (42)")
            c.commit()
            c.close()
            with mock.patch.object(backup.db, "using_supabase", return_value=False), \
                 mock.patch.object(backup.db, "LOCAL_DB", path):
                data, err = backup.db_file_bytes()
            self.assertIsNone(err)
            out = Path(d) / "copy.db"
            out.write_bytes(data)
            c = sqlite3.connect(out)
            self.assertEqual(c.execute("SELECT x FROM t").fetchone()[0], 42)
            c.close()


class CreateFarmTest(ApiTestBase):
    def setUp(self):
        super().setUp()
        self.patches = [
            mock.patch("api.config.app_password", return_value=None),
            mock.patch("api.routers.farms.persist_db",
                       return_value=backup.BackupResult(ok=True, message="GitHub 에 자동 백업되었습니다.")),
        ]
        self.backup_mock = self.patches[1].start()
        self.patches[0].start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def post(self, **body):
        return self.client.post("/api/farms", json={"farm_name": "신규농장", **body})

    def test_create(self):
        r = self.post(farm_code="N100", owner_name="홍길동", region="청도", breeding_type="번식우", total_heads=30)
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual(body["farm"]["label"], "신규농장 (홍길동, 청도)")
        self.assertEqual(body["backup"]["ok"], True)
        row = self.conn.execute("SELECT * FROM farms WHERE id=?", (body["farm"]["id"],)).fetchone()
        self.assertEqual((row["farm_code"], row["breeding_type"], row["total_heads"]), ("N100", "번식우", 30))
        self.backup_mock.assert_called_once_with("신규 농가 등록")

    def test_auto_code(self):
        r = self.post()
        code = self.conn.execute("SELECT farm_code FROM farms WHERE id=?", (r.json()["farm"]["id"],)).fetchone()[0]
        self.assertRegex(code, r"^F\d{1,4}$")

    def test_duplicate_name_needs_confirmation(self):
        r = self.client.post("/api/farms", json={"farm_name": " 나농장 "})      # 앞뒤 공백은 무시하고 비교
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["duplicate_id"], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM farms").fetchone()[0], 5)   # 저장 안 됨
        r = self.client.post("/api/farms", json={"farm_name": "나농장", "confirm_duplicate": True})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM farms").fetchone()[0], 6)

    def test_duplicate_code_cannot_be_forced(self):
        r = self.post(farm_code="T2", confirm_duplicate=True)   # farm_code 는 UNIQUE
        self.assertEqual(r.status_code, 409)
        self.assertIn("T2", r.json()["detail"])
        self.assertNotIn("duplicate_id", r.json())
        self.backup_mock.assert_not_called()

    def test_blank_name_rejected(self):
        self.assertEqual(self.client.post("/api/farms", json={"farm_name": "   "}).status_code, 422)
        self.assertEqual(self.client.post("/api/farms", json={"farm_name": ""}).status_code, 422)
        self.assertEqual(self.post(breeding_type="한우").status_code, 422)
        self.assertEqual(self.post(total_heads=-1).status_code, 422)

    def test_backup_failure_still_saves(self):
        self.backup_mock.return_value = backup.BackupResult(ok=False, message="GitHub 백업 실패. 데이터는 DB 에 저장되어 있습니다.")
        r = self.post()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["backup"]["ok"], False)

    def test_duplicate_lookup(self):
        self.assertEqual(self.client.get("/api/farms/duplicate", params={"code": "T3"}).json()["farm_name"], "다농장")
        self.assertIsNone(self.client.get("/api/farms/duplicate", params={"name": "없는농장"}).json())
        self.assertIsNone(self.client.get("/api/farms/duplicate").json())


if __name__ == "__main__":
    unittest.main()
