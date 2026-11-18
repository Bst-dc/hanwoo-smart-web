"""매일 정기 백업 — 서버 cron 이 `python -m api.backup_job` 으로 부른다.

저장할 때만 도는 `backup.run` 을 하루 한 번 더 돌려, 저장이 뜸한 날에도 최신 사본이 비공개 데이터 저장소에 있게 한다.
DB 가 그대로면 GitHub 사본과 같아서 새 커밋이 생기지 않는다. 실패하면 종료 코드 1 이라 cron 기록으로 알 수 있다.
"""
import logging
import sys

from . import backup

log = logging.getLogger("consulting.backup_job")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = backup.run("매일 정기 백업")
    print(f"백업 결과: ok={result['ok']} · {result['message']}")
    # ok None = 설정 없음/로컬 모드. 서버에서 이러면 백업이 안 되는 상태이므로 실패로 본다.
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
