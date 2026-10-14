// 메뉴 1: 종합 현황 대시보드 — 기존 Streamlit 화면과 같은 구성
//   KPI 7개 → 누락 데이터 명단 → 연도별 추이 차트 + 연도별 집계표 → 거세우 vs 암소 비교
import { api, esc } from "../api.js";

const COLORS = { farm: "#2A78D6", nat: "#A8A69D", cow: "#D95926", bull: "#77766E", grid: "#E2DFD6", label: "#77766E" };
const METRICS = [
  ["carcass_weight", "도체중 (kg)"],
  ["bms", "BMS"],
  ["ribeye", "단면적 (㎠)"],
  ["backfat", "등지방 (mm)"],
  ["plus1_rate", "1+ 이상 출현율 (%)"],
  ["c_rate", "C등급 출현율 (%)"],
  ["month_age", "출하월령"],
];
const GENDER_LABEL = { 거세: "거세우", 암: "암소", 수: "수소" };
const MEMBERS = ["전체", "조합원", "비조합원"];
const ui = { gender: "거세", metric: "carcass_weight", cmpMetric: "carcass_weight", member: "전체" };
const charts = {};

const f1 = (v) => (v === null || v === undefined ? "-" : Number(v).toFixed(1));
const card = (inner, extra = "") => `<section class="rounded-xl bg-white border border-line p-4 ${extra}">${inner}</section>`;

function kpi(label, value, unit, { delta = null, help = "" } = {}) {
  const deltaHtml = delta === null ? "" : `<span class="text-sm font-semibold ${delta < 0 ? "text-neg" : "text-pos"}">
      ${delta < 0 ? "▼" : "▲"} ${Math.abs(delta).toFixed(1)}%p</span>`;
  return `<div class="rounded-xl bg-white border border-line p-4" ${help ? `title="${esc(help)}"` : ""}>
    <div class="text-sm text-muted">${esc(label)}${help ? ' <span aria-hidden="true">ⓘ</span>' : ""}</div>
    <div class="kpi-value text-2xl font-bold mt-1">${esc(value)} <span class="text-base font-medium">${esc(unit)}</span></div>
    ${deltaHtml}${help ? `<div class="sr-only">${esc(help)}</div>` : ""}
  </div>`;
}

function plus1Kpi(label, p, genderWord) {
  if (!p) return kpi(label, "-", "");
  const help = p.national === null ? "" : `${p.base_year}년 전국 ${genderWord} 1+이상 출현율 ${p.national}%와 비교`;
  return kpi(label, p.value.toFixed(1), "%", { delta: p.delta, help });
}

function namesBox(title, names, emptyText, hint, tone) {
  const body = names.length
    ? `<p class="text-sm">${names.map(esc).join(", ")}</p><p class="text-xs text-muted mt-1">${esc(hint)}</p>`
    : `<p class="text-sm text-pos">${esc(emptyText)}</p>`;
  return `<div class="rounded-lg p-3 ${names.length ? tone : "bg-brand-tint"}"><div class="text-sm font-semibold mb-1">${esc(title)}</div>${body}</div>`;
}

// ---------- 연도별 추이 차트 ----------
// 농가 값만 점 위에 숫자로 적는다 (전국값까지 적으면 라벨끼리 겹친다 — 기존 차트와 같은 규칙)
const farmValueLabels = {
  id: "farmValueLabels",
  afterDatasetsDraw(chart) {
    const meta = chart.getDatasetMeta(0);
    const { ctx } = chart;
    ctx.save();
    ctx.font = "600 11px Pretendard, sans-serif";
    ctx.fillStyle = COLORS.farm;
    ctx.textAlign = "center";
    meta.data.forEach((pt, i) => {
      const v = chart.data.datasets[0].data[i];
      if (v !== null && v !== undefined) ctx.fillText(Number(v).toFixed(1), pt.x, pt.y - 12);
    });
    ctx.restore();
  },
};

function drawTrend(rows) {
  const labels = rows.map((r) => `${String(r.year).slice(2)}년`);
  const farm = rows.map((r) => r.farm[ui.metric]);
  const nat = rows.map((r) => r.national[ui.metric]);
  const vals = [...farm, ...nat].filter((v) => v !== null && v !== undefined);
  // 기준선이 0이면 선이 납작해져 추이가 안 보인다 — 값 범위에 맞춰 아래 40%, 위 32% 여유 (기존 차트와 같은 비율)
  let yMin, yMax;
  if (vals.length) {
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const span = hi - lo || Math.max(Math.abs(hi) * 0.1, 1);
    yMin = lo - span * 0.4;
    yMax = hi + span * 0.32;
  }
  const canvas = document.getElementById("trend-chart");
  charts.trend?.destroy();
  charts.trend = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "방문농가 평균", data: farm, borderColor: COLORS.farm, borderWidth: 2.6, tension: 0.35,
          pointRadius: 4.5, pointBackgroundColor: "#fff", pointBorderWidth: 2.2, spanGaps: true, fill: "start",
          backgroundColor: (ctx) => {
            const { chartArea, ctx: c } = ctx.chart;
            if (!chartArea) return "transparent";
            const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
            g.addColorStop(0, "rgba(42,120,214,0.22)");
            g.addColorStop(1, "rgba(255,255,255,0)");
            return g;
          },
        },
        {
          label: "전국 평균", data: nat, borderColor: COLORS.nat, borderWidth: 2.6, borderDash: [5, 4], tension: 0.35,
          pointRadius: 4.5, pointBackgroundColor: "#fff", pointBorderWidth: 2.2, spanGaps: true,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { min: yMin, max: yMax, grid: { color: COLORS.grid }, ticks: { maxTicksLimit: 6, callback: (v) => Number(v).toFixed(1) } },
        x: { grid: { display: false } },
      },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${f1(c.raw)}` } },
      },
    },
    plugins: [farmValueLabels],
  });
}

function yearlyTable(rows) {
  // 기존 화면처럼 연도를 열로(최근 연도가 왼쪽), 지표를 행으로. 괄호 안은 그 해 전국 평균.
  const years = rows.filter((r) => r.heads !== null).reverse();
  if (!years.length) return `<p class="text-sm text-muted">등록된 출하 성적이 없습니다. 농가 성적을 먼저 입력해주세요.</p>`;
  const cell = (r, k) => {
    const v = r.farm[k], n = r.national[k];
    if (v === null) return "-";
    return n === null ? f1(v) : `${f1(v)} <span class="text-muted">(${f1(n)})</span>`;
  };
  const head = years.map((r) => `<th class="px-2 py-1 text-right font-semibold">${String(r.year).slice(2)}년</th>`).join("");
  const line = (label, fn) => `<tr class="border-t border-line"><th class="px-2 py-1 text-left font-medium whitespace-nowrap">${label}</th>
      ${years.map((r) => `<td class="px-2 py-1 text-right whitespace-nowrap kpi-value">${fn(r)}</td>`).join("")}</tr>`;
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
    <thead><tr><th></th>${head}</tr></thead>
    <tbody>
      ${line("농가수", (r) => r.farms)}
      ${line("출하두수", (r) => r.heads)}
      ${METRICS.map(([k, label]) => line(label, (r) => cell(r, k))).join("")}
    </tbody></table></div>`;
}

async function loadTrend() {
  const { rows } = await api(`/api/dashboard/yearly?gender=${encodeURIComponent(ui.gender)}&member=${encodeURIComponent(ui.member)}`);
  const g = GENDER_LABEL[ui.gender];
  document.getElementById("trend-title").textContent = `📈 연도별 성적 추이 (${g} · 방문농가 전체 vs 전국평균)`;
  document.getElementById("table-title").textContent = `📋 연도별 전체 집계표 (${g})`;
  document.getElementById("yearly-table").innerHTML = yearlyTable(rows);
  ui.rows = rows;
  drawTrend(rows);
}

// ---------- 거세우 vs 암소 ----------
function drawCompare(rows) {
  const canvas = document.getElementById("compare-chart");
  charts.compare?.destroy();
  charts.compare = new Chart(canvas, {
    type: "bar",
    data: {
      labels: rows.map((r) => r.gender),
      datasets: [{
        data: rows.map((r) => r[ui.cmpMetric]),
        backgroundColor: rows.map((r) => ({ 거세: COLORS.farm, 암: COLORS.cow, 수: COLORS.bull }[r.gender] || COLORS.bull)),
        borderRadius: { topLeft: 7, topRight: 7 }, maxBarThickness: 44,
      }],
    },
    options: {
      maintainAspectRatio: false,
      scales: { y: { grid: { color: COLORS.grid }, ticks: { maxTicksLimit: 5 } }, x: { grid: { display: false } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => f1(c.raw) } } },
    },
    plugins: [{
      id: "barLabels",
      afterDatasetsDraw(chart) {
        const { ctx } = chart;
        ctx.save();
        ctx.font = "600 12px Pretendard, sans-serif";
        ctx.fillStyle = COLORS.label;
        ctx.textAlign = "center";
        chart.getDatasetMeta(0).data.forEach((bar, i) => ctx.fillText(f1(chart.data.datasets[0].data[i]), bar.x, bar.y - 6));
        ctx.restore();
      },
    }],
  });
}

function compareTable(rows) {
  const cols = [["heads", "출하두수"], ...METRICS.filter(([k]) => k !== "c_rate")];
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
    <thead><tr><th class="px-2 py-1 text-left whitespace-nowrap">성별</th>${cols.map(([, l]) => `<th class="px-2 py-1 text-right whitespace-nowrap">${l}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr class="border-t border-line"><th class="px-2 py-1 text-left whitespace-nowrap">${esc(r.gender)}</th>
      ${cols.map(([k]) => `<td class="px-2 py-1 text-right kpi-value">${k === "heads" ? r.heads.toLocaleString("ko-KR") : f1(r[k])}</td>`).join("")}</tr>`).join("")}
    </tbody></table></div>`;
}

const options = (list, selected) => list.map(([k, l]) => `<option value="${k}" ${k === selected ? "selected" : ""}>${esc(l)}</option>`).join("");

export async function renderDashboard(el) {
  const q = `?member=${encodeURIComponent(ui.member)}`;
  const [s, cmp] = await Promise.all([api(`/api/dashboard/summary${q}`), api(`/api/dashboard/gender-compare${q}`)]);

  el.innerHTML = `
    <h1 class="text-2xl font-bold mb-3">종합 현황 대시보드</h1>
    <div class="flex items-center gap-2 mb-4" role="radiogroup" aria-label="농가 구분">
      <span class="text-sm text-muted mr-1">농가 구분</span>
      ${MEMBERS.map((m) => `<button data-member="${m}" role="radio" aria-checked="${m === ui.member}"
          class="member-btn rounded-full border px-3 py-1 text-sm ${m === ui.member ? "bg-brand text-white border-brand" : "bg-white border-line"}">${m}</button>`).join("")}
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
      ${kpi("총 관리 농가 수", s.total_farms, "농가")}
      ${kpi("누적 현장 방문 횟수", s.total_visits, "회")}
      ${kpi("누적 분석 출하 두수", s.total_shipments.toLocaleString("ko-KR"), "두")}
    </div>
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-3">
      ${plus1Kpi("거세우 1+이상 출현율", s.steer_plus1, "거세우")}
      ${plus1Kpi("암소 1+이상 출현율", s.cow_plus1, "암소")}
      ${kpi("출하성적만 있는 농가", s.farms_missing_survey.length, "농가", { help: "출하성적은 등록되어 있으나, 현장 방문 조사표가 아직 작성되지 않은 농가 수입니다." })}
      ${kpi("조사표만 있는 농가", s.farms_missing_shipment.length, "농가", { help: "현장 방문 조사표는 있으나, 아직 축평원 출하성적 데이터가 수집되지 않은 농가 수입니다." })}
    </div>

    <details class="mt-3 rounded-xl bg-white border border-line p-4">
      <summary class="cursor-pointer text-sm font-semibold">📌 누락 데이터 보유 농가 명단 확인 및 관리</summary>
      <div class="grid md:grid-cols-2 gap-3 mt-3">
        ${namesBox("출하성적만 있고 조사표 없는 농가", s.farms_missing_survey, "해당 농가 없음", "(2단계 메뉴에서 신규 조사표를 작성해주세요)", "bg-[#EEF4FB]")}
        ${namesBox("조사표만 있고 출하성적 없는 농가", s.farms_missing_shipment, "해당 농가 없음", "(1단계 메뉴에서 성적을 수동 또는 엑셀로 추가해주세요)", "bg-[#FBF3E6]")}
      </div>
    </details>

    <div class="flex items-center gap-2 mt-6 mb-3" role="radiogroup" aria-label="연도별 추이 · 집계표 기준 성별">
      <span class="text-sm text-muted mr-1">연도별 추이 · 집계표 기준 성별</span>
      ${["거세", "암"].map((g) => `<button data-gender="${g}" role="radio" aria-checked="${g === ui.gender}"
          class="gender-btn rounded-full border px-3 py-1 text-sm ${g === ui.gender ? "bg-brand text-white border-brand" : "bg-white border-line"}">${GENDER_LABEL[g]}</button>`).join("")}
    </div>
    <div class="grid xl:grid-cols-2 gap-3">
      ${card(`<h2 id="trend-title" class="font-bold mb-2"></h2>
        <label class="text-sm text-muted">비교 지표 선택
          <select id="metric-select" class="ml-2 rounded-lg border border-line bg-white px-2 py-1 text-sm text-ink">${options(METRICS, ui.metric)}</select></label>
        <div class="relative h-[330px] mt-3"><canvas id="trend-chart" aria-label="연도별 성적 추이 차트" role="img"></canvas></div>`, "")}
      ${card(`<h2 id="table-title" class="font-bold mb-1"></h2>
        <p class="text-xs text-muted mb-2">※ 괄호 ( ) 안의 수치는 해당 연도 전국 평균입니다.</p>
        <div id="yearly-table"></div>`, "")}
    </div>

    <h2 class="text-lg font-bold mt-8 mb-3">⚖️ 거세우 vs 암소 전체 누적 평균 비교</h2>
    ${cmp.length ? `<div class="grid lg:grid-cols-2 gap-3">
      ${card(compareTable(cmp))}
      ${card(`<label class="text-sm text-muted">비교 지표
          <select id="cmp-select" class="ml-2 rounded-lg border border-line bg-white px-2 py-1 text-sm text-ink">${options(METRICS.filter(([k]) => k !== "c_rate"), ui.cmpMetric)}</select></label>
        <div class="relative h-[220px] mt-3"><canvas id="compare-chart" aria-label="성별 비교 막대 차트" role="img"></canvas></div>`)}
    </div>` : `<p class="text-sm text-muted">등록된 출하 성적이 없습니다.</p>`}
  `;

  el.querySelectorAll(".member-btn").forEach((b) => b.addEventListener("click", () => {
    ui.member = b.dataset.member;
    renderDashboard(el).catch((e) => { el.innerHTML = `<div class="rounded-xl border border-neg/40 bg-white p-4 text-neg text-sm">⚠️ ${esc(e.message)}</div>`; });
  }));
  el.querySelectorAll(".gender-btn").forEach((b) => b.addEventListener("click", () => {
    ui.gender = b.dataset.gender;
    el.querySelectorAll(".gender-btn").forEach((x) => {
      const on = x.dataset.gender === ui.gender;
      x.setAttribute("aria-checked", on);
      x.className = `gender-btn rounded-full border px-3 py-1 text-sm ${on ? "bg-brand text-white border-brand" : "bg-white border-line"}`;
    });
    loadTrend();
  }));
  el.querySelector("#metric-select").addEventListener("change", (e) => { ui.metric = e.target.value; drawTrend(ui.rows); });
  if (cmp.length) {
    el.querySelector("#cmp-select").addEventListener("change", (e) => { ui.cmpMetric = e.target.value; drawCompare(cmp); });
    drawCompare(cmp);
  }
  await loadTrend();
}
