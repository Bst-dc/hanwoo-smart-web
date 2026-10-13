"""AI 컨설팅 리포트 — 프롬프트·전문자료·Claude 호출·백그라운드 작업·저장.

프롬프트 문구, 모델(claude-sonnet-5), max_tokens(32000), 전문자료 캐시(1시간) 설정은 기존 앱 generate_claude_report 와 같다.
기존 앱과 다르게 한 곳: 생성을 서버의 백그라운드 작업으로 돌린다. 휴대폰 화면이 꺼지거나 앱을 닫아도
서버에서 끝까지 만들어 저장하고, 화면은 몇 초마다 진행 상황을 받아 간다.
저장 규칙(기존 앱과 같음): 끝까지 완성된 리포트만, 농가의 마지막 방문에, 방식(전문/일반)마다 하나씩 덮어쓴다.
"""
import html
import json
import logging
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import markdown as md_lib

from .. import backup, config, db, national_stats
from . import report_data

log = logging.getLogger("consulting.ai_report")

MODEL = "claude-sonnet-5"
MAX_TOKENS = 32000
KNOWLEDGE_DIR = config.BASE_DIR / "knowledge"


class ReportError(Exception):
    """리포트를 만들지 못함. 오류 문구가 리포트 본문으로 저장되지 않게 예외로 알린다."""


def api_key() -> str:
    return config.secret("ANTHROPIC_API_KEY")


# ---------------------------------------------------------------- 전문자료
_kb = {"text": None}
_kb_lock = threading.Lock()


def _remote_knowledge() -> dict:
    token = config.secret("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN 없음")
    repo = config.secret("GITHUB_REPO", "Bst-dc/hanwoo-smart-consulting")
    branch = config.secret("GITHUB_BRANCH", "main")
    headers = {"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "hanwoo-consulting-app"}

    def get(path, accept):
        url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
        with urllib.request.urlopen(urllib.request.Request(url, headers={**headers, "Accept": accept}), timeout=20) as r:
            return r.read()
    listing = json.loads(get("knowledge", "application/vnd.github+json").decode("utf-8"))
    names = [i["name"] for i in listing if i.get("type") == "file" and i["name"].endswith(".md")]
    if not names:
        raise RuntimeError("비공개 저장소에 knowledge/*.md 가 없음")
    return {n: get(f"knowledge/{n}", "application/vnd.github.raw").decode("utf-8") for n in names}


def knowledge() -> str:
    """전문자료 한 덩어리. 파일 이름 순서를 고정해야 프롬프트 캐시가 맞는다. 실패는 캐시하지 않고 '' 를 돌려준다."""
    with _kb_lock:
        if _kb["text"] is not None:
            return _kb["text"]
        try:
            if KNOWLEDGE_DIR.is_dir():
                files = {p.name: p.read_text(encoding="utf-8") for p in KNOWLEDGE_DIR.glob("*.md")}
            else:
                files = _remote_knowledge()
        except Exception as e:
            log.warning("전문자료를 받지 못함: %s", e)
            return ""
        _kb["text"] = "\n\n".join(f'<문서 제목="{n[:-3]}">\n{files[n]}\n</문서>' for n in sorted(files))
        log.info("전문자료 %d개 (%d자)", len(files), len(_kb["text"]))
        return _kb["text"]


# ---------------------------------------------------------------- 프롬프트
def build_request(farm_name: str, gdata: dict, survey: dict, kb: str) -> tuple[list, str]:
    """(system 블록, user 프롬프트). 문구는 기존 앱과 같다."""
    system_prompt = (
        "당신은 대한민국 최고의 한우 사양관리 수석 컨설턴트입니다. "
        "농가의 최근 3개년 출하성적(정량 데이터)과 현장 방문 사양관리 실태(정성 데이터)를 종합 분석하여 "
        "'진단 → 원인 → 처방 → 액션플랜' 흐름의 7단 구성 맞춤형 컨설팅 리포트를 마크다운으로 작성하세요. "
        "농가가 거세우와 암소를 함께 출하하는 경우 두 성별의 데이터가 각각 주어지니 반드시 성별을 구분해서 분석하고, "
        "한 성별 데이터만 주어졌다면 그 성별만 다루고 없는 성별을 언급하지 마세요."
    )
    if kb:
        system_prompt += (
            " 아래 [참고 전문자료]는 농협경제지주·농촌진흥청이 발간한 한우 사양관리 자료입니다. "
            "처방과 기준을 제시할 때 이 자료에 해당 내용이 있으면 반드시 근거로 삼고 어느 자료의 어떤 기준인지 밝히세요. "
            "자료에 없는 수치나 기준은 지어내지 말고, 일반적인 권장사항이라면 그렇다고 명시하세요."
        )
    system = [{"type": "text", "text": system_prompt}]
    if kb:
        system.append({"type": "text", "text": f"[참고 전문자료]\n{kb}", "cache_control": {"type": "ephemeral", "ttl": "1h"}})

    gender_blocks = "\n\n".join(
        f"### {glabel} 출하성적\n"
        f"[출하성적 종합 통계 (전체 기간 통합 평균)]:\n{json.dumps(gd['shipment_stats'], ensure_ascii=False, indent=2)}\n\n"
        f"[연도별 출하성적 추이 및 등급 전체 분포 (전국 평균 대비, 연도 오름차순)]:\n{json.dumps(gd['yearly_breakdown'], ensure_ascii=False, indent=2)}\n\n"
        f"[수익성 분석 (전국 평균 대비 손익, \"계산_방식\" 필드에 실측치인지 추정치인지 명시됨)]:\n{json.dumps(gd['profit_data'], ensure_ascii=False, indent=2)}"
        for glabel, gd in gdata.items()
    ) or "(이 농가는 등록된 출하성적이 없습니다)"

    prompt = f"""
[농가명]: {farm_name}

[출하 성별]: {", ".join(gdata.keys()) if gdata else "없음"}

{gender_blocks}

[현장 방문 조사표 실태 (사료급여, 축사환경, 농가 대화)]:
{json.dumps(survey, ensure_ascii=False, indent=2)}

[보고서 작성 필수 7단 구성 가이드]
농장주가 이해하기 쉽고 현장에서 즉시 적용할 수 있도록 아래 목차에 맞추어 작성해 주세요:
# 1. 📋 종합 컨설팅 개요 배너 (농가명, 조사일, 컨설턴트, 핵심 평가)
# 2. ⚡ 핵심 진단 요약 (30초 요약 카드 3~4개: 성적 및 현장조사 핵심 이슈)
# 3. 📊 출하성적 전국 비교 및 수익성 임팩트 — 위 성별별 [연도별 출하성적 추이 및 등급 전체 분포] 데이터를 근거로 성별마다 연도별 표를 만들어 도체중·BMS·등지방·단면적 추이와, 1++/1+/1/2/3 등 육질등급·A/B/C 육량등급 전체 분포 변화를 전국 평균과 비교하세요. 두당/연간 수익 격차는 각 성별 [수익성 분석] 데이터의 값을 그대로 인용하고, "계산_방식"이 추정치라면 반드시 "~로 추정됩니다"처럼 추정임을 밝히세요. 해당 데이터에 없는 연도·수치·성별은 만들어내지 말고 언급하지 마세요.
# 4. 🔍 현장 사양관리 및 축사환경 실태 진단 (우방밀도, 환기, 성장단계별 사료 급여를 [양호/보통/미흡] 배지로 판정)
# 5. 💡 문제별 원인 분석 및 개선 처방 (1:1 매칭: [문제 현상] → [근본 원인] → [정밀 처방])
# 6. 🚀 실행 우선순위 로드맵 (1단계 즉시조치 1~2주, 2단계 기반구축 1~3개월, 3단계 성적개선 6개월~)
# 7. 📌 안내 및 출처 (농촌진흥청 국립축산과학원 사양표준 인용 및 축협 담당자 협의 권장 면책 문구)
"""
    return system, prompt


def claude_stream(system, prompt, on_text, should_stop):
    """Claude 에 스트리밍으로 묻고 글이 올 때마다 on_text(조각). 반환: stop_reason. 시험에서 바꿔 끼운다."""
    import anthropic
    key = api_key()
    if not key:
        raise ReportError("Anthropic API 키(ANTHROPIC_API_KEY)가 서버에 설정되지 않았습니다.")
    client = anthropic.Anthropic(api_key=key)
    try:
        with client.messages.stream(model=MODEL, max_tokens=MAX_TOKENS, system=system,
                                    messages=[{"role": "user", "content": prompt}]) as stream:
            for text in stream.text_stream:
                if should_stop():
                    return "cancelled"
                on_text(text)
            return stream.get_final_message().stop_reason
    except anthropic.AuthenticationError:
        raise ReportError("Anthropic API 키가 올바르지 않습니다.") from None
    except anthropic.RateLimitError:
        raise ReportError("Anthropic API 사용량 한도에 걸렸습니다. 잠시 후 다시 시도해주세요.") from None
    except anthropic.APIStatusError as e:
        raise ReportError(f"Claude API 오류가 발생했습니다 ({e.status_code}). {e.message}") from None
    except anthropic.APIConnectionError:
        raise ReportError("Anthropic API에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.") from None


# ---------------------------------------------------------------- 저장·읽기
SAVE_SQL = """INSERT INTO ai_reports (visit_id, report_mode, full_markdown, created_at) VALUES (?, ?, ?, ?)
              ON CONFLICT(visit_id, report_mode) DO UPDATE SET full_markdown = excluded.full_markdown, created_at = excluded.created_at"""


def save(conn, visit_id: int, mode: str, text: str) -> int:
    try:
        conn.execute(SAVE_SQL, (visit_id, mode, text, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return conn.execute("SELECT id FROM ai_reports WHERE visit_id = ? AND report_mode = ?", (visit_id, mode)).fetchone()[0]


def list_reports(conn, farm_id: int) -> list[dict]:
    rows = conn.execute("""SELECT a.id, a.report_mode, a.created_at, LENGTH(a.full_markdown), v.visit_number, v.visit_date
                           FROM ai_reports a JOIN visits v ON v.id = a.visit_id WHERE v.farm_id = ?
                           ORDER BY v.visit_number DESC, a.report_mode""", (farm_id,)).fetchall()
    return [{"id": r[0], "mode": r[1], "created_at": r[2], "length": r[3], "visit_number": r[4], "visit_date": r[5]} for r in rows]


def get_report(conn, report_id: int) -> dict | None:
    r = conn.execute("""SELECT a.id, a.report_mode, a.created_at, a.full_markdown, v.farm_id, v.visit_number, f.farm_name
                        FROM ai_reports a JOIN visits v ON v.id = a.visit_id JOIN farms f ON f.id = v.farm_id
                        WHERE a.id = ?""", (report_id,)).fetchone()
    if r is None:
        return None
    return {"id": r[0], "mode": r[1], "created_at": r[2], "markdown": r[3], "farm_id": r[4], "visit_number": r[5], "farm": r[6]}


def to_html(text: str) -> str:
    """마크다운 → HTML. 리포트 안의 HTML 태그는 글자로 보여 준다 (화면에 끼워 넣어도 안전하게)."""
    return md_lib.markdown(text.replace("&", "&amp;").replace("<", "&lt;"), extensions=["tables", "nl2br", "fenced_code"])


def html_document(farm: str, text: str, mode: str) -> str:
    """내려받기용 단독 HTML (기존 앱 build_report_html 과 같은 모양)."""
    title = html.escape(f"{farm} AI 컨설팅 리포트 ({mode})")
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>
body {{ font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #1e293b; line-height: 1.7; }}
h1, h2, h3 {{ color: #1e3a8a; }} h1 {{ border-bottom: 3px solid #1e3a8a; padding-bottom: 10px; }}
h2 {{ margin-top: 2rem; border-left: 5px solid #16a34a; padding-left: 10px; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }} th, td {{ border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }}
th {{ background-color: #eff6ff; color: #1e3a8a; }} tr:nth-child(even) {{ background-color: #f8fafc; }}
blockquote {{ border-left: 4px solid #94a3b8; margin: 1rem 0; padding: 0.5rem 1rem; color: #64748b; background: #f8fafc; }}
code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }} @media print {{ body {{ margin: 0; padding: 20px; }} }}
</style></head><body>
{to_html(text)}
</body></html>"""


# ---------------------------------------------------------------- 백그라운드 작업
JOBS: dict = {}
_jobs_lock = threading.Lock()
MAX_RUNNING = 2
KEEP_SECONDS = 3 * 60 * 60


def _prune():
    now = time.time()
    for jid in [j for j, v in JOBS.items() if v["status"] != "running" and now - v["updated"] > KEEP_SECONDS]:
        JOBS.pop(jid, None)


def running_for(farm_id: int) -> dict | None:
    with _jobs_lock:
        return next((j for j in JOBS.values() if j["farm_id"] == farm_id and j["status"] == "running"), None)


def start(farm_id: int, farm_name: str, mode: str, stream_fn=None, connect=None) -> dict:
    """작업을 만들고 스레드로 돌린다. 데이터 모으기·Claude 호출·저장·백업은 스레드 안에서 한다."""
    with _jobs_lock:
        _prune()
        if any(j["farm_id"] == farm_id and j["status"] == "running" for j in JOBS.values()):
            raise ReportError("이 농가의 리포트를 이미 만들고 있습니다. 끝날 때까지 기다려 주세요.")
        if sum(j["status"] == "running" for j in JOBS.values()) >= MAX_RUNNING:
            raise ReportError("다른 리포트를 만들고 있습니다. 잠시 후 다시 시도해주세요.")
        job = {"id": uuid.uuid4().hex, "farm_id": farm_id, "farm": farm_name, "mode": mode, "status": "running",
               "step": "데이터 모으는 중", "text": "", "error": None, "report_id": None, "saved_note": None,
               "backup": None, "cancel": False, "started": time.time(), "updated": time.time()}
        JOBS[job["id"]] = job
    threading.Thread(target=_run, args=(job, stream_fn or claude_stream, connect or db.connect), daemon=True).start()
    return job


def _finish(job, status, **kw):
    job.update(status=status, updated=time.time(), **kw)


def _run(job, stream_fn, connect):
    conn = None
    try:
        conn = connect()
        stats, _ = national_stats.get()
        gdata = report_data.gender_data(conn, job["farm_id"], stats)
        visit = report_data.last_visit(conn, job["farm_id"])
        kb = ""
        if job["mode"] == "전문":
            job["step"] = "전문자료 준비 중"
            kb = knowledge()
            if not kb:
                raise ReportError("전문자료를 불러오지 못했습니다. '일반 리포트'로 만들거나 잠시 후 다시 시도해주세요.")
        system, prompt = build_request(job["farm"], gdata, report_data.survey_for_prompt(visit), kb)
        job["step"] = "Claude 가 작성 중"
        log.info("AI 리포트 시작: 농가 %s, %s", job["farm_id"], job["mode"])

        def on_text(t):
            job["text"] += t
            job["updated"] = time.time()
        stop = stream_fn(system, prompt, on_text, lambda: job["cancel"])
        if stop == "cancelled":
            return _finish(job, "cancelled", step="취소됨 (저장하지 않음)")
        if stop == "max_tokens":
            raise ReportError("리포트가 최대 길이에 도달해 중간에 잘렸습니다. 다시 시도해주세요. (저장하지 않았습니다)")
        if not job["text"].strip():
            raise ReportError("Claude 가 빈 응답을 보냈습니다. 잠시 후 다시 시도해주세요. (저장하지 않았습니다)")
        if not visit:
            return _finish(job, "done", step="완료", saved_note="이 농가는 방문 기록이 없어 DB 에 저장하지 않았습니다. 필요하면 파일로 내려받으세요.")
        job["step"] = "저장 중"
        rid = save(conn, visit["id"], job["mode"], job["text"])
        log.info("AI 리포트 저장: 농가 %s, 방문 %s, %s (%d자)", job["farm_id"], visit["id"], job["mode"], len(job["text"]))
        b = backup.run("AI 리포트 저장")
        _finish(job, "done", step="완료", report_id=rid, backup=b,
                saved_note=f"{visit['visit_number']}차 방문 리포트({job['mode']})로 저장했습니다. 같은 방식의 이전 리포트는 이것으로 바뀌었습니다.")
    except ReportError as e:
        _finish(job, "error", step="실패", error=str(e))
    except Exception as e:
        log.exception("AI 리포트 작업 실패: 농가 %s", job["farm_id"])
        _finish(job, "error", step="실패", error=f"리포트를 만드는 중 오류가 났습니다 ({type(e).__name__}). 저장된 리포트는 그대로입니다.")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def view(job: dict, offset: int = 0) -> dict:
    return {k: job[k] for k in ("id", "farm_id", "farm", "mode", "status", "step", "error", "report_id", "saved_note", "backup")} | {
        "text": job["text"][offset:], "length": len(job["text"]), "elapsed": int(time.time() - job["started"])}


def knowledge_ready() -> bool:
    return bool(_kb["text"]) or KNOWLEDGE_DIR.is_dir() or bool(config.secret("GITHUB_TOKEN"))


def has_api_key() -> bool:
    return bool(api_key())
