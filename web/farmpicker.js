// 상단 농가 선택 — 검색 + 조합원/비조합원 구분으로 고른다 (기본 <select> 는 검색이 안 돼서 직접 만든다).
//   initFarmPicker({ onSelect }) 한 번, 농가 목록·선택이 바뀌면 renderFarmPicker() 를 부른다.
import { esc, state } from "./api.js";

const SCOPES = ["전체", "조합원", "비조합원"];
const ui = { open: false, scope: "전체", q: "" };
let onSelect = () => {};

const $ = (id) => document.getElementById(id);
const badge = (f) => (f.member_type === "비조합원" ? ' <span class="text-xs font-normal text-muted border border-line rounded px-1">비조합원</span>' : "");

function matches(f) {
  if (ui.scope !== "전체" && f.member_type !== ui.scope) return false;
  const q = ui.q.trim().toLowerCase();
  return !q || [f.name, f.owner, f.region].some((v) => String(v || "").toLowerCase().includes(q));
}

function item(f) {
  const on = String(f.id) === String(state.farmId);
  return `<button type="button" role="option" aria-selected="${on}" data-id="${f.id}" class="fp-item w-full text-left rounded-xl px-3 py-2 min-h-[44px] ${on ? "bg-brand-tint font-semibold" : "active:bg-panel"}">
    <span class="block truncate">${esc(f.name)}${badge(f)}</span>
    <span class="block text-xs text-muted truncate">${esc([f.owner, f.region].filter(Boolean).join(" · ") || "-")}</span></button>`;
}

function renderList() {
  const hits = state.farms.filter(matches);
  const group = (type) => {
    const list = hits.filter((f) => f.member_type === type);
    return list.length ? `<div class="px-3 pt-2 pb-1 text-xs font-semibold text-muted">${type} (${list.length})</div>${list.map(item).join("")}` : "";
  };
  const all = `<button type="button" role="option" aria-selected="${state.farmId === null}" data-id="" class="fp-item w-full text-left rounded-xl px-3 py-2 min-h-[44px] ${state.farmId === null ? "bg-brand-tint font-semibold" : "active:bg-panel"}">전체 농가</button>`;
  $("farm-list").innerHTML = (ui.q.trim() ? "" : all) + group("조합원") + group("비조합원")
    + (hits.length ? "" : '<p class="px-3 py-4 text-sm text-muted">검색 결과가 없습니다.</p>');
  $("farm-list").querySelectorAll(".fp-item").forEach((b) => b.addEventListener("click", () => choose(b.dataset.id)));
}

function renderScopes() {
  const count = (s) => (s === "전체" ? state.farms.length : state.farms.filter((f) => f.member_type === s).length);
  $("farm-scope").innerHTML = SCOPES.map((s) => `<button type="button" data-s="${s}" aria-pressed="${s === ui.scope}" class="rounded-full border px-3 py-1 text-sm min-h-[36px] ${s === ui.scope ? "bg-brand text-white border-brand font-semibold" : "bg-white border-line text-muted"}">${s} ${count(s)}</button>`).join("");
  $("farm-scope").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { ui.scope = b.dataset.s; renderScopes(); renderList(); $("farm-search").focus(); }));
}

function setOpen(open) {
  ui.open = open;
  $("farm-panel").classList.toggle("hidden", !open);
  $("farm-btn").setAttribute("aria-expanded", open);
  if (open) { ui.q = ""; $("farm-search").value = ""; renderScopes(); renderList(); $("farm-search").focus(); }
}

function choose(id) {
  setOpen(false);
  onSelect(id);
}

export function renderFarmPicker() {
  const f = state.farms.find((x) => String(x.id) === String(state.farmId));
  $("farm-btn-label").innerHTML = !state.farms.length ? "등록된 농가가 없습니다" : f ? `${esc(f.name)}${badge(f)}` : "전체 농가";
  if (ui.open) { renderScopes(); renderList(); }
}

export function initFarmPicker(opts) {
  onSelect = opts.onSelect;
  $("farm-btn").addEventListener("click", () => setOpen(!ui.open));
  $("farm-search").addEventListener("input", (e) => { ui.q = e.target.value; renderList(); });
  $("farm-search").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); const first = $("farm-list").querySelector(".fp-item"); if (first) choose(first.dataset.id); }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && ui.open) { setOpen(false); $("farm-btn").focus(); } });
  // 칩·목록을 누르면 그 자리가 다시 그려져 e.target 이 문서에서 빠진다. 클릭 시점의 경로로 안쪽인지 본다.
  document.addEventListener("click", (e) => { if (ui.open && !e.composedPath().includes($("farm-picker"))) setOpen(false); });
}
