"""접속 권한 — 기존 앱 require_password() 를 쿠키 세션으로 옮긴 것. 역할 구분 없이 비밀번호 하나(APP_PASSWORD).

APP_PASSWORD 가 없으면(로컬) 로그인 없이 들어간다. 같은 접속 주소에서 5번 틀리면 15분 동안 로그인을 받지 않는다.
"""
import hashlib
import hmac
import secrets
import threading
import time

from fastapi import HTTPException, Request

from . import config


def session_secret() -> str:
    """세션 쿠키 서명 키. SESSION_SECRET 이 없으면 비밀번호에서 만들어, 서버를 다시 켜도 로그인이 풀리지 않고
    비밀번호를 바꾸면 모든 로그인이 풀리게 한다."""
    explicit = config.secret("SESSION_SECRET")
    if explicit:
        return explicit
    pw = config.app_password()
    if pw:
        return hmac.new(b"hanwoo-consulting-session", pw.encode("utf-8"), hashlib.sha256).hexdigest()
    return secrets.token_hex(32)


def is_logged_in(request: Request) -> bool:
    if config.app_password() is None:
        return True
    return request.session.get("authed") is True


def require_login(request: Request) -> None:
    if not is_logged_in(request):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")


MAX_LOGIN_FAILS = 5
LOCK_SECONDS = 15 * 60
_fails: dict = {}                 # {주소: [실패 횟수, 잠금이 풀리는 시각(time.monotonic), 마지막 실패 시각]}
_fails_lock = threading.Lock()


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def login_locked_for(key: str) -> int:
    """잠겨 있으면 남은 초, 아니면 0."""
    with _fails_lock:
        rec = _fails.get(key)
        if not rec:
            return 0
        left = rec[1] - time.monotonic()
        if left > 0:
            return int(left) + 1
        if rec[1] and left <= 0:
            _fails.pop(key, None)
        return 0


def note_login_failure(key: str) -> int:
    """실패를 기록하고 남은 시도 횟수를 돌려준다 (0 이면 방금 잠겼다)."""
    now = time.monotonic()
    with _fails_lock:
        for k in [k for k, v in _fails.items() if v[1] == 0 and now - v[2] > LOCK_SECONDS]:
            _fails.pop(k, None)
        rec = _fails.setdefault(key, [0, 0.0, now])
        rec[0] += 1
        rec[2] = now
        if rec[0] >= MAX_LOGIN_FAILS:
            rec[1] = now + LOCK_SECONDS
        return max(0, MAX_LOGIN_FAILS - rec[0])


def note_login_success(key: str) -> None:
    with _fails_lock:
        _fails.pop(key, None)


def check_password(candidate: str) -> bool:
    """맞으면 True. 틀리면 대입 시도를 늦추고 False."""
    pw = config.app_password()
    if pw is None:
        return True
    if hmac.compare_digest(candidate.encode("utf-8"), pw.encode("utf-8")):
        return True
    time.sleep(0.7)
    return False
