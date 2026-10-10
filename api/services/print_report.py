"""방문용 A4 3페이지 인쇄 리포트 — streamlit_app.py 의 build_print_comparison_report_html 과 같은 HTML.

이 파일의 함수들은 기존 소스에서 그대로 떼어 온 것이다. 바꾼 것은 전국 통계(NATIONAL_STATS)와 DB 연결(conn)을
인자로 받게 한 것뿐이다. 기존 앱과 글자 하나까지 같은 HTML 이 나오는지는 tests/check_api_parity.py 가 확인한다.
"""
import json

import pandas as pd

PRINT_REPORT_YEARS = [2023, 2024, 2025, 2026]
PRINT_REPORT_GENDERS = [("거세", "거세우"), ("암", "암소")]


def _fmt1(v):
    return f"{v:.1f}" if v is not None and pd.notna(v) else "-"

def _diff_cell(v):
    cls = ""
    if v is not None and pd.notna(v):
        cls = "diff-pos" if v > 0 else ("diff-neg" if v < 0 else "")
        sign = "+" if v > 0 else ""
        return f"<td class='num {cls}'>{sign}{v:.1f}</td>"
    return "<td class='num'>-</td>"

def _build_page1_table(gdf, gender_key, NATIONAL_STATS):
    nat = NATIONAL_STATS.get(gender_key, {})
    metrics = [
        ("도체중 (kg)", "carcass_weight", "도체중"),
        ("근내지방도 (BMS)", "bms", "BMS"),
        ("등지방두께 (mm)", "backfat", "등지방"),
        ("등심단면적 (cm²)", "ribeye", "단면적"),
        ("평균출하월령 (개월)", "month_age", "출하월령"),
    ]
    rows = ""
    for label, col, natkey in metrics:
        farm_vals, nat_vals, diff_vals = [], [], []
        for y in PRINT_REPORT_YEARS:
            ydf = gdf[gdf["slaughter_year"] == y]
            fv = round(ydf[col].mean(), 1) if (not ydf.empty and ydf[col].notna().any()) else None
            nv = nat.get(natkey, {}).get(y)
            dv = round(fv - nv, 1) if (fv is not None and nv is not None) else None
            farm_vals.append(fv); nat_vals.append(nv); diff_vals.append(dv)
        rows += f"<tr class='farm-row'><td rowspan='3' class='metric-label'>{label}</td><td class='sub-label'><strong>농가</strong></td>"
        rows += "".join(f"<td class='num'><strong>{_fmt1(v)}</strong></td>" for v in farm_vals) + "</tr>"
        rows += "<tr><td class='sub-label'>전국</td>" + "".join(f"<td class='num'>{_fmt1(v)}</td>" for v in nat_vals) + "</tr>"
        rows += "<tr class='diff-row'><td class='sub-label'>차이</td>" + "".join(_diff_cell(v) for v in diff_vals) + "</tr>"
    return f"""<table class="page1-table">
    <colgroup><col style="width:18%;"><col style="width:14%;"><col style="width:17%;"><col style="width:17%;"><col style="width:17%;"><col style="width:17%;"></colgroup>
    <thead><tr><th>지표</th><th>구분</th><th>2023</th><th>2024</th><th>2025</th><th>2026</th></tr></thead>
    <tbody>{rows}</tbody>
    </table>"""

def _build_page2_table(gdf, gender_key, NATIONAL_STATS):
    nat = NATIONAL_STATS.get(gender_key, {})
    nat_q = nat.get("grade_quality", {})
    nat_y = nat.get("grade_yield", {})
    q_groups = [("1++", ["1++"]), ("1+", ["1+"]), ("1", ["1"]), ("2", ["2"]), ("3/D", ["3", "D"]), ("1+이상", ["1++", "1+"])]
    y_groups = [("A", ["A"]), ("B", ["B"]), ("C", ["C"])]

    def group_rows(groups, nat_map, natkey_map, rowspan):
        rows = ""
        for i, (glabel, grades) in enumerate(groups):
            farm_cells, nat_cells = [], []
            for y in PRINT_REPORT_YEARS:
                ydf = gdf[gdf["slaughter_year"] == y]
                total = len(ydf)
                cnt = int(ydf["grade_quality" if natkey_map == nat_q else "grade_yield"].isin(grades).sum()) if total > 0 else 0
                pct = round(cnt * 100.0 / total, 1) if total > 0 else 0.0
                farm_cells.append(f"<td class='num'><strong>{pct}%</strong> ({cnt}두)</td>")
                nv = nat_map.get(y, {}).get(glabel)
                nat_cells.append(f"<td class='num'>{_fmt1(nv)}%</td>" if nv is not None else "<td class='num'>-</td>")
            rows += f"<tr class='farm-row'><td rowspan='2' class='metric-label'>{glabel}</td><td class='sub-label'><strong>농가</strong></td>" + "".join(farm_cells) + "</tr>"
            rows += "<tr><td class='sub-label'>전국</td>" + "".join(nat_cells) + "</tr>"
        return rows

    # 세로 제목 칸(육질등급/육량등급)은 자기 행 + 등급별 2행씩을 덮으므로 rowspan = 등급수×2 + 1
    q_rows = group_rows(q_groups, nat_q, nat_q, 12)
    y_rows = group_rows(y_groups, nat_y, nat_y, 6)
    sample_counts = [len(gdf[gdf["slaughter_year"] == y]) for y in PRINT_REPORT_YEARS]
    sample_note = " / ".join(f"{y}년 {c}두" for y, c in zip(PRINT_REPORT_YEARS, sample_counts))

    return sample_note, f"""<table>
    <thead><tr><th style='width:24px;'></th><th>등급</th><th>구분</th><th>2023</th><th>2024</th><th>2025</th><th>2026</th></tr></thead>
    <tbody>
    <tr><td rowspan='13' style='writing-mode:vertical-rl; text-align:center; font-weight:bold; background:#EFEFEF; width:24px;'>육질등급</td></tr>
    {q_rows}
    <tr><td rowspan='7' style='writing-mode:vertical-rl; text-align:center; font-weight:bold; background:#EFEFEF; width:24px;'>육량등급</td></tr>
    {y_rows}
    </tbody>
    </table>"""

def build_print_comparison_report_html(farm_name, farm_id, conn, NATIONAL_STATS):
    """기존 종합컨설팅 최종보고서와 동일한 A4 3페이지 인쇄용 출하성적 비교 리포트 생성 (전국 대비, 2023~2026)"""
    all_df = pd.read_sql_query("""
        SELECT gender, slaughter_year, carcass_weight, bms, backfat, ribeye, month_age, grade_quality, grade_yield
        FROM shipment_records WHERE farm_id = ?
    """, conn, params=(farm_id,))

    page1_sections = ""
    page2_sections = ""
    for gkey, glabel in PRINT_REPORT_GENDERS:
        gdf = all_df[all_df["gender"] == gkey]
        page1_sections += f"<h2>{glabel} — 연도별 도체 성적 요약 (농가 vs 전국)</h2>{_build_page1_table(gdf, gkey, NATIONAL_STATS)}<div style='height:12px;'></div>"
        sample_note, table_html = _build_page2_table(gdf, gkey, NATIONAL_STATS)
        page2_sections += f"""<div style="display:flex; justify-content:space-between; align-items:flex-end; margin:10px 0 4px 0;">
        <h2 style="margin:0;">{glabel} — 연도별 육질·육량등급 출현율 (농가 vs 전국)</h2>
        <span class="note" style="margin:0;">표본두수: {sample_note}</span>
        </div>{table_html}<div style='height:12px;'></div>"""

    # 3페이지: 달성률 차트 (최근 데이터가 있는 연도, 거세우 기준)
    steer_df = all_df[all_df["gender"] == "거세"]
    chart_year = None
    for y in reversed(PRINT_REPORT_YEARS):
        if not steer_df[steer_df["slaughter_year"] == y].empty:
            chart_year = y
            break

    achievement = [100, 100, 100, 100, 100]
    chart_labels = ["도체중 (kg)", "근내지방도 (BMS)", "등지방두께 (mm)", "등심단면적 (cm²)", "평균출하월령 (개월)"]
    if chart_year:
        ydf = steer_df[steer_df["slaughter_year"] == chart_year]
        nat = NATIONAL_STATS.get("거세", {})
        cols_keys = [("carcass_weight", "도체중"), ("bms", "BMS"), ("backfat", "등지방"), ("ribeye", "단면적"), ("month_age", "출하월령")]
        achievement = []
        for col, natkey in cols_keys:
            fv = ydf[col].mean() if ydf[col].notna().any() else None
            nv = nat.get(natkey, {}).get(chart_year)
            achievement.append(round(fv / nv * 100, 1) if (fv is not None and nv) else 0)

    year_label = f"{chart_year}년" if chart_year else "데이터 없음"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{farm_name} 농가 출하성적 비교 리포트 (방문용)</title>
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
@page {{ size: A4; margin: 8mm; }}
* {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ font-family: 'Pretendard', "Malgun Gothic", sans-serif; color:#1E293B; margin:0; padding:0; font-size:12px; line-height:1.3; background-color: #F8FAFC; }}
.page {{ width:100%; max-width: 750px; min-height: 1000px; margin: 0 auto 24px auto; background: #FFFFFF; padding: 20px 30px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03); border-radius: 8px; page-break-after: always; display: flex; flex-direction: column; justify-content: center; }}
.page:last-child {{ page-break-after: auto; }}
h1 {{ font-size:18px; margin:0 0 2px 0; color:#0F172A; font-weight: 700; letter-spacing: -0.5px; }}
h2 {{ font-size:14px; margin:10px 0 4px 0; border-left:4px solid #16A34A; padding-left:8px; color:#1E293B; font-weight: 600; }}
.subtitle {{ color:#64748B; margin:0 0 8px 0; font-size:11.5px; font-weight: 400; }}
table {{ width:100%; border-collapse: separate; border-spacing: 0; margin-bottom:6px; font-size:11.5px; border: 1px solid #E2E8F0; border-radius: 6px; overflow: hidden; }}
th, td {{ border-bottom:1px solid #E2E8F0; border-right:1px solid #E2E8F0; padding:2px 3px; text-align:center; }}
th {{ background:#F1F5F9; font-weight:600; color: #334155; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }}
th:last-child, td:last-child {{ border-right: none; }}
tr:last-child td {{ border-bottom: none; }}
.metric-label {{ font-weight:600; background:#F8FAFC; vertical-align:middle; color: #1E293B; }}
.sub-label {{ color:#64748B; font-size: 11px; }}
.num {{ text-align:center; font-weight:500; }}
.diff-pos {{ color:#EF4444; font-weight:600; background: #FEF2F2; }}
.diff-neg {{ color:#3B82F6; font-weight:600; background: #EFF6FF; }}
.farm-row td {{ background:#FFFFFF; padding-top:4px; padding-bottom:4px; }}
.farm-row strong {{ font-size:1.1em; color:#0F172A; font-weight: 700; }}
.note {{ font-size:11px; color:#94A3B8; margin:2px 0 8px 0; font-style: italic; }}
.page1-table {{ margin-top: 5px; margin-bottom: 9px; }}
.page1-table th, .page1-table td {{ padding-top: 4.5px; padding-bottom: 4.5px; font-size: 11.5px; }}
.page1-table .farm-row td {{ padding-top: 5.5px; padding-bottom: 5.5px; font-size: 11.5px; }}
@media print {{ body {{ background-color: #FFFFFF !important; }} .page {{ box-shadow: none !important; margin: 0 !important; border: none !important; min-height: auto !important; }} }}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.0.0"></script>
</head>
<body>

<div class="page">
  <h1>{farm_name} 농가 출하성적 비교 리포트 — 연도별 도체 성적 요약</h1>
  <p class="subtitle">대구축협 현장컨설팅 · 2023~2026년(2026년은 누계) · 축산물품질평가원 전국 통계 대비</p>
  {page1_sections}
</div>

<div class="page" style="page-break-before: always; break-before: page;">
  <h1>{farm_name} 농가 출하성적 비교 리포트 — 연도별 등급 출현율 요약</h1>
  <p class="subtitle">대구축협 현장컨설팅 · 2023~2026년 · 축산물품질평가원 전국 통계 대비</p>
  {page2_sections}
</div>

<div class="page" style="page-break-before: always; break-before: page; justify-content: flex-start; padding-top: 1cm;">
  <h1>{farm_name} 농가 출하성적 비교 리포트 — 거세우 전국 대비 달성률</h1>
  <p class="subtitle">※ 수취금액(수익성) 분석은 출하가격 데이터가 확보되는 대로 추가 예정입니다.</p>
  <h2>{farm_name} 농가 출하성적 전국 비교 차트 ({year_label} 거세우 기준)</h2>
  <div style="height:440px; margin-top:10px; text-align:center;">
    <canvas id="compareChart" width="560" height="420" style="display:inline-block;"></canvas>
  </div>
</div>

<script>
Chart.register(ChartDataLabels);
const ctx = document.getElementById('compareChart').getContext('2d');
new Chart(ctx, {{
  type: 'bar',
  data: {{
    labels: {json.dumps(chart_labels, ensure_ascii=False)},
    datasets: [
      {{
        type: 'bar',
        label: '농가 달성률(%)',
        data: {json.dumps(achievement)},
        backgroundColor: 'rgba(22, 163, 74, 0.85)',
        borderRadius: 4,
        barPercentage: 0.55
      }},
      {{
        type: 'line',
        label: '전국 평균(=100%)',
        data: [100, 100, 100, 100, 100],
        borderColor: '#94A3B8',
        borderDash: [6, 4],
        borderWidth: 2,
        pointRadius: 0,
        fill: false
      }}
    ]
  }},
  options: {{
    responsive: false,
    animation: false,
    plugins: {{
      datalabels: {{
        anchor: 'end',
        align: 'top',
        formatter: (value, context) => context.dataset.type === 'line' ? null : value + '%',
        font: {{ weight: 'bold' }},
        color: '#16A34A'
      }}
    }},
    scales: {{
      y: {{ beginAtZero: true, suggestedMax: 135, ticks: {{ callback: (v) => v + '%' }} }}
    }}
  }}
}});
</script>
</body>
</html>"""
