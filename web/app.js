// 한우 스마트 컨설팅 화면 — 로그인, 농가 선택(왼쪽 사이드바, 좁은 화면은 위쪽 단추), 메뉴 전환(본문 위 탭)을 맡고 각 화면은 pages/*.js 가 그린다.
//   #/dashboard  #/shipment  #/survey  #/report  #/data
import { api, card, esc, state, store, toast } from "./api.js";
import { destroyCharts } from "./charts.js";
import { initFarmPicker, renderFarmPicker } from "./farmpicker.js";
import { renderDashboard } from "./pages/dashboard.js";
import { renderData } from "./pages/data.js";
import { renderShipment } from "./pages/shipment.js";
import { renderReport } from "./pages/report.js";
import { renderSurvey } from "./pages/survey.js";

// ---------- 메뉴 ----------
// render 가 없는 메뉴는 아직 옮기는 중이다 (기존 Streamlit 앱에서 쓴다).
const TABS = [
  { id: "dashboard", label: "종합 현황", title: "종합 현황 대시보드" },
  { id: "shipment", label: "1단계 · 출하성적 비교", title: "1단계 · 출하성적 비교분석" },
  { id: "survey", label: "2단계 · 현장조사", title: "2단계 · 현장방문조사" },
  { id: "report", label: "3단계 · AI 리포트", title: "3단계 · AI 리포트" },
  { id: "data", label: "데이터 관리", title: "데이터 관리 · 백업" },
];

const currentTab = () => TABS.find((t) => `#/${t.id}` === location.hash) || TABS[0];

function renderTabs() {
  const cur = currentTab();
  document.getElementById("tabs").innerHTML = TABS.map((t) =>
    `<a role="tab" class="tab shrink-0 whitespace-nowrap px-4 py-2.5 text-sm border-b-2 border-transparent text-muted hover:text-ink" href="#/${t.id}" aria-selected="${t.id === cur.id}">${esc(t.label)}</a>`).join("");
}

// ---------- 농가 선택 ----------
function renderFarmSelect() {
  renderFarmPicker();
}

function selectFarm(id) {
  state.farmId = id ? Number(id) : null;
  store.set("farmId", state.farmId ?? "");
  document.getElementById("flash").innerHTML = "";
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

let renderToken = 0;
async function renderPage() {
  const token = ++renderToken;       // 느린 화면이 늦게 도착해 새 화면을 덮어쓰지 않게 한다
  renderTabs();
  const tab = currentTab();
  const el = pageEl();
  try {
    destroyCharts();                  // 다른 화면으로 가면 이전 차트를 정리한다
    const isCurrent = () => token === renderToken;
    const onPickFarm = (id) => {
      selectFarm(id);
      toast(`${state.farms.find((f) => f.id === state.farmId).name} 선택`);
    };
    const farm = state.farms.find((f) => f.id === state.farmId) || null;
    // 성적을 저장하면 농가 목록의 두수가 바뀌므로 목록부터 다시 받는다
    const onSaved = async () => { await loadFarms(); renderFarmSelect(); await renderPage(); };
    if (tab.id === "dashboard") await renderDashboard(el, { farms: state.farms, farmId: state.farmId, isCurrent, onPickFarm });
    else if (tab.id === "shipment") await renderShipment(el, { farm, farms: state.farms, isCurrent, onPickFarm, onSaved });
    else if (tab.id === "survey") await renderSurvey(el, { farm, farms: state.farms, isCurrent, onPickFarm, onSaved });
    else if (tab.id === "report") await renderReport(el, { farm, farms: state.farms, isCurrent, onPickFarm });
    else if (tab.id === "data") await renderData(el, { farm, farms: state.farms, isCurrent, onPickFarm, onSaved });
    else el.innerHTML = pending(tab);
  } catch (e) {
    if (token === renderToken) el.innerHTML = `<div class="rounded-xl border border-neg/40 bg-white p-4 text-neg text-sm">${esc(e.message)}</div>`;
  }
}

// ---------- 로그인 ----------
function showLogin() {
  document.getElementById("app").classList.add("hidden");
  document.getElementById("login").classList.remove("hidden");
  document.getElementById("logout").classList.add("hidden");      // 로그아웃 단추는 머리글에 있어 따로 숨긴다
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

initFarmPicker({ onSelect: selectFarm });
state.onUnauthorized = showLogin;
window.addEventListener("hashchange", () => { document.getElementById("flash").innerHTML = ""; renderPage(); });

(async function start() {
  const s = await api("/api/auth/status");
  if (s.logged_in) await showApp(s);
  else showLogin();
})();
