// 2단계 · 현장방문조사 — 방문 목록, 조사표 새로 쓰기·고치기.
// 양식(항목·선택지·기본값)은 서버(/api/surveys/form)가 기존 앱과 같게 준다. 여기서는 그리고 값을 모으기만 한다.
// 선택 항목은 '선택 안 함(null)'으로 둘 수 있고, 그대로 저장하면 서버가 원래 값을 지킨다.
import { api, card, esc, flash, num } from "../api.js";

const st = { farmId: null, view: "list", visitId: null, values: null, meta: null, dirty: false, leaving: false, saving: false };
let FORM = null;                                    // 양식은 한 번만 받는다

const btn = "rounded-xl px-4 py-3 min-h-[48px] text-sm font-semibold disabled:opacity-50";
const inputCls = "w-full rounded-xl border border-line bg-white px-3 py-2";
const errBox = (m) => `<div class="rounded-xl border border-neg/40 bg-white p-3 mb-3 text-sm text-neg">⚠️ ${esc(m)}</div>`;

function warnLeave(e) { if (st.dirty) { e.preventDefault(); e.returnValue = ""; } }
function setDirty(v) {
  st.dirty = v;
  st.leaving = false;
  if (v) window.addEventListener("beforeunload", warnLeave); else window.removeEventListener("beforeunload", warnLeave);
  const badge = document.getElementById("sv-dirty");
  if (badge) badge.hidden = !v;
}

// ---------------------------------------------------------------- 칸 그리기
function seg(key, options, value, extraAttr = "") {
  return `<div class="flex flex-wrap gap-2" role="group">${options.map((o) => `
    <button type="button" data-seg="${esc(key)}" data-val="${esc(o)}" ${extraAttr}
      class="seg px-3 py-2 min-h-[44px] rounded-xl border text-sm ${value === o ? "bg-brand text-white border-brand font-semibold" : "bg-white border-line text-muted"}"
      aria-pressed="${value === o}">${esc(o)}</button>`).join("")}</div>`;
}

function field(f, v) {
  const id = `sv-${f.key}`;
  const label = `<label class="block text-sm text-muted mb-1" for="${id}">${esc(f.label)}</label>`;
  const hint = f.hint ? `<p class="text-xs text-muted mt-1">${esc(f.hint)}</p>` : "";
  switch (f.kind) {
    case "text":
      return `<div>${label}<input id="${id}" data-key="${f.key}" class="${inputCls}" value="${esc(v)}" placeholder="${esc(f.placeholder || "")}" maxlength="100" autocomplete="off">${hint}</div>`;
    case "date":
      return `<div>${label}<input id="${id}" data-key="${f.key}" type="date" class="${inputCls}" value="${esc(v)}" required></div>`;
    case "textarea":
      return `<div>${label}<textarea id="${id}" data-key="${f.key}" rows="5" class="${inputCls}" maxlength="5000">${esc(v)}</textarea></div>`;
    case "int":
    case "float":
      return `<div>${label}<input id="${id}" data-key="${f.key}" data-kind="${f.kind}" type="number" inputmode="${f.kind === "int" ? "numeric" : "decimal"}"
        step="${f.kind === "int" ? 1 : f.step || "any"}" class="${inputCls} kpi-value" value="${v ?? ""}" required></div>`;
    case "select":
      return `<div>${label}<select id="${id}" data-key="${f.key}" class="${inputCls}">
        <option value="" ${v === null ? "selected" : ""}>(선택 안 함)</option>
        ${f.options.map((o) => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>${hint}</div>`;
    case "radio":
      return `<div><span class="block text-sm text-muted mb-1">${esc(f.label)}${v === null ? ' <span class="text-xs">(선택 안 함)</span>' : ""}</span>${seg(f.key, f.options, v)}</div>`;
    case "feed":
      return feedCards(v);
    default:
      return "";
  }
}

// 사료급여 표(5단계 × 배합사료·조사료·첨가제)는 휴대폰에서 넓어서 단계마다 카드로 나눈다
function feedCards(m) {
  const items = ["배합사료", "조사료", "첨가제"];
  return `<div><span class="block text-sm text-muted mb-2">단계별 사료 품목 · 급여수준</span><div class="space-y-3">${FORM.feed.stages.map((stage) => `
    <div class="rounded-xl border border-line p-3">
      <div class="font-semibold text-sm mb-2">${esc(stage)}</div>
      <div class="space-y-3">${items.map((it) => `
        <div>
          <span class="block text-xs font-semibold text-muted mb-1">${it}</span>
          <input data-feed="${esc(stage)}" data-row="${it} 품목" class="${inputCls} text-sm" value="${esc(m[stage][`${it} 품목`])}" placeholder="${it} 품목" aria-label="${esc(stage)} ${it} 품목" maxlength="100">
          <div class="mt-1.5">${seg(`feed:${stage}:${it} 급여수준`, FORM.feed.levels, m[stage][`${it} 급여수준`] || null)}</div>
        </div>`).join("")}</div>
    </div>`).join("")}</div>
    <p class="text-xs text-muted mt-1">급여수준은 누른 것을 한 번 더 누르면 지워집니다.</p></div>`;
}

// ---------------------------------------------------------------- 목록
function listView(d) {
  const next = d.visits.length ? Math.max(...d.visits.map((v) => v.visit_number)) + 1 : 1;
  return `
    <div class="rounded-2xl bg-brand-tint border border-brand-line p-3 text-sm">📌 <b>${esc(d.farm.name)}</b> <span class="text-muted">(조합원번호 ${esc(d.farm.code || "미등록")}, ${esc(d.farm.region || "지역 미입력")})</span></div>
    <button id="sv-new" class="${btn} w-full mt-3 bg-brand text-white">＋ 새 방문조사 작성 (${num(next)}차)</button>
    <details class="mt-3 rounded-2xl bg-white border border-line p-4">
      <summary class="cursor-pointer text-sm font-semibold">🖨️ 종이 조사표로 현장에서 적고 나중에 입력하기</summary>
      <p class="text-xs text-muted mt-2">A4 로 인쇄해 손으로 적은 뒤, 위 '새 방문조사 작성'에 같은 순서로 옮겨 입력하세요. ${esc(d.farm.name)} 농가의 이름·번호·지역은 미리 적혀 나옵니다.</p>
      <div class="grid grid-cols-2 gap-2 mt-3">
        <a class="${btn} text-center border border-line bg-white" href="/api/surveys/sheet?farm_id=${d.farm.id}&inline=1" target="_blank" rel="noopener">인쇄용 열기 (${esc(d.farm.name)})</a>
        <a class="${btn} text-center border border-line bg-white" href="/api/surveys/sheet?farm_id=${d.farm.id}">파일로 내려받기</a>
        <a class="${btn} text-center border border-line bg-white" href="/api/surveys/sheet?inline=1" target="_blank" rel="noopener">빈 양식 열기</a>
        <a class="${btn} text-center border border-line bg-white" href="/api/surveys/sheet">빈 양식 내려받기</a>
      </div>
    </details>
    <h3 class="text-base font-bold mt-5 mb-2">방문 기록 <span class="text-sm font-normal text-muted">${num(d.visits.length)}회</span></h3>
    ${d.visits.length ? `<div class="space-y-2">${d.visits.slice().reverse().map((v) => `
      <button data-visit="${v.id}" class="open w-full text-left rounded-2xl bg-white border border-line p-4 active:bg-panel">
        <div class="flex items-center justify-between gap-2"><span class="font-semibold">${num(v.visit_number)}차 방문</span><span class="text-sm text-muted kpi-value">${esc(v.visit_date)}</span></div>
        <div class="text-sm text-muted mt-1">${esc(v.investigator || "조사자 미입력")}${v.has_survey ? "" : " · 조사표 비어 있음"} · 눌러서 보기·고치기</div>
      </button>`).join("")}</div>`
      : card('<p class="text-sm text-muted">아직 방문 기록이 없습니다. 위 버튼으로 첫 방문조사를 작성하세요.</p>')}`;
}

// ---------------------------------------------------------------- 조사표
function formView(farm) {
  const title = st.meta ? `${st.meta.visit_number}차 방문조사 고치기` : "새 방문조사 작성";
  return `
    <div class="flex items-center justify-between gap-2">
      <button id="sv-back" class="${btn} border border-line bg-white">← 목록</button>
      <span id="sv-dirty" class="text-xs font-semibold text-neg" ${st.dirty ? "" : "hidden"}>저장 안 한 변경 있음</span>
    </div>
    <h2 class="text-lg font-bold mt-3">${esc(title)}</h2>
    <p class="text-sm text-muted">${esc(farm.name)} 농가${st.meta ? "" : " · 저장하면 다음 회차로 들어갑니다"}</p>
    ${st.extra ? `<p class="text-xs text-muted mt-1">엑셀에서 옮긴 추가 항목은 이 화면에 없지만, 저장해도 그대로 남습니다.</p>` : ""}
    <form id="sv-form" class="mt-3 space-y-3" novalidate>
      ${FORM.sections.map((s, i) => `
        <details class="rounded-2xl bg-white border border-line p-4" ${s.open ? "open" : ""}>
          <summary class="cursor-pointer font-semibold">${esc(s.title)}</summary>
          ${i === 1 ? '<p class="text-xs text-muted mt-2">지역을 바꾸면 그 지역의 2025년 날씨로 다시 채워집니다.</p>' : ""}
          <div class="mt-3 grid gap-4 ${s.fields.some((f) => f.kind === "feed" || f.kind === "textarea") ? "" : "sm:grid-cols-2"}">${s.fields.map((f) => field(f, st.values[f.key])).join("")}</div>
        </details>`).join("")}
      <div class="savebar z-10 rounded-2xl bg-white/95 border border-line p-3 shadow-lg">
        <button id="sv-save" type="submit" class="${btn} w-full bg-brand text-white">💾 ${st.meta ? "고친 내용 저장" : "방문조사 저장"}</button>
      </div>
    </form>`;
}

function readInputs(form) {
  form.querySelectorAll("[data-key]").forEach((el) => {
    const k = el.dataset.key;
    if (el.tagName === "SELECT") st.values[k] = el.value === "" ? null : el.value;
    else if (el.dataset.kind) st.values[k] = el.value === "" ? "" : Number(el.value);
    else st.values[k] = el.value;
  });
  form.querySelectorAll("[data-feed]").forEach((el) => { st.values.feed_matrix[el.dataset.feed][el.dataset.row] = el.value; });
}

function bindForm(el, farm, rerender) {
  const form = el.querySelector("#sv-form");
  form.addEventListener("input", () => setDirty(true));
  form.addEventListener("change", (e) => {
    setDirty(true);
    if (e.target.dataset.key === "region") {               // 지역을 바꾸면 그 지역 날씨로 채운다
      const wd = FORM.weather[e.target.value] || {};
      Object.entries(FORM.weather_fields).forEach(([k, wk]) => {
        const box = form.querySelector(`[data-key="${k}"]`);
        if (box) box.value = wd[wk] ?? 0;
      });
    }
  });
  // 버튼 묶음은 화면을 다시 그리지 않고 제자리에서 색만 바꾼다 (펼친 칸·스크롤이 그대로 남게)
  form.querySelectorAll(".seg").forEach((b) => b.addEventListener("click", () => {
    const key = b.dataset.seg, val = b.dataset.val;
    let now;
    if (key.startsWith("feed:")) {                          // 급여수준: 같은 것을 또 누르면 지운다
      const [, stage, row] = key.split(":");
      now = st.values.feed_matrix[stage][row] === val ? "" : val;
      st.values.feed_matrix[stage][row] = now;
    } else {
      now = val;
      st.values[key] = val;
    }
    b.parentElement.querySelectorAll(".seg").forEach((x) => {
      const on = x.dataset.val === now;
      x.setAttribute("aria-pressed", on);
      x.classList.toggle("bg-brand", on); x.classList.toggle("text-white", on); x.classList.toggle("border-brand", on); x.classList.toggle("font-semibold", on);
      x.classList.toggle("bg-white", !on); x.classList.toggle("border-line", !on); x.classList.toggle("text-muted", !on);
    });
    setDirty(true);
  }));
  el.querySelector("#sv-back").addEventListener("click", (e) => {
    if (st.dirty && !st.leaving) {                          // 확인 창은 쓰지 않고 버튼으로 한 번 더 묻는다
      st.leaving = true;
      e.target.textContent = "저장하지 않고 나가기";
      e.target.classList.add("text-neg", "border-neg");
      return;
    }
    setDirty(false);
    Object.assign(st, { view: "list", visitId: null, values: null, meta: null });
    rerender();
    window.scrollTo(0, 0);
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (st.saving) return;
    readInputs(form);
    const missing = FORM.sections.flatMap((s) => s.fields).find((f) => (f.kind === "int" || f.kind === "float" || f.kind === "date") && st.values[f.key] === "");
    if (missing) { flash(errBox(`'${missing.label}' 칸이 비어 있습니다. 값을 넣어주세요 (없으면 0).`)); window.scrollTo(0, 0); return; }
    const saveBtn = el.querySelector("#sv-save");
    st.saving = true; saveBtn.disabled = true; saveBtn.textContent = "저장 중…";
    try {
      const r = st.meta
        ? await api(`/api/farms/${farm.id}/visits/${st.meta.id}`, { method: "PUT", body: JSON.stringify({ values: st.values }) })
        : await api(`/api/farms/${farm.id}/visits`, { method: "POST", body: JSON.stringify({ values: st.values }) });
      setDirty(false);
      const b = r.backup;
      flash(`<div class="rounded-xl border border-brand-line bg-brand-tint p-3 mb-3 text-sm">✅ <b>${esc(r.farm)}</b> 농가 ${num(r.visit_number)}차 방문조사를 ${st.meta ? "고쳐" : ""} 저장했습니다.
        <div class="text-xs ${b.ok === false ? "text-neg" : "text-muted"} mt-1">${b.ok === true ? "☁️" : b.ok === false ? "⚠️" : "ℹ️"} ${esc(b.message)}</div></div>`);
      Object.assign(st, { view: "list", visitId: null, values: null, meta: null });
      await rerender(true);
      window.scrollTo(0, 0);
    } catch (ex) {
      flash(errBox(ex.message));
      window.scrollTo(0, 0);
    } finally {
      st.saving = false;
      if (saveBtn.isConnected) { saveBtn.disabled = false; saveBtn.textContent = `💾 ${st.meta ? "고친 내용 저장" : "방문조사 저장"}`; }
    }
  });
}

// ---------------------------------------------------------------- 묶음
export async function renderSurvey(el, { farm, farms, onPickFarm, onSaved = async () => {}, isCurrent = () => true }) {
  if (!farm) {
    el.innerHTML = card(`<h2 class="text-lg font-bold mb-1">2단계 · 현장방문조사</h2>
      <p class="text-sm text-muted mb-3">먼저 조사할 농가를 고르세요. (위쪽 목록에서 골라도 됩니다)</p>
      <div class="mb-4 rounded-xl border border-line bg-panel p-3">
        <p class="text-sm font-semibold mb-2">🖨️ 종이 조사표 (농가를 고르지 않고 빈 양식)</p>
        <div class="grid grid-cols-2 gap-2">
          <a class="rounded-xl border border-line bg-white px-3 py-2 min-h-[44px] flex items-center justify-center text-sm font-semibold" href="/api/surveys/sheet">빈 양식 내려받기</a>
          <a class="rounded-xl border border-line bg-white px-3 py-2 min-h-[44px] flex items-center justify-center text-sm font-semibold" href="/api/surveys/sheet?inline=1" target="_blank" rel="noopener">빈 양식 열어 인쇄</a>
        </div>
      </div>
      <div class="space-y-2">${farms.map((f) => `
        <button data-farm="${f.id}" class="pick w-full text-left rounded-xl border border-line bg-white p-3 active:bg-panel">
          <span class="font-semibold">${esc(f.name)}</span><span class="text-xs text-muted ml-2">${esc(f.region)} · 방문 ${num(f.visits)}회</span></button>`).join("")}</div>`);
    el.querySelectorAll(".pick").forEach((b) => b.addEventListener("click", () => onPickFarm(b.dataset.farm)));
    return;
  }
  if (st.farmId !== farm.id) { setDirty(false); Object.assign(st, { farmId: farm.id, view: "list", visitId: null, values: null, meta: null }); }

  const rerender = async (afterSave = false) => {
    if (afterSave) { await onSaved(); return; }               // 농가 목록(방문 수)까지 새로 받는다
    return renderSurvey(el, { farm, farms, onPickFarm, onSaved, isCurrent });
  };

  if (st.view === "form") {
    el.innerHTML = formView(farm);
    bindForm(el, farm, rerender);
    return;
  }

  el.innerHTML = '<p class="text-sm text-muted">불러오는 중…</p>';
  const [d, form] = await Promise.all([api(`/api/farms/${farm.id}/visits`), FORM ? Promise.resolve(FORM) : api("/api/surveys/form")]);
  FORM = form;
  if (!isCurrent()) return;
  el.innerHTML = listView(d);
  const open = async (values, meta, extra) => {
    Object.assign(st, { view: "form", values, meta, extra });
    setDirty(false);
    await rerender();
    window.scrollTo(0, 0);
  };
  el.querySelector("#sv-new").addEventListener("click", () => open(structuredClone(d.blank.values), null, false));
  el.querySelectorAll(".open").forEach((b) => b.addEventListener("click", async () => {
    try {
      const v = await api(`/api/farms/${farm.id}/visits/${b.dataset.visit}`);
      await open(v.values, v.visit, v.extra_keys.length > 0);
    } catch (ex) { flash(errBox(ex.message)); }
  }));
}
