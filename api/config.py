"""설정값 읽기 — 기존 Streamlit 앱과 같은 `.streamlit/secrets.toml` 을 그대로 쓴다.

순서: secrets.toml → 환경변수. 서버(Docker)에서는 secrets.toml 이 /app/.streamlit/secrets.toml 로 끼워진다.
"""
import os
import tomllib
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent      # 한우_스마트컨설팅_웹시스템/
WEB_DIR = BASE_DIR / "web"
SECRETS_PATH = BASE_DIR / ".streamlit" / "secrets.toml"


@lru_cache(maxsize=1)
def _secrets() -> dict:
    try:
        with open(SECRETS_PATH, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def secret(name: str, default: str = "") -> str:
    value = _secrets().get(name)
    if value not in (None, ""):
        return str(value)
    return os.environ.get(name, default)


def app_password() -> str | None:
    """APP_PASSWORD 가 있으면 로그인을 요구한다. 없으면(로컬 PC) 묻지 않는다 — 기존 앱과 같은 규칙."""
    return secret("APP_PASSWORD") or None


def cors_origins() -> list[str]:
    """화면을 API 와 다른 주소(예: VS Code Live Server)에서 열 때 허용할 주소. 쉼표로 여러 개."""
    raw = secret("CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
    return [o.strip() for o in raw.split(",") if o.strip()]


# 시험용: 이 환경변수에 SQLite 파일 경로를 주면 Supabase 설정이 있어도 그 파일만 쓴다 (운영 DB 에 시험 데이터가 들어가지 않게).
LOCAL_DB_OVERRIDE = os.environ.get("HANWOO_LOCAL_DB") or None

# db_adapter 는 환경변수 DATABASE_URL 을 먼저 본다. secrets.toml 에만 있으면 여기서 넘겨준다.
if not LOCAL_DB_OVERRIDE and secret("DATABASE_URL") and not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = secret("DATABASE_URL")
