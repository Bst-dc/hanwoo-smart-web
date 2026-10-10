from fastapi import APIRouter, HTTPException, Request

from .. import auth, config
from ..models import AuthStatus, LoginRequest

router = APIRouter(prefix="/api/auth", tags=["로그인"])


@router.get("/status", response_model=AuthStatus)
def status(request: Request):
    return AuthStatus(password_required=config.app_password() is not None, authed=auth.is_authed(request))


@router.post("/login", response_model=AuthStatus)
def login(body: LoginRequest, request: Request):
    if not auth.check_password(body.password):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    request.session["authed"] = True
    return status(request)


@router.post("/logout", response_model=AuthStatus)
def logout(request: Request):
    request.session.clear()
    return status(request)
