"""한우 스마트컨설팅 — FastAPI 백엔드.

API 는 /api/... 로, 화면(web/ 폴더의 HTML·JS)은 같은 서버의 / 로 내보낸다.
실행: uvicorn api.main:app --reload   (한우_스마트컨설팅_웹시스템 폴더에서)
"""
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, config, db
from .routers import auth as auth_router
from .routers import dashboard, farms

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hanwoo.api")

app = FastAPI(title="한우 스마트컨설팅 API", version="0.1.0")

# 미들웨어는 나중에 붙인 것이 바깥쪽이다: CORS → 세션 → 앱 순서로 지난다.
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.session_secret(),
    session_cookie="hanwoo_session",
    max_age=60 * 60 * 24 * 14,           # 2주
    same_site="lax",
    https_only=config.secret("COOKIE_SECURE", "0") == "1",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_credentials=True,               # 로그인 쿠키를 함께 보내야 한다
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        # 화면 파일(JS 모듈 포함)은 매번 바뀌었는지 확인하게 한다 — 배포 뒤 옛 화면이 남지 않도록.
        response.headers["Cache-Control"] = "no-cache"
    else:
        log.info("%s %s → %s (%.0f ms)", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - started) * 1000)
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # 예상 못 한 오류는 기록에 전체 내용을 남기고, 화면에는 짧은 안내만 보낸다.
    log.exception("처리 중 오류: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"서버 오류가 났습니다 ({type(exc).__name__})."})


@app.get("/api/health", tags=["상태"])
def health():
    """Docker 상태 확인용. DB 에는 붙지 않는다."""
    return {"ok": True, "db": "supabase" if db.using_supabase() else "sqlite"}


app.include_router(auth_router.router)
app.include_router(farms.router)
app.include_router(dashboard.router)

# 화면 파일. API 경로를 다 등록한 뒤 마지막에 붙여야 /api/... 를 가리지 않는다.
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
