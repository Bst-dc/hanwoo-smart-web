// 한우 스마트컨설팅 화면 — 로그인, 농가 선택, 메뉴 전환을 맡고 각 메뉴 화면은 pages/*.js 가 그린다.
import { api, esc, notifySaved, state } from "./api.js";
import { renderDashboard } from "./pages/dashboard.js";
import { renderShipments } from "./pages/shipments.js";
import { renderSurvey } from "./pages/survey.js";
import { renderReport } from "./pages/report.js";

// ---------- 메뉴 ----------
const MENUS = [
  { id: "dashboard", label: "종합 현황 대시보드", render: renderDashboard },
  { id: "shipments", label: "1단계 · 출하성적 비교분석", render: renderShipments },
  { id: "survey", label: "2단계 · 현장방문조사", render: renderSurvey },
  { id: "report", label: "3단계 · AI 리포트", render: renderReport },
  { id: "backup", label: "데이터 관리 · 백업" },
];

function currentMenu() {
  const id = location.hash.replace("#", "");
  return MENUS.find((m) => m.id === id) || MENUS[0];
}

function renderMenu() {
  const cur = currentMenu();
  document.getElementById("menu").innerHTML = MENUS.map((m) => `
    <a href="#${m.id}" class="menu-item block rounded-lg px-3 py-2 text-sm hover:bg-panel" ${m.id === cur.id ? 'aria-current="page"' : ""}>
      ${esc(m.label)}${m.render ? "" : ' <span class="text-xs text-muted">(옮기는 중)</span>'}
    </a>`).join("");
}

async function renderPage() {
  renderMenu();
  const menu = currentMenu();
  const page = document.getElementById("page");
  if (!menu.render) {
    page.innerHTML = `<div class="rounded-xl bg-white border border-line p-6">
      <h1 class="text-xl font-bold mb-2">${esc(menu.label)}</h1>
      <p class="text-muted text-sm">이 화면은 아직 옮기는 중입니다. 기존 Streamlit 앱에서 사용하세요.</p></div>`;
    return;
  }
  page.innerHTML = `<p class="text-muted text-sm">불러오는 중…</p>`;
  try {
    await menu.render(page);
  } catch (e) {
    page.innerHTML = `<div class="rounded-xl border border-neg/40 bg-white p-4 text-neg text-sm">⚠️ ${esc(e.message)}</div>`;
  }
}

// ---------- 농가 선택 ----------
async function loadFarms() {
  state.farms = await api("/api/farms");
  const sel = document.getElementById("farm-select");
  if (!state.farms.length) {
    sel.innerHTML = `<option>등록된 농가 없음</option>`;
    state.farmId = null;
    return;
  }
  let saved = state.farmId;
  if (saved === null) { try { saved = Number(sessionStorage.getItem("farmId")); } catch {} }
  state.farmId = state.farms.some((f) => f.id === saved) ? saved : state.farms[0].id;
  sel.innerHTML = state.farms.map((f) => `<option value="${f.id}" ${f.id === state.farmId ? "selected" : ""}>${esc(f.label)}</option>`).join("");
}

document.getElementById("farm-select").addEventListener("change", (e) => {
  state.farmId = Number(e.target.value);
  try { sessionStorage.setItem("farmId", state.farmId); } catch {}
  renderPage();
});

// ---------- 신규 농가 등록 ----------
const farmForm = document.getElementById("farm-form");
const dupBox = document.getElementById("farm-dup");
const farmErr = document.getElementById("farm-error");
let dupTimer;

function showDuplicate(dup, message) {
  // 같은 농가를 또 등록하면 출하성적과 조사표가 서로 다른 농가로 쪼개져 연결되지 않는다 — 저장 전에 경고하고 확인을 받는다.
  if (!dup && !message) { dupBox.classList.add("hidden"); dupBox.innerHTML = ""; return; }
  const text = message || `이미 등록된 농가와 일치합니다 — ${dup.farm_name} (${dup.owner_name || "대표자 미입력"}, ${dup.region || "지역 미입력"}, 조합원번호 ${dup.farm_code || "미입력"}). 같은 농가라면 여기서 다시 등록하지 말고 위쪽 '현재 컨설팅 농가 선택'에서 이 농가를 고르세요.`;
  dupBox.innerHTML = `<p>⚠️ ${esc(text)}</p>
    <label class="flex items-center gap-1 mt-2 font-medium"><input type="checkbox" name="confirm_duplicate"> 그래도 별개의 새 농가로 등록합니다</label>`;
  dupBox.classList.remove("hidden");
  syncSaveButton();
}

function syncSaveButton() {
  const confirm = farmForm.elements.confirm_duplicate;
  farmForm.querySelector("button").disabled = Boolean(confirm && !confirm.checked);
}

farmForm.addEventListener("input", (e) => {
  if (e.target.name === "confirm_duplicate") return syncSaveButton();
  if (e.target.name !== "farm_name" && e.target.name !== "farm_code") return;
  clearTimeout(dupTimer);
  dupTimer = setTimeout(async () => {
    const q = new URLSearchParams({ name: farmForm.elements.farm_name.value.trim(), code: farmForm.elements.farm_code.value.trim() });
    try {
      showDuplicate(await api(`/api/farms/duplicate?${q}`));
    } catch { /* 미리 경고는 보조 기능 — 저장할 때 서버가 다시 확인한다 */ }
    syncSaveButton();
  }, 300);
});
farmForm.addEventListener("change", (e) => { if (e.target.name === "confirm_duplicate") syncSaveButton(); });

farmForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  farmErr.classList.add("hidden");
  const f = farmForm.elements;
  if (!f.farm_name.value.trim()) {
    farmErr.textContent = "농가명을 입력해주세요.";
    farmErr.classList.remove("hidden");
    return;
  }
  const btn = farmForm.querySelector("button");
  btn.disabled = true;
  btn.textContent = "저장 중…";
  try {
    const res = await api("/api/farms", { method: "POST", body: JSON.stringify({
      farm_code: f.farm_code.value, farm_name: f.farm_name.value, owner_name: f.owner_name.value,
      region: f.region.value, breeding_type: f.breeding_type.value, total_heads: Number(f.total_heads.value || 0),
      confirm_duplicate: Boolean(f.confirm_duplicate?.checked),
    }) });
    farmForm.reset();
    showDuplicate(null);
    document.getElementById("farm-new").open = false;
    state.farmId = res.farm.id;                      // 방금 등록한 농가를 선택해 둔다
    try { sessionStorage.setItem("farmId", state.farmId); } catch {}
    await loadFarms();
    notifySaved(`${res.farm.farm_name} 농가 등록 완료!`, res.backup);
    await renderPage();
  } catch (ex) {
    if (ex.status === 409 && ex.body?.duplicate_id) {
      showDuplicate(null, ex.message);
    } else {
      farmErr.textContent = ex.message;
      farmErr.classList.remove("hidden");
    }
  } finally {
    btn.textContent = "신규 농가 저장";
    syncSaveButton();
  }
});

// ---------- 로그인 ----------
function showLogin() {
  document.getElementById("app").classList.add("hidden");
  document.getElementById("login").classList.remove("hidden");
  document.getElementById("login-pw").focus();
}

async function showApp(passwordRequired) {
  document.getElementById("login").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  document.getElementById("logout").classList.toggle("hidden", !passwordRequired);
  await loadFarms();
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
    await showApp(s.password_required);
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
});

document.getElementById("logout").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  showLogin();
});

state.onUnauthorized = showLogin;
window.addEventListener("hashchange", () => {
  document.getElementById("flash").innerHTML = "";   // 저장 안내는 다른 메뉴로 가면 지운다
  renderPage();
});

(async function start() {
  const s = await api("/api/auth/status");
  if (s.authed) await showApp(s.password_required);
  else showLogin();
})();
