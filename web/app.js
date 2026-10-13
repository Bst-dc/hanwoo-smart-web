// 한우 스마트 컨설팅 화면 — 로그인, 농가 선택(위), 메뉴 전환(아래 탭)을 맡고 각 화면은 pages/*.js 가 그린다.
//   #/dashboard  #/shipment  #/survey  #/report  #/data
import { api, card, esc, num, state, store, toast } from "./api.js";

// ---------- 메뉴 ----------
// render 가 없는 메뉴는 아직 옮기는 중이다 (기존 Streamlit 앱에서 쓴다).
const TABS = [
  { id: "dashboard", icon: "📊", label: "현황", title: "종합 현황 대시보드" },
  { id: "shipment", icon: "🥩", label: "출하성적", title: "1단계 · 출하성적 비교분석" },
  { id: "survey", icon: "📝", label: "현장조사", title: "2단계 · 현장방문조사" },
  { id: "report", icon: "🤖", label: "AI리포트", title: "3단계 · AI 리포트" },
  { id: "data", icon: "💾", label: "데이터", title: "데이터 관리 · 백업" },
];

const currentTab = () => TABS.find((t) => `#/${t.id}` === location.hash) || TABS[0];

function renderTabbar() {
  const cur = currentTab();
  document.querySelector("#tabbar > div").innerHTML = TABS.map((t) =>
    `<a class="tab-item" href="#/${t.id}" ${t.id === cur.id ? 'aria-current="page"' : ""}><span class="ico" aria-hidden="true">${t.icon}</span>${esc(t.label)}</a>`).join("");
}

// ---------- 농가 선택 ----------
function renderFarmSelect() {
  const sel = document.getElementById("farm-select");
  if (!state.farms.length) {
    sel.innerHTML = '<option value="">등록된 농가가 없습니다</option>';
    return;
  }
  sel.innerHTML = '<option value="">전체 농가</option>' + state.farms.map((f) =>
    `<option value="${f.id}" ${String(f.id) === String(state.farmId) ? "selected" : ""}>${esc(f.name)}</option>`).join("");
}

function selectFarm(id) {
  state.farmId = id ? Number(id) : null;
  store.set("farmId", state.farmId ?? "");
  renderFarmSelect();
  renderPage();
}

async function loadFarms() {
  state.farms = (await api("/api/farms")).farms;
  const saved = Number(store.get("farmId"));
  state.farmId = state.farms.some((f) => f.id === saved) ? saved : null;
}

// ---------- 화면 그리기 ----------
const pageEl = () => document.getElementById("page");

function pending(tab) {
  return card(`<h2 class="text-lg font-bold mb-2">${esc(tab.title)}</h2>
    <p class="text-muted text-sm">이 화면은 아직 옮기는 중입니다. 기존 앱(consulting 주소)에서 사용하세요.</p>`);
}

function kpi(label, value, sub = "") {
  return `<div class="rounded-2xl bg-white border border-line p-4">
    <div class="text-sm text-muted">${esc(label)}</div>
    <div class="kpi-value text-2xl font-bold mt-1">${esc(value)}</div>
    ${sub ? `<div class="text-xs text-muted mt-1">${esc(sub)}</div>` : ""}</div>`;
}

// 0단계 대시보드: 농가 수·방문 횟수·출하성적 두수 (기존 앱 대시보드 숫자와 맞춰 보는 용도) + 농가 카드
function renderDashboard(el) {
  const farms = state.farms;
  const visits = farms.reduce((s, f) => s + f.visits, 0);
  const ships = farms.reduce((s, f) => s + f.shipments, 0);
  const noShip = farms.filter((f) => f.shipments === 0).length;
  el.innerHTML = `<h2 class="text-xl font-bold mb-3">종합 현황 대시보드</h2>
    <div class="grid grid-cols-2 gap-3">
      ${kpi("총 관리 농가 수", `${num(farms.length)} 농가`)}
      ${kpi("누적 현장 방문 횟수", `${num(visits)} 회`)}
      ${kpi("누적 분석 출하 두수", `${num(ships)} 두`)}
      ${kpi("출하성적 없는 농가", `${num(noShip)} 농가`)}
    </div>
    <h3 class="text-base font-bold mt-6 mb-2">농가 목록</h3>
    <div class="space-y-2">${farms.map((f) => `
      <button data-farm="${f.id}" class="farm-card w-full text-left rounded-2xl bg-white border ${f.id === state.farmId ? "border-brand" : "border-line"} p-4 active:bg-panel">
        <div class="flex items-center justify-between gap-2">
          <span class="font-semibold truncate">${esc(f.name)}</span>
          <span class="text-xs text-muted shrink-0">${esc(f.region)}</span>
        </div>
        <div class="text-sm text-muted mt-1">방문 ${num(f.visits)}회 · 출하성적 ${num(f.shipments)}두</div>
      </button>`).join("")}</div>`;
  el.querySelectorAll(".farm-card").forEach((b) => b.addEventListener("click", () => {
    selectFarm(b.dataset.farm);
    toast(`${state.farms.find((f) => f.id === state.farmId).name} 선택`);
  }));
}

let renderToken = 0;
async function renderPage() {
  const token = ++renderToken;       // 느린 화면이 늦게 도착해 새 화면을 덮어쓰지 않게 한다
  renderTabbar();
  const tab = currentTab();
  const el = pageEl();
  try {
    if (tab.id === "dashboard") renderDashboard(el);
    else el.innerHTML = pending(tab);
  } catch (e) {
    if (token === renderToken) el.innerHTML = `<div class="rounded-xl border border-neg/40 bg-white p-4 text-neg text-sm">⚠️ ${esc(e.message)}</div>`;
  }
}

// ---------- 로그인 ----------
function showLogin() {
  document.getElementById("app").classList.add("hidden");
  document.getElementById("login").classList.remove("hidden");
  document.getElementById("login-pw").focus();
}

async function showApp(status) {
  document.getElementById("login").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  document.getElementById("logout").classList.toggle("hidden", !status.password_required);
  await loadFarms();
  renderFarmSelect();
  await renderPage();
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("login-pw");
  const err = document.getElementById("login-error");
  err.classList.add("hidden");
  try {
    const s = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ password: input.value }) });
    input.value = "";
    await showApp(s);
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
});

document.getElementById("logout").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  location.hash = "#/dashboard";
  showLogin();
});

document.getElementById("farm-select").addEventListener("change", (e) => selectFarm(e.target.value));
state.onUnauthorized = showLogin;
window.addEventListener("hashchange", () => { document.getElementById("flash").innerHTML = ""; renderPage(); });

(async function start() {
  const s = await api("/api/auth/status");
  if (s.logged_in) await showApp(s);
  else showLogin();
})();
