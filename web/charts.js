// 여러 화면이 같이 쓰는 차트 (Chart.js). 색은 기존 Streamlit 앱과 같다.
export const C = { farm: "#2A78D6", nat: "#A8A69D", cow: "#D95926", bull: "#77766E", grid: "#E2DFD6", label: "#77766E" };

export const fmt1 = (v) => (v === null || v === undefined ? "-" : Number(v).toFixed(1));

// y 범위: 선이 납작해지지 않게 실제 값 범위에 맞춘다 (기존 앱과 같은 여유: 아래 40%, 위 32%)
function yRange(values) {
  const v = values.filter((x) => x !== null && x !== undefined);
  if (!v.length) return {};
  const lo = Math.min(...v), hi = Math.max(...v);
  const span = (hi - lo) || Math.max(Math.abs(hi) * 0.1, 1);
  return { min: lo - span * 0.4, max: hi + span * 0.32 };
}

// 첫 번째 선(농가)의 값만 점 위에 숫자로 적는다 (전국 값까지 적으면 겹쳐서 읽기 어렵다)
const valueLabels = {
  id: "valueLabels",
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    ctx.save();
    ctx.font = "600 11px Pretendard, sans-serif";
    ctx.fillStyle = C.farm;
    ctx.textAlign = "center";
    chart.getDatasetMeta(0).data.forEach((pt, i) => {
      const v = chart.data.datasets[0].data[i];
      if (v !== null && v !== undefined) ctx.fillText(Number(v).toFixed(1), pt.x, pt.y - 10);
    });
    ctx.restore();
  },
};

function noChartLib(canvas) {
  canvas.parentElement.innerHTML = '<p class="text-sm text-muted">차트를 불러오지 못했습니다. 인터넷 연결을 확인하고 새로고침하세요.</p>';
  return null;
}

// 농가(실선) vs 전국 평균(점선) 꺾은선. 차트 객체를 돌려준다 (다시 그릴 때 destroy 해야 한다).
export function lineChart(canvas, { labels, farm, national, yTitle, farmLabel = "농가 평균" }) {
  if (!window.Chart) return noChartLib(canvas);
  return new Chart(canvas, {
    type: "line",
    data: { labels, datasets: [
      { label: farmLabel, data: farm, borderColor: C.farm, backgroundColor: C.farm, borderWidth: 2.6, tension: 0.3, pointRadius: 4, pointBackgroundColor: "#fff", pointBorderWidth: 2, spanGaps: true },
      { label: "전국 평균", data: national, borderColor: C.nat, backgroundColor: C.nat, borderWidth: 2.4, borderDash: [5, 4], tension: 0.3, pointRadius: 3.5, pointBackgroundColor: "#fff", pointBorderWidth: 2, spanGaps: true },
    ] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
                 tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt1(c.parsed.y)}` } } },
      scales: { y: { ...yRange([...farm, ...national]), grid: { color: C.grid }, ticks: { color: C.label, maxTicksLimit: 5, callback: (v) => Number(v).toFixed(1) }, title: { display: true, text: yTitle, color: C.label } },
                x: { grid: { display: false }, ticks: { color: C.label } } },
    },
    plugins: [valueLabels],
  });
}

// 항목별 막대 (막대 위에 값). colors 는 막대마다.
export function barChart(canvas, { labels, values, colors, valueLabel }) {
  if (!window.Chart) return noChartLib(canvas);
  return new Chart(canvas, {
    type: "bar",
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 7, maxBarThickness: 56 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${valueLabel}: ${fmt1(c.parsed.y)}` } } },
      scales: { y: { beginAtZero: true, grid: { color: C.grid }, ticks: { color: C.label, maxTicksLimit: 4 } }, x: { grid: { display: false }, ticks: { color: C.label, font: { weight: 600 } } } },
    },
    plugins: [{ id: "barLabels", afterDatasetsDraw(chart) {
      const { ctx } = chart; ctx.save(); ctx.font = "600 12px Pretendard, sans-serif"; ctx.fillStyle = C.label; ctx.textAlign = "center";
      chart.getDatasetMeta(0).data.forEach((bar, i) => { const v = chart.data.datasets[0].data[i]; if (v !== null && v !== undefined) ctx.fillText(Number(v).toFixed(1), bar.x, bar.y - 6); });
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
