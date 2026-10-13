"""저장 뒤 GitHub 자동 백업 — 기존 앱 persist_db() 의 Supabase 경우를 옮겼다.

Supabase(hanwoo 스키마) 전체를 SQLite .db 파일로 떠서 비공개 데이터 저장소(GITHUB_REPO)의
data/consulting.db 로 올린다. 무료 요금제엔 내려받을 백업이 없어 이것이 복구 수단이다.
- 로컬 SQLite 모드에서는 하지 않는다 (시험용 DB 가 운영 백업을 덮어쓰지 않게).
- 백업 파일은 늘 DB 전체의 최신 사본이라, 기존 앱처럼 '다른 곳에서 바뀜' 검사는 하지 않는다.
- 저장은 이미 끝난 뒤라 여기서 실패해도 오류를 던지지 않고 안내 문구만 돌려준다.
"""
import base64
import hashlib
import json
import logging
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from . import config, db

log = logging.getLogger("consulting.backup")

GITHUB_DB_PATH = "data/consulting.db"


def _git_blob_sha(data: bytes) -> str:
    """git 이 파일을 식별하는 해시(blob SHA-1). GitHub API 가 돌려주는 sha 와 같은 값."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _snapshot() -> bytes:
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(tmp)                       # sqlite3 가 빈 자리에 새로 만들게 비운다
    try:
        db.db_adapter.export_to_sqlite(db.db_schema.SCHEMA, tmp, db.db_schema.SQLITE_DDL, db.db_schema.TABLES)
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def run(reason: str) -> dict:
    """반환: {"ok": True|False|None, "message": 안내}. None 은 '백업을 하지 않음'."""
    token = config.secret("GITHUB_TOKEN")
    if not token:
        return {"ok": None, "message": "GitHub 자동 백업이 설정되지 않았습니다. 데이터는 DB 에 저장되었습니다."}
    if not db.using_supabase():
        return {"ok": None, "message": "로컬 DB 모드라 GitHub 백업은 건너뜁니다."}
    repo = config.secret("GITHUB_REPO", "Bst-dc/hanwoo-smart-consulting")
    branch = config.secret("GITHUB_BRANCH", "main")
    api = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(GITHUB_DB_PATH)}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "hanwoo-consulting-app"}
    fail = "데이터는 DB 에 저장되어 있습니다."
    try:
        req = urllib.request.Request(f"{api}?ref={urllib.parse.quote(branch)}", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            remote_sha = json.loads(resp.read().decode("utf-8")).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            log.warning("백업: 원격 DB 조회 실패 %s", e.code)
            return {"ok": False, "message": f"GitHub 백업 실패 (DB 조회 {e.code}). {fail}"}
        remote_sha = None                  # 저장소에 아직 DB 가 없음 → 새로 만든다
    except Exception as e:
        log.warning("백업: 원격 DB 조회 실패 %s", e)
        return {"ok": False, "message": f"GitHub 백업 실패 ({type(e).__name__}). {fail}"}

    try:
        data = _snapshot()
    except Exception as e:
        log.exception("백업: DB 스냅샷 실패")
        return {"ok": False, "message": f"DB 스냅샷 실패 ({type(e).__name__}). {fail}"}
    local_sha = _git_blob_sha(data)
    if remote_sha == local_sha:
        return {"ok": True, "message": "GitHub 백업과 이미 같습니다."}

    body = {"message": f"data: {reason} (새 앱 자동 백업)", "content": base64.b64encode(data).decode("ascii"), "branch": branch}
    if remote_sha:
        body["sha"] = remote_sha
    try:
        req = urllib.request.Request(api, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=30):
            pass
    except urllib.error.HTTPError as e:
        log.warning("백업: 업로드 실패 %s", e.code)
        if e.code in (409, 422):
            return {"ok": False, "message": "GitHub 백업이 방금 다른 곳에서 바뀌어 이번 백업은 건너뛰었습니다. 다음 저장 때 다시 올립니다."}
        return {"ok": False, "message": f"GitHub 백업 실패 (업로드 {e.code}). {fail}"}
    except Exception as e:
        log.warning("백업: 업로드 실패 %s", e)
        return {"ok": False, "message": f"GitHub 백업 실패 ({type(e).__name__}). {fail}"}
    log.info("백업 완료: %s (%d bytes)", reason, len(data))
    return {"ok": True, "message": "GitHub 에 자동 백업되었습니다."}
