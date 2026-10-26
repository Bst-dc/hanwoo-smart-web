"""한우노트(옵시디언 보관함)를 비공개 데이터 저장소의 한우노트/ 로 올린다. 서버의 AI 리포트가 이 폴더를 읽는다.

사용:
    python tools/sync_notes.py          # 무엇이 바뀌는지만 보여준다 (올리지 않음)
    python tools/sync_notes.py --run    # 실제로 커밋·푸시

- 올리는 곳은 `git remote` 의 `data`(비공개 저장소) 뿐이다. 공개 저장소(origin)에는 절대 올리지 않는다.
- 보관함 설정(.obsidian/)은 올리지 않는다. 폴더를 통째로 맞추므로 지운 노트는 서버에서도 사라진다.
- 서버는 노트를 10분마다 다시 읽는다 (api/services/ai_report.py KB_TTL).
"""
import logging
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "한우노트"
FOLDER = "한우노트"
log = logging.getLogger("sync_notes")


def git(*args, cwd, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)} 실패: {r.stderr.strip()}")
    return r.stdout


def _rmtree(path: Path):
    def force(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=force)


def main(run: bool) -> int:
    if not VAULT.is_dir():
        log.error("보관함이 없음: %s", VAULT)
        return 1
    url = git("remote", "get-url", "data", cwd=ROOT).strip()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "data"
        log.info("비공개 저장소 받는 중 (%s)", url)
        git("clone", "--depth", "1", url, str(work), cwd=tmp)
        target = work / FOLDER
        if target.exists():
            _rmtree(target)
        shutil.copytree(VAULT, target, ignore=shutil.ignore_patterns(".obsidian", ".trash"))
        git("add", "-A", FOLDER, cwd=work)
        changes = git("status", "--porcelain", FOLDER, cwd=work).strip().splitlines()
        total = sum(1 for _ in target.rglob("*.md"))
        log.info("노트 %d개 · 바뀐 파일 %d개", total, len(changes))
        for line in changes:
            print("  ", line)
        if not changes:
            log.info("이미 최신입니다")
            return 0
        if not run:
            log.info("여기까지는 확인만 했습니다. 올리려면 --run")
            return 0
        git("-c", "user.name=hanwoo-notes", "-c", "user.email=notes@localhost", "commit", "-m",
            f"notes: 한우노트 동기화 ({len(changes)}개 파일)\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>", cwd=work)
        branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=work).strip()
        r = subprocess.run(["git", "push", "origin", branch], cwd=work, capture_output=True, text=True, encoding="utf-8")
        if r.returncode:                      # 앱의 자동 백업이 먼저 푸시했을 수 있다 → 한 번만 다시 받아 얹는다
            log.warning("푸시 거절, 한 번 다시 시도: %s", r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
            git("pull", "--rebase", "origin", branch, cwd=work)
            git("push", "origin", branch, cwd=work)
        log.info("올렸습니다 — 서버는 10분 안에 새 노트를 읽습니다")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main("--run" in sys.argv))
