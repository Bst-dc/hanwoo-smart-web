"""DB 까지 실제로 닿는지 보는 점검 — 외부 감시(UptimeRobot 등)용 `/api/health/deep`.

`/api/health` 는 Docker 생존 확인용이라 일부러 DB 에 붙지 않는다(DB 가 끊겼다고 컨테이너를 다시 띄우지 않으려는 뜻).
이 모듈은 반대로 DB 를 실제로 건드려 본다. db_adapter 의 연결 풀과 조회 캐시(600초)를 거치면
DB 가 죽어도 정상으로 보이므로, 일회용 연결로 `SELECT 1` 을 한다.
결과는 CACHE_SECONDS 동안 기억해, 인증 없이 열려 있는 이 주소가 DB 에 부하를 주지 못하게 한다.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from . import db

log = logging.getLogger("consulting.health")

TIMEOUT_SECONDS = 3     # 연결과 조회를 합쳐 이 시간 안에 못 끝내면 '내려감' 으로 본다
CACHE_SECONDS = 20      # 감시가 자주 불러도 이 시간 안에는 DB 에 다시 붙지 않는다

_lock = threading.Lock()
_expires = 0.0          # time.monotonic() 기준. 이 시각 전이면 _last 를 그대로 쓴다
_last = False
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="health")


def _select_one() -> bool:
    import psycopg2
    raw = psycopg2.connect(db.db_adapter.database_url(), connect_timeout=TIMEOUT_SECONDS,
                           application_name="hanwoo-consulting-health")
    try:
        raw.autocommit = True
        with raw.cursor() as c:
            c.execute("SELECT 1")
            return c.fetchone()[0] == 1
    finally:
        raw.close()


def _probe() -> bool:
    if not db.using_supabase():
        return True                       # 로컬 SQLite 개발 모드에는 점검할 원격 DB 가 없다
    try:
        return bool(_pool.submit(_select_one).result(timeout=TIMEOUT_SECONDS))
    except FutureTimeout:
        log.warning("DB 점검 시간 초과 (%ds)", TIMEOUT_SECONDS)
    except Exception as e:                # 오류 내용에 접속 정보가 섞일 수 있어 종류만 남긴다
        log.warning("DB 점검 실패: %s", type(e).__name__)
    return False


def is_up() -> bool:
    global _expires, _last
    with _lock:                           # 동시에 여러 요청이 와도 DB 에는 한 번만 붙는다
        now = time.monotonic()
        if now >= _expires:
            _last = _probe()
            _expires = time.monotonic() + CACHE_SECONDS
        return _last
