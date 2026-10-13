"""한우 스마트 컨설팅 — FastAPI 백엔드 (모바일용 새 화면).

API 는 /api/... 로, 화면(web/ 폴더의 HTML·JS)은 같은 서버의 / 로 내보낸다.
실행: uvicorn api.main:app --reload   (저장소 맨 위 폴더에서)
기존 Streamlit 앱(streamlit_app.py)과 같은 저장소·같은 DB 를 쓰며 병행 운영한다.
"""
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, config, db
from .limits import BodyLimitMiddleware
from .routers import auth as auth_router
from .routers import farms

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("consulting.api")

# 운영에서는 /docs·/openapi.json 을 닫는다. 개발할 때만 ENABLE_API_DOCS=1.
_docs = config.secret("ENABLE_API_DOCS") == "1"
app = FastAPI(title="한우 스마트 컨설팅 API", version="0.1.0",
              docs_url="/docs" if _docs else None, redoc_url="/redoc" if _docs else None,
              openapi_url="/openapi.json" if _docs else None)

# 미들웨어는 나중에 붙인 것이 바깥쪽이다: CORS → 본문 제한 → 세션 → 앱 순서로 지난다.
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.session_secret(),
    session_cookie="consulting_session",
    max_age=60 * 60 * 24 * 14,           # 2주
    same_site="lax",
    https_only=config.secret("COOKIE_SECURE", "0") == "1",
)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"      # 배포 뒤 옛 화면이 남지 않게
    else:
        log.info("%s %s → %s (%.0f ms)", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - started) * 1000)
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("처리 중 오류: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"서버 오류가 났습니다 ({type(exc).__name__})."})


@app.get("/api/health", tags=["상태"])
def health():
    """Docker 상태 확인용. DB 에는 붙지 않는다."""
    return {"ok": True, "db": "supabase" if db.using_supabase() else "sqlite"}


app.include_router(auth_router.router)
app.include_router(farms.router)

# 화면 파일. API 경로를 다 등록한 뒤 마지막에 붙여야 /api/... 를 가리지 않는다.
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
