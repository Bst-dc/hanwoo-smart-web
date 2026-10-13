"""설정값 읽기 — 기존 Streamlit 앱과 같은 `.streamlit/secrets.toml` 과 환경변수를 그대로 쓴다.

순서: 환경변수 → secrets.toml. 서버(Docker)에서는 secrets.toml 이 /app/.streamlit/secrets.toml 로 끼워진다.
"""
import os
import tomllib
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
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
    value = os.environ.get(name)
    if value:
        return value
    value = _secrets().get(name)
    return str(value) if value not in (None, "") else default


def app_password() -> str | None:
    """APP_PASSWORD(접속 비밀번호). 없으면(로컬 PC) 묻지 않는다 — 기존 앱과 같은 규칙."""
    return secret("APP_PASSWORD") or None


def cors_origins() -> list[str]:
    raw = secret("CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
    return [o.strip() for o in raw.split(",") if o.strip()]


# 시험용: 1 이면 DATABASE_URL 이 있어도 쓰지 않고 로컬 SQLite 만 쓴다 (운영 Supabase 에 시험 데이터가 들어가지 않게).
LOCAL_ONLY = os.environ.get("CONSULTING_LOCAL_ONLY") == "1"

# 로컬 SQLite 파일. 기존 앱과 같은 data/consulting.db (gitignore 됨).
DB_PATH = Path(os.environ.get("CONSULTING_DB_PATH") or BASE_DIR / "data" / "consulting.db")

# db_adapter 는 환경변수 DATABASE_URL 을 먼저 본다. secrets.toml 에만 있으면 여기서 넘겨준다.
if LOCAL_ONLY:
    os.environ.pop("DATABASE_URL", None)
elif secret("DATABASE_URL") and not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = secret("DATABASE_URL")
