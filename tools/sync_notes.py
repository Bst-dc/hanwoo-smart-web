"""한우노트(옵시디언 보관함)를 비공개 데이터 저장소의 한우노트/ 로 올린다. 서버의 AI 리포트가 이 폴더를 읽는다.

사용:
    python tools/sync_notes.py                  # 무엇이 바뀌는지만 보여준다 (올리지 않음)
    python tools/sync_notes.py --run            # 실제로 커밋·푸시
    python tools/sync_notes.py --run --ignore-pii   # 개인정보 의심 경고를 확인했고 그래도 올릴 때

- 올리는 곳은 `git remote` 의 `data`(비공개 저장소) 뿐이다. 공개 저장소(origin)에는 절대 올리지 않는다.
  data 가 origin 과 같거나 로그인 없이 읽히는(=공개) 저장소면 멈춘다.
- 노트에서 전화번호·주민번호·12자리 이력번호·로컬 DB 의 농가/농장주 이름이 보이면 --run 을 막는다 (노트 전문이 외부 Claude API 로 나간다).
- 보관함 설정(.obsidian/)은 올리지 않는다. 폴더를 통째로 맞추므로 지운 노트는 서버에서도 사라진다 → 삭제될 노트를 따로 크게 보여준다.
- 서버는 노트를 10분마다 다시 읽는다 (api/services/ai_report.py KB_TTL).
"""
import logging
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "한우노트"
FOLDER = "한우노트"
LOCAL_DB = ROOT / "data" / "consulting.db"
log = logging.getLogger("sync_notes")

PII_PATTERNS = {
    "전화번호": re.compile(r"(?<!\d)01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)"),
    "주민등록번호": re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)"),
    "12자리 번호(이력번호?)": re.compile(r"(?<!\d)\d{12}(?!\d)"),
}


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


def _norm(url: str) -> str:
    return url.strip().lower().removesuffix("/").removesuffix(".git")


def is_public(url: str) -> bool:
    """로그인 정보 없이 읽히는 저장소인가 (= 공개). 확인 못 하면(네트워크 오류 등) False."""
    # 로그인 창이 뜨며 멈추지 않게 모든 로그인 수단을 끈다 (비공개면 인증 실패로 끝난다)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_ASKPASS": "echo"}
    try:
        r = subprocess.run(["git", "-c", "credential.helper=", "-c", "core.askPass=", "ls-remote", "--exit-code", url, "HEAD"],
                           capture_output=True, text=True, env=env, timeout=30)
    except subprocess.TimeoutExpired:
        log.warning("공개 여부를 확인하지 못했습니다(시간 초과): %s", url)
        return False
    return r.returncode == 0


def check_remote(data_url: str, origin_url: str) -> str | None:
    """올려도 되는 곳이면 None, 아니면 멈출 이유."""
    if _norm(data_url) == _norm(origin_url):
        return "data 원격이 공개 저장소(origin)와 같습니다"
    if is_public(data_url):
        return "data 원격이 로그인 없이 읽힙니다 (공개 저장소로 보입니다)"
    return None


def farm_names() -> set[str]:
    """로컬 DB 의 농가·농장주 이름 (3글자 이상만 — 짧은 이름은 일반 낱말과 겹쳐 오탐이 많다)."""
    if not LOCAL_DB.is_file():
        return set()
    try:
        con = sqlite3.connect(f"file:{LOCAL_DB.as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT farm_name, owner_name FROM farms").fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        log.warning("로컬 DB 에서 이름을 읽지 못해 이름 검사는 건너뜁니다: %s", e)
        return set()
    return {n.strip() for row in rows for n in row if n and len(n.strip()) >= 3}


def find_pii(notes: dict, names: set) -> list:
    """notes: {상대경로: 본문}. 의심 항목 [(상대경로, 종류, 일부 문구)]."""
    found = []
    for rel, text in sorted(notes.items()):
        for kind, pat in PII_PATTERNS.items():
            for m in pat.finditer(text):
                found.append((rel, kind, m.group(0)))
        for name in sorted(names):
            if name in text:
                found.append((rel, "농가·농장주 이름", name))
    return found


def main(run: bool, ignore_pii: bool = False) -> int:
    if not VAULT.is_dir():
        log.error("보관함이 없음: %s", VAULT)
        return 1
    url = git("remote", "get-url", "data", cwd=ROOT).strip()
    origin = git("remote", "get-url", "origin", cwd=ROOT, check=False).strip()
    reason = check_remote(url, origin)
    if reason:
        log.error("멈춤: %s (%s). 노트는 비공개 저장소에만 올립니다.", reason, url)
        return 2
    notes = {p.relative_to(VAULT).as_posix(): p.read_text(encoding="utf-8")
             for p in VAULT.rglob("*.md") if ".obsidian" not in p.parts and ".trash" not in p.parts}
    pii = find_pii(notes, farm_names())
    if pii:
        log.warning("개인정보로 보이는 내용 %d건 — 노트 전문이 외부 Claude API 로 나갑니다:", len(pii))
        for rel, kind, snippet in pii:
            print(f"   [{kind}] {rel}: {snippet}")
        if run and not ignore_pii:
            log.error("멈춤: 위 내용을 노트에서 지우거나 코드(농가-2026-001)로 바꾸세요. 확인했고 그래도 올리려면 --ignore-pii")
            return 3
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "data"
        log.info("비공개 저장소 받는 중 (%s)", url)
        git("clone", "--depth", "1", url, str(work), cwd=tmp)
        target = work / FOLDER
        if target.exists():
            _rmtree(target)
        shutil.copytree(VAULT, target, ignore=shutil.ignore_patterns(".obsidian", ".trash"))
        git("add", "-A", FOLDER, cwd=work)
        changes = git("-c", "core.quotepath=false", "status", "--porcelain", FOLDER, cwd=work).strip().splitlines()
        total = sum(1 for _ in target.rglob("*.md"))
        log.info("노트 %d개 · 바뀐 파일 %d개", total, len(changes))
        for line in changes:
            print("  ", line)
        removed = [l[3:].strip('"') for l in changes if l[:2].strip() == "D" or l.startswith("R")]
        if removed:
            log.warning("!! 서버에서 사라질 노트 %d개 (보관함에서 지워졌거나 이름이 바뀜) — 의도한 것인지 확인하세요:", len(removed))
            for r in removed:
                print("   -", r)
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
    sys.exit(main("--run" in sys.argv, "--ignore-pii" in sys.argv))
