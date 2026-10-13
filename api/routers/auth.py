from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import auth, config

router = APIRouter(prefix="/api/auth", tags=["로그인"])


class LoginRequest(BaseModel):
    password: str


def _status(request: Request) -> dict:
    return {"password_required": config.app_password() is not None, "logged_in": auth.is_logged_in(request)}


@router.get("/status")
def status(request: Request):
    return _status(request)


@router.post("/login")
def login(body: LoginRequest, request: Request):
    key = auth.client_key(request)
    left = auth.login_locked_for(key)
    if left:
        raise HTTPException(status_code=429, detail=f"로그인을 {auth.MAX_LOGIN_FAILS}번 틀려 잠겼습니다. {(left + 59) // 60}분 뒤에 다시 시도하세요.")
    if not auth.check_password(body.password):
        remain = auth.note_login_failure(key)
        if remain == 0:
            raise HTTPException(status_code=429, detail=f"로그인을 {auth.MAX_LOGIN_FAILS}번 틀려 {auth.LOCK_SECONDS // 60}분 동안 잠겼습니다.")
        raise HTTPException(status_code=401, detail=f"비밀번호가 올바르지 않습니다. (남은 시도 {remain}번)")
    auth.note_login_success(key)
    request.session["authed"] = True
    return _status(request)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return _status(request)
