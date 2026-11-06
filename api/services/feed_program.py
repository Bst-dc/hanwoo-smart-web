"""대구축협 고급육생산프로그램 — AI 리포트가 사료 급여를 이 프로그램 기준으로 설명하게 하는 자료와 비교 계산.

- 프로그램 표(1~29개월 사료·급여량·조사료·목표체중)는 대구축협 내부 자료라 공개 저장소에 두지 않는다.
  tools/build_feed_program.py 가 엑셀을 JSON 으로 바꿔 비공개 데이터 저장소의 knowledge/feed_program.json 에 올리고,
  서버는 그것을 10분마다 다시 읽는다. 로컬에 knowledge/ 폴더가 있으면 거기서 읽는다 (전문자료와 같은 규칙).
- 거세우 비육 기준이다. 암소 비육 프로그램은 없고, 번식우는 대상이 아니다 (2026-11-06 사용자 확인).
- 현장조사 사료 칸(송아지·육성우·비육전기·비육후기)과 개월령 대응도 사용자 확인값이다 (STAGES).
- 급여량을 AI 가 개월령에서 거꾸로 맞추다 틀리지 않게, 단계별 기준과 품목 판정은 여기서 계산해 넘긴다.
  조사표의 급여수준은 낮음·적정·높음 평가라 kg 비교는 하지 않는다.
"""
import json
import logging
import re
import threading
import time

from .. import config

log = logging.getLogger("consulting.feed_program")

LOCAL_DIR = config.BASE_DIR / "knowledge"
FILE_NAME = "feed_program.json"
TTL = 600
RETRY = 60

# 현장조사 사료 단계 → 프로그램 개월령 (끝이 None 이면 출하까지, 29개월 뒤는 마지막 줄 급여를 이어 간다)
STAGES = {"송아지": (1, 3), "육성우": (4, 16), "비육전기": (17, 23), "비육후기": (24, None)}
NOT_COVERED = {"번식우": "번식우는 고급육생산프로그램(거세우 비육) 대상이 아님"}

_cache = {"prog": None, "at": 0.0}
_lock = threading.Lock()


# ---------------------------------------------------------------- 읽기
def _remote() -> dict:
    from .ai_report import _github_fetch            # 같은 GitHub 설정을 쓴다 (모듈끼리 서로 부르므로 여기서 가져온다)
    get, _ = _github_fetch()
    return json.loads(get(f"knowledge/{FILE_NAME}", "application/vnd.github.raw").decode("utf-8"))


def _validate(prog: dict) -> dict:
    months = prog.get("months") or []
    if [m.get("month") for m in months] != list(range(1, len(months) + 1)) or not months:
        raise ValueError("개월령 줄이 1부터 이어지지 않음")
    for m in months:
        for k in ("feed", "high_protein_feed", "feed_kg", "roughage_kg", "target_weight"):
            if m.get(k) in (None, ""):
                raise ValueError(f"{m['month']}개월 {k} 비어 있음")
    return prog


def load() -> dict | None:
    """프로그램(dict). 못 읽으면 지난 값, 그것도 없으면 None (리포트는 프로그램 없이 예전처럼 만든다)."""
    with _lock:
        if _cache["prog"] is not None and time.time() - _cache["at"] < TTL:
            return _cache["prog"]
        stale = _cache["prog"]
    try:
        local = LOCAL_DIR.is_dir()
        prog = _validate(json.loads((LOCAL_DIR / FILE_NAME).read_text(encoding="utf-8")) if local else _remote())
    except Exception as e:
        log.warning("사료 프로그램을 읽지 못함(%s): %s", "지난 값 사용" if stale else "프로그램 없이 리포트", e)
        with _lock:
            _cache["at"] = time.time() - TTL + RETRY
        return stale
    with _lock:
        _cache.update(prog=prog, at=time.time())
    log.info("사료 프로그램 %s (%s, %d개월)", prog.get("name"), prog.get("source_modified"), len(prog["months"]))
    return prog


# ---------------------------------------------------------------- 품목 이름 맞추기
def _key(name: str) -> str:
    """'팔공1 (후레이크)' → '팔공1', '어린송아지 플러스' → '어린송아지플러스'"""
    return re.sub(r"\(.*?\)|\s", "", str(name or "")).lower()


def _tokens(text: str) -> list[str]:
    """'슈퍼송아지→팔공1' 처럼 한 칸에 여러 사료를 적은 경우를 나눈다."""
    return [t.strip() for t in re.split(r"→|->|,|/|\+|·|및|>", str(text or "")) if _key(t)]


def _products(prog: dict) -> dict:
    """품목 키 → {"name", "normal": [개월], "high": [개월]}"""
    out = {}
    for m in prog["months"]:
        for kind, field in (("normal", "feed"), ("high", "high_protein_feed")):
            p = out.setdefault(_key(m[field]), {"name": m[field], "normal": [], "high": []})
            p[kind].append(m["month"])
    return out


def match_product(text: str, prog: dict) -> dict | None:
    """농가가 적은 사료 이름 하나 → 프로그램 품목 (없으면 None). 정확히 같거나, '팔공'을 뺀 이름이거나, 앞부분이 한 품목에만 맞을 때."""
    prods, k = _products(prog), _key(text)
    if not k:
        return None
    if k in prods:
        return prods[k]
    if "팔공" + k in prods:
        return prods["팔공" + k]
    if len(k) >= 3:
        hits = [p for pk, p in prods.items() if pk.startswith(k) or (len(pk) >= 3 and k.startswith(pk))]
        if len(hits) == 1:
            return hits[0]
    return None


def _span(nums: list[int]) -> str:
    return f"{nums[0]}개월" if len(nums) == 1 else f"{nums[0]}~{nums[-1]}개월"


def _kg(lo: float, hi: float) -> str:
    return f"{lo:g}" if lo == hi else f"{lo:g}~{hi:g}"


def _in_stage(months: list[int], stage: tuple) -> list[int]:
    lo, hi = stage
    return [m for m in months if m >= lo and (hi is None or m <= hi)]


def judge(text: str, stage_name: str, prog: dict) -> list[dict]:
    """조사표 배합사료 품목 칸 하나의 판정. 칸에 여러 사료가 있으면 사료마다."""
    stage = STAGES[stage_name]
    out = []
    for t in _tokens(text):
        p = match_product(t, prog)
        if p is None:
            out.append({"품목": t, "판정": "프로그램에 없는 사료"})
            continue
        normal, high = _in_stage(p["normal"], stage), _in_stage(p["high"], stage)
        if normal:
            verdict = f"이 단계 프로그램 사료 ({p['name']}, {_span(normal)})"
        elif high:
            verdict = f"이 단계 단백질 높은 사료 — 농가 선택 사항 ({p['name']}, {_span(high)})"
        else:
            verdict = f"프로그램 사료지만 다른 개월령용 ({p['name']}, 프로그램은 {_span(p['normal'] or p['high'])})"
        out.append({"품목": t, "판정": verdict})
    return out


# ---------------------------------------------------------------- 리포트에 넘길 모양
def stage_plan(prog: dict, stage_name: str) -> list[dict]:
    """단계 안에서 사료가 같은 개월령끼리 묶은 기준표."""
    lo, hi = STAGES[stage_name]
    rows = [m for m in prog["months"] if m["month"] >= lo and (hi is None or m["month"] <= hi)]
    groups = []
    for m in rows:
        if groups and groups[-1][0]["feed"] == m["feed"] and groups[-1][0]["high_protein_feed"] == m["high_protein_feed"]:
            groups[-1].append(m)
        else:
            groups.append([m])
    out = []
    for g in groups:
        months = [m["month"] for m in g]
        span = _span(months)
        if hi is None and g is groups[-1]:                 # 마지막 단계는 출하까지 이어 간다
            span = f"{months[0]}개월~출하 ({months[-1]}개월 뒤는 {months[-1]}개월 급여 유지)"
        out.append({
            "개월령": span,
            "목표체중_kg": _kg(g[0]["target_weight"], g[-1]["target_weight"]),
            "사료": g[0]["feed"],
            "단백질_높은_사료(농가_선택)": g[0]["high_protein_feed"] if _key(g[0]["high_protein_feed"]) != _key(g[0]["feed"]) else "없음(같은 사료)",
            "사료량_kg_두_일": _kg(min(m["feed_kg"][0] for m in g), max(m["feed_kg"][1] for m in g)),
            "조사료_kg_두_일": _kg(min(m["roughage_kg"][0] for m in g), max(m["roughage_kg"][1] for m in g)),
        })
    return out


def compare(prog: dict, feed_matrix: dict | None) -> dict:
    """현장조사 사료 칸(feed_matrix: {단계: {행: 값}})과 프로그램 기준을 단계별로 나란히."""
    fm = feed_matrix if isinstance(feed_matrix, dict) else {}
    stages = []
    for name, (lo, hi) in STAGES.items():
        rec = {k: v for k, v in (fm.get(name) or {}).items() if v not in (None, "")}
        stages.append({
            "단계": name,
            "프로그램_개월령": f"{lo}~{hi}개월" if hi else f"{lo}개월~출하",
            "프로그램_기준": stage_plan(prog, name),
            "농가_현장조사_기록": rec or "기록 없음",
            "배합사료_품목_판정": judge(rec.get("배합사료 품목", ""), name, prog) or "품목 기록 없음",
        })
    return {
        "기준": f"{prog.get('name')} ({prog.get('applies_to')}, 자료 {prog.get('source_modified')})",
        "주의": "현장조사의 급여수준(낮음·적정·높음)은 조사자 평가이며 kg 실측이 아님",
        "단계별_비교": stages,
        "프로그램_대상_아님": NOT_COVERED,
    }


def program_text(prog: dict) -> str:
    """시스템 프롬프트에 넣을 프로그램 전체 표 (개월령마다 한 줄)."""
    lines = [f"[{prog.get('name')}] {prog.get('applies_to')} · 자료 {prog.get('source_modified')}"]
    lines += [f"- {n}" for n in prog.get("notes", [])]
    lines.append("개월령 | 목표체중(kg) | 사료 | 사료량(kg/두/일) | 단백질 높은 사료(농가 선택) | 조사료(kg/두/일)")
    for m in prog["months"]:
        lines.append(f"{m['month']} | {m['target_weight']:g} | {m['feed']} | {_kg(*m['feed_kg'])} | {m['high_protein_feed']} | {_kg(*m['roughage_kg'])}")
    return "\n".join(lines)
