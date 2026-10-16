// 전국 1:1 비교표 인쇄·내려받기 — 화면에 이미 불러온 출하성적 응답(d)으로 A4 한 장짜리 독립 HTML 을 만든다.
// 서버 호출 없이 브라우저에서 만들고, 새 탭에서 열어 인쇄하거나 HTML 파일로 내려받는다.
import { esc, num } from "./api.js";

const CSS = `
@page { size: A4; margin: 14mm; }
* { box-sizing: border-box; }
body { font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; color: #1f2937; margin: 0; font-size: 12px; }
.bar { padding: 10px 14px; background: #f3f4f6; border-bottom: 1px solid #d1d5db; display: flex; gap: 12px; align-items: center; }
.bar button { padding: 8px 14px; font-size: 14px; font-weight: 700; border: 0; border-radius: 8px; background: #166534; color: #fff; cursor: pointer; }
.sheet { max-width: 190mm; margin: 0 auto; padding: 16px; }
h1 { font-size: 20px; margin: 0 0 4px; }
h2 { font-size: 14px; margin: 18px 0 6px; border-left: 4px solid #166534; padding-left: 8px; }
.meta { color: #4b5563; margin-bottom: 4px; }
table { width: 100%; border-collapse: collapse; margin-bottom: 6px; }
th, td { border: 1px solid #9ca3af; padding: 5px 6px; text-align: center; }
th { background: #e5f2e8; }
td.l { text-align: left; }
.neg { color: #b91c1c; font-weight: 700; }
.note { color: #6b7280; font-size: 11px; }
tr { break-inside: avoid; }
@media print { .bar { display: none; } .sheet { padding: 0; max-width: none; } }
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

/** d: /api/farms/{id}/shipments 응답, ctx: { gName, yearCaption } */
export function compareSheetHtml(d, { gName, yearCaption }) {
  const f = d.farm;
  const p = d.profit;
  const profit = p?.available
    ? `<p>두당(전국 평균 대비) <b class="${p.total < 0 ? "neg" : ""}">${p.per_head >= 0 ? "+" : ""}${num(p.per_head)}원</b> · 총 출하 ${num(d.total_count)}두 기준 <b class="${p.total < 0 ? "neg" : ""}">${p.total >= 0 ? "+" : ""}${num(p.total)}원</b></p>
       <p class="note">음성공판장 기준 도체중 격차 × kg당 21,000원으로 계산한 추정치입니다.</p>` : "";
  const today = new Date().toLocaleDateString("ko-KR");
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(f.name)} 전국 1:1 비교표</title><style>${CSS}</style></head><body>
<div class="bar"><button onclick="window.print()">🖨️ 인쇄 (A4)</button><span>인쇄 창에서 'PDF로 저장'을 고르면 파일로도 받을 수 있습니다.</span></div>
<div class="sheet">
<h1>출하성적 전국 1:1 비교표</h1>
<div class="meta"><b>${esc(f.name)}</b> (조합원번호 ${esc(f.code || "미등록")}, ${esc(f.region || "지역 미입력")}) · 출력일 ${esc(today)}</div>
<div class="meta">${esc(gName)} 기준 · ${esc(yearCaption)} · 전국 ${esc(d.national_year)}년 평균 · 총 ${num(d.total_count)}두</div>
<h2>전국 1:1 비교</h2>${compareTable(d.comparison)}
${profit ? `<h2>추정 수익성</h2>${profit}` : ""}
<h2>최근 ${d.trend.years.length}년 전국 1:1 종합 비교표 (${d.trend.years[0]}~${d.trend.years.at(-1)}년)</h2>${trendTable(d.trend)}
<p class="note">대구축협 한우 스마트 컨설팅 · 전국 평균은 축평원/KOSIS 자료 기준</p>
</div></body></html>`;
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
