"""대구축협 고급육생산프로그램(엑셀)을 AI 리포트용 JSON 으로 바꾸고, 비공개 데이터 저장소의 knowledge/ 에 올린다.

사용:
    python tools/build_feed_program.py <엑셀 경로>          # 읽어서 knowledge/feed_program.json 을 만들고 표만 보여 준다 (올리지 않음)
    python tools/build_feed_program.py <엑셀 경로> --run    # 비공개 저장소(git remote 'data')의 knowledge/feed_program.json 으로 올림
    python tools/build_feed_program.py <엑셀 경로> --check  # 로컬 DB 조사표 전체에 돌려 단계별 품목 판정 집계 (점검용)

- 엑셀 원본은 reference/사료프로그램/ 에 둔다 (공개 저장소에 올라가지 않음). 프로그램 내용도 공개 저장소에는 넣지 않는다.
- 엑셀 모양(2026-11-04 판): 시트 1개, 머리글 '개월령·목표체중·품목·사료량(kg)·단백질 높은사료(kg)·조사료(kg)',
  1~29개월 한 줄씩. 품목·단백질 높은사료 칸은 단계마다 병합되어 있어 위 값을 아래로 채운다. 사료량은 '9-9.5' 같은 범위 글자일 수 있다.
- 서버는 10분마다 다시 읽는다 (api/services/feed_program.py).
"""
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_notes  # noqa: E402  (git·공개 저장소 검사 함수를 같이 쓴다)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "knowledge" / "feed_program.json"
REMOTE_PATH = "knowledge/feed_program.json"
HEADER = ["개월령", "목표체중", "품목", "사료량(kg)", "단백질 높은사료(kg)", "조사료(kg)"]
log = logging.getLogger("build_feed_program")


def _clean(v) -> str:
    return " ".join(str(v).split()).replace(" (", "(") if v is not None else ""     # 줄바꿈 든 '팔공1 (후레이크)' → '팔공1(후레이크)'


def _kg(v, where) -> list[float]:
    """0.5 → [0.5, 0.5], '4.5-5' → [4.5, 5.0]"""
    parts = [p for p in str(v).replace("~", "-").split("-") if p.strip()]
    if not 1 <= len(parts) <= 2:
        raise ValueError(f"{where}: 급여량을 읽을 수 없음 ({v!r})")
    lo, hi = float(parts[0]), float(parts[-1])
    if lo > hi or lo < 0:
        raise ValueError(f"{where}: 급여량 범위가 이상함 ({v!r})")
    return [lo, hi]


def parse(xlsx: Path) -> dict:
    wb = openpyxl.load_workbook(xlsx)
    if len(wb.worksheets) != 1:
        raise ValueError(f"시트가 {len(wb.worksheets)}개 — 1개라고 보고 만든 읽기 방식입니다")
    ws = wb.worksheets[0]
    head = [_clean(c.value) for c in ws[1]][:len(HEADER)]
    if head != HEADER:
        raise ValueError(f"머리글이 다름: {head}")
    merged = {}                                  # 병합 칸 → 맨 위 값
    for rng in ws.merged_cells.ranges:
        top = ws.cell(rng.min_row, rng.min_col).value
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                merged[(r, c)] = top
    val = lambda r, c: merged.get((r, c), ws.cell(r, c).value)
    months = []
    for r in range(2, ws.max_row + 1):
        if val(r, 1) is None:
            continue
        where = f"{r}행"
        m = {"month": int(val(r, 1)), "target_weight": float(val(r, 2)), "feed": _clean(val(r, 3)),
             "feed_kg": _kg(val(r, 4), where), "high_protein_feed": _clean(val(r, 5)), "roughage_kg": _kg(val(r, 6), where)}
        if not m["feed"] or not m["high_protein_feed"]:
            raise ValueError(f"{where}: 품목 칸이 비어 있음")
        months.append(m)
    nums = [m["month"] for m in months]
    if nums != list(range(1, len(nums) + 1)):
        raise ValueError(f"개월령이 1부터 이어지지 않음: {nums}")
    weights = [m["target_weight"] for m in months]
    if any(b <= a for a, b in zip(weights, weights[1:])):
        raise ValueError("목표체중이 개월령마다 늘지 않는 곳이 있음")
    return {
        "name": "대구축협 고급육생산프로그램",
        "applies_to": "거세우 비육 (암소 비육 프로그램은 없음)",
        "notes": ["단백질 높은 사료는 같은 개월령에 일반 사료 대신 농가가 고를 수 있는 선택 사항이다 (급여량은 같은 줄 기준).",
                  "29개월 이후 출하까지는 29개월 급여(마지막 줄)를 그대로 이어 간다.",
                  "조사료는 종류와 관계없이 kg 기준이다."],
        "source_file": xlsx.name,
        "source_modified": datetime.fromtimestamp(xlsx.stat().st_mtime).strftime("%Y-%m-%d"),
        "months": months,
    }


def show(prog: dict):
    print(f"{prog['name']} ({prog['applies_to']}) — 원본 {prog['source_file']} {prog['source_modified']}, {len(prog['months'])}개월")
    print(" 개월 | 목표체중 | 사료 | 사료량 | 단백질 높은 사료 | 조사료")
    for m in prog["months"]:
        kg = lambda v: f"{v[0]:g}" if v[0] == v[1] else f"{v[0]:g}~{v[1]:g}"
        print(f" {m['month']:>4} | {m['target_weight']:>6g} | {m['feed']} | {kg(m['feed_kg'])} | {m['high_protein_feed']} | {kg(m['roughage_kg'])}")


def check(prog: dict, db_path: Path = ROOT / "data" / "consulting.db"):
    """로컬 DB 의 조사표 사료 칸 전체를 프로그램과 대조해, 단계별 판정 수와 프로그램에서 못 찾은 품목 이름을 보여 준다 (농가 이름은 찍지 않음)."""
    import collections
    import sqlite3
    sys.path.insert(0, str(ROOT))
    from api.services import feed_program as fp
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT survey_data FROM field_surveys WHERE survey_data IS NOT NULL").fetchall()
    finally:
        con.close()
    counts, unknown, n = collections.Counter(), collections.Counter(), 0
    for (raw,) in rows:
        try:
            fm = json.loads(raw).get("feed_matrix")
        except (ValueError, AttributeError):
            continue
        if not isinstance(fm, dict):
            continue
        n += 1
        for st in fp.compare(prog, fm)["단계별_비교"]:
            verdicts = st["배합사료_품목_판정"]
            if isinstance(verdicts, str):
                counts[(st["단계"], verdicts)] += 1
                continue
            for v in verdicts:
                counts[(st["단계"], v["판정"].split(" (")[0])] += 1
                if v["판정"] == "프로그램에 없는 사료":
                    unknown[v["품목"]] += 1
    print()
    print(f"조사표 {n}건 (사료 칸 있는 것) — 단계별 배합사료 품목 판정")
    for stage in fp.STAGES:
        print(f"  [{stage}] " + ", ".join(f"{k[1]} {c}" for k, c in sorted(counts.items(), key=lambda x: -x[1]) if k[0] == stage))
    print("  프로그램에 없는 품목: " + (", ".join(f"{k} {c}" for k, c in unknown.most_common()) or "없음"))


def upload(text: str) -> int:
    url = sync_notes.git("remote", "get-url", "data", cwd=ROOT).strip()
    origin = sync_notes.git("remote", "get-url", "origin", cwd=ROOT, check=False).strip()
    reason = sync_notes.check_remote(url, origin)
    if reason:
        log.error("멈춤: %s (%s). 사료 프로그램은 비공개 저장소에만 올립니다.", reason, url)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "data"
        log.info("비공개 저장소 받는 중 (%s)", url)
        sync_notes.git("clone", "--depth", "1", url, str(work), cwd=tmp)
        target = work / REMOTE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        sync_notes.git("add", "-f", REMOTE_PATH, cwd=work)      # 비공개 저장소의 .gitignore 가 knowledge/ 를 막고 있어 -f (기존 전문자료도 같은 방식)
        if not sync_notes.git("status", "--porcelain", REMOTE_PATH, cwd=work).strip():
            log.info("이미 최신입니다")
            return 0
        sync_notes.git("-c", "user.name=hanwoo-feed", "-c", "user.email=feed@localhost", "commit", "-m",
                       "knowledge: 대구축협 고급육생산프로그램 갱신\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>", cwd=work)
        branch = sync_notes.git("rev-parse", "--abbrev-ref", "HEAD", cwd=work).strip()
        r = subprocess.run(["git", "push", "origin", branch], cwd=work, capture_output=True, text=True, encoding="utf-8")
        if r.returncode:                      # 앱의 자동 백업이 먼저 푸시했을 수 있다 → 한 번만 다시 받아 얹는다
            log.warning("푸시 거절, 한 번 다시 시도")
            sync_notes.git("pull", "--rebase", "origin", branch, cwd=work)
            sync_notes.git("push", "origin", branch, cwd=work)
    log.info("올렸습니다 — 서버는 10분 안에 새 프로그램을 읽습니다")
    return 0


def main(argv) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 1
    try:
        prog = parse(Path(args[0]))
    except Exception as e:
        log.error("엑셀을 읽지 못함: %s", e)
        return 1
    show(prog)
    text = json.dumps(prog, ensure_ascii=False, indent=1)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    log.info("만듦: %s", OUT.relative_to(ROOT))
    if "--check" in argv:
        check(prog)
    if "--run" not in argv:
        log.info("여기까지는 확인만 했습니다. 서버에 올리려면 --run")
        return 0
    return upload(text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main(sys.argv[1:]))
