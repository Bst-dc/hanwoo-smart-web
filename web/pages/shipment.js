// 1단계 · 출하성적 비교분석 (조회) — 농가 한 곳의 성적을 전국 평균과 1:1 비교, 최근 3년 추이, 수익성 추정, 개체별 성적표.
// 숫자·진단 문구는 서버(/api/farms/{id}/shipments)가 기존 앱과 같은 규칙으로 만들어 준다. 여기서는 그리기만 한다.
// 성적 입력(축평원 조회·엑셀 업로드)은 아직 옮기는 중이라 기존 앱에서 한다.
import { api, card, esc, num, table } from "../api.js";
import { keep, lineChart } from "../charts.js";

const OLD_APP = "https://consulting.3-38-225-111.sslip.io/";
const GOOD = new Set(["우수 (▲)", "우수 (▼)", "적정", "단기출하 (우수)"]);
const GENDER_NAME = { 거세: "거세우", 암: "암소" };
const RECORD_PAGE = 50;

// 농가가 바뀌면 연도 선택은 처음(전체 누적)으로 돌린다. 성별은 그대로 둔다.
const filters = { farmId: null, year: "", gender: "" };

function badge(text) {
  const tone = text === "-" ? "bg-panel text-muted" : GOOD.has(text) ? "bg-brand-tint text-pos" : "bg-[#FBEDE8] text-neg";
  return `<span class="shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${tone}">${esc(text)}</span>`;
}

function comparisonList(rows) {
  return `<ul class="divide-y divide-line">${rows.map((r) => `
    <li class="py-3">
      <div class="flex items-center justify-between gap-2"><span class="font-semibold">${esc(r.item)}</span>${badge(r.diagnosis)}</div>
      <div class="kpi-value text-sm text-muted mt-1">농가 <b class="text-ink">${esc(r.farm)}</b> · 전국 ${esc(r.national)} · 격차 <b class="${r.diff.startsWith("-") ? "text-neg" : "text-ink"}">${esc(r.diff)}</b></div>
    </li>`).join("")}</ul>`;
}

function profitCard(p, count) {
  if (!p.available) return card('<p class="text-sm text-muted">도체중 데이터(농가 또는 전국)가 없어 수익성을 추정할 수 없습니다.</p>');
  const plus = p.total >= 0;
  const head = `${plus ? "+" : ""}${num(p.per_head)}원`;
  const total = `${plus ? "+" : ""}${num(p.total)}원`;
  return card(`<h3 class="font-bold mb-2">💰 음성공판장 기준 추정 수익성</h3>
    <div class="grid grid-cols-2 gap-3">
      <div><div class="text-xs text-muted">두당 (전국 평균 대비)</div><div class="kpi-value text-lg font-bold ${plus ? "text-pos" : "text-neg"}">${head}</div></div>
      <div><div class="text-xs text-muted">총 출하 ${num(count)}두 기준</div><div class="kpi-value text-lg font-bold ${plus ? "text-pos" : "text-neg"}">${total}</div></div>
    </div>
    <p class="text-xs text-muted mt-2">도체중 격차 × kg당 21,000원으로 계산한 추정치입니다.${plus ? "" : " 사양관리 개선이 필요합니다."}</p>`);
}

function trendTable(t) {
  const columns = ["연도", "구분", ...t.metrics.map((m) => m.label)];
  const rows = t.table.flatMap((r) => [[`${r.year}년`, "농가", ...r.farm], [`${r.year}년`, "전국", ...r.national]]);
  return table({ columns, rows }, { align: Object.fromEntries(columns.map((c, i) => [c, i < 2 ? "left" : "center"])) });
}

function recordsTable(records, shown) {
  const columns = ["이력번호", "성별", "도축일자", "도체중 (kg)", "육질", "육량", "BMS", "등지방 (mm)", "단면적 (㎠)", "월령"];
  const rows = records.slice(0, shown).map((r) => [r.animal_no, r.gender, r.date, r.carcass_weight, r.grade_quality, r.grade_yield, r.bms, r.backfat, r.ribeye, r.month_age]);
  return table({ columns, rows }, { align: { 이력번호: "left", 성별: "center", 도축일자: "center", 육질: "center", 육량: "center" } });
}

function pickFarmCard(farms, onPickFarm) {
  return card(`<h2 class="text-lg font-bold mb-1">1단계 · 출하성적 비교분석</h2>
    <p class="text-sm text-muted mb-3">먼저 컨설팅할 농가를 고르세요. (위쪽 목록에서 골라도 됩니다)</p>
    <div class="space-y-2">${farms.map((f) => `
      <button data-farm="${f.id}" class="pick w-full text-left rounded-xl border border-line bg-white p-3 active:bg-panel">
        <span class="font-semibold">${esc(f.name)}</span><span class="text-xs text-muted ml-2">${esc(f.region)} · 출하성적 ${num(f.shipments)}두</span></button>`).join("")}</div>`);
}

export async function renderShipment(el, { farm, farms, onPickFarm, isCurrent = () => true }) {
  if (!farm) {
    el.innerHTML = pickFarmCard(farms, onPickFarm);
    el.querySelectorAll(".pick").forEach((b) => b.addEventListener("click", () => onPickFarm(b.dataset.farm)));
    return;
  }
  if (filters.farmId !== farm.id) Object.assign(filters, { farmId: farm.id, year: "" });

  el.innerHTML = '<p class="text-sm text-muted">불러오는 중…</p>';
  const q = new URLSearchParams();
  if (filters.year) q.set("year", filters.year);
  if (filters.gender) q.set("gender", filters.gender);
  const d = await api(`/api/farms/${farm.id}/shipments?${q}`);
  if (!isCurrent()) return;           // 기다리는 사이 다른 화면으로 옮겼으면 그리지 않는다

  const yearCaption = filters.year ? `${filters.year}년` : "전체 누적";
  const gName = GENDER_NAME[d.cmp_gender] || d.cmp_gender;
  const seg = (val, label) => `<button data-g="${val}" class="gseg px-4 py-2 min-h-[44px] ${val ? "border-l border-line" : ""} ${filters.gender === val ? "bg-brand text-white font-semibold" : "bg-white text-muted"}" aria-pressed="${filters.gender === val}">${label}</button>`;

  let body;
  if (!d.has_data) {
    body = card(`<p class="text-sm text-muted">${filters.year ? `${esc(filters.year)}년에 등록된 ${esc(gName)} 출하 성적이 없습니다. 다른 연도나 성별을 골라보세요.` : "등록된 출하 성적이 없습니다. 기존 앱에서 이력번호 조회나 엑셀로 성적을 먼저 입력해주세요."}</p>`);
  } else {
    body = `
      <h3 class="text-base font-bold mt-5 mb-1">📊 전국 1:1 비교 <span class="text-sm font-normal text-muted">(${esc(gName)} 기준 · ${esc(yearCaption)} · 전국 ${d.national_year}년 평균)</span></h3>
      ${d.gender_forced ? `<p class="text-xs text-muted mb-2">※ 성별 '전체'여도 전국 비교는 성별이 섞이지 않게 ${esc(gName)} 출하분만으로 계산합니다. 아래 개체별 성적표에는 전체 개체가 나옵니다.</p>` : ""}
      ${card(comparisonList(d.comparison))}
      <div class="mt-3">${profitCard(d.profit, d.total_count)}</div>

      <h3 class="text-base font-bold mt-6 mb-2">📈 최근 ${d.trend.years.length}년 추이 <span class="text-sm font-normal text-muted">(${d.trend.years[0]}~${d.trend.years.at(-1)}년)</span></h3>
      ${card(`
        <label class="block text-sm text-muted mb-1" for="sh-metric">평가항목</label>
        <select id="sh-metric" class="w-full rounded-xl border border-line bg-white px-3 py-2 mb-3">
          ${d.trend.metrics.map((m) => `<option value="${m.key}">${esc(m.label)}</option>`).join("")}</select>
        <div class="relative" style="height:240px"><canvas id="sh-trend" role="img" aria-label="최근 연도별 평가항목 추이"></canvas></div>`)}
      <details class="mt-3 rounded-2xl bg-white border border-line p-4">
        <summary class="cursor-pointer font-semibold text-sm">🖨️ 최근 ${d.trend.years.length}년 전국 1:1 종합 비교표</summary>
        <div class="mt-3">${trendTable(d.trend)}</div>
      </details>`;
  }

  el.innerHTML = `
    <div class="rounded-2xl bg-brand-tint border border-brand-line p-3 text-sm">
      📌 <b>${esc(d.farm.name)}</b> <span class="text-muted">(조합원번호 ${esc(d.farm.code || "미등록")}, ${esc(d.farm.region || "지역 미입력")})</span>
    </div>
    <p class="text-xs text-muted mt-2">성적 입력(축평원 이력번호 조회·엑셀 업로드)은 아직 옮기는 중입니다. <a class="underline text-brand" href="${OLD_APP}" target="_blank" rel="noopener noreferrer">기존 앱</a>에서 입력하세요.</p>

    <div class="flex flex-wrap items-end gap-3 mt-4">
      <div class="flex-1 min-w-[9rem]">
        <label class="block text-sm text-muted mb-1" for="sh-year">비교 연도</label>
        <select id="sh-year" class="w-full rounded-xl border border-line bg-white px-3 py-2">
          <option value="">전체 (누적)</option>${d.years.map((y) => `<option value="${y}" ${String(y) === String(filters.year) ? "selected" : ""}>${y}년</option>`).join("")}</select>
      </div>
      <div class="inline-flex rounded-xl border border-line overflow-hidden text-sm" role="group" aria-label="성별">${seg("", "전체")}${seg("거세", "거세")}${seg("암", "암")}</div>
    </div>
    ${body}
    <h3 class="text-base font-bold mt-6 mb-2">📑 개체별 출하 성적표 <span class="text-sm font-normal text-muted">(${esc(yearCaption)}, 총 ${num(d.records.length)}두)</span></h3>
    <div id="sh-records"></div>`;

  // ---- 동작 연결 ----
  const reload = () => renderShipment(el, { farm, farms, onPickFarm, isCurrent });
  el.querySelector("#sh-year").addEventListener("change", (e) => { filters.year = e.target.value; reload(); });
  el.querySelectorAll(".gseg").forEach((b) => b.addEventListener("click", () => { filters.gender = b.dataset.g; reload(); }));

  let shown = RECORD_PAGE;
  const drawRecords = () => {
    const box = el.querySelector("#sh-records");
    if (!d.records.length) { box.innerHTML = '<p class="text-sm text-muted">해당 개체가 없습니다.</p>'; return; }
    box.innerHTML = recordsTable(d.records, shown) + (d.records.length > shown
      ? `<button id="sh-more" class="mt-2 w-full rounded-xl border border-line bg-white py-3 text-sm font-semibold active:bg-panel">더 보기 (${num(Math.min(RECORD_PAGE, d.records.length - shown))}두 · 남은 ${num(d.records.length - shown)}두)</button>` : "");
    box.querySelector("#sh-more")?.addEventListener("click", () => { shown += RECORD_PAGE; drawRecords(); });
  };
  drawRecords();

  if (!d.has_data) keep("sh-trend", null);   // 성적이 없는 화면으로 바뀌면 이전 차트를 정리한다
  else {
    const sel = el.querySelector("#sh-metric");
    const draw = () => {
      const s = d.trend.series[sel.value];
      keep("sh-trend", lineChart(el.querySelector("#sh-trend"), {
        labels: d.trend.years.map((y) => `${y}년`), farm: s.farm, national: s.national,
        yTitle: d.trend.metrics.find((m) => m.key === sel.value).label }));
    };
    sel.addEventListener("change", draw);
    draw();
  }
}
