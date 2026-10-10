// 메뉴 4: 3단계 · AI 리포트 — 기존 Streamlit 화면과 같은 구성
//   대상 농가 → [📚 전문자료 기반 | ✨ 일반 | ❌ 조회취소] → 생성되는 글을 그대로 보여 줌 → 성공하면 저장 안내 → .md/.html 내려받기
import { api, apiDownloadPost, apiStream, esc, notifySaved, saveBlob, state } from "../api.js";

const MODE_LABEL = { 전문: "📚 전문자료 기반", 일반: "✨ 일반 모드" };
// 화면을 다시 그려도 남는 마지막 리포트 (기존 session_state["ai_report"]) — 농가별로 하나
const ui = { reports: {}, running: null };
let root;

const renderMarkdown = (md) => DOMPurify.sanitize(marked.parse(md || "", { gfm: true, breaks: true }));
const note = (cls, html) => `<div class="rounded-lg p-3 text-sm ${cls}">${html}</div>`;

function reportHtml(r) {
  return `<div class="flex flex-wrap items-center justify-between gap-2 mb-3">
      <span class="text-sm text-muted">${MODE_LABEL[r.mode]}</span>
      <div class="flex gap-2">
        <button id="dl-md" class="rounded-lg border border-line bg-white px-3 py-1.5 text-sm hover:bg-panel">📥 마크다운(.md) 다운로드 [${r.mode}]</button>
        <button id="dl-html" class="rounded-lg border border-line bg-white px-3 py-1.5 text-sm hover:bg-panel">🌐 HTML(.html) 다운로드 [${r.mode}]</button>
      </div></div>
    <article class="report-md">${renderMarkdown(r.markdown)}</article>`;
}

function bindDownloads(farm, r) {
  root.querySelector("#dl-md")?.addEventListener("click", () =>
    saveBlob(new Blob([r.markdown], { type: "text/markdown;charset=utf-8" }), `${farm.farm_name}_AI컨설팅리포트_${r.mode}.md`));
  root.querySelector("#dl-html")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      await apiDownloadPost("/api/report/html", { farm_id: farm.id, markdown: r.markdown, mode: r.mode },
        `${farm.farm_name}_AI컨설팅리포트_${r.mode}.html`);
    } catch (ex) {
      btn.insertAdjacentHTML("afterend", `<span class="text-xs text-neg">⚠️ ${esc(ex.message)}</span>`);
    } finally {
      btn.disabled = false;
    }
  });
}

function showSaved(farm) {
  const out = root.querySelector("#report-out");
  const r = ui.reports[farm.id];
  out.innerHTML = r ? reportHtml(r) : "";
  if (r) bindDownloads(farm, r);
}

async function generate(farm, mode) {
  const out = root.querySelector("#report-out");
  const msg = root.querySelector("#report-msg");
  const buttons = root.querySelectorAll("[data-mode]");
  delete ui.reports[farm.id];
  document.getElementById("flash").innerHTML = "";   // 이전 저장 안내가 새 결과(특히 실패)와 같이 보이지 않게
  buttons.forEach((b) => { b.disabled = true; });
  msg.innerHTML = note("bg-[#EEF4FB]", `${mode === "전문" ? "📚 전문자료(한우 컨설팅 길라잡이·자가TMR·육종가 기초지식)를 근거로 분석합니다."
    : "✨ 일반 모드 — Claude의 일반 지식만으로 분석합니다. (자료 근거 인용 없음)"}<br>
    <span class="inline-block animate-pulse">⏳ [${esc(farm.farm_name)}] 농가의 출하성적과 현장조사 데이터를 Claude가 융합 분석 중입니다… (몇 분 걸릴 수 있습니다. 멈추려면 '조회취소')</span>`);
  out.innerHTML = `<article class="report-md"></article>`;
  const article = out.querySelector("article");

  const controller = new AbortController();
  ui.running = controller;
  let text = "", last = null, timer = null;
  const paint = () => { timer = null; article.innerHTML = renderMarkdown(text + " ▌"); };
  try {
    await apiStream(`/api/farms/${farm.id}/report`, { mode }, (ev) => {
      if (ev.text) {
        text += ev.text;
        timer ||= setTimeout(paint, 250);   // 글이 올 때마다 다시 그리면 무거워서 0.25초마다 한 번
      } else if (ev.done || ev.error) {
        last = ev;
      }
    }, controller.signal);
  } catch (e) {
    last = { error: e.name === "AbortError" ? null : `서버와 연결이 끊겼습니다: ${e.message}`, aborted: e.name === "AbortError" };
  } finally {
    clearTimeout(timer);
    ui.running = null;
    buttons.forEach((b) => { b.disabled = b.dataset.mode === "전문" && !root.dataset.kbReady; });
  }

  if (last?.aborted) {
    msg.innerHTML = note("bg-[#EEF4FB]", "리포트 생성 작업이 취소(초기화) 되었습니다. 저장하지 않았습니다.");
    out.innerHTML = "";
  } else if (!last || last.error) {
    // 실패·잘림·빈 응답은 저장하지 않는다 → 기존에 저장된 리포트는 그대로 (기존과 같음)
    msg.innerHTML = note("bg-white border border-neg/40 text-neg",
      `⚠️ 리포트 생성에 실패했습니다. 기존에 저장된 리포트는 그대로 유지됩니다.<br>${esc(last?.error || "응답이 중간에 끊겼습니다.")}`);
    out.innerHTML = text.trim() ? `<details class="rounded-lg border border-line p-3"><summary class="cursor-pointer text-sm">중단되기 전까지 생성된 내용 보기 (저장되지 않음)</summary>
      <article class="report-md mt-3">${renderMarkdown(text)}</article></details>` : "";
  } else {
    msg.innerHTML = last.saved ? "" : note("bg-[#FBF3E6]", esc(last.message));
    if (last.saved) notifySaved(last.message, last.backup);
    ui.reports[farm.id] = { mode, markdown: text };
    showSaved(farm);
  }
}

export async function renderReport(el) {
  root = el;
  const farm = state.farms.find((f) => f.id === state.farmId);
  const head = `<h1 class="text-2xl font-bold">3단계 · AI 맞춤형 종합 컨설팅 보고서</h1>
    <p class="text-sm text-muted mb-4">출하성적(정량)과 현장조사(정성)를 융합 분석하여 '진단 → 원인 → 처방' 7단 구성 리포트를 생성합니다.</p>`;
  if (!farm) {
    el.innerHTML = head + note("bg-[#FBF3E6]", "등록된 농가가 없습니다. 농가를 먼저 등록해주세요.");
    return;
  }
  const s = await api("/api/report/status");
  el.dataset.kbReady = s.knowledge_ready ? "1" : "";
  el.innerHTML = `${head}
    <section class="rounded-xl bg-white border border-line p-4">
      <h2 class="font-bold mb-1">🎯 리포트 대상 농가</h2>
      <p class="text-sm mb-3"><b>${esc(farm.label)}</b> <span class="text-muted">— 다른 농가는 왼쪽 '현재 컨설팅 농가 선택'에서 바꿔주세요.</span></p>
      ${s.key_configured ? "" : note("bg-white border border-neg/40 text-neg mb-3", "⚠️ Anthropic API 키가 설정되지 않아 리포트를 만들 수 없습니다.")}
      <div class="grid sm:grid-cols-[2fr_2fr_1fr] gap-2">
        <button data-mode="전문" class="rounded-lg bg-brand text-white py-2 font-semibold disabled:opacity-40" ${s.knowledge_ready && s.key_configured ? "" : "disabled"}
          title="${s.knowledge_ready ? "한우 컨설팅 길라잡이·자가TMR·육종가 기초지식을 근거로 처방합니다. 출처를 인용하지만 시간과 비용이 더 듭니다." : "전문자료(knowledge)를 찾지 못했습니다."}">📚 전문자료 기반 리포트 생성</button>
        <button data-mode="일반" class="rounded-lg border border-brand text-brand bg-white py-2 font-semibold disabled:opacity-40" ${s.key_configured ? "" : "disabled"}
          title="Claude의 일반 지식만으로 작성합니다. 빠르고 저렴하지만 자료 근거 인용은 없습니다.">✨ 일반 리포트 생성 (빠름)</button>
        <button id="report-cancel" class="rounded-lg border border-line bg-white py-2 hover:bg-panel">❌ 조회취소</button>
      </div>
      <p class="text-xs text-muted mt-2">엔진: Claude Sonnet 5 · ${s.knowledge_ready ? "📚 전문자료 준비됨" : "⚠️ 전문자료 없음"}</p>
    </section>
    <div id="report-msg" class="mt-3"></div>
    <section class="rounded-xl bg-white border border-line p-4 mt-3"><div id="report-out"></div></section>`;

  el.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => generate(farm, b.dataset.mode)));
  el.querySelector("#report-cancel").addEventListener("click", () => {
    if (ui.running) ui.running.abort();
    else {
      delete ui.reports[farm.id];
      showSaved(farm);
      el.querySelector("#report-msg").innerHTML = note("bg-[#EEF4FB]", "리포트 생성 작업이 취소(초기화) 되었습니다.");
    }
  });
  showSaved(farm);
}
