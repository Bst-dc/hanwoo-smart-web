// 전국 1:1 비교표 인쇄·내려받기 — 화면에 이미 불러온 출하성적 응답(d)으로 A4 한 장짜리 독립 HTML 을 만든다.
// 서버 호출 없이 브라우저에서 만들고, 새 탭에서 열어 인쇄하거나 HTML 파일로 내려받는다.
import { esc, num } from "./api.js";

const CSS = `
@page { size: A4; margin: 14mm; }
* { box-sizing: border-box; }
body { font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; color: #1f2937; margin: 0; font-size: var(--fs, 14px); }
.bar { padding: 10px 14px; background: #f3f4f6; border-bottom: 1px solid #d1d5db; display: flex; gap: 12px; align-items: center; }
.bar button { padding: 8px 14px; font-size: 14px; font-weight: 700; border: 0; border-radius: 8px; background: #166534; color: #fff; cursor: pointer; }
.sheet { max-width: 190mm; margin: 0 auto; padding: 16px; }
h1 { font-size: calc(var(--fs, 14px) + 8px); margin: 0 0 4px; }
h2 { font-size: calc(var(--fs, 14px) + 2px); margin: 16px 0 6px; border-left: 4px solid #166534; padding-left: 8px; }
.meta { color: #4b5563; margin-bottom: 4px; }
table { width: 100%; border-collapse: collapse; margin-bottom: 6px; }
th, td { border: 1px solid #9ca3af; padding: calc(var(--fs, 14px) * 0.45) 6px; text-align: center; }
th { background: #d4ebd9 !important; color: #14532d; font-weight: 700; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
td.l { text-align: left; }
.neg { color: #b91c1c; font-weight: 700; }
.charts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 8px; }
.chart { border: 1px solid #d1d5db; border-radius: 6px; padding: 6px; break-inside: avoid; }
.chart h3 { font-size: 12px; margin: 0 0 4px; text-align: center; color: #166534; }
.chart div { position: relative; height: 170px; }
.chart.main { grid-column: 1 / -1; border: 2px solid #166534; background: #f0f9f2; padding: 10px; }
.chart.main h3 { font-size: 18px; }
.chart.main div { height: 250px; }
@media (max-width: 640px) { .charts { grid-template-columns: 1fr; } }
.note { color: #6b7280; font-size: calc(var(--fs, 14px) - 2px); }
.bar select { font-size: 14px; padding: 6px; }
tr { break-inside: avoid; }
@media print { .charts { grid-template-columns: repeat(3, 1fr); } .chart div { height: 160px; } .chart.main div { height: 230px; } * { -webkit-print-color-adjust: exact; print-color-adjust: exact; } .bar { display: none; } .sheet { padding: 0; max-width: none; } }
`;

function compareTable(rows) {
  return `<table><thead><tr><th>평가항목</th><th>농가</th><th>전국 평균</th><th>격차</th><th>진단</th></tr></thead><tbody>${rows.map((r) =>
    `<tr><td class="l">${esc(r.item)}</td><td>${esc(r.farm)}</td><td>${esc(r.national)}</td><td class="${String(r.diff).startsWith("-") ? "neg" : ""}">${esc(r.diff)}</td><td>${esc(r.diagnosis)}</td></tr>`).join("")}</tbody></table>`;
}

function trendTable(t) {
  const head = ["연도", "구분", ...t.metrics.map((m) => m.label)];
  const rows = t.table.flatMap((r) => [[`${r.year}년`, "농가", ...r.farm], [`${r.year}년`, "전국", ...r.national]]);
  return `<table><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) =>
    `<tr>${r.map((v, i) => `<td class="${i < 2 ? "l" : ""}">${esc(v === null || v === undefined || v === "" ? "-" : v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

// 추이 차트 7개. 근내지방도(BMS)를 맨 위에 전체 폭으로 크게, 나머지 6개는 3열. 값이 모두 없는 지표는 그리지 않는다.
const CHARTS = [
  { key: "bms", title: "⭐ 근내지방도(BMS) 추이", type: "line", main: true },
  { key: "carcass_weight", title: "도체중 추이 (kg)", type: "line" },
  { key: "backfat", title: "등지방두께 추이 (mm)", type: "line" },
  { key: "ribeye", title: "등심단면적 추이 (㎠)", type: "line" },
  { key: "q1plus", title: "1+등급 이상 출현율 (%)", type: "bar" },
  { key: "c_grade", title: "C등급 출현율 (%)", type: "bar" },
  { key: "month_age", title: "출하월령 추이 (개월)", type: "line" },
];

function chartsBlock(t) {
  const specs = CHARTS.filter((c) => t.series[c.key] && [...t.series[c.key].farm, ...t.series[c.key].national].some((v) => v != null));
  if (!specs.length) return { html: "", script: "" };
  const data = specs.map((c) => ({ ...c, farm: t.series[c.key].farm, national: t.series[c.key].national }));
  const json = JSON.stringify({ labels: t.years.map((y) => `${y}년`), charts: data }).replace(/</g, "\\u003c");
  const html = `<div class="charts" id="charts">${data.map((c, i) => `<div class="chart${c.main ? " main" : ""}"><h3>${esc(c.title)}</h3><div><canvas id="c${i}"></canvas></div></div>`).join("")}</div>`;
  const script = `<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
(function () {
  var D = ${json};
  if (typeof Chart === "undefined") { document.getElementById("charts").style.display = "none"; return; }
  var labelPlugin = { id: "vals", afterDatasetsDraw: function (ch) {
    var ctx = ch.ctx; ctx.save(); ctx.font = "bold 10px 'Malgun Gothic', sans-serif"; ctx.textAlign = "center";
    ch.data.datasets.forEach(function (ds, di) {
      ctx.fillStyle = ds.borderColor;
      ch.getDatasetMeta(di).data.forEach(function (pt, i) {
        if (ds.data[i] == null) return;
        ctx.textBaseline = "bottom"; ctx.fillText(Number(ds.data[i]).toFixed(1), pt.x, pt.y - 4);
      });
    }); ctx.restore(); } };
  D.charts.forEach(function (c, i) {
    var bar = c.type === "bar";
    new Chart(document.getElementById("c" + i), {
      type: c.type, plugins: [labelPlugin],
      data: { labels: D.labels, datasets: [
        { label: "농가", data: c.farm, borderColor: "#166534", backgroundColor: bar ? "#166534" : "#166534", borderWidth: 2.5, tension: 0.25, pointRadius: 4, pointBackgroundColor: "#166534" },
        { label: "전국 평균", data: c.national, borderColor: "#475569", backgroundColor: bar ? "#cbd5e1" : "#475569", borderWidth: 2, borderDash: bar ? [] : [6, 4], tension: 0.25, pointRadius: 3, pointBackgroundColor: "#475569" } ] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, layout: { padding: { top: 14 } },
        plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 10 } } }, tooltip: { enabled: true } },
        scales: { x: { ticks: { font: { size: 10 } }, grid: { display: false } }, y: { ticks: { font: { size: 10 } }, grace: "12%" } } }
    });
  });
})();
</script>`;
  return { html, script };
}

/** d: /api/farms/{id}/shipments 응답, ctx: { gName, yearCaption } */
export function compareSheetHtml(d, { gName, yearCaption }) {
  const f = d.farm;
  const p = d.profit;
  const profit = p?.available
    ? `<p>두당(전국 평균 대비) <b class="${p.total < 0 ? "neg" : ""}">${p.per_head >= 0 ? "+" : ""}${num(p.per_head)}원</b> · 총 출하 ${num(d.total_count)}두 기준 <b class="${p.total < 0 ? "neg" : ""}">${p.total >= 0 ? "+" : ""}${num(p.total)}원</b></p>
       <p class="note">음성공판장 기준 도체중 격차 × kg당 21,000원으로 계산한 추정치입니다.</p>` : "";
  const ch = chartsBlock(d.trend);
  const today = new Date().toLocaleDateString("ko-KR");
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(f.name)} 전국 1:1 비교표</title><style>${CSS}</style></head><body>
<div class="bar"><button onclick="window.print()">🖨️ 인쇄 (A4)</button><label>글자 크기 <select onchange="document.documentElement.style.setProperty('--fs', this.value)"><option value="12px">작게</option><option value="14px" selected>보통</option><option value="16px">크게</option><option value="18px">아주 크게</option></select></label><span>인쇄 창에서 'PDF로 저장'을 고르면 파일로도 받을 수 있습니다.</span></div>
<div class="sheet">
<h1>출하성적 전국 1:1 비교표</h1>
<div class="meta"><b>${esc(f.name)}</b> (조합원번호 ${esc(f.code || "미등록")}, ${esc(f.region || "지역 미입력")}) · 출력일 ${esc(today)}</div>
<div class="meta">${esc(gName)} 기준 · ${esc(yearCaption)} · 전국 ${esc(d.national_year)}년 평균 · 총 ${num(d.total_count)}두</div>
<h2>전국 1:1 비교</h2>${compareTable(d.comparison)}
${profit ? `<h2>추정 수익성</h2>${profit}` : ""}
<h2>최근 ${d.trend.years.length}년 전국 1:1 종합 비교표 (${d.trend.years[0]}~${d.trend.years.at(-1)}년)</h2>${trendTable(d.trend)}
${ch.html ? `<h2>성적 변화 추이 (농가 vs 전국)</h2>${ch.html}` : ""}
<p class="note">대구축협 한우 스마트 컨설팅 · 전국 평균은 축평원/KOSIS 자료 기준</p>
</div>${ch.script}</body></html>`;
}

export function openCompareSheet(html) {
  const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
  const w = window.open(url, "_blank");
  if (!w) location.href = url;                 // 팝업이 막히면 현재 탭에서 연다
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function downloadCompareSheet(html, filename) {
  const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
