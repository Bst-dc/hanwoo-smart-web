"""DB 자동 백업 — streamlit_app.py 섹션 2-1 (persist_db) 을 옮긴 것.

저장할 때마다 DB 전체를 SQLite .db 파일로 떠서 비공개 데이터 저장소(GITHUB_REPO)의 data/consulting.db 로 커밋한다.
Supabase 무료 요금제엔 내려받을 수 있는 백업이 없어서 이것이 유일한 복구 수단이다.
GITHUB_TOKEN 이 없으면 아무것도 하지 않는다(ok=None).

기존 앱과 다른 점 하나: 클라우드 DB 를 쓸 때는 '시작 이후 GitHub 쪽이 바뀌었으면 덮어쓰지 않는다' 검사를 하지 않는다.
그 검사는 로컬 파일 DB 시절, 다른 PC 에서 올린 DB 를 덮어쓰지 않으려던 장치다. 클라우드 모드의 백업 파일은 늘
DB 전체의 최신 사본이라 덮어써도 잃는 것이 없고, 오히려 앱이 둘(Streamlit·AWS) 이상 같은 파일에 올리면
서로를 '다른 곳에서 변경됨' 으로 보고 백업을 멈추게 된다.
"""
import base64
import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

from pydantic import BaseModel

from .. import config, db

log = logging.getLogger(__name__)

GITHUB_DB_PATH = "data/consulting.db"
BASE_SHA_PATH = config.BASE_DIR / "data" / ".db_base_sha"   # 로컬 파일 DB 가 어느 GitHub 버전에서 출발했는지
_backup_lock = threading.Lock()   # 동시에 두 요청이 저장해도 백업은 하나씩 (GitHub 409 충돌 방지)


class BackupResult(BaseModel):
    ok: bool | None   # True 성공, False 실패(데이터는 DB 에 저장됨), None 백업 미설정
    message: str


def git_blob_sha(data: bytes) -> str:
    """git 이 파일을 식별하는 해시(blob SHA-1). GitHub API 가 돌려주는 sha 와 같은 값."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _read_base_sha():
    try:
        return BASE_SHA_PATH.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _write_base_sha(sha):
    try:
        BASE_SHA_PATH.parent.mkdir(exist_ok=True)
        BASE_SHA_PATH.write_text(sha, encoding="utf-8")
    except OSError:
        log.warning("백업 기준 해시를 기록하지 못함: %s", BASE_SHA_PATH)


def db_file_bytes():
    """현재 DB 전체를 SQLite .db 파일 바이트로. 반환: (bytes, None) 또는 (None, 오류문구).
    GitHub 백업과 'DB 파일 내려받기' 가 같이 쓴다."""
    if db.using_supabase():
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(tmp)   # sqlite3 가 빈 자리에 새로 만들도록
        try:
            db.db_adapter.export_to_sqlite(db.db_schema.SCHEMA, tmp, db.db_schema.SQLITE_DDL, db.db_schema.TABLES)
            with open(tmp, "rb") as f:
                return f.read(), None
        except Exception as e:
            log.exception("클라우드 DB 스냅샷 실패")
            return None, f"클라우드 DB 스냅샷 실패 ({type(e).__name__}). 저장된 데이터는 클라우드에 그대로 있습니다."
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    try:
        # 쓰는 중인 파일을 그대로 읽지 않고 sqlite 백업 API 로 일관된 사본을 뜬다.
        src = sqlite3.connect(db.LOCAL_DB)
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            dst = sqlite3.connect(tmp)
            src.backup(dst)
            dst.close()
            with open(tmp, "rb") as f:
                return f.read(), None
        finally:
            src.close()
            os.remove(tmp)
    except (OSError, sqlite3.Error) as e:
        return None, f"로컬 DB 파일을 읽지 못했습니다 ({e}). 저장된 데이터는 그대로입니다."


def _github(url, token, body=None, method="GET", timeout=20):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hanwoo-consulting-api",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def persist_db(reason: str) -> BackupResult:
    """DB 를 GitHub 에 커밋한다. 저장 자체는 이미 끝난 뒤라 여기서 실패해도 오류를 올리지 않고 결과만 돌려준다."""
    token = config.secret("GITHUB_TOKEN")
    if not token:
        return BackupResult(ok=None, message="GitHub 자동 백업이 설정되지 않아 DB 에만 저장되었습니다.")
    repo = config.secret("GITHUB_REPO", "Bst-dc/hanwoo-smart-consulting")
    branch = config.secret("GITHUB_BRANCH", "main")
    # 경로에 한글이 들어가도 urllib 이 터지지 않게 quote ("/" 는 남는다)
    api = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(GITHUB_DB_PATH)}"
    cloud = db.using_supabase()

    with _backup_lock:
        try:
            remote_sha = _github(f"{api}?ref={urllib.parse.quote(branch)}", token).get("sha")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                log.warning("GitHub 백업: DB 조회 실패 %s", e.code)
                return BackupResult(ok=False, message=f"GitHub 백업 실패 (DB 조회 {e.code}). 데이터는 DB 에 저장되어 있습니다.")
            remote_sha = None   # 저장소에 아직 DB 가 없음 → 새로 만든다
        except Exception as e:
            log.warning("GitHub 백업: DB 조회 실패 %s", type(e).__name__)
            return BackupResult(ok=False, message=f"GitHub 백업 실패 ({type(e).__name__}). 데이터는 DB 에 저장되어 있습니다.")

        base_sha = None if cloud else _read_base_sha()
        if remote_sha and base_sha and remote_sha != base_sha:
            return BackupResult(ok=False, message=(
                "GitHub 의 DB 가 이 앱이 시작된 뒤 다른 곳에서 변경되어 자동 백업을 멈췄습니다 (덮어쓰면 그쪽 데이터가 사라짐). "
                "'데이터 관리 · 백업' 메뉴에서 DB 파일을 내려받아 보관한 뒤 관리자에게 병합을 요청하세요."))

        data, err = db_file_bytes()
        if err:
            return BackupResult(ok=False, message=err)
        local_sha = git_blob_sha(data)
        if remote_sha == local_sha:
            if not cloud:
                _write_base_sha(local_sha)
            return BackupResult(ok=True, message="GitHub DB 와 이미 같습니다.")

        body = {"message": f"data: {reason} (앱 자동 백업)", "content": base64.b64encode(data).decode("ascii"), "branch": branch}
        if remote_sha:
            body["sha"] = remote_sha
        try:
            new_sha = (_github(api, token, body, method="PUT", timeout=30).get("content") or {}).get("sha") or local_sha
        except urllib.error.HTTPError as e:
            log.warning("GitHub 백업: 업로드 실패 %s", e.code)
            if e.code in (409, 422):
                return BackupResult(ok=False, message="GitHub 의 DB 가 방금 다른 곳에서 변경되어 백업하지 못했습니다 (데이터는 DB 에 저장되어 있습니다). 잠시 후 '데이터 관리 · 백업'에서 다시 시도해주세요.")
            return BackupResult(ok=False, message=f"GitHub 백업 실패 (업로드 {e.code}). 데이터는 DB 에 저장되어 있습니다.")
        except Exception as e:
            log.warning("GitHub 백업: 업로드 실패 %s", type(e).__name__)
            return BackupResult(ok=False, message=f"GitHub 백업 실패 ({type(e).__name__}). 데이터는 DB 에 저장되어 있습니다.")
        if not cloud:
            _write_base_sha(new_sha)
        log.info("GitHub 백업 완료: %s (%d bytes)", reason, len(data))
        return BackupResult(ok=True, message="GitHub 에 자동 백업되었습니다.")
