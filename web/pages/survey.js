// 메뉴 3: 2단계 · 현장방문조사 — 기존 Streamlit 양식과 같은 항목·순서·기본값
//   작성 모드(신규 / 기존 수정) → 1. 기본정보 → 2. 날씨(지역 고르면 자동) → 3. 사육환경 → 4. 사료급여(성장단계 표)
//   → 5. 사육두수 → 6~8. 번식·질병·특이사항 → 저장
import { api, esc, notifySaved, state } from "../api.js";

const DEFAULT_INVESTIGATOR = "컨설턴트 배성태";   // 기존 양식의 기본값
const WEATHER_KEYS = [   // [조사표 키, 날씨표 키, 라벨]
  ["dailyAvgTemp", "avgTemp", "연평균기온 (℃)"], ["highTemp", "highTemp", "최고기온 (℃)"],
  ["lowTemp", "lowTemp", "최저기온 (℃)"], ["annualPrecip", "precip", "평균강수량 (연간) (mm)"],
  ["avgWindSpeed", "wind", "평균풍속 (m/s)"], ["avgHumidity", "humid", "평균상대습도 (%)"],
];

const ui = { mode: "new", visitId: null, farmId: null };
let opts = null;      // /api/survey/options
let root;

// ---------------------------------------------------------------- 입력 칸 만들기
// 저장값이 선택지에 없으면(예전 데이터) 첫 선택지로 바꿔치지 않고 그 값을 그대로 보여 준다
const withCurrent = (choices, v) => (v && !choices.includes(v) ? [...choices, v] : choices);

function select(key, label, choices, value, extra = "") {
  const list = withCurrent(choices, value);
  // 저장값이 빈 칸이면(예전 엑셀에서 옮긴 조사표) 첫 선택지를 고른 것으로 바꾸지 않는다 — 조사 안 한 항목이 사실처럼 저장된다
  const blank = value === "" ? `<option value="" selected>(미입력)</option>` : "";
  return `<label class="block text-sm font-medium">${label}
    <select name="${key}" class="mt-1 w-full rounded-lg border border-line bg-white px-2 py-2 text-sm font-normal" ${extra}>
      ${blank}${list.map((c) => `<option ${c === value ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>`;
}

function radio(key, label, choices, value) {
  const list = withCurrent(choices, value);
  return `<fieldset class="text-sm"><legend class="font-medium mb-1">${label}</legend>
    <div class="flex flex-wrap gap-x-4 gap-y-1">${list.map((c) => `<label class="flex items-center gap-1">
      <input type="radio" name="${key}" value="${esc(c)}" ${c === value ? "checked" : ""}> ${esc(c)}</label>`).join("")}</div></fieldset>`;
}

function text(key, label, value, extra = "") {
  return `<label class="block text-sm font-medium">${label}
    <input name="${key}" value="${esc(value)}" class="mt-1 w-full rounded-lg border border-line px-2 py-1.5 font-normal" ${extra}></label>`;
}

function num(key, label, value, { int = false, step } = {}) {
  return `<label class="block text-sm font-medium">${label}
    <input name="${key}" type="number" data-type="${int ? "int" : "float"}" step="${step ?? (int ? 1 : "any")}" value="${value ?? 0}"
      class="mt-1 w-full rounded-lg border border-line px-2 py-1.5 text-right font-normal"></label>`;
}

const section = (title, body, open = false) => `<details class="rounded-xl bg-white border border-line p-4" ${open ? "open" : ""}>
  <summary class="cursor-pointer font-bold">${title}</summary><div class="mt-3 space-y-3">${body}</div></details>`;
const grid = (cols, items) => `<div class="grid gap-3 ${cols === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"}">${items.join("")}</div>`;

// ---------------------------------------------------------------- 날씨
function weatherValue(existing, region, key, wdKey) {
  // 기존과 같게: 저장된 값이 0 이 아니면 그 값, 아니면 지역 날씨표 값
  const saved = existing[key];
  if (saved !== undefined && saved !== null && Number(saved) !== 0) return Number(saved);
  return Number(opts.weather[region]?.[wdKey] ?? 0);
}

function weatherHtml(existing, region) {
  const wd = opts.weather[region];
  const note = wd ? `<p class="text-xs text-muted">출처: ${esc(wd.source)} · 2025년 전국 연강수량 ${opts.national_precip_2025}mm</p>`
    : `<p class="text-xs text-muted">등록된 지역이 아니라서 자동으로 채워지는 값이 없습니다. 직접 입력해주세요.</p>`;
  return note + grid(2, WEATHER_KEYS.map(([k, wk, label]) => num(k, label, weatherValue(existing, region, k, wk))));
}

// ---------------------------------------------------------------- 사료 표
function feedTable(matrix) {
  const m = matrix || {};
  return `<div class="overflow-x-auto"><table class="text-sm">
    <thead><tr><th></th>${opts.feed_cols.map((c) => `<th class="px-1 py-1 font-semibold">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${opts.feed_rows.map((row) => `<tr><th class="px-1 py-1 text-left font-medium whitespace-nowrap">${esc(row)}</th>
      ${opts.feed_cols.map((col) => `<td class="px-1 py-1"><input data-feed-col="${esc(col)}" data-feed-row="${esc(row)}"
        value="${esc(m[col]?.[row] ?? "")}" ${row.endsWith("급여수준") ? 'list="feed-levels" placeholder="낮음/적정/높음"' : ""}
        class="w-28 rounded border border-line px-1 py-1" aria-label="${esc(col)} ${esc(row)}"></td>`).join("")}</tr>`).join("")}
    </tbody></table>
    <datalist id="feed-levels"><option>낮음</option><option>적정</option><option>높음</option></datalist></div>`;
}

// ---------------------------------------------------------------- 양식
function formHtml(e, isEdit) {
  const c = opts.choices;
  const g = (k, fallback) => (e[k] === undefined || e[k] === null ? fallback : e[k]);
  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const visitDate = /^\d{4}-\d{2}-\d{2}/.test(String(e.visitDate ?? "")) ? String(e.visitDate).slice(0, 10) : today;
  const region = g("region", opts.regions[0]);
  const pens = [["fattening", "비육우방"], ["breeding", "번식우방"], ["calf", "송아지우방"]];
  return `<form id="survey-form" class="space-y-3" novalidate>
    ${section("1. 조사 기본정보", `
      ${grid(2, [text("investigator", "조사자 성명", g("investigator", DEFAULT_INVESTIGATOR)),
        `<label class="block text-sm font-medium">조사일자<input name="visitDate" type="date" required value="${visitDate}" class="mt-1 w-full rounded-lg border border-line px-2 py-1.5 font-normal"></label>`])}
      ${grid(2, [text("memberName", "조합원명", g("memberName", "")), text("memberId", "조합원번호", g("memberId", ""))])}
      ${select("region", "지역 (선택하면 아래 '2. 날씨 정보'가 자동으로 채워집니다)", opts.regions, region)}
      ${radio("farmType", "전업여부", c.farmType, g("farmType", "전업"))}
      ${select("bizGoal", "🎯 농가 경영 목표 (출하 전략)", c.bizGoal, g("bizGoal", c.bizGoal[0]))}`, true)}
    ${section("2. 날씨 정보 (2025년 기준)", `<div id="weather">${weatherHtml(e, region)}</div>`, true)}
    ${section("3. 축산 사육환경", `
      ${select("breedingType", "사육형태", c.breedingType, g("breedingType", c.breedingType[0]))}
      ${grid(3, pens.map(([k, l]) => `<div class="space-y-2">
        ${select(`${k}PenSize`, `${l} 크기`, c.penSize, g(`${k}PenSize`, c.penSize[0]))}
        ${select(`${k}PenDensity`, `${l} 밀도`, c.penDensity, g(`${k}PenDensity`, "적정"))}</div>`))}
      ${grid(2, [radio("bulkBin", "벌크빈", c.yesNo, g("bulkBin", "부")), radio("autoFeeder", "자동급이시설", c.yesNo, g("autoFeeder", "부")),
        radio("tmr", "TMR 급여", c.yesNo, g("tmr", "부")), radio("selfMix", "자가배합", c.yesNo, g("selfMix", "부")),
        num("castrationAge", "거세시기 (개월)", g("castrationAge", 0), { int: true }),
        radio("castrationMethod", "거세방법", c.castrationMethod, g("castrationMethod", "무혈")),
        select("floorCondition", "축사바닥", c.floorCondition, g("floorCondition", "양호")),
        num("dewormingCount", "정기구충 (회/년)", g("dewormingCount", 0), { int: true })])}
      <p class="text-sm font-semibold pt-2">🔍 추가 정밀 진단 항목</p>
      ${grid(2, [select("waterQuality", "💧 음수(물) 관리 실태", c.waterQuality, g("waterQuality", c.waterQuality[1])),
        select("manureScore", "💩 소 분변 상태", c.manureScore, g("manureScore", c.manureScore[1]))])}
      ${radio("troughCleaning", "🍽️ 사조(밥통) 매일 청소 및 잔량 폐기 여부", c.yesNo2, g("troughCleaning", "예"))}`)}
    ${section("4. 사료급여", `
      ${grid(2, [text("feedOrder", "급여순서", g("feedOrder", ""), 'placeholder="예: 조사료 → 배합사료"'),
        num("feedFrequency", "급여횟수 (회/일)", g("feedFrequency", 2), { int: true })])}
      ${select("forageQuality", "🌾 조사료의 품질(질) 평가", c.forageQuality, g("forageQuality", c.forageQuality[1]))}
      <p class="text-sm font-medium">성장단계별 품목과 급여수준(낮음/적정/높음)을 입력하세요</p>
      ${feedTable(e.feed_matrix)}`)}
    ${section("5. 사육두수 현황", grid(2, [
      num("countCow", "번식우(암소) (두)", g("countCow", 0), { int: true }), num("countSteer", "거세우 (두)", g("countSteer", 0), { int: true }),
      num("countGrowing", "육성우 (두)", g("countGrowing", 0), { int: true }), num("countCalf", "송아지 (두)", g("countCalf", 0), { int: true }),
      num("countOptimal", "적정 사육두수 (두)", g("countOptimal", 0), { int: true })]))}
    ${section("6. 번식관리 / 7. 질병예방 / 8. 특이사항", `
      ${radio("aiMethod", "인공수정 방법", c.aiMethod, g("aiMethod", c.aiMethod[0]))}
      ${grid(2, [num("calvingInterval", "평균 분만간격 (개월)", g("calvingInterval", 0)), num("mortalityRate", "최근 1년 폐사율 (%)", g("mortalityRate", 0))])}
      <p class="text-sm font-semibold pt-2">🍼 송아지 포유 관리</p>
      ${grid(2, [num("weaningAge", "송아지 이유 월령", g("weaningAge", 0), { step: 0.5 }),
        radio("artificialRearing", "인공포유 여부", c.yesNo2, g("artificialRearing", "아니오"))])}
      <label class="block text-sm font-medium">현장 점검 소견 및 컨설팅사항
        <textarea name="consultingNotes" rows="4" maxlength="5000" class="mt-1 w-full rounded-lg border border-line px-2 py-1.5 font-normal">${esc(g("consultingNotes", ""))}</textarea></label>`)}
    <p id="survey-error" class="hidden text-sm text-neg" role="alert"></p>
    <button class="w-full rounded-lg bg-brand text-white py-3 font-semibold disabled:opacity-40">${isEdit ? "💾 방문조사 수정사항 저장" : "💾 종합 현장 조사표 DB 저장"}</button>
  </form>`;
}

function collect(form) {
  const data = {};
  for (const el of form.elements) {
    if (!el.name || el.dataset.feedCol) continue;
    if (el.type === "radio") { if (el.checked) data[el.name] = el.value; continue; }
    if (el.type === "number") {   // 빈 칸은 기존 양식처럼 0. 정수 칸에 소수를 넣으면 서버가 어느 칸인지 알려 준다
      data[el.name] = el.value === "" ? 0 : Number(el.value);
      continue;
    }
    data[el.name] = el.value;
  }
  data.feed_matrix = {};
  form.querySelectorAll("[data-feed-col]").forEach((el) => {
    (data.feed_matrix[el.dataset.feedCol] ||= {})[el.dataset.feedRow] = el.value;
  });
  return data;
}

function errorText(ex) {
  // 422 는 항목별 오류 목록이 온다 — 어느 칸인지 라벨로 알려 준다
  if (Array.isArray(ex.body?.detail)) {
    return ex.body.detail.map((d) => {
      const key = d.loc?.[d.loc.length - 1];
      const label = root.querySelector(`[name="${key}"]`)?.closest("label")?.firstChild?.textContent?.trim() || key;
      return `${label}: 값을 확인해주세요`;
    }).join(" · ");
  }
  return ex.message;
}

// ---------------------------------------------------------------- 화면
async function renderForm() {
  const farm = state.farms.find((f) => f.id === state.farmId);
  const box = root.querySelector("#survey-body");
  let existing = {}, isEdit = false, head = "";

  if (ui.mode === "edit") {
    const visits = await api(`/api/farms/${farm.id}/visits`);
    if (!visits.length) {
      box.innerHTML = `<div class="rounded-lg bg-[#EEF4FB] p-3 text-sm">'${esc(farm.label)}' 농가의 방문 기록이 없습니다. '신규 방문조사 작성'으로 입력해주세요.</div>`;
      return;
    }
    if (!visits.some((v) => v.id === ui.visitId)) ui.visitId = visits[visits.length - 1].id;
    const v = await api(`/api/visits/${ui.visitId}`);
    existing = v.survey;
    isEdit = true;
    head = `<label class="block text-sm font-medium mb-3">수정할 방문 회차 선택
        <select id="visit-select" class="mt-1 w-full rounded-lg border border-line bg-white px-2 py-2 text-sm font-normal">
          ${visits.map((x) => `<option value="${x.id}" ${x.id === ui.visitId ? "selected" : ""}>${x.visit_number}차 (${esc(x.visit_date)})${x.has_survey ? "" : " — 조사표 비어 있음"}</option>`).join("")}</select></label>
      ${Object.keys(existing).length ? "" : `<p class="text-xs text-muted mb-3">이 방문 기록은 상세 조사표가 비어 있어 빈 양식으로 시작합니다 — 입력 후 저장하면 이 방문에 채워집니다.</p>`}`;
  } else {
    head = `<div class="rounded-lg bg-[#EEF4FB] p-3 text-sm mb-3">📌 <b>${esc(farm.farm_name)}</b> 농가의 새 방문(다음 회차)으로 저장됩니다. 다른 농가라면 왼쪽 '현재 컨설팅 농가 선택'에서 먼저 바꿔주세요.</div>`;
  }

  box.innerHTML = head + formHtml(existing, isEdit);
  const form = box.querySelector("#survey-form");
  box.querySelector("#visit-select")?.addEventListener("change", (ev) => { ui.visitId = Number(ev.target.value); renderForm(); });
  form.elements.region.addEventListener("change", (ev) => {
    box.querySelector("#weather").innerHTML = weatherHtml(existing, ev.target.value);
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const err = box.querySelector("#survey-error");
    err.classList.add("hidden");
    if (!form.elements.visitDate.value) {
      err.textContent = "조사일자를 입력해주세요.";
      err.classList.remove("hidden");
      return;
    }
    const btn = form.querySelector("button");
    btn.disabled = true;
    btn.textContent = "저장 중…";
    try {
      const body = JSON.stringify(collect(form));
      if (isEdit) {
        const res = await api(`/api/visits/${ui.visitId}`, { method: "PUT", body });
        notifySaved(`방문 기록(ID ${res.visit_id})이 수정되어 저장되었습니다!`, res.backup);
      } else {
        const res = await api(`/api/farms/${farm.id}/visits`, { method: "POST", body });
        notifySaved(`${res.visit_number}차 현장 방문 조사표가 DB에 성공적으로 통합 저장되었습니다!`, res.backup);
        // 같은 양식을 또 눌러 방문이 두 번 생기지 않게, 방금 만든 방문의 수정 화면으로 넘어간다
        ui.mode = "edit";
        ui.visitId = res.visit_id;
        renderModes();
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
      await renderForm();
    } catch (ex) {
      err.textContent = `⚠️ 저장하지 못했습니다 — ${errorText(ex)}`;
      err.classList.remove("hidden");
      btn.disabled = false;
      btn.textContent = isEdit ? "💾 방문조사 수정사항 저장" : "💾 종합 현장 조사표 DB 저장";
    }
  });
}

function renderModes() {
  root.querySelectorAll("[name=survey-mode]").forEach((r) => { r.checked = r.value === ui.mode; });
}

export async function renderSurvey(el) {
  root = el;
  const farm = state.farms.find((f) => f.id === state.farmId);
  const title = `<h1 class="text-2xl font-bold mb-4">2단계 · 현장 방문 조사표 입력</h1>`;
  if (!farm) {
    el.innerHTML = title + `<div class="rounded-lg bg-[#FBF3E6] p-3 text-sm">먼저 좌측 사이드바에서 농가를 선택해주세요.</div>`;
    return;
  }
  if (ui.farmId !== farm.id) { ui.farmId = farm.id; ui.visitId = null; }
  opts ||= await api("/api/survey/options");
  el.innerHTML = `${title}
    <fieldset class="flex flex-wrap gap-4 mb-4 text-sm" aria-label="작성 모드">
      <label class="flex items-center gap-1"><input type="radio" name="survey-mode" value="new"> 🆕 신규 방문조사 작성</label>
      <label class="flex items-center gap-1"><input type="radio" name="survey-mode" value="edit"> ✏️ 기존 방문조사 수정</label>
    </fieldset>
    <div id="survey-body"><p class="text-muted text-sm">불러오는 중…</p></div>`;
  renderModes();
  el.querySelectorAll("[name=survey-mode]").forEach((r) => r.addEventListener("change", () => { ui.mode = r.value; renderForm(); }));
  await renderForm();
}
