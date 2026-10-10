// 메뉴 2: 1단계 · 출하성적 비교분석 — 기존 Streamlit 화면과 같은 구성
//   저장 대상 농가 배너 → [축평원 이력제 조회 | 엑셀 업로드] → 연도·성별 선택 → 인쇄 리포트
//   → 전국 1:1 비교분석표 → 최근 3년 추이 → 수익성 추정 → 개체별 성적표
import { api, apiDownload, esc, notifySaved, state } from "../api.js";

const COLORS = { farm: "#2A78D6", nat: "#A8A69D", grid: "#E2DFD6" };
const METRICS = [
  ["carcass_weight", "도체중 (kg)"],
  ["bms", "근내지방도 (BMS)"],
  ["ribeye", "단면적 (㎠)"],
  ["backfat", "등지방 (mm)"],
  ["plus1_rate", "1+ 이상 출현율 (%)"],
  ["c_rate", "C등급 출현율 (%)"],
  ["month_age", "출하월령"],
];
// 조회 결과 검토 표의 칸 (기존 data_editor 와 같은 순서)
const DRAFT_COLS = [
  ["animal_no", "이력번호", "text"],
  ["gender", "성별", "gender"],
  ["slaughter_date", "도축일자", "text"],
  ["carcass_weight", "도체중", "num"],
  ["grade_quality", "육질", "text"],
  ["grade_yield", "육량", "text"],
  ["bms", "BMS", "num"],
  ["backfat", "등지방", "num"],
  ["ribeye", "단면적", "num"],
  ["month_age", "월령", "num"],
  ["costAmt", "단가(원/kg)", "num"],
];
const RECORD_COLS = [
  ["animal_no", "이력번호"], ["gender", "성별"], ["slaughter_date", "도축일자"], ["carcass_weight", "도체중_kg"],
  ["grade_quality", "육질등급"], ["grade_yield", "육량등급"], ["bms", "BMS"], ["backfat", "등지방_mm"],
  ["ribeye", "단면적_㎠"], ["month_age", "출하월령"],
];
const LOOKUP_BATCH = 20;   // 서버가 한 번에 받는 두수

// 화면을 다시 그려도 남아 있어야 하는 것 (기존 앱의 session_state)
const ui = {
  farmId: null, tab: "api", year: null, gender: "", metric: "carcass_weight",
  lookupText: "", drafts: null, lookupMsg: null, excel: null,
};
const charts = {};
let root;

const f1 = (v) => (v === null || v === undefined ? "-" : Number(v).toFixed(1));
const won = (n) => n.toLocaleString("ko-KR");
const card = (inner, extra = "") => `<section class="rounded-xl bg-white border border-line p-4 ${extra}">${inner}</section>`;
const note = (tone, html) => {
  const cls = { info: "bg-[#EEF4FB]", warn: "bg-[#FBF3E6]", ok: "bg-brand-tint", err: "bg-white border border-neg/40 text-neg" }[tone];
  return `<div class="rounded-lg p-3 text-sm ${cls}">${html}</div>`;
};
const currentFarm = () => state.farms.find((f) => f.id === state.farmId);

// ---------------------------------------------------------------- 입력: 축평원 이력제 조회
function parseNumbers(text) {
  // 기존과 같게: 줄바꿈·쉼표로 나누고 8자 미만은 버린다
  return text.replace(/,/g, "\n").split("\n").map((s) => s.trim()).filter((s) => s.length >= 8);
}

function draftCell(row, i, [key, , type]) {
  const v = row[key] ?? "";
  if (type === "gender") {
    return `<select data-i="${i}" data-k="${key}" class="w-16 rounded border border-line bg-white px-1 py-0.5">
      ${["", "거세", "암", "수"].map((g) => `<option value="${g}" ${g === v ? "selected" : ""}>${g || "-"}</option>`).join("")}</select>`;
  }
  const width = key === "animal_no" ? "w-32" : key === "slaughter_date" ? "w-28" : type === "num" ? "w-20" : "w-14";
  return `<input data-i="${i}" data-k="${key}" ${type === "num" ? 'type="number" step="any"' : ""} value="${esc(v)}"
    class="${width} rounded border border-line px-1 py-0.5 ${type === "num" ? "text-right" : ""}">`;
}

const draftCount = () => ui.drafts.filter((r) => String(r.animal_no ?? "").trim()).length;
const draftCountText = (farm, n) => `↳ 저장 시 <b>${esc(farm.farm_name)}</b> 농가로 ${n}두가 적재됩니다.`;

function draftsHtml(farm) {
  if (!ui.drafts) return "";
  const rows = ui.drafts.map((r, i) => `<tr class="border-t border-line">
      ${DRAFT_COLS.map((c) => `<td class="px-1 py-1">${draftCell(r, i, c)}</td>`).join("")}
      <td class="px-1 py-1"><button data-del="${i}" class="rounded px-2 py-0.5 hover:bg-panel" aria-label="${i + 1}번째 행 지우기" title="이 행 지우기">🗑️</button></td>
    </tr>`).join("");
  const count = draftCount();
  return `<h3 class="font-bold mt-5 mb-2">🔍 조회된 데이터 검토 및 선별</h3>
    ${note("info", "💡 칸을 눌러 값을 고칠 수 있고, 필요 없는 개체는 오른쪽 🗑️ 로 지우면 됩니다. 이력번호가 빈 행은 저장하지 않습니다.")}
    <div class="overflow-x-auto mt-2"><table class="text-sm">
      <thead><tr>${DRAFT_COLS.map(([, l]) => `<th class="px-1 py-1 text-left font-semibold whitespace-nowrap">${l}</th>`).join("")}<th></th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <button id="draft-add" class="mt-2 text-sm text-brand hover:underline">＋ 행 추가</button>
    <p id="draft-count" class="text-xs text-muted mt-2">${draftCountText(farm, count)}</p>
    <div class="grid sm:grid-cols-2 gap-2 mt-2">
      <button id="draft-save" class="rounded-lg bg-brand text-white py-2 font-semibold disabled:opacity-40" ${count ? "" : "disabled"}>💾 검토 완료 및 DB 최종 적재</button>
      <button id="draft-clear" class="rounded-lg border border-line bg-white py-2 hover:bg-panel">🔄 조회 목록 초기화</button>
    </div>`;
}

function apiTabHtml(farm) {
  const m = ui.lookupMsg;
  return `<p class="text-sm mb-2">개체이력번호(12자리)를 줄바꿈하여 입력하면 축산물품질평가원에서 도체성적을 실시간으로 가져옵니다.</p>
    <label class="block text-sm font-medium" for="lookup-text">이력번호 입력</label>
    <textarea id="lookup-text" rows="4" placeholder="002154889011&#10;002154889012&#10;002154889013"
      class="mt-1 w-full rounded-lg border border-line px-3 py-2 font-mono text-sm">${esc(ui.lookupText)}</textarea>
    <button id="lookup-btn" class="mt-2 rounded-lg bg-brand text-white px-4 py-2 font-semibold disabled:opacity-40">⚡ 축평원 성적 임시 조회</button>
    <div id="lookup-progress" class="hidden mt-3">
      <div class="h-2 rounded bg-panel overflow-hidden"><div class="h-full bg-brand transition-all" style="width:0%"></div></div>
      <p class="text-xs text-muted mt-1" aria-live="polite"></p>
    </div>
    <div id="lookup-msg" class="mt-3">${m ? note(m.tone, m.html) : ""}</div>
    <div id="drafts">${draftsHtml(farm)}</div>`;
}

async function runLookup(farm) {
  ui.lookupText = root.querySelector("#lookup-text").value;
  const nos = parseNumbers(ui.lookupText);
  if (!nos.length) {
    ui.lookupMsg = { tone: "err", html: "올바른 이력번호를 입력해주세요." };
    return renderInput();
  }
  const btn = root.querySelector("#lookup-btn");
  const box = root.querySelector("#lookup-progress");
  const bar = box.querySelector("div > div");
  const label = box.querySelector("p");
  btn.disabled = true;
  box.classList.remove("hidden");
  root.querySelector("#lookup-msg").innerHTML = "";

  const records = [], notFound = [];
  let error = null;
  for (let i = 0; i < nos.length; i += LOOKUP_BATCH) {
    label.textContent = `축평원 조회 중… ${i} / ${nos.length}두`;
    try {
      const res = await api("/api/ekape/lookup", { method: "POST", body: JSON.stringify({ animal_nos: nos.slice(i, i + LOOKUP_BATCH) }) });
      if (!res.key_configured) {
        error = "축평원 API 키(EKAPE_API_KEY)가 설정되어 있지 않아 조회할 수 없습니다.";
        break;
      }
      records.push(...res.records);
      notFound.push(...res.not_found);
    } catch (e) {
      error = `조회 중 오류가 나서 ${i}두까지만 조회했습니다: ${e.message}`;
      break;
    }
    bar.style.width = `${Math.round(Math.min(i + LOOKUP_BATCH, nos.length) / nos.length * 100)}%`;
  }

  const parts = [];
  if (records.length) parts.push(`✅ ${records.length}두의 데이터를 가져왔습니다. 아래 표에서 확인 후 최종 저장해주세요.`);
  if (notFound.length) parts.push(`조회되지 않은 번호 ${notFound.length}개: <span class="font-mono">${notFound.map(esc).join(", ")}</span>`);
  if (error) parts.push(`⚠️ ${esc(error)}`);
  if (!records.length && !error) parts.push("조회된 데이터가 없습니다. (API 키가 누락되었거나 잘못된 이력번호일 수 있습니다.)");
  ui.lookupMsg = { tone: error ? "err" : records.length ? "ok" : "warn", html: parts.join("<br>") };
  ui.drafts = records.length ? records : null;
  renderInput();
}

async function saveDrafts(farm) {
  const btn = root.querySelector("#draft-save");
  btn.disabled = true;
  btn.textContent = "저장 중…";
  try {
    const res = await api(`/api/farms/${farm.id}/shipments/ekape`, { method: "POST", body: JSON.stringify({ records: ui.drafts }) });
    ui.drafts = null;
    ui.lookupMsg = null;
    ui.lookupText = "";
    notifySaved(`${res.saved}두의 출하성적이 데이터베이스에 누적 저장되었습니다!`, res.backup);
    renderInput();
    await loadAnalysis();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "💾 검토 완료 및 DB 최종 적재";
    ui.lookupMsg = { tone: "err", html: `⚠️ 저장하지 못했습니다: ${esc(e.message)}` };
    root.querySelector("#lookup-msg").innerHTML = note("err", ui.lookupMsg.html);
  }
}

function bindApiTab(farm) {
  root.querySelector("#lookup-btn").addEventListener("click", () => runLookup(farm));
  root.querySelector("#lookup-text").addEventListener("input", (e) => { ui.lookupText = e.target.value; });
  const drafts = root.querySelector("#drafts");
  if (!ui.drafts) return;
  drafts.addEventListener("input", (e) => {
    const { i, k } = e.target.dataset;
    if (i === undefined) return;
    const type = DRAFT_COLS.find(([key]) => key === k)[2];
    const raw = e.target.value.trim();
    ui.drafts[i][k] = raw === "" ? null : type === "num" ? Number(raw) : raw;
    if (k === "animal_no") {   // 저장 두수 문구와 버튼만 고친다 (표를 다시 그리면 입력 칸 포커스가 사라진다)
      const count = draftCount();
      drafts.querySelector("#draft-count").innerHTML = draftCountText(farm, count);
      drafts.querySelector("#draft-save").disabled = !count;
    }
  });
  drafts.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => {
    ui.drafts.splice(Number(b.dataset.del), 1);
    if (!ui.drafts.length) ui.drafts = null;
    renderInput();
  }));
  drafts.querySelector("#draft-add").addEventListener("click", () => {
    ui.drafts.push(Object.fromEntries(DRAFT_COLS.map(([k]) => [k, null])));
    renderInput();
  });
  drafts.querySelector("#draft-save").addEventListener("click", () => saveDrafts(farm));
  drafts.querySelector("#draft-clear").addEventListener("click", () => {
    ui.drafts = null;
    ui.lookupMsg = null;
    renderInput();
  });
}

// ---------------------------------------------------------------- 입력: 엑셀 업로드
function excelPreviewHtml(farm) {
  const x = ui.excel;
  if (!x) return "";
  if (x.error) return note("err", `⚠️ ${esc(x.error)}`);
  const p = x.preview;
  const willSave = p.rows - p.will_skip;
  const parts = [];
  if (!p.animal_no_column) {
    parts.push(note("err", `⚠️ 이력번호 열(이력번호 · 개체번호 · 개체식별번호)을 찾지 못해 저장할 행이 없습니다.
      엑셀 <b>첫 번째 시트</b>에 출하 데이터가 있는지 확인해주세요. (읽은 열: ${p.columns.map(esc).join(", ") || "없음"})`));
  }
  if (p.mismatched_names.length) {
    parts.push(note("warn", `⚠️ 파일 안의 이름(${p.mismatched_names.map(esc).join(", ")})이 현재 선택된 농가 <b>${esc(farm.farm_name)}</b>와(과) 다릅니다.
      다른 농가 파일을 잘못 올린 건 아닌지 확인해주세요.
      <label class="flex items-center gap-1 mt-2 font-medium"><input id="excel-confirm" type="checkbox" ${x.confirm ? "checked" : ""}>
        그래도 이 파일을 '${esc(farm.farm_name)}' 농가로 업로드합니다</label>`));
  }
  const missingCols = p.missing_columns.filter((c) => c !== "이력번호");
  const infos = [];
  if (p.will_skip && p.animal_no_column) infos.push(`이력번호가 비었거나 8자 미만인 ${p.will_skip}행은 건너뜁니다.`);
  if (p.missing_date) infos.push(`도축일자를 읽지 못한 ${p.missing_date}행은 2025년으로 들어갑니다.`);
  if (missingCols.length) infos.push(`파일에 없는 항목: ${missingCols.map(esc).join(", ")} (빈 값으로 저장)`);
  if (infos.length) parts.push(note("info", infos.map((t) => `ℹ️ ${t}`).join("<br>")));
  const blocked = !willSave || (p.mismatched_names.length && !x.confirm);
  parts.push(`<p class="text-xs text-muted">↳ <b>${esc(x.file.name)}</b> ${p.rows}행 — 저장 시 <b>${esc(farm.farm_name)}</b> 농가로 ${willSave}두가 적재됩니다.</p>
    <button id="excel-save" class="rounded-lg bg-brand text-white px-4 py-2 font-semibold disabled:opacity-40" ${blocked ? "disabled" : ""}>📥 엑셀 데이터 파싱 및 적재</button>`);
  return `<div class="space-y-2 mt-3">${parts.join("")}</div>`;
}

function excelTabHtml(farm) {
  return `<p class="text-sm mb-2"><code>농가출하데이터.xlsx</code> 파일을 올리면 한 번에 수십~수백 두의 성적을 적재합니다. (첫 번째 시트를 읽습니다)</p>
    <label class="block text-sm font-medium" for="excel-file">엑셀 파일 선택 (.xlsx)</label>
    <input id="excel-file" type="file" accept=".xlsx" class="mt-1 block text-sm file:mr-3 file:rounded-lg file:border file:border-line file:bg-white file:px-3 file:py-1.5 hover:file:bg-panel">
    <div id="excel-preview">${excelPreviewHtml(farm)}</div>`;
}

function excelForm(extra = {}) {
  const fd = new FormData();
  fd.append("file", ui.excel.file);
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  return fd;
}

function bindExcelTab(farm) {
  const input = root.querySelector("#excel-file");
  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file) { ui.excel = null; return renderInput(); }
    ui.excel = { file, preview: null, confirm: false };
    root.querySelector("#excel-preview").innerHTML = `<p class="text-sm text-muted mt-3">파일 확인 중…</p>`;
    try {
      ui.excel.preview = await api(`/api/farms/${farm.id}/shipments/excel/preview`, { method: "POST", body: excelForm() });
    } catch (e) {
      ui.excel.error = e.message;
    }
    root.querySelector("#excel-preview").innerHTML = excelPreviewHtml(farm);
    bindExcelPreview(farm);
  });
  bindExcelPreview(farm);
}

function bindExcelPreview(farm) {
  const confirm = root.querySelector("#excel-confirm");
  const save = root.querySelector("#excel-save");
  confirm?.addEventListener("change", () => {
    ui.excel.confirm = confirm.checked;
    const p = ui.excel.preview;
    save.disabled = !(p.rows - p.will_skip) || !confirm.checked;
  });
  save?.addEventListener("click", async () => {
    save.disabled = true;
    save.textContent = "적재 중…";
    try {
      const res = await api(`/api/farms/${farm.id}/shipments/excel`, {
        method: "POST", body: excelForm({ confirm_name_mismatch: ui.excel.confirm ? "true" : "false" }) });
      ui.excel = null;
      notifySaved(`엑셀에서 ${res.saved}두의 출하성적을 성공적으로 적재했습니다!`, res.backup);
      renderInput();
      await loadAnalysis();
    } catch (e) {
      save.disabled = false;
      save.textContent = "📥 엑셀 데이터 파싱 및 적재";
      save.insertAdjacentHTML("afterend", note("err", `⚠️ ${esc(e.message)}`));
    }
  });
}

// ---------------------------------------------------------------- 입력 영역 (탭)
function renderInput() {
  const farm = currentFarm();
  const box = root.querySelector("#input-area");
  const tab = (id, label) => `<button data-tab="${id}" role="tab" aria-selected="${ui.tab === id}"
      class="tab-btn px-3 py-2 text-sm border-b-2 ${ui.tab === id ? "border-brand text-brand font-semibold" : "border-transparent text-muted hover:text-ink"}">${label}</button>`;
  box.innerHTML = `<div role="tablist" class="flex gap-1 border-b border-line mb-4">
      ${tab("api", "⚡ 축평원 OpenAPI 실시간 조회")}${tab("excel", "📁 농가출하데이터.xlsx 엑셀 업로드")}</div>
    <div role="tabpanel">${ui.tab === "api" ? apiTabHtml(farm) : excelTabHtml(farm)}</div>`;
  box.querySelectorAll(".tab-btn").forEach((b) => b.addEventListener("click", () => { ui.tab = b.dataset.tab; renderInput(); }));
  if (ui.tab === "api") bindApiTab(farm);
  else bindExcelTab(farm);
}

// ---------------------------------------------------------------- 분석: 전국 1:1 비교
function verdictClass(v) {
  if (v === "-") return "text-muted";
  return /우수|적정/.test(v) ? "text-pos font-semibold" : "text-neg font-semibold";
}

function comparisonTable(rows) {
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
    <thead><tr class="text-left">${["평가 항목", "농가 성적", "전국 평균", "격차 (+/-)", "진단"].map((h, i) =>
      `<th class="px-2 py-1.5 font-semibold whitespace-nowrap ${i && i < 4 ? "text-right" : ""}">${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr class="border-t border-line">
      <th class="px-2 py-1.5 text-left font-medium whitespace-nowrap">${esc(r.label)}</th>
      <td class="px-2 py-1.5 text-right kpi-value">${f1(r.farm)}</td>
      <td class="px-2 py-1.5 text-right kpi-value text-muted">${f1(r.national)}</td>
      <td class="px-2 py-1.5 text-right kpi-value">${f1(r.diff)}</td>
      <td class="px-2 py-1.5 whitespace-nowrap ${verdictClass(r.verdict)}">${esc(r.verdict)}</td></tr>`).join("")}
    </tbody></table></div>`;
}

function profitHtml(c) {
  const p = c.profit;
  if (!p) return note("info", "도체중 데이터(농가 또는 전국)가 없어 수익성을 추정할 수 없습니다.");
  if (p.total >= 0) {
    return `<p class="text-sm">전국 평균 대비 <b>두당 약 +${won(p.per_head)}원</b>, 총 출하(${p.heads}두) 기준
      <b class="text-pos text-base">+${won(p.total)}원</b>의 추가 조수입을 달성하고 계십니다.</p>`;
  }
  return `<p class="text-sm">전국 평균 대비 <b>두당 약 ${won(p.per_head)}원</b>, 총 출하 기준
    <b class="text-neg text-base">${won(p.total)}원</b>의 수익 손실이 발생하고 있어 사양관리 개선이 시급합니다.</p>`;
}

function drawRecent(recent) {
  const canvas = root.querySelector("#recent-chart");
  if (!canvas) return;
  const farm = recent.map((r) => r.farm[ui.metric]);
  const nat = recent.map((r) => r.national[ui.metric]);
  charts.recent?.destroy();
  charts.recent = new Chart(canvas, {
    type: "line",
    data: {
      labels: recent.map((r) => `${r.year}년`),
      datasets: [
        { label: "농가 평균", data: farm, borderColor: COLORS.farm, backgroundColor: COLORS.farm, borderWidth: 3,
          pointRadius: 5, pointBackgroundColor: "#fff", pointBorderWidth: 2.2, spanGaps: true },
        { label: "전국 평균", data: nat, borderColor: COLORS.nat, backgroundColor: COLORS.nat, borderWidth: 3, borderDash: [5, 4],
          pointRadius: 5, pointBackgroundColor: "#fff", pointBorderWidth: 2.2, spanGaps: true },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {   // 0 부터 그리지 않는다 (기존 차트 zero=False)
        y: { grace: "15%", grid: { color: COLORS.grid }, ticks: { maxTicksLimit: 6, callback: (v) => Number(v).toFixed(1) } },
        x: { grid: { display: false } },
      },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${f1(c.raw)}` } },
      },
    },
  });
}

function recentTable(recent) {
  const cols = METRICS;
  const line = (r, who, label) => `<tr class="border-t border-line">
      ${who === "farm" ? `<th rowspan="2" class="px-2 py-1 text-left align-top whitespace-nowrap">${r.year}년</th>` : ""}
      <td class="px-2 py-1 whitespace-nowrap">${label}</td>
      ${cols.map(([k]) => `<td class="px-2 py-1 text-right kpi-value ${who === "national" ? "text-muted" : ""}">${f1(r[who][k])}</td>`).join("")}</tr>`;
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
    <thead><tr><th class="px-2 py-1 text-left">연도</th><th class="px-2 py-1 text-left">구분</th>
      ${cols.map(([, l]) => `<th class="px-2 py-1 text-right whitespace-nowrap">${l}</th>`).join("")}</tr></thead>
    <tbody>${recent.map((r) => line(r, "farm", "🏆 농가 성적") + line(r, "national", "📊 전국 평균")).join("")}</tbody></table></div>`;
}

function recordsTable(records) {
  const fmt = (k, v) => (v === null || v === undefined ? "-" : ["carcass_weight", "bms", "backfat", "ribeye", "month_age"].includes(k) ? Number(v).toLocaleString("ko-KR", { maximumFractionDigits: 1 }) : esc(v));
  return `<div class="overflow-auto max-h-[480px] border border-line rounded-lg"><table class="w-full text-sm">
    <thead class="sticky top-0 bg-panel"><tr>${RECORD_COLS.map(([, l]) => `<th class="px-2 py-1.5 text-left font-semibold whitespace-nowrap">${l}</th>`).join("")}</tr></thead>
    <tbody>${records.map((r) => `<tr class="border-t border-line">${RECORD_COLS.map(([k]) =>
      `<td class="px-2 py-1 whitespace-nowrap ${k === "animal_no" ? "font-mono" : ""}">${fmt(k, r[k])}</td>`).join("")}</tr>`).join("")}
    </tbody></table></div>`;
}

const options = (list, selected) => list.map(([k, l]) => `<option value="${k}" ${String(k) === String(selected ?? "") ? "selected" : ""}>${esc(l)}</option>`).join("");

async function loadAnalysis() {
  const farm = currentFarm();
  const box = root.querySelector("#analysis");
  const q = new URLSearchParams();
  if (ui.year) q.set("year", ui.year);
  if (ui.gender) q.set("gender", ui.gender);
  let c = await api(`/api/farms/${farm.id}/comparison?${q}`);
  if (ui.year && !c.years.includes(ui.year)) {   // 다른 농가로 바꿨더니 그 연도가 없는 경우
    ui.year = null;
    return loadAnalysis();
  }
  const yearCaption = c.year ? `${c.year}년` : "전체 누적";

  const filters = `<div class="grid sm:grid-cols-2 gap-3">
      <label class="text-sm font-medium">📅 비교 연도 선택
        <select id="year-select" class="mt-1 w-full rounded-lg border border-line bg-white px-2 py-2 text-sm">
          ${options([["", "전체 (누적)"], ...c.years.map((y) => [y, String(y)])], ui.year)}</select></label>
      <label class="text-sm font-medium">🐂 성별 선택
        <select id="gender-select" class="mt-1 w-full rounded-lg border border-line bg-white px-2 py-2 text-sm">
          ${options([["", "전체"], ["거세", "거세"], ["암", "암"]], ui.gender)}</select></label>
    </div>
    ${c.years.length ? `<div class="flex flex-wrap items-center justify-between gap-2 mt-3 rounded-lg bg-panel px-3 py-2">
      <span class="text-xs text-muted">🖨️ 방문용 A4 인쇄 리포트: 2023~2026년 도체성적·등급출현율·달성률을 3페이지로 정리합니다.</span>
      <button id="print-btn" class="rounded-lg border border-line bg-white px-3 py-1.5 text-sm hover:bg-page">🖨️ 인쇄용 비교 리포트(.html) 다운로드</button>
    </div>` : ""}`;

  let body;
  if (!c.total_count) {
    body = note("info", c.year ? `${c.year}년에 등록된 출하 성적이 없습니다. 다른 연도를 선택하거나 위 입력창을 통해 데이터를 추가해주세요.`
      : "등록된 출하 성적이 없습니다. 위 입력창을 통해 이력번호 또는 엑셀을 업로드해주세요.");
  } else {
    const r0 = c.recent[0]?.year, r1 = c.recent[c.recent.length - 1]?.year;
    body = `
      ${card(`<h2 class="font-bold mb-1">📊 출하성적 전국 1:1 비교분석표 (${esc(c.gender_caption)} 기준, ${yearCaption} · 전국 ${c.national_year}년 평균과 비교)</h2>
        ${ui.gender ? "" : `<p class="text-xs text-muted mb-2">※ 성별 '전체'를 선택해도 전국 비교는 성별이 섞이지 않도록 ${esc(c.gender_caption)} 출하분만으로 계산합니다. 아래 개체별 성적표에는 전체 개체가 나옵니다.</p>`}
        ${comparisonTable(c.rows)}
        <h3 class="font-bold mt-5 mb-1">💰 음성공판장 기준 추정 수익성 임팩트</h3>
        ${profitHtml(c)}`)}
      ${c.recent.length ? card(`<h2 class="font-bold mb-2">📈 최근 ${c.recent.length}년 연도별 평가항목 추이 (${r0}~${r1}년)</h2>
        <label class="text-sm text-muted">추이를 확인할 평가항목
          <select id="metric-select" class="ml-2 rounded-lg border border-line bg-white px-2 py-1 text-sm text-ink">${options(METRICS, ui.metric)}</select></label>
        <div class="relative h-[320px] mt-3"><canvas id="recent-chart" role="img" aria-label="최근 연도별 농가 평균과 전국 평균 추이"></canvas></div>
        <details class="mt-4"><summary class="cursor-pointer text-sm font-semibold">🖨️ 최근 ${c.recent.length}년 전국 1:1 종합 비교분석표 보기 (인쇄용)</summary>
          <p class="text-xs text-muted my-2">※ 화면 캡처 또는 브라우저 인쇄(Ctrl+P)를 통해 농가 현장 컨설팅 리포트로 바로 활용하세요.</p>
          ${recentTable(c.recent)}</details>`, "mt-3") : ""}
      ${card(`<h2 class="font-bold mb-2">📑 개체별 출하 상세 성적표 (${yearCaption}, 총 ${c.records.length}두)</h2>${recordsTable(c.records)}`, "mt-3")}`;
  }
  box.innerHTML = `${card(filters)}<div class="mt-3">${body}</div>`;

  box.querySelector("#year-select").addEventListener("change", (e) => { ui.year = e.target.value ? Number(e.target.value) : null; loadAnalysis(); });
  box.querySelector("#gender-select").addEventListener("change", (e) => { ui.gender = e.target.value; loadAnalysis(); });
  box.querySelector("#print-btn")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "리포트 만드는 중…";
    try {
      await apiDownload(`/api/farms/${farm.id}/print-report`, `${farm.farm_name}_출하성적_비교_리포트.html`);
    } catch (ex) {
      btn.insertAdjacentHTML("afterend", `<span class="text-xs text-neg">⚠️ ${esc(ex.message)}</span>`);
    } finally {
      btn.disabled = false;
      btn.textContent = "🖨️ 인쇄용 비교 리포트(.html) 다운로드";
    }
  });
  const metric = box.querySelector("#metric-select");
  if (metric) {
    metric.addEventListener("change", () => { ui.metric = metric.value; drawRecent(c.recent); });
    drawRecent(c.recent);
  }
}

// ---------------------------------------------------------------- 화면
export async function renderShipments(el) {
  root = el;
  const farm = currentFarm();
  const title = `<h1 class="text-2xl font-bold mb-4">1단계 · 출하성적 추출 &amp; 전국 성적 1:1 비교</h1>`;
  if (!farm) {
    el.innerHTML = title + note("warn", "먼저 사이드바 '➕ 신규 농가 등록'으로 농가를 등록하거나, '현재 컨설팅 농가 선택'에서 등록된 농가를 골라주세요.");
    return;
  }
  if (ui.farmId !== farm.id) {   // 농가를 바꾸면 연도 선택과 올려 둔 엑셀은 비운다 (조회해 둔 목록은 기존처럼 남긴다)
    ui.farmId = farm.id;
    ui.year = null;
    ui.excel = null;
  }
  Object.values(charts).forEach((ch) => ch.destroy());
  // 이 화면에서 조회·업로드하는 성적이 어느 농가로 저장되는지 늘 보이게 한다 (농가 선택을 깜빡 안 바꾼 사고 방지)
  el.innerHTML = `${title}
    ${note("info", `📌 지금부터 조회·업로드하는 출하성적은 <b>${esc(farm.farm_name)}</b> 농가(조합원번호 ${esc(farm.farm_code || "미등록")}, ${esc(farm.region || "지역 미입력")})로 저장됩니다.
      다른 농가라면 왼쪽 '현재 컨설팅 농가 선택'에서 먼저 바꿔주세요.`)}
    ${card(`<div id="input-area"></div>`, "mt-3")}
    <div id="analysis" class="mt-6"><p class="text-muted text-sm">불러오는 중…</p></div>`;
  renderInput();
  await loadAnalysis();
}
