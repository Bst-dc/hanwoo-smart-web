// 여러 화면이 같이 쓰는 차트 (Chart.js).
// 모양은 피그마 커뮤니티 'Full charts components' 의 단색(파랑) 팔레트를 따른다 (2026-11-01):
//   꺾은선 = 'User supplied data' 카드 — 부드러운 곡선, 굵은 선(6px) + 뒤에 옅은 띠(34px, 7%), 세로 눈금선만, 강조 점 + 검은 말풍선
//   막대   = 'Contributions' 카드 — 모서리 8px, 축·눈금 없이 막대 위에 값
// 팔레트: #03045E #023E8A #0077B6 #0096C7 #00B4D8 #48CAE4 #90E0EF #ADE8F4 #D3F7FF
export const C = { farm: "#0096C7", nat: "#48CAE4", steer: "#0077B6", cow: "#48CAE4", bull: "#ADE8F4", grid: "#F3F3F3", label: "#59605F", ink: "#161A19" };

export const fmt1 = (v) => (v === null || v === undefined ? "-" : Number(v).toFixed(1));

const FONT = '"IBM Plex Sans KR", "Malgun Gothic", sans-serif';
if (window.Chart) Object.assign(Chart.defaults.font, { family: FONT, size: 12 });

// 마우스·손가락을 댔을 때 나오는 말풍선: 검은 바탕, 모서리 4px (피그마 tooltips)
const TOOLTIP = { backgroundColor: "#000", cornerRadius: 4, padding: { x: 12, y: 7 }, titleFont: { size: 11, weight: "500" }, bodyFont: { size: 12 }, boxPadding: 4, usePointStyle: true };

// y 범위: 선이 납작해지지 않게 실제 값 범위에 맞춘다 (기존 앱과 같은 여유: 아래 40%, 위 32%)
function yRange(values) {
  const v = values.filter((x) => x !== null && x !== undefined);
  if (!v.length) return {};
  const lo = Math.min(...v), hi = Math.max(...v);
  const span = (hi - lo) || Math.max(Math.abs(hi) * 0.1, 1);
  return { min: lo - span * 0.4, max: hi + span * 0.32 };
}

const lastIndex = (arr) => { for (let i = arr.length - 1; i >= 0; i--) if (arr[i] !== null && arr[i] !== undefined) return i; return -1; };

// 농가 선의 값을 점 위에 적는다 (전국 값까지 적으면 겹쳐서 읽기 어렵다). 가장 최근 값은 검은 말풍선으로 강조.
const valueLabels = {
  id: "valueLabels",
  afterDatasetsDraw(chart) {
    const ds = chart.data.datasets.findIndex((d) => d.isFarm);
    if (ds < 0) return;
    const { ctx } = chart;
    const data = chart.data.datasets[ds].data;
    const last = lastIndex(data);
    ctx.save();
    ctx.textAlign = "center";
    chart.getDatasetMeta(ds).data.forEach((pt, i) => {
      const v = data[i];
      if (v === null || v === undefined) return;
      const text = Number(v).toFixed(1);
      if (i === last) {
        ctx.font = `500 11px ${FONT}`;
        const w = ctx.measureText(text).width + 20, h = 22, x = pt.x - w / 2, y = pt.y - h - 14;
        ctx.fillStyle = "#000";
        ctx.beginPath(); ctx.roundRect(x, y, w, h, 4); ctx.fill();
        ctx.fillStyle = "#fff"; ctx.textBaseline = "middle";
        ctx.fillText(text, pt.x, y + h / 2 + 0.5);
        ctx.textBaseline = "alphabetic";
      } else {
        ctx.font = `600 11px ${FONT}`;
        ctx.fillStyle = C.steer;
        ctx.fillText(text, pt.x, pt.y - 12);
      }
    });
    ctx.restore();
  },
};

function noChartLib(canvas) {
  canvas.parentElement.innerHTML = '<p class="text-sm text-muted">차트를 불러오지 못했습니다. 인터넷 연결을 확인하고 새로고침하세요.</p>';
  return null;
}

// 농가(굵은 선 + 옅은 띠) vs 전국 평균(가는 연한 선) 꺾은선. 차트 객체를 돌려준다 (다시 그릴 때 destroy 해야 한다).
export function lineChart(canvas, { labels, farm, national, yTitle, farmLabel = "농가 평균" }) {
  if (!window.Chart) return noChartLib(canvas);
  const last = lastIndex(farm);
  const curve = { cubicInterpolationMode: "monotone", spanGaps: true, borderCapStyle: "round", borderJoinStyle: "round" };   // 값 사이를 부드럽게, 값보다 튀어 나가지 않게
  return new Chart(canvas, {
    type: "line",
    data: { labels, datasets: [
      { label: farmLabel, isFarm: true, data: farm, borderColor: C.farm, backgroundColor: C.farm, borderWidth: 5.8, order: 1, ...curve,
        pointRadius: (c) => (c.dataIndex === last ? 7 : 0), pointHoverRadius: 7, pointBackgroundColor: C.farm, pointBorderColor: "#fff", pointBorderWidth: 2 },
      { label: "전국 평균", data: national, borderColor: C.nat, backgroundColor: C.nat, borderWidth: 3.5, order: 2, ...curve,
        pointRadius: 0, pointHoverRadius: 5, pointBackgroundColor: C.nat, pointBorderColor: "#fff", pointBorderWidth: 2 },
      { label: "_halo", data: farm, borderColor: "rgba(0,150,199,0.07)", borderWidth: 34, order: 3, pointRadius: 0, pointHoverRadius: 0, ...curve },   // 농가 선 뒤의 옅은 띠
    ] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      layout: { padding: { top: 30, left: 4, right: 12 } },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "circle", boxWidth: 10, boxHeight: 10, padding: 18, color: C.ink, font: { size: 13 }, filter: (i) => i.text !== "_halo" } },
        tooltip: { ...TOOLTIP, filter: (i) => i.dataset.label !== "_halo", callbacks: { label: (c) => ` ${c.dataset.label}: ${fmt1(c.parsed.y)}` } },
      },
      scales: {
        y: { ...yRange([...farm, ...national]), border: { display: false }, grid: { display: false },
             ticks: { color: C.label, maxTicksLimit: 5, padding: 8, callback: (v) => Number(v).toFixed(1) }, title: { display: true, text: yTitle, color: C.label, font: { size: 12 } } },
        x: { offset: true, border: { display: false }, grid: { color: C.grid, lineWidth: 1, drawTicks: false }, ticks: { color: C.ink, padding: 10, font: { size: 13 } } },
      },
    },
    plugins: [valueLabels],
  });
}

// 항목별 막대 (막대 위에 값). colors 는 막대마다. 축·눈금선 없이 막대와 값만 (피그마 Contributions 카드).
export function barChart(canvas, { labels, values, colors, valueLabel }) {
  if (!window.Chart) return noChartLib(canvas);
  return new Chart(canvas, {
    type: "bar",
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 8, borderSkipped: false, barPercentage: 0.7, categoryPercentage: 0.9, maxBarThickness: 64 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      layout: { padding: { top: 22 } },
      plugins: { legend: { display: false }, tooltip: { ...TOOLTIP, callbacks: { label: (c) => ` ${valueLabel}: ${fmt1(c.parsed.y)}` } } },
      scales: { y: { display: false, beginAtZero: true }, x: { border: { display: false }, grid: { display: false }, ticks: { color: C.ink, padding: 6, font: { size: 13, weight: "500" } } } },
    },
    plugins: [{ id: "barLabels", afterDatasetsDraw(chart) {
      const { ctx } = chart; ctx.save(); ctx.font = `600 13px ${FONT}`; ctx.fillStyle = C.ink; ctx.textAlign = "center";
      chart.getDatasetMeta(0).data.forEach((bar, i) => { const v = chart.data.datasets[0].data[i]; if (v !== null && v !== undefined) ctx.fillText(Number(v).toFixed(1), bar.x, bar.y - 8); });
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
