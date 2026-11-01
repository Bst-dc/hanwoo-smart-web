// 농가 선택 — 검색 + 조합원/비조합원 구분으로 고른다 (기본 <select> 는 검색이 안 돼서 직접 만든다).
//   1280px 이상: 왼쪽 사이드바에 목록을 늘 펼쳐 둔다(CSS). 그보다 좁으면 위쪽 단추를 눌러 여는 떠 있는 상자.
//   initFarmPicker({ onSelect }) 한 번, 농가 목록·선택이 바뀌면 renderFarmPicker() 를 부른다.
import { esc, state, store } from "./api.js";

const SCOPES = ["전체", "조합원", "비조합원"];
const ui = { open: false, scope: SCOPES.includes(store.get("farmScope")) ? store.get("farmScope") : "전체", q: "" };   // 고른 구분은 다음에 열어도 그대로
let onSelect = () => {};

const $ = (id) => document.getElementById(id);
const badge = (f) => (f.member_type === "비조합원" ? ' <span class="text-xs font-normal text-muted border border-line rounded px-1">비조합원</span>' : "");

function matches(f) {
  if (ui.scope !== "전체" && f.member_type !== ui.scope) return false;
  const q = ui.q.trim().toLowerCase();
  return !q || [f.name, f.owner, f.region].some((v) => String(v || "").toLowerCase().includes(q));
}

// 목록은 장부처럼 한 줄에 한 농가 — 이름·지역 | 출하 두수 | 방문 횟수. 0 은 옅게 써서 자료가 빈 농가가 눈에 띄게 한다.
const ROW = "grid grid-cols-[minmax(0,1fr)_3.5rem_3rem] items-center gap-2";
const count = (n, unit) => `<span class="kpi-value text-right text-[13px] ${n ? "text-ink" : "text-[#A8ADAC]"}">${Number(n || 0).toLocaleString("ko-KR")}<span class="text-[11px] text-muted">${unit}</span></span>`;
const rowCls = (on) => `fp-item ${ROW} w-full text-left rounded-md px-3 py-1.5 min-h-[40px] ${on ? "bg-panel font-semibold shadow-[inset_2px_0_0_#1F6B5E]" : "hover:bg-panel active:bg-panel"}`;

function item(f) {
  const on = String(f.id) === String(state.farmId);
  return `<button type="button" role="option" aria-selected="${on}" data-id="${f.id}" class="${rowCls(on)}">
    <span class="truncate">${esc(f.name)}${f.region ? ` <span class="text-xs font-normal text-muted">${esc(f.region)}</span>` : ""}</span>
    ${count(f.shipments, "두")}${count(f.visits, "회")}</button>`;
}

// 조합원·비조합원이 다 있을 때만 '전체'에서 묶음 제목을 붙인다
const hasBothTypes = () => new Set(state.farms.map((f) => f.member_type)).size > 1;

function renderList() {
  const hits = state.farms.filter(matches);
  const both = ui.scope === "전체" && hasBothTypes();
  const group = (type) => {
    const list = hits.filter((f) => f.member_type === type);
    if (!list.length) return "";
    return (both ? `<div class="px-3 pt-3 pb-1 text-xs font-semibold text-muted">${type} ${list.length}</div>` : "") + list.map(item).join("");
  };
  const all = `<button type="button" role="option" aria-selected="${state.farmId === null}" data-id="" class="${rowCls(state.farmId === null)}">
    <span>전체 농가 <span class="text-xs font-normal text-muted kpi-value">${state.farms.length}</span></span></button>`;
  const head = `<div class="${ROW} px-3 pt-2 pb-1 text-[11px] text-muted border-t border-line mt-1"><span></span><span class="text-right">출하</span><span class="text-right">방문</span></div>`;
  $("farm-list").innerHTML = (ui.q.trim() ? "" : all) + (hits.length ? head : "") + group("조합원") + group("비조합원")
    + (hits.length ? "" : `<p class="px-3 py-4 text-sm text-muted">${ui.q.trim() ? "검색 결과가 없습니다." : `등록된 ${ui.scope} 농가가 없습니다.`}</p>`);
  $("farm-list").querySelectorAll(".fp-item").forEach((b) => b.addEventListener("click", () => choose(b.dataset.id)));
}

// 구분 선택: 전체 · 조합원 · 비조합원 세 칸 단추 (고른 칸은 잉크색). 고르면 아래 목록에 그 구분 농가만 나온다.
function renderScopes() {
  const box = $("farm-scope");
  const n = (s) => (s === "전체" ? state.farms.length : state.farms.filter((f) => f.member_type === s).length);
  box.innerHTML = SCOPES.map((s, i) => `<button type="button" data-s="${s}" aria-pressed="${s === ui.scope}" class="flex-1 px-2 py-1.5 min-h-[36px] text-sm ${i ? "border-l border-line" : ""} ${s === ui.scope ? "bg-brand text-white font-semibold" : "bg-white text-muted hover:text-ink"}">${s} <span class="kpi-value text-xs ${s === ui.scope ? "" : "text-[#A8ADAC]"}">${n(s)}</span></button>`).join("");
  box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    ui.scope = b.dataset.s;
    store.set("farmScope", ui.scope);
    renderScopes(); renderList();         // 검색칸에 초점을 주지 않는다 (패드에서 자판이 올라오지 않게)
  }));
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
  renderScopes(); renderList();       // 넓은 화면은 목록이 늘 보이므로 닫혀 있어도 새로 그린다
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
