"""접속 비밀번호 — 기존 앱 require_password() 를 쿠키 세션으로 옮긴 것.

APP_PASSWORD 가 없으면 로그인 없이 열린다. 있으면 /api/auth/login 으로 맞힌 뒤에만 다른 API 가 열린다.
"""
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request

from . import config


def session_secret() -> str:
    """세션 쿠키 서명 키. SESSION_SECRET 이 없으면 APP_PASSWORD 에서 만들어,
    서버를 다시 켜도 로그인이 풀리지 않고 비밀번호를 바꾸면 모든 로그인이 풀리게 한다."""
    explicit = config.secret("SESSION_SECRET")
    if explicit:
        return explicit
    pw = config.app_password()
    if pw:
        return hmac.new(b"hanwoo-consulting-session", pw.encode("utf-8"), hashlib.sha256).hexdigest()
    return secrets.token_hex(32)


def is_authed(request: Request) -> bool:
    return config.app_password() is None or bool(request.session.get("authed"))


def require_auth(request: Request) -> None:
    """로그인이 필요한 API 에 붙이는 의존성."""
    if not is_authed(request):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")


def check_password(candidate: str) -> bool:
    pw = config.app_password()
    if pw is None:
        return True
    ok = hmac.compare_digest(candidate.encode("utf-8"), pw.encode("utf-8"))
    if not ok:
        time.sleep(0.7)  # 비밀번호를 빠르게 대입해 보는 것을 늦춘다
    return ok
