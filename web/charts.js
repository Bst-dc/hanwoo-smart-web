// 여러 화면이 같이 쓰는 차트 (Chart.js).
// 모양 (2026-11-06 다시 정함 — 앱 공통 색과 같게, '전국보다 얼마나 높고 낮은가'가 바로 보이게):
//   꺾은선 = 농가는 장부 녹색 실선 + 해마다 점, 전국은 회색 점선. 범례 대신 선 끝에 이름·값,
//            연도 밑에 '전국 대비 +x.x' 줄 (좋은 쪽이면 녹색, 나쁜 쪽이면 빨강). 곡선·꾸밈 띠는 쓰지 않는다(없는 오르내림이 보임).
//   비교 막대 = 가로 막대(장부 녹색) 위에 전국 평균을 세로 선으로 겹치고, 옆에 '전국 x (+y)'.
export const C = { farm: "#1F6B5E", nat: "#9AA1A0", grid: "#ECEEEE", axis: "#D3D8D7", label: "#59605F", ink: "#161A19", pos: "#1E7A4F", neg: "#B4321F" };

export const fmt1 = (v) => (v === null || v === undefined ? "-" : Number(v).toFixed(1));

const FONT = '"Orbit", "Malgun Gothic", sans-serif';   // 앱 글꼴(오빗)과 같게
if (window.Chart) Object.assign(Chart.defaults.font, { family: FONT, size: 12 });

// 지표마다 어느 쪽이 좋은지. 여기 없는 지표(등지방·출하월령)는 좋고 나쁨을 정하지 않고 차이만 회색으로 적는다.
const BETTER = { carcass_weight: "high", bms: "high", ribeye: "high", q1plus: "high", c_grade: "low" };

const has = (v) => v !== null && v !== undefined;
const signed = (d) => `${d > 0 ? "+" : d < 0 ? "-" : "±"}${Math.abs(d).toFixed(1)}`;
function diffColor(d, metric) {
  const better = BETTER[metric];
  if (!better || Math.abs(d) < 0.05) return C.label;
  return (d > 0) === (better === "high") ? C.pos : C.neg;
}

// 마우스·손가락을 댔을 때 나오는 말풍선: 검은 바탕, 모서리 4px
const TOOLTIP = { backgroundColor: "#000", cornerRadius: 4, padding: { x: 12, y: 7 }, titleFont: { size: 11, weight: "500" }, bodyFont: { size: 12 }, boxPadding: 4, usePointStyle: true };

const lastIndex = (arr) => { for (let i = arr.length - 1; i >= 0; i--) if (has(arr[i])) return i; return -1; };

function textWidth(canvas, font, texts) {
  const ctx = canvas.getContext("2d");
  ctx.save(); ctx.font = font;
  const w = Math.max(0, ...texts.map((t) => ctx.measureText(t).width));
  ctx.restore();
  return w;
}

function noChartLib(canvas) {
  canvas.parentElement.innerHTML = '<p class="text-sm text-muted">차트를 불러오지 못했습니다. 인터넷 연결을 확인하고 새로고침하세요.</p>';
  return null;
}

// 같은 캔버스에 이미 차트가 있으면 먼저 지운다. Chart.js 4 는 쓰고 있는 캔버스에 새 차트를 만들면
// 오류를 내고 이전 차트를 그대로 둔다 — keep(name, lineChart(...)) 은 새 차트를 만든 뒤에야 이전 것을 지우므로 여기서 막는다.
function freeCanvas(canvas) { Chart.getChart(canvas)?.destroy(); }

const END_FONT = `600 12px ${FONT}`;
const DIFF_FONT = `500 12px ${FONT}`;

// 선 끝 이름·값과 연도 밑 '전국 대비' 줄
function trendLabels(metric, farmLabel) {
  return {
    id: "trendLabels",
    afterDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      const [farm, nat] = chart.data.datasets.map((d) => d.data);
      ctx.save();
      // 1) 선 끝 이름·값. 두 끝이 너무 가까우면 위아래로 벌린다.
      const ends = [[0, C.farm, farmLabel], [1, C.nat, "전국"]].map(([ds, color, name]) => {
        const i = lastIndex(chart.data.datasets[ds].data);
        if (i < 0) return null;
        const pt = chart.getDatasetMeta(ds).data[i];
        return { color, text: `${name} ${fmt1(chart.data.datasets[ds].data[i])}`, x: pt.x + 10, y: pt.y };
      });
      if (ends[0] && ends[1] && Math.abs(ends[0].y - ends[1].y) < 16) {
        const [hi, lo] = ends[0].y <= ends[1].y ? ends : [ends[1], ends[0]];
        const mid = (hi.y + lo.y) / 2;
        hi.y = mid - 8; lo.y = mid + 8;
      }
      ctx.font = END_FONT; ctx.textBaseline = "middle"; ctx.textAlign = "left";
      ends.forEach((e) => { if (e) { ctx.fillStyle = e.color; ctx.fillText(e.text, e.x, e.y); } });
      // 2) 연도 밑 차이 줄 (두 값이 다 있는 연도만)
      const y = scales.x.bottom + 12;
      let any = false;
      ctx.font = DIFF_FONT; ctx.textAlign = "center";
      chart.getDatasetMeta(0).data.forEach((pt, i) => {
        if (!has(farm[i]) || !has(nat[i])) return;
        const d = Math.round((farm[i] - nat[i]) * 10) / 10;
        ctx.fillStyle = diffColor(d, metric);
        ctx.fillText(signed(d), pt.x, y);
        any = true;
      });
      if (any) { ctx.textAlign = "right"; ctx.fillStyle = C.label; ctx.font = `400 11px ${FONT}`; ctx.fillText("전국 대비", chartArea.left - 6, y); }
      ctx.restore();
    },
  };
}

// 농가 vs 전국 평균 연도별 꺾은선. metric 은 지표 키(좋은 쪽 판단용). 차트 객체를 돌려준다 (다시 그릴 때 destroy 해야 한다).
export function lineChart(canvas, { labels, farm, national, yTitle, metric, farmLabel = "이 농가" }) {
  if (!window.Chart) return noChartLib(canvas);
  freeCanvas(canvas);
  const right = textWidth(canvas, END_FONT, [`${farmLabel} 000.0`, "전국 000.0"]) + 16;
  const last = lastIndex(farm);
  return new Chart(canvas, {
    type: "line",
    data: { labels, datasets: [
      { label: farmLabel, data: farm, borderColor: C.farm, backgroundColor: C.farm, borderWidth: 2.5, tension: 0, spanGaps: true, order: 1,
        pointRadius: (c) => (c.dataIndex === last ? 5 : 3.5), pointHoverRadius: 6, pointBackgroundColor: C.farm, pointBorderColor: "#fff", pointBorderWidth: 1.5 },
      { label: "전국", data: national, borderColor: C.nat, backgroundColor: C.nat, borderWidth: 1.5, borderDash: [5, 4], tension: 0, spanGaps: true, order: 2,
        pointRadius: 0, pointHoverRadius: 4, pointBackgroundColor: C.nat, pointBorderColor: "#fff", pointBorderWidth: 1.5 },
    ] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      layout: { padding: { top: 12, left: 4, right, bottom: 22 } },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { ...TOOLTIP, callbacks: {
          label: (c) => ` ${c.dataset.label}: ${fmt1(c.parsed.y)}`,
          footer: (items) => { const f = farm[items[0].dataIndex], n = national[items[0].dataIndex]; return has(f) && has(n) ? `전국 대비 ${signed(Math.round((f - n) * 10) / 10)}` : ""; },
        } },
      },
      scales: {
        y: { grace: "10%", border: { display: false }, grid: { color: C.grid, drawTicks: false },
             ticks: { color: C.label, maxTicksLimit: 5, padding: 8 }, title: { display: true, text: yTitle, color: C.label, font: { size: 12 } } },
        x: { offset: true, border: { color: C.axis }, grid: { display: false }, ticks: { color: C.ink, padding: 8, font: { size: 13 } } },
      },
    },
    plugins: [trendLabels(metric, farmLabel)],
  });
}

// 항목별 가로 막대 + 전국 평균 세로 선. national 은 항목마다 값(없으면 null → 선·글자 없음).
export function compareChart(canvas, { labels, values, national, valueLabel, metric }) {
  if (!window.Chart) return noChartLib(canvas);
  freeCanvas(canvas);
  const right = textWidth(canvas, END_FONT, ["000.0  전국 000.0 (+00.0)"]) + 12;
  const max = Math.max(0, ...[...values, ...national].filter(has));
  return new Chart(canvas, {
    type: "bar",
    data: { labels, datasets: [{ data: values, backgroundColor: C.farm, borderRadius: 4, borderSkipped: "start", barThickness: 22 }] },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false,
      layout: { padding: { right, top: 4, bottom: 4 } },
      plugins: { legend: { display: false }, tooltip: { ...TOOLTIP, callbacks: {
        label: (c) => ` ${valueLabel}: ${fmt1(c.parsed.x)}`,
        afterLabel: (c) => (has(national[c.dataIndex]) ? ` 전국: ${fmt1(national[c.dataIndex])}` : ""),
      } } },
      scales: { x: { display: false, beginAtZero: true, max: max * 1.02 || undefined },
                y: { border: { display: false }, grid: { display: false }, ticks: { color: C.ink, padding: 6, font: { size: 13 } } } },
    },
    plugins: [{ id: "compareLabels", afterDatasetsDraw(chart) {
      const { ctx } = chart, xs = chart.scales.x;
      ctx.save(); ctx.textBaseline = "middle"; ctx.textAlign = "left";
      chart.getDatasetMeta(0).data.forEach((bar, i) => {
        const v = values[i], n = national[i];
        if (!has(v)) return;
        let x = bar.x;
        if (has(n)) {                                   // 전국 평균 세로 선
          const nx = xs.getPixelForValue(n);
          ctx.strokeStyle = C.ink; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(nx, bar.y - bar.height / 2 - 5); ctx.lineTo(nx, bar.y + bar.height / 2 + 5); ctx.stroke();
          x = Math.max(x, nx);
        }
        x += 8;
        ctx.font = END_FONT; ctx.fillStyle = C.ink;
        const vt = fmt1(v), vw = ctx.measureText(vt).width;
        ctx.fillText(vt, x, bar.y);
        if (has(n)) {
          const d = Math.round((v - n) * 10) / 10;
          ctx.font = DIFF_FONT; ctx.fillStyle = diffColor(d, metric);
          ctx.fillText(`전국 ${fmt1(n)} (${signed(d)})`, x + vw + 14, bar.y);
        }
      });
      ctx.restore();
    } }],
  });
}

// 화면을 다시 그리거나 다른 메뉴로 갈 때 이전 차트를 정리한다.
const live = new Map();          // 이름 → 차트
export function keep(name, chart) {
  live.get(name)?.destroy();
  if (chart) live.set(name, chart); else live.delete(name);
}
export function destroyCharts() {
  live.forEach((c) => c.destroy());
  live.clear();
}
