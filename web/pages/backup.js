// 메뉴 5: 데이터 관리 · 백업 — 기존 Streamlit 화면과 같은 구성
//   농가별 조회 → 농가 마스터 / 누적 출하성적 / 방문 이력 / AI 리포트 이력(전체 보기·내려받기) → CSV → DB 파일 백업
import { api, apiDownload, esc, saveBlob, state } from "../api.js";

const ui = { filter: null };   // null = 전체 보기. 처음엔 사이드바에서 고른 농가
let root;

const SHOW_ROWS = 300;   // 출하성적은 2천 건이 넘어 한 번에 다 그리면 느리다 — 표는 앞부분만, CSV 는 전체
const card = (inner) => `<section class="rounded-xl bg-white border border-line p-4 mt-4">${inner}</section>`;

function table(t, { limit = SHOW_ROWS } = {}) {
  if (!t.rows.length) return `<p class="text-sm text-muted">데이터가 없습니다.</p>`;
  const shown = t.rows.slice(0, limit);
  const cell = (v) => (v === null || v === undefined ? '<span class="text-muted">-</span>' : esc(v));
  return `<div class="overflow-auto max-h-[420px] border border-line rounded-lg"><table class="w-full text-sm">
    <thead class="sticky top-0 bg-panel"><tr>${t.columns.map((c) => `<th class="px-2 py-1.5 text-left font-semibold whitespace-nowrap">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${shown.map((r) => `<tr class="border-t border-line">${r.map((v) => `<td class="px-2 py-1 whitespace-nowrap max-w-[22rem] truncate" title="${esc(v)}">${cell(v)}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div>
    <p class="text-xs text-muted mt-1">총 ${t.rows.length.toLocaleString("ko-KR")}행${t.rows.length > limit ? ` · 화면에는 앞의 ${limit}행만 보입니다 (CSV 로 받으면 전체)` : ""}</p>`;
}

function reportSection(t) {
  if (!t.rows.length) {
    return `<p class="text-sm bg-[#EEF4FB] rounded-lg p-3">아직 저장된 AI 리포트가 없습니다. '3단계 · AI 리포트' 메뉴에서 생성하면 여기에 누적됩니다.</p>`;
  }
  const idx = Object.fromEntries(t.columns.map((c, i) => [c, i]));
  const label = (r) => `[${r[idx["리포트ID"]]}] ${r[idx.farm_name]} · ${r[idx.visit_date]} · ${r[idx.report_mode]} 생성(${r[idx.created_at]})`;
  return `${table(t)}
    <label class="block text-sm font-medium mt-4">전체 내용을 볼 리포트 선택
      <select id="report-pick" class="mt-1 w-full rounded-lg border border-line bg-white px-2 py-2 text-sm font-normal">
        ${t.rows.map((r) => `<option value="${r[idx["리포트ID"]]}">${esc(label(r))}</option>`).join("")}</select></label>
    <div id="report-detail" class="mt-3"></div>`;
}

async function showReport(id) {
  const box = root.querySelector("#report-detail");
  box.innerHTML = `<p class="text-sm text-muted">불러오는 중…</p>`;
  try {
    const r = await api(`/api/data/reports/${id}`);
    const base = `${r.farm_name}_AI리포트_${r.report_mode}_${r.id}`;
    box.innerHTML = `<details open class="rounded-lg border border-line p-3">
        <summary class="cursor-pointer font-semibold text-sm">📄 ${esc(r.farm_name)} 리포트 전체 내용</summary>
        <article class="report-md mt-3">${DOMPurify.sanitize(marked.parse(r.markdown, { gfm: true, breaks: true }))}</article></details>
      <div class="grid sm:grid-cols-2 gap-2 mt-3">
        <button id="dl-md" class="rounded-lg border border-line bg-white py-2 text-sm hover:bg-panel">📥 이 리포트 마크다운(.md) 다운로드</button>
        <button id="dl-html" class="rounded-lg border border-line bg-white py-2 text-sm hover:bg-panel">🌐 이 리포트 HTML(.html) 다운로드</button></div>`;
    box.querySelector("#dl-md").addEventListener("click", () => saveBlob(new Blob([r.markdown], { type: "text/markdown;charset=utf-8" }), `${base}.md`));
    box.querySelector("#dl-html").addEventListener("click", (e) => withButton(e.currentTarget, () => apiDownload(`/api/data/reports/${r.id}/html`, `${base}.html`)));
  } catch (e) {
    box.innerHTML = `<p class="text-sm text-neg">⚠️ ${esc(e.message)}</p>`;
  }
}

async function withButton(btn, fn) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "만드는 중…";
  btn.nextElementSibling?.matches(".dl-error") && btn.nextElementSibling.remove();
  try {
    await fn();
  } catch (e) {
    btn.insertAdjacentHTML("afterend", `<span class="dl-error text-xs text-neg ml-2">⚠️ ${esc(e.message)}</span>`);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

export async function renderBackup(el) {
  root = el;
  if (ui.filter === null && state.farmId) ui.filter = state.farmId;       // 처음엔 사이드바에서 고른 농가
  if (ui.filter && !state.farms.some((f) => f.id === ui.filter)) ui.filter = 0;
  const q = ui.filter ? `?farm_id=${ui.filter}` : "";
  const data = await api(`/api/data/tables${q}`);

  el.innerHTML = `
    <h1 class="text-2xl font-bold">데이터 관리 · 누적 DB &amp; 엑셀 백업</h1>
    <p class="text-sm text-muted mb-4">모든 컨설팅 기록과 출하 데이터를 안전하게 보관하고 언제든 엑셀/CSV로 내보냅니다.</p>
    <label class="block text-sm font-medium">농가별로 조회 <span class="text-muted font-normal">(왼쪽에서 고른 농가가 기본 선택됩니다 — 리포트 만든 농가의 기록을 바로 확인할 때 유용합니다)</span>
      <select id="filter" class="mt-1 w-full rounded-lg border border-line bg-white px-2 py-2 text-sm font-normal">
        <option value="0" ${ui.filter ? "" : "selected"}>🔎 전체 보기</option>
        ${state.farms.map((f) => `<option value="${f.id}" ${f.id === ui.filter ? "selected" : ""}>${esc(f.label)}</option>`).join("")}</select></label>
    ${card(`<h2 class="font-bold mb-2">📋 전체 등록 농가 마스터</h2>${table(data.farms)}`)}
    ${card(`<h2 class="font-bold mb-2">🥩 전체 누적 출하 성적 데이터</h2>${table(data.shipments)}`)}
    ${card(`<h2 class="font-bold mb-1">🚗 현장 방문 컨설팅 이력</h2>
      <p class="text-xs text-muted mb-2">사양관리 실태(facility_info), 급여 현황(feed_info) 등 현장조사 원본 항목까지 표시합니다. 수정은 '2단계 · 현장방문조사' 메뉴의 '기존 방문조사 수정' 모드를 이용하세요.</p>${table(data.visits)}`)}
    ${card(`<h2 class="font-bold mb-2">🤖 AI 컨설팅 리포트 저장 이력</h2>${reportSection(data.reports)}`)}
    <div class="grid sm:grid-cols-3 gap-2 mt-4">
      ${[["farms", "📥 농가 목록 CSV 다운로드", "농가목록_DB.csv"], ["shipments", "📥 전체 출하성적 CSV 다운로드", "출하성적_전체_DB.csv"],
        ["visits", "📥 현장 방문 이력 CSV 다운로드", "현장방문이력_전체_DB.csv"]].map(([n, l, f]) =>
        `<button data-csv="${n}" data-file="${f}" class="rounded-lg border border-line bg-white py-2 text-sm hover:bg-panel">${l}</button>`).join("")}</div>
    ${card(`<h2 class="font-bold mb-1">💾 전체 DB 파일 백업</h2>
      <p class="text-xs text-muted mb-3">위 표들을 포함한 DB 전체를 .db 파일 하나로 내려받습니다. 조합원 정보가 들어 있으니 보관에 주의하세요.</p>
      <button id="dl-db" class="rounded-lg bg-brand text-white px-4 py-2 font-semibold disabled:opacity-40">💾 DB 파일 만들어 내려받기</button>`)}`;

  el.querySelector("#filter").addEventListener("change", (e) => { ui.filter = Number(e.target.value); renderBackup(el); });
  el.querySelectorAll("[data-csv]").forEach((b) => b.addEventListener("click", () =>
    withButton(b, () => apiDownload(`/api/data/export/${b.dataset.csv}.csv${q}`, b.dataset.file))));
  el.querySelector("#dl-db").addEventListener("click", (e) => {
    const stamp = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16).replace(/[-:T]/g, "").replace(/^(\d{8})/, "$1_");
    return withButton(e.currentTarget, () => apiDownload("/api/data/db-file", `consulting_${stamp}.db`));
  });
  const pick = el.querySelector("#report-pick");
  if (pick) {
    pick.addEventListener("change", () => showReport(pick.value));
    showReport(pick.value);
  }
}
