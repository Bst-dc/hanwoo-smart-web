// 종합 현황 대시보드 — KPI 카드, 누락 농가 명단, 연도별 추이 차트·집계표, 거세우 vs 암소 비교.
// 값은 서버(/api/dashboard)가 기존 앱과 같은 공식으로 계산해 준다. 여기서는 그리기만 한다.
import { api, card, esc, num, table } from "../api.js";
import { barChart, C, destroyCharts, fmt1, keep, lineChart } from "../charts.js";

const GENDER_COLOR = { 거세: C.farm, 암: C.cow, 수: C.bull };

function kpi(label, value, sub = "", subTone = "", span = "") {
  return `<div class="rounded-2xl bg-white border border-line p-4 ${span}">
    <div class="text-sm text-muted">${esc(label)}</div>
    <div class="kpi-value text-2xl font-bold mt-1">${esc(value)}</div>
    ${sub ? `<div class="text-xs mt-1 ${subTone || "text-muted"}">${sub}</div>` : ""}</div>`;
}

// 1+이상 출현율 카드: 전국(작년) 대비 격차를 색으로 보여 준다 (+는 초록, -는 빨강)
function onePlusCard(label, o) {
  if (o.national === null) return kpi(label, `${fmt1(o.value)}%`);
  const tone = o.delta >= 0 ? "text-pos" : "text-neg";
  const sign = o.delta > 0 ? "+" : "";
  return kpi(label, `${fmt1(o.value)}%`, `전국 ${o.base_year}년 ${fmt1(o.national)}% 대비 ${sign}${fmt1(o.delta)}%p`, `${tone} font-semibold`);
}

// 연도별 집계표: 가로가 연도(최신이 왼쪽), 세로가 지표. 값 옆 괄호는 그 해 전국 평균.
function yearlyTable(d, gender) {
  const g = d.trend.genders[gender];
  if (!g.rows.length) return '<p class="text-sm text-muted">등록된 출하 성적이 없습니다. 농가 성적을 먼저 입력해주세요.</p>';
  const yearIdx = Object.fromEntries(d.trend.years.map((y, i) => [y, i]));
  const rows = [...g.rows].sort((a, b) => b.year - a.year);
  const columns = ["지표", ...rows.map((r) => `${String(r.year).slice(2)}년`)];
  const cell = (r, key) => {
    const v = r[key];
    if (v === null || v === undefined) return "-";
    const nat = g.series[key].national[yearIdx[r.year]];
    return nat === null || nat === undefined ? fmt1(v) : `${fmt1(v)} (${fmt1(nat)})`;
  };
  const body = [
    ["농가수", ...rows.map((r) => num(r.farms))],
    ["출하두수", ...rows.map((r) => num(r.heads))],
    ...d.trend.metrics.map((m) => [m.label, ...rows.map((r) => cell(r, m.key))]),
  ];
  return `<p class="text-xs text-muted mb-2">※ 괄호 ( ) 안의 수치는 해당 연도 전국 평균입니다.</p>` +
    table({ columns, rows: body }, { align: Object.fromEntries(columns.map((c, i) => [c, i === 0 ? "left" : "center"])) });
}

const COMPARE_METRICS = [["carcass_weight", "도체중 (kg)"], ["bms", "BMS"], ["ribeye", "단면적 (㎠)"], ["backfat", "등지방 (mm)"], ["q1plus", "1+ 이상 출현율 (%)"], ["month_age", "출하월령 (개월)"]];

function compareTable(d) {
  const columns = ["성별", "출하두수", "도체중 (kg)", "BMS", "단면적 (㎠)", "등지방 (mm)", "1+ 이상 (%)", "월령"];
  const rows = d.compare.map((r) => [r.gender, num(r.heads), fmt1(r.carcass_weight), fmt1(r.bms), fmt1(r.ribeye), fmt1(r.backfat), fmt1(r.q1plus), fmt1(r.month_age)]);
  return table({ columns, rows }, { align: Object.fromEntries(columns.map((c, i) => [c, i === 0 ? "left" : "center"])) });
}

const MEMBERS = ["전체", "조합원", "비조합원"];
let member = "전체";                                  // 선택한 농가 구분은 화면을 옮겨도 유지한다

export async function renderDashboard(el, ctx) {
  const { farms, farmId, onPickFarm, isCurrent = () => true } = ctx;
  destroyCharts();
  el.innerHTML = '<p class="text-sm text-muted">불러오는 중…</p>';
  const d = await api(`/api/dashboard?member=${encodeURIComponent(member)}`);
  if (!isCurrent()) return;           // 기다리는 사이 다른 화면으로 옮겼으면 그리지 않는다
  const k = d.kpi;
  const src = d.national_source;
  const srcNote = src.kosis === "live" ? "전국 평균: 통계청(KOSIS) 최신값 반영"
    : src.kosis === "partial" ? "전국 평균: KOSIS 일부만 반영 (나머지는 기본값)"
    : "전국 평균: 기본값 사용 중 (KOSIS 최신값을 받지 못했습니다)";
  const srcTone = src.kosis === "live" ? "text-muted" : "text-neg";

  const list = (names) => (names.length ? names.map(esc).join(", ") : "해당 농가 없음");
  el.innerHTML = `
    <h2 class="text-xl font-bold mb-3">종합 현황 대시보드</h2>
    <div id="member-seg" class="inline-flex rounded-xl border border-line overflow-hidden text-sm mb-3" role="group" aria-label="농가 구분">
      ${MEMBERS.map((m, i) => `<button data-m="${m}" aria-pressed="${m === member}" class="px-4 py-2 min-h-[44px] ${i ? "border-l border-line" : ""} ${m === member ? "bg-brand text-white font-semibold" : "bg-white text-muted"}">${m}</button>`).join("")}
    </div>
    <div class="grid grid-cols-2 gap-3">
      ${kpi("총 관리 농가 수", `${num(k.farms)} 농가`)}
      ${kpi("누적 현장 방문 횟수", `${num(k.visits)} 회`)}
      ${kpi("누적 분석 출하 두수", `${num(k.shipments)} 두`, "", "", "col-span-2")}
      ${onePlusCard("거세우 1+이상 출현율", k.steer_1plus)}
      ${onePlusCard("암소 1+이상 출현율", k.cow_1plus)}
      ${kpi("출하성적만 있는 농가", `${num(k.missing_survey.length)} 농가`, "조사표 미작성")}
      ${kpi("조사표만 있는 농가", `${num(k.missing_shipment.length)} 농가`, "출하성적 미수집")}
    </div>
    <details class="mt-3 rounded-2xl bg-white border border-line p-4">
      <summary class="cursor-pointer font-semibold text-sm">📌 누락 데이터 보유 농가 명단</summary>
      <div class="mt-3 space-y-3 text-sm">
        <div><div class="font-semibold">출하성적만 있고 조사표 없는 농가</div><div class="text-muted mt-1">${list(k.missing_survey)}</div></div>
        <div><div class="font-semibold">조사표만 있고 출하성적 없는 농가</div><div class="text-muted mt-1">${list(k.missing_shipment)}</div></div>
      </div>
    </details>
    <p class="text-xs ${srcTone} mt-2">${esc(srcNote)}</p>

    <div class="flex items-center justify-between gap-3 mt-6 mb-2">
      <h3 class="text-base font-bold">연도별 성적 추이</h3>
      <div id="gender-seg" class="inline-flex rounded-xl border border-line overflow-hidden text-sm" role="group" aria-label="성별">
        <button data-g="거세" class="px-4 py-2 min-h-[44px]">거세우</button>
        <button data-g="암" class="px-4 py-2 min-h-[44px] border-l border-line">암소</button>
      </div>
    </div>
    ${card(`
      <label class="block text-sm text-muted mb-1" for="trend-metric">비교 지표</label>
      <select id="trend-metric" class="w-full rounded-xl border border-line bg-white px-3 py-2 mb-3">
        ${d.trend.metrics.map((m) => `<option value="${m.key}">${esc(m.label)}</option>`).join("")}</select>
      <div class="relative" style="height:260px"><canvas id="trend-chart" aria-label="연도별 성적 추이 차트" role="img"></canvas></div>`)}
    <h3 class="text-base font-bold mt-5 mb-2">연도별 전체 집계표</h3>
    <div id="yearly-table"></div>

    <h3 class="text-base font-bold mt-6 mb-2">거세우 vs 암소 전체 누적 평균 비교</h3>
    <div id="compare-table" class="mb-3"></div>
    ${card(`
      <label class="block text-sm text-muted mb-1" for="cmp-metric">비교 지표</label>
      <select id="cmp-metric" class="w-full rounded-xl border border-line bg-white px-3 py-2 mb-3">
        ${COMPARE_METRICS.map(([key, label]) => `<option value="${key}">${esc(label)}</option>`).join("")}</select>
      <div class="relative" style="height:220px"><canvas id="cmp-chart" aria-label="거세우와 암소 비교 차트" role="img"></canvas></div>`)}

    <h3 class="text-base font-bold mt-6 mb-2">농가 목록</h3>
    <div class="space-y-2">${farms.filter((f) => member === "전체" || f.member_type === member).map((f) => `
      <button data-farm="${f.id}" class="farm-card w-full text-left rounded-2xl bg-white border ${f.id === farmId ? "border-brand" : "border-line"} p-4 active:bg-panel">
        <div class="flex items-center justify-between gap-2"><span class="font-semibold truncate">${esc(f.name)}${f.member_type === "비조합원" ? ' <span class="text-xs font-normal text-muted border border-line rounded px-1">비조합원</span>' : ""}</span><span class="text-xs text-muted shrink-0">${esc(f.region)}</span></div>
        <div class="text-sm text-muted mt-1">방문 ${num(f.visits)}회 · 출하성적 ${num(f.shipments)}두</div></button>`).join("")}</div>`;

  // ---- 동작 연결 ----
  let gender = "거세";
  const trendSel = el.querySelector("#trend-metric");
  const cmpSel = el.querySelector("#cmp-metric");
  const trendLabel = (key) => d.trend.metrics.find((m) => m.key === key).label;
  const compareLabel = (key) => COMPARE_METRICS.find(([k]) => k === key)[1];

  const redrawTrend = () => {
    el.querySelectorAll("#gender-seg button").forEach((b) => {
      const on = b.dataset.g === gender;
      b.className = `px-4 py-2 min-h-[44px] ${b.dataset.g === "암" ? "border-l border-line" : ""} ${on ? "bg-brand text-white font-semibold" : "bg-white text-muted"}`;
      b.setAttribute("aria-pressed", on);
    });
    const s = d.trend.genders[gender].series[trendSel.value];
    keep("dash-trend", lineChart(el.querySelector("#trend-chart"), {
      labels: d.trend.years.map((y) => `${String(y).slice(2)}년`), farm: s.farm, national: s.national,
      yTitle: trendLabel(trendSel.value), farmLabel: "방문농가 평균" }));
    el.querySelector("#yearly-table").innerHTML = yearlyTable(d, gender);
  };
  const redrawCompare = () => {
    keep("dash-compare", barChart(el.querySelector("#cmp-chart"), {
      labels: d.compare.map((r) => r.gender), values: d.compare.map((r) => r[cmpSel.value]),
      colors: d.compare.map((r) => GENDER_COLOR[r.gender] || C.bull), valueLabel: compareLabel(cmpSel.value) }));
  };
  el.querySelectorAll("#gender-seg button").forEach((b) => b.addEventListener("click", () => { gender = b.dataset.g; redrawTrend(); }));
  trendSel.addEventListener("change", redrawTrend);
  cmpSel.addEventListener("change", redrawCompare);
  el.querySelector("#compare-table").innerHTML = compareTable(d);
  redrawTrend();
  redrawCompare();
  el.querySelectorAll("#member-seg button").forEach((b) => b.addEventListener("click", () => {
    member = b.dataset.m;
    renderDashboard(el, ctx).catch((e) => { el.innerHTML = `<p class="text-sm text-neg">⚠️ ${esc(e.message)}</p>`; });
  }));
  el.querySelectorAll(".farm-card").forEach((b) => b.addEventListener("click", () => onPickFarm(b.dataset.farm)));
}

