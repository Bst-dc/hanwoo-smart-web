// 3단계 · AI 리포트 — 만들기(서버 백그라운드 작업, 진행 상황을 몇 초마다 받아 옴)·저장된 리포트 보기·내려받기.
// 휴대폰 화면이 꺼지거나 다른 메뉴로 가도 서버에서 끝까지 만들어 저장한다. 다시 들어오면 진행 중인 작업에 다시 붙는다.
import { api, card, esc, flash, num } from "../api.js";

const POLL_MS = 2500;
const btn = "rounded-xl px-4 py-3 min-h-[48px] text-sm font-semibold disabled:opacity-50";
const errBox = (m) => `<div class="rounded-xl border border-neg/40 bg-white p-3 mb-3 text-sm text-neg">⚠️ ${esc(m)}</div>`;
const st = { farmId: null, openId: null, armed: null, pollTimer: null };

// DB 시각은 UTC 'YYYY-MM-DD HH:MM:SS' → 한국 시각으로 보여 준다
function kst(s) {
  const d = new Date(String(s || "").replace(" ", "T") + "Z");
  return isNaN(d) ? esc(s || "") : d.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
const mmss = (s) => `${Math.floor(s / 60)}분 ${String(s % 60).padStart(2, "0")}초`;

function stopPolling() { clearTimeout(st.pollTimer); st.pollTimer = null; }

function makeButtons(d) {
  if (!d.api_key) return card('<p class="text-sm text-neg">서버에 Anthropic API 키가 없어 리포트를 만들 수 없습니다. 관리자에게 설정을 요청하세요.</p>');
  const has = (m) => d.last_visit && d.reports.some((r) => r.mode === m && r.visit_number === d.last_visit.visit_number);
  const one = (mode, icon, title, sub, disabled) => `
    <button data-mode="${mode}" class="gen w-full text-left rounded-2xl border ${st.armed === mode ? "border-neg" : "border-line"} bg-white p-4 active:bg-panel disabled:opacity-50" ${disabled ? "disabled" : ""}>
      <div class="font-semibold">${icon} ${esc(title)}</div>
      <div class="text-xs text-muted mt-1">${esc(sub)}</div>
      ${st.armed === mode ? `<div class="text-xs text-neg font-semibold mt-2">한 번 더 누르면 ${d.last_visit.visit_number}차 방문의 기존 [${mode}] 리포트를 새 리포트로 바꿉니다.</div>`
        : has(mode) ? `<div class="text-xs text-muted mt-2">※ 이미 [${mode}] 리포트가 있습니다. 새로 만들면 바뀝니다.</div>` : ""}
    </button>`;
  return `<div class="grid gap-2 sm:grid-cols-2">
    ${one("전문", "📚", "전문자료 기반 리포트", "한우 컨설팅 길라잡이·자가TMR·육종가 자료를 근거로 처방합니다. 느리고 비용이 더 듭니다.", !d.knowledge)}
    ${one("일반", "✨", "일반 리포트 (빠름)", "Claude 의 일반 지식만으로 작성합니다. 빠르고 저렴하지만 자료 인용은 없습니다.", false)}
  </div>
  <p class="text-xs text-muted mt-2">엔진: ${esc(d.model)} · ${d.knowledge ? "📚 전문자료 사용 가능" : "⚠️ 전문자료를 쓸 수 없음"} · 몇 분 걸릴 수 있습니다. 화면을 꺼도 서버에서 계속 만듭니다.</p>`;
}

function reportList(d) {
  if (!d.reports.length) return card('<p class="text-sm text-muted">저장된 리포트가 없습니다.</p>');
  return `<div class="space-y-2">${d.reports.map((r) => `
    <button data-report="${r.id}" class="openrep w-full text-left rounded-2xl bg-white border ${st.openId === r.id ? "border-brand" : "border-line"} p-4 active:bg-panel">
      <div class="flex items-center justify-between gap-2"><span class="font-semibold">${num(r.visit_number)}차 방문 · ${r.mode === "전문" ? "📚 전문" : "✨ 일반"}</span><span class="text-xs text-muted">${num(r.length)}자</span></div>
      <div class="text-sm text-muted mt-1">${kst(r.created_at)} 만듦 · 눌러서 보기</div>
    </button>`).join("")}</div>`;
}

async function showReport(box, id) {
  box.innerHTML = '<p class="text-sm text-muted">불러오는 중…</p>';
  const r = await api(`/api/reports/${id}`);
  box.innerHTML = `
    <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
      <div class="text-sm"><b>${esc(r.farm)}</b> ${num(r.visit_number)}차 · ${r.mode === "전문" ? "📚 전문" : "✨ 일반"} · <span class="text-muted">${kst(r.created_at)}</span></div>
      <div class="flex gap-2">
        <a class="${btn} border border-line bg-white" href="/api/reports/${r.id}/download?fmt=html">🌐 HTML 받기</a>
        <a class="${btn} border border-line bg-white" href="/api/reports/${r.id}/download?fmt=md">📄 MD 받기</a>
      </div>
    </div>
    <article class="report rounded-2xl bg-white border border-line p-4">${r.html}</article>`;
  box.querySelectorAll(".report table").forEach((t) => {   // 넓은 표는 표만 옆으로 밀리게
    const w = document.createElement("div"); w.className = "table-wrap"; t.replaceWith(w); w.appendChild(t);
  });
}

function jobCard(j) {
  const running = j.status === "running";
  return card(`
    <div class="flex items-center justify-between gap-2">
      <div class="font-semibold">${running ? "⏳" : j.status === "done" ? "✅" : j.status === "cancelled" ? "⏹️" : "⚠️"} ${esc(j.farm)} · ${j.mode === "전문" ? "📚 전문" : "✨ 일반"} 리포트</div>
      <span class="text-xs text-muted kpi-value">${mmss(j.elapsed)} · ${num(j.length)}자</span>
    </div>
    <p class="text-sm mt-1 ${j.status === "error" ? "text-neg" : "text-muted"}">${esc(j.error || j.step)}</p>
    <div id="rp-live" class="mt-3 max-h-80 overflow-y-auto whitespace-pre-wrap text-sm rounded-xl bg-panel p-3 ${j.length ? "" : "hidden"}"></div>
    ${running ? `<button id="rp-cancel" class="${btn} w-full mt-3 border border-neg text-neg bg-white">⏹️ 만들기 취소 (저장 안 함)</button>` : ""}`, "border-brand");
}

// 작업에 붙어서 끝날 때까지 몇 초마다 새 글을 받아 온다
function follow(el, jobId, ctx) {
  stopPolling();
  let offset = 0, text = "";
  const tick = async () => {
    if (!el.isConnected || !ctx.isCurrent()) return stopPolling();
    let j;
    try { j = await api(`/api/report-jobs/${jobId}?offset=${offset}`); }
    catch (e) { el.querySelector("#rp-job").innerHTML = errBox(e.message); return stopPolling(); }
    text += j.text; offset = j.length;
    const box = el.querySelector("#rp-job");
    if (!box) return stopPolling();
    box.innerHTML = jobCard(j);
    const live = box.querySelector("#rp-live");
    live.textContent = text;
    live.scrollTop = live.scrollHeight;
    box.querySelector("#rp-cancel")?.addEventListener("click", async (ev) => {
      ev.target.disabled = true; ev.target.textContent = "취소하는 중…";
      await api(`/api/report-jobs/${jobId}/cancel`, { method: "POST" });
    });
    if (j.status === "running") { st.pollTimer = setTimeout(tick, POLL_MS); return; }
    stopPolling();
    if (j.status !== "done") {                              // 취소·실패: 알림을 남기고 만들기 버튼을 다시 보여 준다
      flash(j.status === "cancelled"
        ? `<div class="rounded-xl border border-line bg-white p-3 mb-3 text-sm">⏹️ ${esc(j.farm)} ${j.mode} 리포트 만들기를 취소했습니다. 저장된 리포트는 그대로입니다.</div>`
        : errBox(`${j.error} (저장된 리포트는 그대로입니다)`));
      await renderReport(el, ctx);
      window.scrollTo(0, 0);
      return;
    }
    if (j.status === "done") {
      const b = j.backup;
      flash(`<div class="rounded-xl border border-brand-line bg-brand-tint p-3 mb-3 text-sm">✅ ${esc(j.farm)} ${j.mode} 리포트를 만들었습니다. ${esc(j.saved_note || "")}
        ${b ? `<div class="text-xs ${b.ok === false ? "text-neg" : "text-muted"} mt-1">${b.ok === true ? "☁️" : b.ok === false ? "⚠️" : "ℹ️"} ${esc(b.message)}</div>` : ""}</div>`);
      st.openId = j.report_id;
      await renderReport(el, ctx);
      window.scrollTo(0, 0);
    }
  };
  tick();
}

export async function renderReport(el, ctx) {
  const { farm, farms, onPickFarm, isCurrent = () => true } = ctx;
  stopPolling();
  if (!farm) {
    el.innerHTML = card(`<h2 class="text-lg font-bold mb-1">3단계 · AI 리포트</h2>
      <p class="text-sm text-muted mb-3">먼저 리포트를 만들 농가를 고르세요. (위쪽 목록에서 골라도 됩니다)</p>
      <div class="space-y-2">${farms.map((f) => `
        <button data-farm="${f.id}" class="pick w-full text-left rounded-xl border border-line bg-white p-3 active:bg-panel">
          <span class="font-semibold">${esc(f.name)}</span><span class="text-xs text-muted ml-2">방문 ${num(f.visits)}회 · 출하성적 ${num(f.shipments)}두</span></button>`).join("")}</div>`);
    el.querySelectorAll(".pick").forEach((b) => b.addEventListener("click", () => onPickFarm(b.dataset.farm)));
    return;
  }
  if (st.farmId !== farm.id) Object.assign(st, { farmId: farm.id, openId: null, armed: null });

  el.innerHTML = '<p class="text-sm text-muted">불러오는 중…</p>';
  const d = await api(`/api/farms/${farm.id}/reports`);
  if (!isCurrent()) return;
  if (st.openId === null && d.reports.length) st.openId = d.reports[0].id;

  el.innerHTML = `
    <div class="rounded-2xl bg-brand-tint border border-brand-line p-3 text-sm">📌 <b>${esc(d.farm.name)}</b>
      ${d.last_visit ? `<span class="text-muted">· 리포트는 마지막 방문(${num(d.last_visit.visit_number)}차, ${esc(d.last_visit.visit_date)})의 조사표로 만들고 그 방문에 저장합니다.</span>`
        : '<span class="text-neg">· 방문 기록이 없어 리포트를 DB 에 저장하지 않습니다. 현장조사를 먼저 입력하세요.</span>'}</div>
    <h3 class="text-base font-bold mt-5 mb-2">리포트 만들기</h3>
    <div id="rp-job" class="mb-3"></div>
    <div id="rp-make">${d.running_job ? "" : makeButtons(d)}</div>
    <h3 class="text-base font-bold mt-6 mb-2">저장된 리포트</h3>
    ${reportList(d)}
    <div id="rp-view" class="mt-4"></div>`;

  if (d.running_job) follow(el, d.running_job, ctx);

  el.querySelectorAll(".gen").forEach((b) => b.addEventListener("click", async () => {
    const mode = b.dataset.mode;
    const exists = d.last_visit && d.reports.some((r) => r.mode === mode && r.visit_number === d.last_visit.visit_number);
    if (exists && st.armed !== mode) { st.armed = mode; return renderReport(el, ctx); }   // 덮어쓰기는 한 번 더 눌러야
    st.armed = null;
    flash("");
    try {
      const r = await api(`/api/farms/${farm.id}/reports`, { method: "POST", body: JSON.stringify({ mode }) });
      el.querySelector("#rp-make").innerHTML = "";
      follow(el, r.job_id, ctx);
    } catch (e) { flash(errBox(e.message)); window.scrollTo(0, 0); }
  }));
  el.querySelectorAll(".openrep").forEach((b) => b.addEventListener("click", async () => {
    st.openId = Number(b.dataset.report);
    el.querySelectorAll(".openrep").forEach((x) => x.classList.toggle("border-brand", x === b));
    try { await showReport(el.querySelector("#rp-view"), st.openId); el.querySelector("#rp-view").scrollIntoView({ behavior: "smooth" }); }
    catch (e) { flash(errBox(e.message)); }
  }));
  if (st.openId) showReport(el.querySelector("#rp-view"), st.openId).catch((e) => { el.querySelector("#rp-view").innerHTML = errBox(e.message); });
}
