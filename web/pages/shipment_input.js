// 출하성적 입력 — 축평원 이력번호 조회 → 검토·선별 → 저장, 엑셀 미리보기 → 저장.
// 조회·미리보기는 DB 에 쓰지 않는다. '저장' 버튼만 운영 DB 에 쓴다 (저장 규칙은 서버가 기존 앱과 같게 지킨다).
import { api, esc, flash, num, table } from "../api.js";

const STATUS = {
  new: ["신규", "bg-brand-tint text-pos"],
  update: ["갱신", "bg-panel text-muted"],
  move: ["다른 농가에서 옮겨짐", "bg-[#FBEDE8] text-neg"],
};
const chip = (s) => `<span class="shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS[s][1]}">${STATUS[s][0]}</span>`;
const f1 = (v) => (v === null || v === undefined ? "-" : Number(v).toFixed(1).replace(/\.0$/, ""));
const btn = "rounded-xl px-4 py-3 min-h-[48px] text-sm font-semibold disabled:opacity-50";
const warn = (t) => `<p class="text-sm text-neg mt-2">⚠️ ${t}</p>`;
const note = (t) => `<p class="text-xs text-muted mt-1">${t}</p>`;

// 농가가 바뀌면 처음부터. 같은 농가에서 화면을 다시 그려도 입력하던 것은 남는다.
const st = { farmId: null, tab: "api", text: "", lookup: null, off: new Set(), confirm: false, file: null, preview: null, mode: "match", busy: false };
function reset(farmId) {
  Object.assign(st, { farmId, text: "", lookup: null, off: new Set(), confirm: false, file: null, preview: null, mode: "match", busy: false });
}

function ownershipLine(o) {
  const moved = o.moved_from.map((m) => `${esc(m.farm)} ${num(m.count)}두`).join(", ");
  return `<div class="flex flex-wrap gap-2 text-xs mt-2">
    <span class="rounded-full bg-brand-tint text-pos px-2 py-0.5">신규 ${num(o.new)}두</span>
    <span class="rounded-full bg-panel text-muted px-2 py-0.5">갱신 ${num(o.update)}두</span>
    ${o.move ? `<span class="rounded-full bg-[#FBEDE8] text-neg px-2 py-0.5">옮겨짐 ${num(o.move)}두 (${moved})</span>` : ""}</div>`;
}

function savedFlash(farmName, saved, backup) {
  const tone = backup.ok === false ? "text-neg" : "text-muted";
  const icon = backup.ok === true ? "☁️" : backup.ok === false ? "⚠️" : "ℹ️";
  flash(`<div class="rounded-xl border border-brand-line bg-brand-tint p-3 mb-3 text-sm">
    ✅ <b>${esc(farmName)}</b> 농가에 출하성적 ${num(saved)}두를 저장했습니다.
    <div class="text-xs ${tone} mt-1">${icon} ${esc(backup.message)}</div></div>`);
}

// ---------------------------------------------------------------- 축평원 조회
function apiTab(farm) {
  const L = st.lookup;
  let result = "";
  if (L) {
    const chosen = L.records.filter((_, i) => !st.off.has(i));
    const moving = chosen.filter((r) => r.status === "move").length;
    result = `
      <div class="mt-4 border-t border-line pt-3">
        <div class="font-semibold">🔍 조회 결과 검토 <span class="text-sm font-normal text-muted">가져옴 ${num(L.records.length)}두${L.failed.length ? ` · 실패 ${num(L.failed.length)}두` : ""}${L.duplicates ? ` · 겹친 번호 ${num(L.duplicates)}개 뺌` : ""}</span></div>
        ${L.failed.length ? `<details class="mt-2 text-sm"><summary class="cursor-pointer text-neg">가져오지 못한 ${num(L.failed.length)}두 보기</summary>
          <ul class="mt-1 space-y-1">${L.failed.map((f) => `<li class="kpi-value text-xs">${esc(f.animal_no)} — <span class="text-muted">${esc(f.reason)}</span></li>`).join("")}</ul></details>` : ""}
        ${L.records.length ? `${ownershipLine(L.ownership)}
        ${note("저장하지 않을 개체는 체크를 끄세요.")}
        <ul class="divide-y divide-line mt-1">${L.records.map((r, i) => `
          <li><label class="flex items-start gap-3 py-2.5">
            <input type="checkbox" data-i="${i}" ${st.off.has(i) ? "" : "checked"} class="pick mt-0.5 h-5 w-5 shrink-0 accent-[#2F6B54]">
            <div class="flex-1 min-w-0">
              <div class="flex items-center justify-between gap-2"><span class="kpi-value font-semibold">${esc(r.animal_no)}</span>${chip(r.status)}</div>
              <div class="text-xs text-muted mt-0.5">${esc(r.gender || "성별 없음(거세로 저장)")} · ${esc(r.slaughter_date || "도축일 없음")} · 도체중 ${f1(r.carcass_weight)}kg · ${esc(r.grade_quality || "-")}/${esc(r.grade_yield || "-")} · BMS ${f1(r.bms)} · ${f1(r.month_age)}개월</div>
            </div></label></li>`).join("")}</ul>
        ${moving ? `<label class="flex items-start gap-2 mt-3 text-sm text-neg"><input id="api-confirm" type="checkbox" ${st.confirm ? "checked" : ""} class="mt-0.5 h-5 w-5 shrink-0">
          <span>다른 농가에 등록된 ${num(moving)}두를 <b>${esc(farm.name)}</b> 농가로 옮기는 것을 확인했습니다.</span></label>` : ""}
        <div class="grid grid-cols-2 gap-2 mt-3">
          <button id="api-clear" class="${btn} border border-line bg-white">🔄 목록 비우기</button>
          <button id="api-save" class="${btn} bg-brand text-white" ${chosen.length ? "" : "disabled"}>💾 ${num(chosen.length)}두 저장</button>
        </div>` : '<p class="text-sm text-muted mt-2">가져온 성적이 없습니다. 번호와 아래 실패 이유를 확인해주세요.</p>'}
      </div>`;
  }
  return `
    <label class="block text-sm text-muted mb-1" for="api-text">이력번호 (한 줄에 하나, 쉼표로 나눠도 됩니다 · 한 번에 200두까지)</label>
    <textarea id="api-text" rows="4" class="w-full rounded-xl border border-line bg-white px-3 py-2 kpi-value" placeholder="002154889011&#10;002154889012" autocomplete="off">${esc(st.text)}</textarea>
    <button id="api-lookup" class="${btn} w-full mt-2 bg-brand text-white" ${st.busy ? "disabled" : ""}>${st.busy ? "축평원에 묻는 중… (많으면 1분 정도)" : "⚡ 축평원 성적 조회 (저장 안 함)"}</button>
    ${result}`;
}

function bindApi(box, farm, redraw, onSaved) {
  const text = box.querySelector("#api-text");
  text.addEventListener("input", () => { st.text = text.value; });
  box.querySelector("#api-lookup").addEventListener("click", async () => {
    st.busy = true; flash(""); redraw();
    try {
      const res = await api(`/api/farms/${farm.id}/shipments/lookup`, { method: "POST", body: JSON.stringify({ text: st.text }) });
      if (st.farmId !== farm.id) return;         // 기다리는 사이 다른 농가로 바뀌었으면 버린다
      st.lookup = res;
      st.off = new Set();
      st.confirm = false;
    } catch (e) {
      st.lookup = null;
      flash(`<div class="rounded-xl border border-neg/40 bg-white p-3 mb-3 text-sm text-neg">⚠️ ${esc(e.message)}</div>`);
    } finally { st.busy = false; redraw(); }
  });
  if (!st.lookup) return;
  box.querySelectorAll(".pick").forEach((c) => c.addEventListener("change", () => {
    const i = Number(c.dataset.i);
    if (c.checked) st.off.delete(i); else st.off.add(i);
    redraw();
  }));
  box.querySelector("#api-confirm")?.addEventListener("change", (e) => { st.confirm = e.target.checked; });
  box.querySelector("#api-clear")?.addEventListener("click", () => { st.lookup = null; st.off = new Set(); redraw(); });
  box.querySelector("#api-save")?.addEventListener("click", async (ev) => {
    const records = st.lookup.records.filter((_, i) => !st.off.has(i)).map(({ status, ...r }) => r);
    const confirm = box.querySelector("#api-confirm");
    if (confirm && !confirm.checked) { flash(warn("다른 농가에서 옮겨지는 개체가 있습니다. 확인란에 체크하거나 그 개체의 체크를 끄세요.")); return; }
    ev.target.disabled = true; ev.target.textContent = "저장 중…";
    try {
      const r = await api(`/api/farms/${farm.id}/shipments/save-api`, { method: "POST", body: JSON.stringify({ records, confirm: !!confirm?.checked }) });
      reset(farm.id);
      savedFlash(r.farm, r.saved, r.backup);
      window.scrollTo(0, 0);
      await onSaved();
    } catch (e) {
      flash(`<div class="rounded-xl border border-neg/40 bg-white p-3 mb-3 text-sm text-neg">⚠️ ${esc(e.message)}</div>`);
      ev.target.disabled = false; ev.target.textContent = `💾 ${num(records.length)}두 저장`;
    }
  });
}

// ---------------------------------------------------------------- 엑셀
function excelTab(farm) {
  const P = st.preview;
  let body = "";
  if (st.busy) body = '<p class="text-sm text-muted mt-3">파일을 읽는 중…</p>';
  else if (P) {
    const n = P.names;
    const fileTotal = n ? n.match + n.blank + n.others.reduce((s, o) => s + o.count, 0) : P.selected_rows;
    const othersRows = n ? n.others.reduce((s, o) => s + o.count, 0) : 0;
    const seg = (val, label) => `<button data-mode="${val}" class="mode px-3 py-2 min-h-[44px] flex-1 ${val === "all" ? "border-l border-line" : ""} ${P.mode === val ? "bg-brand text-white font-semibold" : "bg-white text-muted"}">${label}</button>`;
    const cols = ["이력번호", ...(n ? ["이름"] : []), "성별", "도축일자", "도체중", "육질", "육량", "BMS", "등지방", "단면적", "월령", "저장하면"];
    const rows = P.sample.map((r) => [r.animal_no, ...(n ? [r.name] : []), r.gender, r.slaughter_date, r.carcass_weight, r.grade_quality, r.grade_yield, r.bms, r.backfat, r.ribeye, r.month_age, STATUS[r.status][0]]);
    body = `
      <div class="mt-4 border-t border-line pt-3 text-sm">
        <div class="font-semibold">📄 미리보기 <span class="font-normal text-muted">(아직 저장 안 됨)</span></div>
        <p class="mt-1">시트 <b>${esc(P.sheet)}</b> · 전체 ${num(P.total_rows)}행${P.invalid ? ` · 이력번호가 없거나 잘못된 ${num(P.invalid)}행 제외` : ""}</p>
        ${P.missing_cols.length ? warn(`파일에 없는 칸: ${P.missing_cols.map(esc).join(", ")} → 빈 값으로 저장됩니다.`) : ""}
        ${n ? `
          <p class="mt-2">파일의 <b>${esc(n.col)}</b> 칸: ${esc(farm.name)} ${num(n.match)}행${n.others.length ? ` · 다른 이름 ${num(n.others.length)}명 ${num(othersRows)}행` : ""}${n.blank ? ` · 빈 칸 ${num(n.blank)}행` : ""}</p>
          ${n.others.length ? `<details class="mt-1"><summary class="cursor-pointer text-xs text-muted">다른 이름 보기</summary><p class="text-xs text-muted mt-1">${n.others.map((o) => `${esc(o.name)} ${num(o.count)}`).join(", ")}</p></details>` : ""}
          <div class="flex rounded-xl border border-line overflow-hidden text-sm mt-2" role="group" aria-label="저장할 행">${seg("match", `이 농가 이름 행만 (${num(n.match)})`)}${seg("all", `파일 전체 (${num(fileTotal)})`)}</div>
          ${P.mode === "match" && !n.match ? warn(`이 파일에 '${esc(farm.name)}' 이름의 행이 없습니다. 다른 농가 파일이 아닌지 확인해주세요.`) : ""}
          ${P.mode === "all" && n.others.length ? warn(`다른 이름의 ${num(othersRows)}행도 모두 <b>${esc(farm.name)}</b> 농가 성적으로 저장됩니다.`) : ""}`
        : warn(`파일에 농가 이름 칸이 없어 대조할 수 없습니다. 모든 행이 <b>${esc(farm.name)}</b> 농가로 저장됩니다.`)}
        ${P.duplicates ? note(`같은 이력번호가 ${num(P.duplicates)}번 더 나옵니다 → 아래쪽 행 값으로 저장됩니다.`) : ""}
        ${P.date_missing ? note(`도축일자가 빈 ${num(P.date_missing)}행은 기존 앱 규칙대로 2025-01-01 로 저장됩니다.`) : ""}
        ${P.unique ? ownershipLine(P.ownership) : ""}
        ${P.sample.length ? `<div class="mt-3">${table({ columns: cols, rows }, { align: { 이력번호: "left", 이름: "left", 성별: "center", 도축일자: "center", 육질: "center", 육량: "center", 저장하면: "left" }, fmt: { 도체중: f1, BMS: f1, 등지방: f1, 단면적: f1, 월령: f1 } })}</div>
          ${P.selected_rows > P.sample.length ? note(`처음 ${num(P.sample.length)}행만 보여 줍니다 (저장할 행 ${num(P.selected_rows)}행).`) : ""}` : ""}
        ${P.needs_confirm ? `<label class="flex items-start gap-2 mt-3 text-sm text-neg"><input id="xl-confirm" type="checkbox" class="mt-0.5 h-5 w-5 shrink-0">
          <span>위 내용을 확인했고 <b>${esc(farm.name)}</b> 농가로 저장합니다.</span></label>` : ""}
        ${note("엑셀 저장은 축평원에서 받은 kg당 단가·금액을 지우지 않습니다.")}
        <button id="xl-save" class="${btn} w-full mt-3 bg-brand text-white" ${P.unique ? "" : "disabled"}>💾 ${esc(farm.name)} 농가로 ${num(P.unique)}두 저장</button>
      </div>`;
  }
  return `
    <label class="block text-sm text-muted mb-1" for="xl-file">농가출하데이터.xlsx 같은 엑셀 파일 (.xlsx, 10MB까지)</label>
    <input id="xl-file" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      class="block w-full text-sm file:mr-3 file:rounded-xl file:border-0 file:bg-brand-tint file:px-4 file:py-3 file:font-semibold file:text-brand">
    ${st.file ? note(`선택한 파일: ${esc(st.file.name)}`) : note("파일을 고르면 먼저 미리보기를 보여 줍니다. 저장은 그다음입니다.")}
    ${body}`;
}

function excelForm(extra = {}) {
  const fd = new FormData();
  fd.append("file", st.file);
  fd.append("mode", st.mode);
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  return fd;
}

function bindExcel(box, farm, redraw, onSaved) {
  const preview = async () => {
    st.busy = true; redraw();
    try {
      const res = await api(`/api/farms/${farm.id}/shipments/excel/preview`, { method: "POST", body: excelForm() });
      if (st.farmId !== farm.id) return;
      st.preview = res;
      st.mode = res.mode;
    } catch (e) {
      st.preview = null;
      flash(`<div class="rounded-xl border border-neg/40 bg-white p-3 mb-3 text-sm text-neg">⚠️ ${esc(e.message)}</div>`);
    } finally { st.busy = false; redraw(); }
  };
  box.querySelector("#xl-file").addEventListener("change", (e) => {
    st.file = e.target.files[0] || null;
    st.mode = "match";
    st.preview = null;
    flash("");
    if (st.file) preview(); else redraw();
  });
  box.querySelectorAll(".mode").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.mode !== st.mode) { st.mode = b.dataset.mode; preview(); }
  }));
  box.querySelector("#xl-save")?.addEventListener("click", async (ev) => {
    const confirm = box.querySelector("#xl-confirm");
    if (confirm && !confirm.checked) { flash(warn("미리보기 내용을 확인하고 확인란에 체크해주세요.")); return; }
    ev.target.disabled = true; ev.target.textContent = "저장 중… (행이 많으면 시간이 걸립니다)";
    try {
      const r = await api(`/api/farms/${farm.id}/shipments/excel/save`, { method: "POST", body: excelForm({ confirm: !!confirm?.checked }) });
      reset(farm.id);
      st.tab = "excel";
      savedFlash(r.farm, r.saved, r.backup);
      window.scrollTo(0, 0);
      await onSaved();
    } catch (e) {
      flash(`<div class="rounded-xl border border-neg/40 bg-white p-3 mb-3 text-sm text-neg">⚠️ ${esc(e.message)}</div>`);
      ev.target.disabled = false; ev.target.textContent = `💾 ${farm.name} 농가로 ${num(st.preview.unique)}두 저장`;
    }
  });
}

// ---------------------------------------------------------------- 묶음
export function renderInput(box, { farm, onSaved }) {
  if (st.farmId !== farm.id) reset(farm.id);
  // 그사이 농가가 바뀌었으면 그리지 않고, 화면이 새로 그려졌으면 새 칸에 그린다
  const redraw = () => {
    if (st.farmId !== farm.id) return;
    const b = box.isConnected ? box : document.getElementById("sh-input-box");
    if (b) renderInput(b, { farm, onSaved });
  };
  const tabBtn = (id, label) => `<button data-tab="${id}" class="itab flex-1 px-3 py-2 min-h-[44px] ${id === "excel" ? "border-l border-line" : ""} ${st.tab === id ? "bg-brand text-white font-semibold" : "bg-white text-muted"}" aria-pressed="${st.tab === id}">${label}</button>`;
  box.innerHTML = `
    <p class="text-sm mb-3">저장하는 성적은 <b>${esc(farm.name)}</b> 농가로 들어갑니다. 다른 농가라면 위쪽 농가 선택을 먼저 바꿔주세요.</p>
    <div class="flex rounded-xl border border-line overflow-hidden text-sm mb-3" role="group" aria-label="입력 방식">${tabBtn("api", "⚡ 축평원 조회")}${tabBtn("excel", "📁 엑셀 업로드")}</div>
    <div id="itab-body">${st.tab === "api" ? apiTab(farm) : excelTab(farm)}</div>`;
  box.querySelectorAll(".itab").forEach((b) => b.addEventListener("click", () => { st.tab = b.dataset.tab; redraw(); }));
  if (st.tab === "api") bindApi(box, farm, redraw, onSaved);
  else bindExcel(box, farm, redraw, onSaved);
}
