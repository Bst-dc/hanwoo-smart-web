# -*- coding: utf-8 -*-
"""
한우 스마트 컨설팅 통합 웹 플랫폼 (한우컨설팅일지 정밀 양식 연동판)
Streamlit Cloud 배포용 (https://hanwoo-smart-web-rfkwappjmj7yr4xv6ahuwes.streamlit.app/)
"""
import streamlit as st
import pandas as pd
import sqlite3
import os
import json
import re
import base64
import hashlib
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import markdown as md_lib
import anthropic
import db_adapter
import db_schema

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 디자인 CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="한우 스마트 컨설팅 시스템",
    page_icon="🐂",
    layout="wide",
    initial_sidebar_state="auto"
)

# 모던 스타일 커스텀 CSS
st.markdown("""
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/wanteddev/wanted-sans@v1.0.3/packages/wanted-sans/fonts/webfonts/variable/split/WantedSansVariable.min.css">
<style>
    /* =========================================================================
       디자인 토큰 — 세이지그린 · 크림 팔레트 ("한우 컨설팅 대시보드 v1" 목업 반영)
       - 강조색은 세이지그린(브랜드) 하나로 통일한다. 초록/적갈은 장식이 아니라
         손익 부호(+/-)를 나타낼 때만 쓴다.
       - 모서리 반경은 3단계만 쓴다: sm=배지/입력, md=버튼/메뉴, lg=카드/헤더
       ========================================================================= */
    :root {
        --brand-900: #2B2B28;
        --brand-800: #5E7F66;
        --brand-700: #4A6F8A;
        --brand-500: #5E6F55;
        --brand-50:  #E6EFE3;

        --ink-900: #2B2B28;
        --ink-700: #4A4741;
        --ink-500: #77726A;
        --ink-400: #8F897E;
        --line:    #E4DBCB;
        --surface: #FBF8F2;
        --tint:      #E6EFE3;
        --tint-line: #CFDCCB;
        --tint-hover: #DCE8D8;

        /* 손익 표기 전용(장식 금지). 밝은 배경에서 WCAG AA를 통과하는 농도로 잡는다 */
        --pos: #3F6B46;
        --neg: #9A4F3A;

        --r-sm: 10px;
        --r-md: 14px;
        --r-lg: 18px;
    }

    html, body, [class*="css"] {
        font-family: 'Wanted Sans Variable', 'Pretendard', system-ui, sans-serif;
    }
    [data-testid="stAppViewContainer"], .stApp {
        background:
            radial-gradient(1200px 700px at 0% 0%, #B0CDB7 0%, transparent 60%),
            radial-gradient(1000px 800px at 100% 100%, #ABC4D8 0%, transparent 60%),
            linear-gradient(135deg, #C6D8C3 0%, #C0D2DF 100%);
        background-attachment: fixed;
        color: var(--ink-900);
    }
    [data-testid="stHeader"] { background: transparent; }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(166,198,174,.8) 0%, rgba(160,186,210,.8) 100%);
        border-right: 1px solid #C9D6D2;
    }
    [data-testid="stSidebarUserContent"] {
        padding: 28px 10px 24px 10px;
    }
    /* 핸드오프 스펙의 포커스 표시 */
    *:focus-visible { outline: 2px solid var(--brand-500); outline-offset: 2px; }

    /* ===== 페이지 머리글 (핸드오프 스펙: 키커 → H1 → 설명 → 구분선) =====
       메인 영역에는 색 밴드를 두지 않는다. 브랜드 표시는 사이드바가 전담하고,
       본문 상단은 지금 보고 있는 화면이 무엇인지만 알려준다. */
    .page-header {
        display: flex;
        flex-direction: column;
        gap: 12px;
        padding-bottom: 32px;
        margin-bottom: 8px;
        border-bottom: 1px solid #DDD3C2;
    }
    .page-kicker {
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.04em;
        color: var(--brand-500);
    }
    .page-header h1.page-title {
        margin: 0 !important;
        padding: 0 !important;
        font-size: clamp(28px, 4vw, 40px) !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em;
        line-height: 1.2 !important;
        color: var(--ink-900) !important;
        word-break: keep-all;
    }
    .page-header p.page-desc {
        margin: 0 !important;
        font-size: 15px !important;
        line-height: 1.6 !important;
        color: var(--ink-500) !important;
        max-width: 68ch;
        word-break: keep-all;
    }
    /* st.subheader도 같은 체계로 끌어온다 (제목 스타일이 두 종류로 갈리던 문제).
       data-testid는 h3이 아니라 부모 div에 붙는다. */
    div[data-testid="stHeadingWithActionElements"] h3 {
        font-size: clamp(1.05rem, 0.95rem + 0.5vw, 1.3rem) !important;
        font-weight: 700 !important;
        color: var(--ink-900) !important;
        letter-spacing: -0.01em;
        padding: 0 0 0 11px !important;
        border-left: 3px solid var(--brand-800);
        line-height: 1.45 !important;
    }

    /* ===== 숫자 정렬: 자릿수가 흔들리지 않게 고정폭 숫자 사용 ===== */
    div[data-testid="stMetricValue"] {
        font-variant-numeric: tabular-nums;
        font-weight: 700;
        color: var(--ink-900);
        letter-spacing: -0.01em;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: 0.82rem !important;
        font-weight: 600;
        color: var(--ink-500) !important;
    }
    /* KPI를 허공에 띄우지 않고 한 덩어리로 묶는다.
       delta(증감 배지)가 있는 카드만 한 줄 더 길어져서 높이가 어긋나므로,
       delta 유무와 무관하게 모든 카드가 같은 높이를 갖도록 min-height로 고정한다.
       (height:100%는 Streamlit의 중간 래퍼 div들이 높이를 상속하지 않아 무효했음) */
    div[data-testid="stMetric"] {
        background: var(--tint);
        border: 1px solid var(--tint-line);
        border-radius: var(--r-md);
        padding: 14px 16px;
        min-height: 135px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 4px 6px -1px rgba(60, 55, 40, 0.05), 0 2px 4px -1px rgba(60, 55, 40, 0.03);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 24px -14px rgba(60, 55, 40, 0.35);
        border-color: #A9B39C;
    }
    table, .stDataFrame, div[data-testid="stTable"] { font-variant-numeric: tabular-nums; }

    .card {
        background: var(--surface);
        padding: 20px;
        border-radius: var(--r-lg);
        border: 1px solid var(--line);
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(60, 55, 40, 0.05), 0 2px 4px -1px rgba(60, 55, 40, 0.03);
    }
    .kpi-badge {
        background-color: var(--brand-50);
        color: var(--brand-800);
        padding: 4px 10px;
        border-radius: var(--r-sm);
        font-weight: 600;
        font-size: 0.85rem;
    }
    .profit-plus  { color: var(--pos); font-weight: 700; font-size: 1.2rem; font-variant-numeric: tabular-nums; }
    .profit-minus { color: var(--neg); font-weight: 700; font-size: 1.2rem; font-variant-numeric: tabular-nums; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { height: 45px; font-weight: 600; font-size: 0.95rem; border-radius: var(--r-sm) var(--r-sm) 0 0; }

    /* ===== 사이드바 브랜드 블록 =====
       카드로 감싸지 않는다. 그라디언트는 44px 아이콘 박스만 쓰고 글자는 먹색으로 둔다. */
    .sb-brand {
        display: flex;
        align-items: center;
        gap: 14px;
        margin: 0 0 4px 0;
    }
    .sb-brand-mark {
        flex: 0 0 auto;
        width: 44px;
        height: 44px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, var(--brand-800) 0%, var(--brand-700) 100%);
        border-radius: var(--r-md);
    }
    .sb-brand-mark svg { width: 34px; height: 34px; }
    .sb-brand-body { min-width: 0; }
    .sb-brand-org {
        display: block;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.08em;
        color: #6E7A64;
        margin-bottom: 2px;
    }
    .sb-brand-name {
        font-size: 17px;
        font-weight: 700;
        color: var(--ink-900);
        letter-spacing: -0.01em;
        line-height: 1.3;
    }
    .sb-brand-desc {
        font-size: 12px;
        line-height: 1.5;
        color: var(--ink-500);
        margin-top: 2px;
    }

    /* ===== 컨설팅 프로세스 내비게이션 ===== */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] label[data-testid="stWidgetLabel"] p {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.08em;
        color: var(--ink-400);
        margin-bottom: 10px;
    }
    /* 농가 선택 라벨 / 셀렉트: 사이드바는 본문보다 한 톤 따뜻한 베이지를 쓴다 */
    section[data-testid="stSidebar"] label[data-testid="stWidgetLabel"] p {
        font-size: 12px;
        font-weight: 500;
        color: var(--ink-500);
    }
    section[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
        background-color: #F8F4EC !important;
    }
    /* '＋ 신규 농가 등록'은 스펙상 점선 테두리 버튼이다 (Streamlit expander로 구현돼 있음) */
    section[data-testid="stSidebar"] div[data-testid="stExpander"] {
        border: 1px dashed #A9B39C !important;
        background: transparent !important;
        border-radius: var(--r-sm) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stExpander"] summary {
        color: var(--brand-500);
        font-weight: 500;
    }
    section[data-testid="stSidebar"] div[data-testid="stExpander"] summary:hover {
        background-color: #E3E6D9;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] {
        display: flex;
        flex-direction: column;
        gap: 5px;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label {
        display: flex;
        align-items: center;
        min-height: 44px;
        padding: 11px 14px;
        border-radius: var(--r-sm);
        color: var(--ink-700);
        font-weight: 400;
        cursor: pointer;
        transition: background-color 0.25s ease, color 0.25s ease;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
        background-color: #E3E6D9;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-selected="true"],
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
        background: linear-gradient(135deg, var(--brand-800) 0%, var(--brand-700) 100%);
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) div[data-testid="stMarkdownContainer"] p {
        color: #F4EFE6;
        font-weight: 600;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label > div > div:first-child {
        display: none;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] p {
        font-size: 0.93rem;
        letter-spacing: -0.01em;
        margin: 0;
    }

    /* ===== 사이드바 푸터 (담당자 표기) ===== */
    .sb-foot {
        border-top: 1px solid var(--line);
        margin-top: 6px;
        padding-top: 13px;
    }
    .sb-foot-role {
        font-size: 0.66rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        color: var(--ink-400);
    }
    .sb-foot-name {
        font-size: 0.92rem;
        font-weight: 700;
        color: var(--ink-700);
        margin-top: 3px;
    }
    .sb-foot-note {
        font-size: 0.72rem;
        line-height: 1.55;
        color: var(--ink-400);
        margin-top: 5px;
    }

    /* ===== 본문 영역 가로 라디오(거세우/암소 등) — 세그먼트 필 버튼 ===== */
    section[data-testid="stMain"] div[role="radiogroup"] {
        display: inline-flex;
        gap: 4px;
        padding: 4px;
        background: #EDE6D9;
        border-radius: 999px;
    }
    section[data-testid="stMain"] div[role="radiogroup"] label {
        border-radius: 999px;
        padding: 7px 18px;
        transition: background-color 0.2s ease, color 0.2s ease;
    }
    section[data-testid="stMain"] div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] p {
        font-weight: 500;
        color: var(--ink-700);
    }
    section[data-testid="stMain"] div[role="radiogroup"] label:has(input:checked) {
        background: var(--ink-900);
    }
    section[data-testid="stMain"] div[role="radiogroup"] label:has(input:checked) div[data-testid="stMarkdownContainer"] p {
        color: #F4EFE6;
        font-weight: 600;
    }
    section[data-testid="stMain"] div[role="radiogroup"] label > div > div:first-child { display: none; }

    /* ===== 접기/펼치기 패널(누락 데이터 명단 등) — 카드형 아코디언 ===== */
    div[data-testid="stExpander"] {
        border: 1px solid var(--line) !important;
        border-radius: var(--r-md) !important;
        background: var(--surface);
        overflow: hidden;
    }
    div[data-testid="stExpander"] summary {
        font-weight: 600;
        color: var(--ink-900);
    }
    div[data-testid="stExpander"] summary:hover {
        background-color: #EDE6D9;
    }

    /* ===== 입력 요소 표면 — BaseWeb이 흰색을 직접 지정하는 날짜/숫자 입력까지 아이보리로 ===== */
    input:not([type="checkbox"]):not([type="radio"]), textarea {
        background-color: var(--surface) !important;
    }

    /* ===== 입력칸 테두리 =====
       Streamlit은 입력칸 테두리색을 테마의 backgroundColor에서 뽑아 쓴다. 배경과 같은 색이라
       현장조사처럼 입력이 수십 개 나열되는 화면에서 칸 경계가 전혀 보이지 않는다 → 직접 지정한다. */
    [data-testid="stTextInputRootElement"],
    [data-testid="stTextAreaRootElement"],
    [data-testid="stNumberInputContainer"],
    [data-testid="stDateInputField"],
    [data-testid="stFileUploaderDropzone"],
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stMultiSelect"] > div > div {
        border: 1px solid #D6CCBA !important;
        background-color: var(--surface) !important;
    }
    [data-testid="stTextInputRootElement"]:focus-within,
    [data-testid="stTextAreaRootElement"]:focus-within,
    [data-testid="stNumberInputContainer"]:focus-within,
    [data-testid="stDateInputField"]:focus-within,
    [data-testid="stSelectbox"] > div > div:focus-within,
    [data-testid="stMultiSelect"] > div > div:focus-within {
        border-color: var(--brand-500) !important;
        box-shadow: 0 0 0 3px rgba(94, 111, 85, 0.14);
    }

    /* ===== 탭/버튼 기본 색 정리 ===== */
    .stTabs [data-baseweb="tab"][aria-selected="true"] { color: var(--brand-800); }
    .stTabs [data-baseweb="tab-highlight"] { background-color: var(--brand-500) !important; }
    button[kind="primary"] {
        background-color: var(--brand-800) !important;
        border-color: var(--brand-800) !important;
    }

    /* ===== 모바일 (현장에서 폰으로 쓰는 경우가 기본) ===== */
    @media (max-width: 640px) {
        .page-header {
            gap: 8px;
            padding-bottom: 20px;
        }
        div[data-testid="stMetric"] { padding: 12px 13px; }
    }

    /* ===== 모션: 상태 전환에만 쓰고, 줄이기 설정을 존중한다 ===== */
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            animation-duration: 0.001ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.001ms !important;
        }
    }
</style>
""", unsafe_allow_html=True)


def cow_mark(size: int = 64) -> str:
    """한우(브라운) 캐릭터 마크. 외부 이미지 의존이 없도록 인라인 SVG로 그린다."""
    return f"""<svg viewBox="0 0 72 72" width="{size}" height="{size}" role="img" aria-label="한우" style="display:block;">
    <g transform="translate(0,7)">
        <ellipse cx="21" cy="17.5" rx="3.4" ry="6" transform="rotate(-48 21 17.5)" fill="#f5e2bd"/>
        <ellipse cx="51" cy="17.5" rx="3.4" ry="6" transform="rotate(48 51 17.5)" fill="#f5e2bd"/>
        <ellipse cx="14" cy="30" rx="9" ry="5.6" transform="rotate(-20 14 30)" fill="#a96f3e"/>
        <ellipse cx="58" cy="30" rx="9" ry="5.6" transform="rotate(20 58 30)" fill="#a96f3e"/>
        <rect x="17" y="15" width="38" height="38" rx="17" fill="#c98b52"/>
        <ellipse cx="36" cy="20" rx="8" ry="4.5" fill="#a96f3e"/>
        <ellipse cx="36" cy="43" rx="12" ry="8.4" fill="#f0dcc6"/>
        <circle cx="28.5" cy="30" r="2.7" fill="#3d2414"/>
        <circle cx="43.5" cy="30" r="2.7" fill="#3d2414"/>
        <ellipse cx="31.8" cy="43.5" rx="1.8" ry="2.4" fill="#b07d5e"/>
        <ellipse cx="40.2" cy="43.5" rx="1.8" ry="2.4" fill="#b07d5e"/>
    </g>
</svg>"""


# 차트 색상: 위 CSS 디자인 토큰과 같은 값을 쓴다 (Vega는 CSS 변수를 못 읽어서 한 벌 더 둔다)
CHART_FARM = "#5E6F55"      # 농가 실적 = 브랜드 세이지
CHART_NAT = "#B9B1A3"       # 전국 평균 = 무채색 웜그레이 (비교 기준선이라 눈에 덜 띄게)
CHART_COW = "#C98B76"
CHART_BULL = "#7F9BB0"      # 수소. 색 지정이 없으면 막대가 통째로 안 그려진다
CHART_GRID = "#E4DBCB"
CHART_LABEL = "#77726A"
CHART_MUTED = "#8F897E"
CHART_SURFACE = "#FBF8F2"
CHART_FONT = "Wanted Sans Variable, Pretendard, system-ui, sans-serif"


def page_header(title: str, desc: str = "") -> None:
    """페이지 머리글. 브랜드 표기는 사이드바가 전담하므로 본문에는 키커 한 줄만 남긴다."""
    desc_html = f"<p class='page-desc'>{desc}</p>" if desc else ""
    st.markdown(
        "<header class='page-header'>"
        "<span class='page-kicker'>대구축협 지도컨설팅 · 한우 스마트 AI 전문 플랫폼</span>"
        f"<h1 class='page-title'>{title}</h1>{desc_html}</header>",
        unsafe_allow_html=True,
    )


def style_chart(chart):
    """대시보드 차트 공통 마감. 축 선/눈금을 지우고 가로 점선 격자만 남겨, 데이터 자체가
    먼저 읽히도록 한다. Streamlit 기본 vega 테마를 끄고(st.altair_chart(theme=None)) 쓴다."""
    return (
        chart
        .properties(background='transparent')  # 카드 배경 위에 차트 판이 겹쳐 보이지 않게
        .configure_view(strokeWidth=0, fill=None)
        .configure_axis(
            labelFont=CHART_FONT, titleFont=CHART_FONT,
            labelColor=CHART_MUTED, titleColor=CHART_LABEL,
            domain=False, ticks=False, labelPadding=9, titlePadding=12,
            gridColor=CHART_GRID, gridDash=[3, 4],
        )
        .configure_legend(
            labelFont=CHART_FONT, labelColor=CHART_LABEL, labelFontSize=12,
            symbolStrokeWidth=3, symbolSize=110, padding=0, offset=14,
        )
        .configure_text(font=CHART_FONT)
    )


# -----------------------------------------------------------------------------
# 2. 데이터베이스 초기화 및 연동
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "consulting.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def using_supabase():
    """secrets(또는 환경변수)에 DATABASE_URL 이 있으면 Supabase 를 쓴다. Turso 설정보다 우선한다.
    (Supabase 로 옮긴 직후 문제가 생기면 DATABASE_URL 만 지워 Turso 로 되돌릴 수 있게 Turso 분기는 남겨 둔다)"""
    return db_adapter.enabled()

def get_db():
    import sqlite3 as std_sqlite3

    # Supabase(시험농장 앱과 같은 프로젝트, hanwoo 스키마). 어댑터가 sqlite3 처럼 동작하게 맞춰 준다.
    if using_supabase():
        return db_adapter.connect(db_schema.SCHEMA)

    # 클라우드 DB(Turso) 접속 설정이 secrets에 있으면 클라우드 연결
    if "TURSO_DATABASE_URL" in st.secrets:
        import libsql_experimental
        url = st.secrets["TURSO_DATABASE_URL"]
        token = st.secrets.get("TURSO_AUTH_TOKEN", "")
        raw_conn = libsql_experimental.connect(url, auth_token=token)
        
        class Sqlite3Row:
            """sqlite3.Row 흉내 — 이름/위치 양쪽으로 접근되고, 순회하면 '값'이 나온다.

            dict을 상속하면 안 된다. dict은 순회할 때 값이 아니라 '키'를 내주기 때문에
            pandas.read_sql_query 가 모든 칸을 컬럼명으로 채워버린다. 예외도 안 나고
            행 수도 맞아서 눈치채기 어려운 조용한 데이터 오염이 된다.
            keys() + __getitem__ 을 두면 dict(row) 도 그대로 동작한다.
            """
            __slots__ = ("_cols", "_values", "_map")
            def __init__(self, cols, values):
                self._cols = tuple(cols)
                self._values = tuple(values)
                self._map = dict(zip(self._cols, self._values))
            def __getitem__(self, key):
                if isinstance(key, (int, slice)): return self._values[key]
                return self._map[key]
            def keys(self): return list(self._cols)
            def get(self, key, default=None): return self._map.get(key, default)
            def __iter__(self): return iter(self._values)
            def __len__(self): return len(self._values)
            def __contains__(self, key): return key in self._map
            def __repr__(self): return f"Sqlite3Row({self._map!r})"
                
        class DictCursor:
            def __init__(self, cursor):
                self._c = cursor
            @property
            def description(self): return self._c.description
            @property
            def lastrowid(self): return self._c.lastrowid
            def execute(self, sql, params=()):
                self._c.execute(sql, params)
                return self
            def close(self):
                if hasattr(self._c, 'close'): self._c.close()
            def fetchmany(self, size=None):
                # pandas가 chunksize를 쓸 때 호출한다. libsql이 지원하지 않으면 통째로 가져온다.
                f = getattr(self._c, "fetchmany", None)
                if f is None:
                    rows = self._c.fetchall()
                else:
                    rows = f(size) if size is not None else f()
                if not rows or not self.description: return rows
                cols = [c[0] for c in self.description]
                return [Sqlite3Row(cols, row) for row in rows]
            @property
            def rowcount(self): return getattr(self._c, "rowcount", -1)
            @property
            def arraysize(self): return getattr(self._c, "arraysize", 1)
            def fetchall(self):
                rows = self._c.fetchall()
                if not rows or not self.description: return rows
                cols = [c[0] for c in self.description]
                return [Sqlite3Row(cols, row) for row in rows]
            def fetchone(self):
                row = self._c.fetchone()
                if not row or not self.description: return row
                cols = [c[0] for c in self.description]
                return Sqlite3Row(cols, row)
            def __iter__(self): return iter(self.fetchall())
        
        class DictConnection:
            def __init__(self, c): self._c = c
            def execute(self, sql, params=()): return DictCursor(self._c.execute(sql, params))
            def cursor(self): return DictCursor(self._c.cursor())
            def commit(self): self._c.commit()
            def rollback(self):
                # pandas는 쿼리 실패 시 conn.rollback()을 부른다. 없으면 진짜 오류가 가려진다.
                r = getattr(self._c, "rollback", None)
                if r: r()
            def close(self): pass
            
        conn = DictConnection(raw_conn)
    else:
        # 설정이 없으면 기존처럼 로컬 파일 DB 연결 (백업/개발용)
        conn = std_sqlite3.connect(DB_PATH)
        conn.row_factory = std_sqlite3.Row
        
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except:
        pass
    return conn

def init_db():
    if using_supabase():
        # Postgres 표 정의는 db_schema.py 에 따로 있다 (아래 SQLite 정의·마이그레이션은 Turso/로컬 파일용)
        db_adapter.ensure_schema(db_schema.SCHEMA, db_schema.PG_DDL,
                                 required_tables=db_schema.TABLES, required_columns=db_schema.REQUIRED_COLUMNS)
        return
    conn = get_db()
    c = conn.cursor()
    # 1. 농가 마스터
    c.execute("""
    CREATE TABLE IF NOT EXISTS farms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farm_code TEXT UNIQUE,
        farm_name TEXT NOT NULL,
        owner_name TEXT,
        phone TEXT,
        address TEXT,
        region TEXT,
        full_time TEXT DEFAULT '전업',
        side_job TEXT,
        breeding_type TEXT DEFAULT '비육우',
        total_heads INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # farms 테이블 자동 컬럼 마이그레이션
    c.execute("PRAGMA table_info(farms)")
    farm_cols = [row[1] for row in c.fetchall()]
    for col in ["region", "full_time", "side_job"]:
        if col not in farm_cols:
            c.execute(f"ALTER TABLE farms ADD COLUMN {col} TEXT")

    # 2. 방문 이력
    c.execute("""
    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farm_id INTEGER NOT NULL,
        visit_number INTEGER NOT NULL DEFAULT 1,
        visit_date DATE NOT NULL,
        consultant_name TEXT,
        status TEXT DEFAULT 'completed',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farm_id) REFERENCES farms (id) ON DELETE CASCADE
    );
    """)
    # 3. 한우컨설팅일지 정밀 현장조사표
    c.execute("""
    CREATE TABLE IF NOT EXISTS field_surveys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visit_id INTEGER UNIQUE NOT NULL,
        facility_info TEXT,  -- JSON: 비육우방/번식우방/송아지우방 크기 및 밀도
        feed_info TEXT,      -- JSON: 급여순서, 횟수, 단계별 품목 및 급여수준
        consult_notes TEXT,  -- 농가 상담 내용 및 특이사항
        consultant_memo TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (visit_id) REFERENCES visits (id) ON DELETE CASCADE
    );
    """)
    # field_surveys 테이블 마이그레이션
    c.execute("PRAGMA table_info(field_surveys)")
    survey_cols = [row[1] for row in c.fetchall()]
    for col in ["facility_info", "feed_info", "consult_notes", "consultant_memo", "survey_data"]:
        if col not in survey_cols:
            c.execute(f"ALTER TABLE field_surveys ADD COLUMN {col} TEXT")

    # 4. 개체별 출하성적
    c.execute("""
    CREATE TABLE IF NOT EXISTS shipment_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farm_id INTEGER NOT NULL,
        animal_no TEXT UNIQUE NOT NULL,  -- 이력번호는 소 한 마리에 하나 (운영 DB와 같은 기준, 저장 시 ON CONFLICT(animal_no))
        gender TEXT NOT NULL,
        slaughter_date DATE,
        slaughter_year INTEGER,
        month_age REAL,
        carcass_weight REAL,
        grade_quality TEXT,
        grade_yield TEXT,
        bms REAL,
        backfat REAL,
        ribeye REAL,
        price_per_kg INTEGER,
        total_price INTEGER,
        data_source TEXT DEFAULT 'manual',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farm_id) REFERENCES farms (id) ON DELETE CASCADE
    );
    """)
    # 5. AI 리포트
    # UNIQUE(visit_id, report_mode): 같은 방문이라도 전문/일반 리포트를 각각 1개씩 보관한다.
    # (예전엔 visit_id만 UNIQUE라 일반으로 다시 만들면 전문 리포트가 사라졌다)
    c.execute("""
    CREATE TABLE IF NOT EXISTS ai_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visit_id INTEGER NOT NULL,
        report_type TEXT DEFAULT 'final', -- previsit / final
        report_mode TEXT NOT NULL DEFAULT '일반', -- 전문(전문자료 기반) / 일반
        full_markdown TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (visit_id) REFERENCES visits (id) ON DELETE CASCADE,
        UNIQUE(visit_id, report_mode)
    );
    """)
    c.execute("PRAGMA table_info(ai_reports)")
    report_cols = [row[1] for row in c.fetchall()]
    if "report_type" not in report_cols:
        c.execute("ALTER TABLE ai_reports ADD COLUMN report_type TEXT DEFAULT 'final'")
    # 생성 시각 컬럼명을 created_at으로 통일한다. 한때 이 코드가 generated_at으로 만들었는데
    # 화면(데이터 관리 메뉴)은 created_at을 조회해서, 그 시기에 새로 만든 DB에서는 메뉴가 오류로 멈췄다.
    # (ALTER ADD COLUMN은 CURRENT_TIMESTAMP 기본값을 못 받으므로 저장 시 created_at을 직접 넣는다)
    if "created_at" not in report_cols:
        c.execute("ALTER TABLE ai_reports ADD COLUMN created_at DATETIME")
        if "generated_at" in report_cols:
            c.execute("UPDATE ai_reports SET created_at = generated_at")

    # 전문/일반 리포트를 각각 보관하도록 UNIQUE 제약을 (visit_id) → (visit_id, report_mode)로 바꾼다.
    # SQLite는 ALTER TABLE로 제약을 못 고치므로 새 표를 만들어 옮기는 수밖에 없다.
    # (기존 행은 전문/일반 구분이 생기기 전에 만들어져 어느 쪽인지 알 수 없다 → '일반'으로 둔다.
    #  같은 방문을 일반 모드로 다시 만들면 그 행을 덮어쓰는데, 이는 동일 모드 재생성이라 맞는 동작이다)
    if "report_mode" not in report_cols:
        c.execute("PRAGMA foreign_keys = OFF")  # 표 재구성 중에는 꺼두는 게 SQLite 권장 절차
        c.execute("""
        CREATE TABLE ai_reports_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_id INTEGER NOT NULL,
            report_type TEXT DEFAULT 'final',
            report_mode TEXT NOT NULL DEFAULT '일반',
            full_markdown TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (visit_id) REFERENCES visits (id) ON DELETE CASCADE,
            UNIQUE(visit_id, report_mode)
        );
        """)
        c.execute("""
        INSERT INTO ai_reports_new (id, visit_id, report_type, report_mode, full_markdown, created_at)
        SELECT id, visit_id, report_type, '일반', full_markdown, created_at FROM ai_reports
        """)
        c.execute("DROP TABLE ai_reports")
        c.execute("ALTER TABLE ai_reports_new RENAME TO ai_reports")
        conn.commit()
        c.execute("PRAGMA foreign_keys = ON")

    conn.commit()
    conn.close()

init_db()

# -----------------------------------------------------------------------------
# 2-1. DB 자동 백업: 저장할 때마다 consulting.db를 GitHub 저장소에 커밋
# -----------------------------------------------------------------------------
# 원래 목적: Streamlit Cloud는 재배포될 때마다 서버 파일이 GitHub 상태로 되돌아가서,
# 배포 사이트에서 저장한 출하성적·조사표가 사라졌다. 저장 직후 DB를 GitHub에 커밋해 막았다.
# Turso로 옮긴 뒤로는 운영 데이터가 클라우드에 있어 재배포로 사라지지 않으므로,
# 이 커밋은 "되살리기 위한 수단"이 아니라 순수한 백업(스냅샷)이 되었다.
# Turso 무료 티어에는 자동 백업이 없어서 이 백업이 유일한 복구 수단이다.
# 2026-10-04 Supabase(시험농장과 같은 프로젝트, hanwoo 스키마)로 옮긴 뒤에도 그대로 쓴다 — 무료 요금제엔 내려받을 수 있는 백업이 없다.
# Secrets에 GITHUB_TOKEN(해당 저장소 Contents 쓰기 권한)이 있을 때만 동작하고, 없으면 아무것도 안 한다.
#
# 백업은 코드 저장소가 아니라 별도의 "비공개 데이터 저장소"(GITHUB_REPO, 기본 Bst-dc/hanwoo-smart-consulting)로 간다.
# 코드 저장소는 Streamlit 무료 요금제(비공개 앱 1개 제한) 때문에 공개라서, 조합원 개인정보가 든 DB를
# 거기 올리면 누구나 내려받을 수 있게 된다. 경로는 데이터 저장소 루트 기준 고정값이다.
GITHUB_DB_PATH = "data/consulting.db"
DB_BASE_SHA_PATH = os.path.join(BASE_DIR, "data", ".db_base_sha")  # 이 DB가 어느 GitHub 버전에서 출발했는지

def _secret(name, default=""):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)

def _git_blob_sha(data: bytes) -> str:
    """git이 파일을 식별하는 해시(blob SHA-1). GitHub API가 돌려주는 sha와 같은 값"""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()

def _read_base_sha():
    try:
        with open(DB_BASE_SHA_PATH, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None

def _write_base_sha(sha):
    try:
        with open(DB_BASE_SHA_PATH, "w", encoding="utf-8") as f:
            f.write(sha)
    except OSError:
        pass

# 앱이 처음 뜰 때의 DB = GitHub에서 받아온 그대로의 파일이므로, 그 해시를 출발점으로 기록해 둔다
if _read_base_sha() is None and os.path.exists(DB_PATH):
    with open(DB_PATH, "rb") as _f:
        _write_base_sha(_git_blob_sha(_f.read()))

def github_backup_enabled():
    return bool(_secret("GITHUB_TOKEN"))

def using_cloud_db():
    """앱이 클라우드 DB(Supabase 또는 Turso)에 붙어 있는지 (get_db와 같은 기준으로 판단)."""
    if using_supabase():
        return True
    try:
        return "TURSO_DATABASE_URL" in st.secrets
    except Exception:
        return False

# 백업 대상 테이블 — 외래키 순서대로 (부모가 먼저 들어가야 INSERT가 깨지지 않는다)
CLOUD_BACKUP_TABLES = ["farms", "visits", "field_surveys", "shipment_records", "ai_reports"]

def _snapshot_cloud_db():
    """Turso의 현재 내용을 SQLite 파일 바이트로 떠낸다. 반환: (bytes, None) 또는 (None, 오류문구).

    클라우드 모드에서는 로컬 data/consulting.db 가 갱신되지 않는다. 배포 환경에는 그 파일이
    아예 없어서(.gitignore 제외) 예전처럼 열면 FileNotFoundError로 앱이 통째로 멈췄고,
    설령 있더라도 옛날 데이터를 백업이라며 덮어쓰게 된다.
    → 백업할 때마다 Turso에서 읽어 그 시점의 .db 파일을 새로 만든다.

    Supabase 는 sqlite_master 에 표 정의(sql)가 없으므로, db_schema.SQLITE_DDL 로 표를 만들어 옮긴다.
    """
    import tempfile
    tmp = None
    try:
        if using_supabase():
            fd, tmp = tempfile.mkstemp(suffix=".db")
            os.close(fd)
            os.remove(tmp)
            db_adapter.export_to_sqlite(db_schema.SCHEMA, tmp, db_schema.SQLITE_DDL, db_schema.TABLES)
            with open(tmp, "rb") as f:
                return f.read(), None

        src = get_db()
        schemas, payload = [], {}
        for t in CLOUD_BACKUP_TABLES:
            r = src.cursor().execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
            if not r or not r[0]:
                continue  # 아직 만들어지지 않은 테이블은 건너뛴다
            schemas.append(r[0])
            cur = src.cursor().execute(f"SELECT * FROM {t}")
            cols = [c[0] for c in cur.description] if cur.description else []
            payload[t] = (cols, [list(row) for row in cur.fetchall()])
        src.close()

        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(tmp)  # sqlite3가 빈 파일에 새로 만들도록 비워둔다
        out = sqlite3.connect(tmp)
        for sql in schemas:
            out.execute(sql)
        for t, (cols, rows) in payload.items():
            if not rows:
                continue
            col_sql = ", ".join(f'"{c}"' for c in cols)
            out.executemany(
                f"INSERT INTO {t} ({col_sql}) VALUES ({', '.join('?' * len(cols))})", rows)
        out.commit()
        out.close()
        with open(tmp, "rb") as f:
            return f.read(), None
    except Exception as e:
        return None, f"클라우드 DB 스냅샷 실패 ({e})."
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

def db_file_bytes():
    """현재 DB 전체를 SQLite .db 파일 바이트로. 반환: (bytes, None) 또는 (None, 오류문구).
    GitHub 백업과 '데이터 관리 · 백업' 메뉴의 DB 파일 다운로드가 같이 쓴다."""
    if using_cloud_db():
        data, err = _snapshot_cloud_db()
        if err:
            return None, err + " 저장된 데이터는 클라우드에 그대로 있습니다."
        return data, None
    try:
        with open(DB_PATH, "rb") as f:
            return f.read(), None
    except OSError as e:
        return None, f"로컬 DB 파일을 읽지 못했습니다 ({e}). 저장된 데이터는 그대로입니다."

def persist_db(reason):
    """DB를 GitHub에 커밋한다. 반환: (성공 여부, 안내 문구). 토큰이 없으면 (None, 문구).

    클라우드 모드면 Turso 내용을 그때그때 파일로 떠서 올리고,
    아니면 기존처럼 로컬 data/consulting.db 를 올린다.
    """
    token = _secret("GITHUB_TOKEN")
    if not token:
        return None, "GitHub 자동 백업이 설정되지 않아 이 서버에만 저장되었습니다."
    repo = _secret("GITHUB_REPO", "Bst-dc/hanwoo-smart-consulting")
    branch = _secret("GITHUB_BRANCH", "main")
    # 경로에 한글이 들어있어 그대로 쓰면 urllib이 URL을 ASCII로 인코딩하다 터진다
    # (UnicodeEncodeError). quote는 기본으로 "/"를 남겨두므로 경로 구분자는 보존된다.
    api = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(GITHUB_DB_PATH)}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hanwoo-consulting-app",
    }
    try:
        req = urllib.request.Request(f"{api}?ref={urllib.parse.quote(branch)}", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            remote_sha = json.loads(resp.read().decode("utf-8")).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return False, f"GitHub 백업 실패 (DB 조회 {e.code}). 데이터는 이 서버에만 저장되어 있습니다."
        remote_sha = None  # 저장소에 아직 DB가 없음 → 새로 만든다
    except Exception as e:
        return False, f"GitHub 백업 실패 ({e}). 데이터는 이 서버에만 저장되어 있습니다."

    # 이 DB가 출발한 버전 이후에 누군가(다른 PC·로컬 커밋 등) GitHub의 DB를 바꿨다면 덮어쓰지 않는다.
    # 덮어쓰면 그쪽에서 저장한 데이터가 사라지기 때문
    base_sha = _read_base_sha()
    if remote_sha and base_sha and remote_sha != base_sha:
        return False, ("GitHub의 DB가 이 앱이 시작된 뒤 다른 곳에서 변경되어 자동 백업을 멈췄습니다 (덮어쓰면 그쪽 데이터가 사라짐). "
                       "'데이터 관리 · 백업' 메뉴에서 DB 파일을 내려받아 보관한 뒤 관리자에게 병합을 요청하세요.")

    # 저장 자체는 이미 끝난 뒤라, 여기서 실패해도 앱은 계속 돌아가야 한다
    data, err = db_file_bytes()
    if err:
        return False, err
    local_sha = _git_blob_sha(data)
    if remote_sha == local_sha:
        _write_base_sha(local_sha)
        return True, "GitHub DB와 이미 같습니다."

    body = {
        "message": f"data: {reason} (앱 자동 백업)",
        "content": base64.b64encode(data).decode("ascii"),
        "branch": branch,
    }
    if remote_sha:
        body["sha"] = remote_sha
    try:
        req = urllib.request.Request(api, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=30) as resp:
            new_sha = json.loads(resp.read().decode("utf-8")).get("content", {}).get("sha") or local_sha
    except urllib.error.HTTPError as e:
        if e.code in (409, 422):
            return False, "GitHub의 DB가 방금 다른 곳에서 변경되어 자동 백업을 멈췄습니다. 잠시 후 '데이터 관리 · 백업'에서 다시 시도해주세요."
        return False, f"GitHub 백업 실패 (업로드 {e.code}). 데이터는 이 서버에만 저장되어 있습니다."
    except Exception as e:
        return False, f"GitHub 백업 실패 ({e}). 데이터는 이 서버에만 저장되어 있습니다."
    _write_base_sha(new_sha)
    return True, "GitHub에 자동 백업되었습니다 (재배포되어도 유지)."

def notify_saved(message, reason):
    """저장 성공 문구 + GitHub 백업 결과를 다음 화면(st.rerun 이후)에도 보이도록 session_state에 남긴다"""
    ok, backup_msg = persist_db(reason)
    st.session_state["_flash"] = (message, ok, backup_msg)

def show_flash():
    flash = st.session_state.pop("_flash", None)
    if not flash:
        return
    message, ok, backup_msg = flash
    st.success(message)
    if ok is True:
        st.caption(f"☁️ {backup_msg}")
    elif ok is False:
        st.error(f"⚠️ {backup_msg}")
    else:
        st.caption(f"ℹ️ {backup_msg}")

# -----------------------------------------------------------------------------
# 3. KOSIS 전국 통계 및 음성공판장 경락단가 벤치마크 기준 데이터
# -----------------------------------------------------------------------------
NATIONAL_STATS = {
    "거세": {
        "도체중": {2023: 467.0, 2024: 470.6, 2025: 478.1, 2026: 490.4},
        "BMS": {2023: 6.2, 2024: 6.2, 2025: 6.3, 2026: 7.0},
        "등지방": {2023: 12.7, 2024: 12.3, 2025: 12.4, 2026: 12.5},
        "단면적": {2023: 97.7, 2024: 97.6, 2025: 100.3, 2026: 106.7},
        "출하월령": {2023: 31.1, 2024: 31.6, 2025: 31.7, 2026: 31.7},
        "grade_quality": {
            2023: {"1++": 39.1, "1+": 30.0, "1": 22.1, "2": 7.9, "3": 0.9, "1+이상": 69.1},
            2024: {"1++": 39.1, "1+": 29.8, "1": 22.1, "2": 8.2, "3": 0.9, "1+이상": 68.9},
            2025: {"1++": 41.5, "1+": 29.9, "1": 20.7, "2": 7.1, "3": 0.8, "1+이상": 71.3},
            2026: {"1++": 45.5, "1+": 28.7, "1": 19.0, "2": 6.1, "3": 0.8, "1+이상": 74.2},
        },
        "grade_yield": {
            2023: {"A": 29.3, "B": 50.9, "C": 19.7},
            2024: {"A": 32.2, "B": 49.0, "C": 18.8},
            2025: {"A": 33.6, "B": 49.6, "C": 16.7},
            2026: {"A": 33.3, "B": 50.1, "C": 16.5},
        }
    },
    "암": {
        "도체중": {2023: 366.1, 2024: 371.0, 2025: 377.3, 2026: 393.1},
        "BMS": {2023: 4.5, 2024: 4.6, 2025: 4.7, 2026: 5.0},
        "등지방": {2023: 13.0, 2024: 12.7, 2025: 12.9, 2026: 13.1},
        "단면적": {2023: 86.3, 2024: 87.2, 2025: 88.8, 2026: 96.3},
        "출하월령": {2023: 55.7, 2024: 53.4, 2025: 53.2, 2026: 53.2},
        "grade_quality": {
            2023: {"1++": 12.2, "1+": 19.9, "1": 27.2, "2": 26.2, "3": 14.6, "1+이상": 32.1},
            2024: {"1++": 14.7, "1+": 20.7, "1": 27.5, "2": 24.6, "3": 12.6, "1+이상": 35.4},
            2025: {"1++": 15.4, "1+": 21.5, "1": 27.4, "2": 23.7, "3": 12.0, "1+이상": 36.9},
            2026: {"1++": 16.4, "1+": 22.1, "1": 28.1, "2": 22.7, "3": 10.6, "1+이상": 38.5},
        },
        # reference/통계자료/품종별__성별__육질·육량등급별_출현율_20260917213854.xlsx 원본 대조. 2026년은 아직
        # 확정 통계연보가 없어(연중 진행형) 비워둠 — grade_quality 2026처럼 별도 수치가 확보되면 추가할 것.
        "grade_yield": {
            2023: {"A": 26.6, "B": 52.6, "C": 20.4},
            2024: {"A": 28.7, "B": 51.3, "C": 19.6},
            2025: {"A": 29.1, "B": 51.3, "C": 19.2},
        }
    }
}

EUMSEONG_PRICES_2025 = {
    "1++": 23038, "1+": 19590, "1": 18165, "2": 14969, "3": 12735, "등외": 10000
}

NATIONAL_PRECIP_2025 = 1325.6
WEATHER_DATA = {
  '대구': {'avgTemp':15.2, 'highTemp':37.4, 'lowTemp':-10.7, 'precip':1029.0, 'wind':2.2, 'humid':61.1, 'source':'대구 관측소 (직접)'},
  '경산': {'avgTemp':15.2, 'highTemp':37.4, 'lowTemp':-10.7, 'precip':1029.0, 'wind':2.2, 'humid':61.1, 'source':'인접 대구 관측소 값 준용'},
  '영천': {'avgTemp':14.0, 'highTemp':36.7, 'lowTemp':-11.8, 'precip':1047.7, 'wind':1.7, 'humid':67.3, 'source':'영천 관측소 (직접)'},
  '구미': {'avgTemp':14.6, 'highTemp':38.3, 'lowTemp':-11.0, 'precip':1046.5, 'wind':1.3, 'humid':65.0, 'source':'구미 관측소 (직접)'},
  '군위': {'avgTemp':13.3, 'highTemp':38.3, 'lowTemp':-17.1, 'precip':964.3,  'wind':1.1, 'humid':71.5, 'source':'인접 의성 관측소 값 준용'},
  '청도': {'avgTemp':15.1, 'highTemp':39.2, 'lowTemp':-12.0, 'precip':1314.0, 'wind':1.3, 'humid':64.3, 'source':'인접 밀양 관측소 값 준용'},
  '고령': {'avgTemp':14.6, 'highTemp':37.7, 'lowTemp':-12.7, 'precip':1580.6, 'wind':0.9, 'humid':72.2, 'source':'인접 합천 관측소 값 준용'},
  '성주': {'avgTemp':14.6, 'highTemp':38.3, 'lowTemp':-11.0, 'precip':1046.5, 'wind':1.3, 'humid':65.0, 'source':'인접 구미 관측소 값 준용'},
  '합천': {'avgTemp':14.6, 'highTemp':37.7, 'lowTemp':-12.7, 'precip':1580.6, 'wind':0.9, 'humid':72.2, 'source':'합천 관측소 (직접)'},
  '창녕': {'avgTemp':15.1, 'highTemp':39.2, 'lowTemp':-12.0, 'precip':1314.0, 'wind':1.3, 'humid':64.3, 'source':'인접 밀양 관측소 값 준용'},
  '경주': {'avgTemp':14.6, 'highTemp':37.6, 'lowTemp':-11.3, 'precip':1033.0, 'wind':2.6, 'humid':65.7, 'source':'경주 관측소 (직접)'},
  '의성': {'avgTemp':13.3, 'highTemp':38.3, 'lowTemp':-17.1, 'precip':964.3,  'wind':1.1, 'humid':71.5, 'source':'의성 관측소 (직접)'},
  '청송': {'avgTemp':12.5, 'highTemp':38.2, 'lowTemp':-18.1, 'precip':957.3,  'wind':1.9, 'humid':69.5, 'source':'청송 관측소 (직접)'},
  '안동': {'avgTemp':13.5, 'highTemp':37.6, 'lowTemp':-15.0, 'precip':887.2,  'wind':1.5, 'humid':66.0, 'source':'안동 관측소 (직접)'},
  '김천': {'avgTemp':14.6, 'highTemp':38.3, 'lowTemp':-11.0, 'precip':1046.5, 'wind':1.3, 'humid':65.0, 'source':'인접 구미 관측소 값 준용'},
  '칠곡': {'avgTemp':14.6, 'highTemp':38.3, 'lowTemp':-11.0, 'precip':1046.5, 'wind':1.3, 'humid':65.0, 'source':'인접 구미 관측소 값 준용'},
}
REGION_OPTIONS = list(WEATHER_DATA.keys()) + ['기타']

FEED_CATS = [
  {'key':'calf', 'label':'송아지'},
  {'key':'growing', 'label':'육성우'},
  {'key':'fatten1', 'label':'비육전기'},
  {'key':'fatten2', 'label':'비육후기'},
  {'key':'dam', 'label':'번식우'}
]
LEVELS = ['낮음','적정','높음']

def get_kosis_api_key():
    if "KOSIS_API_KEY" in st.secrets:
        return st.secrets["KOSIS_API_KEY"]
    local_paths = [
        os.path.join(BASE_DIR, "kosis_key.txt"),
    ]
    for p in local_paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                k = f.read().strip()
                if k: return k
    return os.environ.get("KOSIS_API_KEY", "")

@st.cache_data(ttl=86400) # 24시간마다 API 갱신 (캐시)
def fetch_kosis_national_stats():
    new_stats = {"거세": {}, "암": {}, "수": {}}
    kosis_key = get_kosis_api_key()
    if not kosis_key:
        return new_stats

    # 1. 도체성적 상세 (도체중, BMS, 등지방, 단면적)
    url1 = f"https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey={kosis_key}&itmId=13103112721T1+&objL1=ALL&objL2=ALL&objL3=ALL&objL4=&objL5=&objL6=&objL7=&objL8=&format=json&jsonVD=Y&prdSe=Y&newEstPrdCnt=10&outputFields=TBL_NM+OBJ_NM+NM+ITM_NM+UNIT_NM+PRD_SE+PRD_DE+LST_CHN_DE+&orgId=323&tblId=DT_APGS_011"
    try:
        req1 = urllib.request.urlopen(url1, timeout=10)
        data1 = json.loads(req1.read().decode('utf-8'))
        for row in data1:
            if row.get("C1_NM") != "한우": continue
            gender = row.get("C2_NM")
            if gender not in new_stats: continue
            metric = row.get("C3_NM")
            try:
                year = int(row.get("PRD_DE"))
                val = float(row.get("DT", 0))
            except: continue
            
            metric_map = {"도체중": "도체중", "근내지방": "BMS", "등지방": "등지방", "등심면적": "단면적"}
            if metric in metric_map:
                mm = metric_map[metric]
                if mm not in new_stats[gender]: new_stats[gender][mm] = {}
                new_stats[gender][mm][year] = round(val, 1)
    except: pass

    # 2. 등급 판정 두수 비율 계산 (1+이상, 육량 등)
    url2 = f"https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey={kosis_key}&itmId=13103112713T1+&objL1=ALL&objL2=ALL&objL3=ALL&objL4=&objL5=&objL6=&objL7=&objL8=&format=json&jsonVD=Y&prdSe=Y&newEstPrdCnt=10&outputFields=TBL_NM+OBJ_NM+NM+ITM_NM+UNIT_NM+PRD_SE+PRD_DE+LST_CHN_DE+&orgId=323&tblId=DT_APGS_002"
    try:
        req2 = urllib.request.urlopen(url2, timeout=10)
        data2 = json.loads(req2.read().decode('utf-8'))
        
        grade_counts = {}
        for row in data2:
            if row.get("C1_NM") != "한우": continue
            gender = row.get("C2_NM")
            if gender not in new_stats: continue
            try:
                year = int(row.get("PRD_DE"))
                val = float(row.get("DT", 0))
            except: continue
            
            grade_str = row.get("C3_NM")
            if year not in grade_counts: grade_counts[year] = {"거세": {}, "암": {}, "수": {}}
            
            if grade_str == "전체":
                grade_counts[year][gender]["total"] = val
            elif len(grade_str) >= 2 and grade_str not in ["등외", "D"]:
                q_grade = grade_str[:-1] # "1++", "1+", "1", "2", "3"
                y_grade = grade_str[-1]  # "A", "B", "C"
                
                grade_counts[year][gender][q_grade] = grade_counts[year][gender].get(q_grade, 0) + val
                grade_counts[year][gender][y_grade] = grade_counts[year][gender].get(y_grade, 0) + val
                
        for year, genders in grade_counts.items():
            for gender, counts in genders.items():
                total = counts.get("total", 0)
                if total > 0:
                    if "grade_quality" not in new_stats[gender]: new_stats[gender]["grade_quality"] = {}
                    if "grade_yield" not in new_stats[gender]: new_stats[gender]["grade_yield"] = {}
                    
                    one_pp = counts.get("1++", 0)
                    one_p = counts.get("1+", 0)
                    
                    # NATIONAL_STATS와 같은 [연도][등급] 구조로 만든다 (예전엔 [등급][연도]라 병합돼도 조회되지 않았음)
                    gq = {q: round((counts.get(q, 0) / total) * 100, 1) for q in ["1++", "1+", "1", "2", "3"]}
                    gq["1+이상"] = round(((one_pp + one_p) / total) * 100, 1)
                    new_stats[gender]["grade_quality"][year] = gq
                    new_stats[gender]["grade_yield"][year] = {y: round((counts.get(y, 0) / total) * 100, 1) for y in ["A", "B", "C"]}
    except: pass
    
    return new_stats if any(new_stats.values()) else None

# KOSIS API로 최신 통계 조회 후 NATIONAL_STATS 덮어쓰기/추가 (런타임 동적 업데이트)
kosis_live_data = fetch_kosis_national_stats()
if kosis_live_data:
    for gender, metrics in kosis_live_data.items():
        if gender in NATIONAL_STATS:
            for metric, years_data in metrics.items():
                if metric in NATIONAL_STATS[gender]:
                    # update existing dict with new years
                    NATIONAL_STATS[gender][metric].update(years_data)
                else:
                    NATIONAL_STATS[gender][metric] = years_data

# 사용자 수동 보정 (요청사항: 26년 전국 BMS 6.5)
if "BMS" in NATIONAL_STATS.get("거세", {}):
    NATIONAL_STATS["거세"]["BMS"][2026] = 6.5

def nat_latest_year(gender_key, metric="도체중"):
    """전국 통계에서 해당 성별·지표의 가장 최근 연도(올해 이하)를 돌려준다. 없으면 None"""
    years = [y for y in NATIONAL_STATS.get(gender_key, {}).get(metric, {}) if isinstance(y, int) and y <= datetime.now().year]
    return max(years) if years else None

# -----------------------------------------------------------------------------
# 4. 축평원(ekape) OpenAPI 연동
# -----------------------------------------------------------------------------
def get_ekape_api_key():
    if "EKAPE_API_KEY" in st.secrets:
        return st.secrets["EKAPE_API_KEY"]
    local_paths = [
        os.path.join(BASE_DIR, "ekape_key.txt"),
    ]
    for p in local_paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                k = f.read().strip()
                if k: return k
    return os.environ.get("EKAPE_API_KEY", "")

def normalize_animal_no(value):
    """이력번호를 12자리 문자열로 정규화한다.
    - "002 1531 7717 0", "002-1531-7717-0"처럼 띄어 쓰거나 "-"로 구분해도 한 덩어리로 붙인다.
    - 엑셀이 숫자로 읽어 앞자리 "00"이 떨어진 값(2019416036, 2019416036.0)도 12자리로 되살린다.
    값이 비어 있으면 빈 문자열을 돌려준다."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = re.sub(r"[\s\-]", "", str(value))
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    if s.isdigit() and len(s) < 12:
        s = s.zfill(12)
    return s

def fetch_cattle_grade(animal_no):
    animal_no = normalize_animal_no(animal_no)
    ekape_key = get_ekape_api_key()
    if not ekape_key:
        return None
    try:
        url1 = f"http://data.ekape.or.kr/openapi-data/service/user/grade/confirm/issueNo?animalNo={animal_no}&ServiceKey={ekape_key}"
        req1 = urllib.request.urlopen(url1, timeout=6)
        xml1 = req1.read().decode('utf-8')
        root1 = ET.fromstring(xml1)
        issue_node = root1.find('.//issueNo')
        if issue_node is None or not issue_node.text: return None
        issue_no = issue_node.text.strip()

        url2 = f"http://data.ekape.or.kr/openapi-data/service/user/grade/confirm/cattle?issueNo={urllib.parse.quote(issue_no)}&ServiceKey={ekape_key}"
        req2 = urllib.request.urlopen(url2, timeout=6)
        xml2 = req2.read().decode('utf-8')
        root2 = ET.fromstring(xml2)
        item = root2.find('.//item')
        if item is None: return None

        def get_t(tag):
            n = item.find(tag)
            return n.text if n is not None else None
        def to_f(v):
            try: return float(v) if v else None
            except: return None

        # judgeSexNm: "거세" / "암" / "수" — DB의 gender 값과 같은 표기로 맞춘다
        sex_nm = (get_t('judgeSexNm') or '').strip()
        gender = "거세" if "거세" in sex_nm else ("암" if "암" in sex_nm else ("수" if "수" in sex_nm else None))

        return {
            'animal_no': animal_no,
            'gender': gender,
            'costAmt': to_f(get_t('costAmt')),
            'carcass_weight': to_f(get_t('weight')),
            'grade_quality': get_t('qgrade'),
            'grade_yield': get_t('wgrade'),
            'bms': to_f(get_t('insfat')),
            'backfat': to_f(get_t('backfat')),
            'ribeye': to_f(get_t('rea')),
            'month_age': to_f(get_t('birthmonth')),
            # abattDate=도축일자, judgeDate=등급판정일(도축 다음날). judgeBreedNm은 품종명("한우")이라 날짜가 아니다
            'slaughter_date': get_t('abattDate') or get_t('judgeDate')
        }
    except:
        return None

@st.cache_data(ttl=86400) # 24시간마다 API 갱신 (캐시)
def fetch_eumseong_grade_prices(year):
    """도축장코드 0905(이 시스템 농가들이 실제 출하하는 도축장 — EUMSEONG_PRICES_2025가 가리키던 곳과 동일)
    기준, 지정 연도 육질등급별 평균 경락단가(원/kg)를 축평원(eKAPE) grade/auct/cattle OpenAPI로 실시간 조회한다.
    API 키 누락/호출 실패/데이터 없음이면 None을 돌려주고, 호출 측은 EUMSEONG_PRICES_2025 고정값으로 폴백한다."""
    ekape_key = get_ekape_api_key()
    if not ekape_key or not year:
        return None
    try:
        url = (
            "http://data.ekape.or.kr/openapi-data/service/user/grade/auct/cattle"
            f"?startYmd={year}0101&endYmd={year}1231&qgradeYn=Y&ServiceKey={ekape_key}"
        )
        xml = urllib.request.urlopen(url, timeout=8).read()
        root = ET.fromstring(xml)
        # gradeNm "D"는 축평원 응답상 최하위 등급 구간으로, 기존 고정표의 "등외"에 대응시킨다
        grade_map = {"1++": "1++", "1+": "1+", "1": "1", "2": "2", "3": "3", "D": "등외"}
        prices = {}
        for item in root.findall('.//item'):
            def gt(tag):
                n = item.find(tag)
                return n.text if n is not None else None
            grade = grade_map.get(gt('gradeNm'))
            if not grade:
                continue
            try:
                amt, cnt = float(gt('c_0905Amt')), int(gt('c_0905Cnt'))
            except (TypeError, ValueError):
                continue
            if cnt > 0:
                prices[grade] = amt
        return prices or None
    except Exception:
        return None

# -----------------------------------------------------------------------------
# 5. Claude AI 연동 리포트 생성기
# -----------------------------------------------------------------------------
def get_claude_api_key():
    if "ANTHROPIC_API_KEY" in st.secrets:
        return st.secrets["ANTHROPIC_API_KEY"]
    local_paths = [
        os.path.join(BASE_DIR, "api_key.txt"),
    ]
    for p in local_paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                k = f.read().strip()
                if k: return k
    return os.environ.get("ANTHROPIC_API_KEY", "")

class ClaudeReportError(Exception):
    """리포트 생성 실패. 오류 문구가 리포트 본문으로 DB에 저장되지 않도록 텍스트가 아닌 예외로 알린다."""

def build_ai_report_yearly_breakdown(farm_id, gender="거세"):
    """AI 컨설팅 리포트용: 연도별 출하성적 추이 + 육질/육량 등급 전체 분포를 전국 평균과 함께 구성한다.
    (인쇄용 비교리포트의 _build_page1_table/_build_page2_table와 같은 데이터를, AI 프롬프트에 넣기 좋은 dict 리스트로 만든 버전)"""
    conn = get_db()
    df = pd.read_sql_query("""
        SELECT slaughter_year, carcass_weight, bms, backfat, ribeye, month_age, grade_quality, grade_yield
        FROM shipment_records WHERE farm_id = ? AND gender = ?
    """, conn, params=(farm_id, gender))
    conn.close()

    nat = NATIONAL_STATS.get(gender, {})
    nat_q = nat.get("grade_quality", {})
    nat_y = nat.get("grade_yield", {})
    quality_grades = ["1++", "1+", "1", "2", "3"]
    yield_grades = ["A", "B", "C"]

    breakdown = []
    for year in PRINT_REPORT_YEARS:
        ydf = df[df["slaughter_year"] == year]
        count = len(ydf)
        if count == 0:
            continue

        def avg(col):
            return round(ydf[col].mean(), 1) if ydf[col].notna().any() else None

        quality_pct = {g: round((ydf["grade_quality"] == g).sum() * 100.0 / count, 1) for g in quality_grades}
        quality_pct["1+이상"] = round(ydf["grade_quality"].isin(["1++", "1+"]).sum() * 100.0 / count, 1)
        yield_pct = {g: round((ydf["grade_yield"] == g).sum() * 100.0 / count, 1) for g in yield_grades}

        breakdown.append({
            "year": year,
            "head_count": count,
            "carcass_weight_kg": {"농가": avg("carcass_weight"), "전국": nat.get("도체중", {}).get(year)},
            "bms": {"농가": avg("bms"), "전국": nat.get("BMS", {}).get(year)},
            "backfat_mm": {"농가": avg("backfat"), "전국": nat.get("등지방", {}).get(year)},
            "ribeye_cm2": {"농가": avg("ribeye"), "전국": nat.get("단면적", {}).get(year)},
            "month_age": {"농가": avg("month_age"), "전국": nat.get("출하월령", {}).get(year)},
            "grade_quality_pct": {"농가": quality_pct, "전국": nat_q.get(year)},
            "grade_yield_pct": {"농가": yield_pct, "전국": nat_y.get(year)},
        })
    return breakdown

def build_ai_report_profit_estimate(farm_id, gender="거세"):
    """AI 컨설팅 리포트용 수익성(손익) 추정.
    1순위: shipment_records에 실제 두당 정산액(total_price)이 기록돼 있으면 그 실측 평균을 그대로 쓴다.
    2순위(현재 DB는 전량 excel_batch 임포트라 total_price가 비어 있어 대부분 이 경로를 탐): 음성공판장
    (도축장코드 0905) 등급별 낙찰가를 축평원 OpenAPI로 실시간 조회해(fetch_eumseong_grade_prices) 농가/전국
    등급분포에 가중평균, 두당 매출을 추정한다. 실시간 조회가 실패하면 EUMSEONG_PRICES_2025 고정값으로 폴백한다.
    과거의 'kg당 21,000원 고정' 방식보다 실제 등급 시세를 반영하며, 어떤 방식으로 계산됐는지를
    결과에 명시해 AI가 추정치를 실측치처럼 서술하지 않도록 한다."""
    conn = get_db()
    df = pd.read_sql_query("""
        SELECT carcass_weight, grade_quality, price_per_kg, total_price
        FROM shipment_records WHERE farm_id = ? AND gender = ?
    """, conn, params=(farm_id, gender))
    conn.close()

    head_count = len(df)
    if head_count == 0:
        return {}

    nat_year = nat_latest_year(gender)
    nat = NATIONAL_STATS.get(gender, {})
    nat_w = nat.get("도체중", {}).get(nat_year) if nat_year else None
    nat_grade_pct = nat.get("grade_quality", {}).get(nat_year, {}) if nat_year else {}
    farm_w = round(df["carcass_weight"].mean(), 1) if df["carcass_weight"].notna().any() else None

    live_prices = fetch_eumseong_grade_prices(nat_year)
    if live_prices:
        price_table = {**EUMSEONG_PRICES_2025, **live_prices}
        price_basis = f"음성공판장(도축장코드 0905) {nat_year}년 육질등급별 실시간 경락단가 (축평원 OpenAPI)"
    else:
        price_table = EUMSEONG_PRICES_2025
        price_basis = "음성공판장 2025년 육질등급별 낙찰가 (EUMSEONG_PRICES_2025 고정값, 실시간 API 조회 실패로 대체 사용)"

    real_price_df = df[df["total_price"].notna() & (df["total_price"] > 0)]
    if len(real_price_df) >= max(3, head_count * 0.5):
        farm_revenue_per_head = real_price_df["total_price"].mean()
        method = "실측 두당 정산액(shipment_records.total_price) 평균"
    else:
        grade_counts = df["grade_quality"].value_counts()
        farm_price_per_kg = (
            sum(price_table.get(g, price_table["등외"]) * c for g, c in grade_counts.items()) / head_count
            if head_count else None
        )
        farm_revenue_per_head = (farm_w * farm_price_per_kg) if (farm_w and farm_price_per_kg) else None
        method = f"{price_basis} × 농가 등급분포 가중평균 추정 (실제 두당 정산액 데이터 없음)"

    nat_revenue_per_head = None
    if nat_w and nat_grade_pct:
        nat_price_per_kg = sum(
            price_table[g] * (pct / 100.0) for g, pct in nat_grade_pct.items() if g in price_table
        )
        nat_revenue_per_head = nat_w * nat_price_per_kg if nat_price_per_kg else None

    result = {
        "계산_방식": method,
        "가격_기준": price_basis,
        "national_base_year": nat_year,
        "head_count": head_count,
    }
    if farm_revenue_per_head is not None and nat_revenue_per_head is not None:
        diff = round(farm_revenue_per_head - nat_revenue_per_head)
        result.update({
            "farm_revenue_per_head_est": int(round(farm_revenue_per_head)),
            "national_revenue_per_head_est": int(round(nat_revenue_per_head)),
            "diff_revenue_per_head": diff,
            "total_diff_revenue": diff * head_count,
        })
    return result

# 2단계 현장조사 폼의 영문 키(s_dict['...'])를 AI 프롬프트에 넣기 좋은 한글 라벨로 바꾼다.
# (라벨은 폼 위젯에 실제로 쓰인 문구와 맞춤 — streamlit_app.py의 "2단계 · 현장방문조사" 섹션 참고)
# 매핑에 없는 키(과거 엑셀 임포트 데이터 등 이미 한글 키인 경우)는 원래 키 그대로 둔다.
SURVEY_FIELD_LABELS = {
    "investigator": "조사자 성명", "visitDate": "조사일자",
    "memberName": "조합원명", "memberId": "조합원번호",
    "region": "지역", "farmType": "전업여부", "bizGoal": "농가 경영 목표(출하 전략)",
    "dailyAvgTemp": "연평균기온(℃)", "highTemp": "최고기온(℃)", "lowTemp": "최저기온(℃)",
    "annualPrecip": "평균강수량(연간, mm)", "avgWindSpeed": "평균풍속(m/s)", "avgHumidity": "평균상대습도(%)",
    "breedingType": "사육형태",
    "fatteningPenSize": "비육우방 크기", "fatteningPenDensity": "비육우방 밀도",
    "breedingPenSize": "번식우방 크기", "breedingPenDensity": "번식우방 밀도",
    "calfPenSize": "송아지우방 크기", "calfPenDensity": "송아지우방 밀도",
    "bulkBin": "벌크빈 보유", "autoFeeder": "자동급이시설", "tmr": "TMR 급여", "selfMix": "자가배합",
    "castrationAge": "거세시기(개월)", "castrationMethod": "거세방법",
    "floorCondition": "축사바닥 상태", "dewormingCount": "정기구충(회/년)",
    "waterQuality": "음수(물) 관리 실태", "manureScore": "소 분변 상태",
    "troughCleaning": "사조(밥통) 매일 청소 및 잔량 폐기 여부",
    "feedOrder": "급여순서", "feedFrequency": "급여횟수(회/일)", "forageQuality": "조사료 품질(질) 평가",
    "feed_matrix": "성장단계별(송아지/육성우/비육전기/비육후기/번식우) 배합사료·조사료·첨가제 급여 현황",
    "countCow": "번식우(암소) 두수", "countSteer": "거세우 두수", "countGrowing": "육성우 두수",
    "countCalf": "송아지 두수", "countOptimal": "적정 사육두수",
    "aiMethod": "인공수정 방법", "calvingInterval": "평균 분만간격(개월)", "mortalityRate": "최근 1년 폐사율(%)",
    "weaningAge": "송아지 이유 월령", "artificialRearing": "인공포유 여부",
    "consultingNotes": "현장 점검 소견 및 컨설팅사항",
}

def relabel_survey_data(survey_data):
    """AI 프롬프트에 넣기 전, 현장조사 원본 영문 키를 한글 라벨로 바꾼다 (해석 오류·환각 방지)."""
    if not isinstance(survey_data, dict):
        return survey_data
    return {SURVEY_FIELD_LABELS.get(k, k): v for k, v in survey_data.items()}

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge")

def _fetch_remote_knowledge_files():
    """비공개 데이터 저장소(GITHUB_REPO)의 knowledge/*.md 를 {파일명: 본문}으로 받아온다.

    전문자료는 농협 등 남의 출판물에서 추출한 글이라 공개 코드 저장소에 올리지 않는다.
    배포 서버엔 knowledge/ 폴더가 없으므로, DB 백업과 같은 비공개 저장소에서 GitHub API로 읽는다.
    실패하면 예외를 던진다 — 호출 측 캐시가 실패 결과를 붙잡아 두지 않게 하기 위함.
    """
    token = _secret("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN 없음")
    repo = _secret("GITHUB_REPO", "Bst-dc/hanwoo-smart-consulting")
    branch = _secret("GITHUB_BRANCH", "main")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hanwoo-consulting-app",
    }
    def _get(path, accept):
        url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
        req = urllib.request.Request(url, headers={**headers, "Accept": accept})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    listing = json.loads(_get("knowledge", "application/vnd.github+json").decode("utf-8"))
    names = [item["name"] for item in listing if item.get("type") == "file" and item["name"].endswith(".md")]
    if not names:
        raise RuntimeError("비공개 저장소에 knowledge/*.md 가 없음")
    return {name: _get(f"knowledge/{name}", "application/vnd.github.raw").decode("utf-8") for name in names}

@st.cache_resource(show_spinner=False)
def _load_knowledge_cached():
    if os.path.isdir(KNOWLEDGE_DIR):
        files = {}
        for name in os.listdir(KNOWLEDGE_DIR):
            if name.endswith(".md"):
                with open(os.path.join(KNOWLEDGE_DIR, name), encoding="utf-8") as f:
                    files[name] = f.read()
    else:
        files = _fetch_remote_knowledge_files()
    return "\n\n".join(
        f'<문서 제목="{name[:-3]}">\n{files[name]}\n</문서>' for name in sorted(files)
    )

def load_knowledge_base():
    """AI 리포트가 근거로 삼을 전문자료(knowledge/*.md)를 한 덩어리로 합쳐 돌려준다.

    build_knowledge.py가 reference/원본PDF/ 의 PDF에서 미리 추출해 둔 파일들이다.
    (한우 컨설팅 길라잡이 / 자가TMR / 육종가 기초지식, 합쳐서 약 15만 토큰)
    로컬엔 knowledge/ 폴더가 있고, 배포 서버에선 비공개 데이터 저장소에서 받아온다.

    파일명 정렬 순서를 고정하는 게 중요하다. 이 덩어리는 프롬프트 캐시의 앞부분이라
    한 글자라도 순서가 바뀌면 캐시가 통째로 무효가 되어 비용이 10배가 된다.

    자료를 구하지 못하면 빈 문자열을 돌려주고, 리포트는 전문자료 없이 생성된다.
    실패는 캐시되지 않으므로 다음 호출 때 다시 시도한다.
    """
    try:
        return _load_knowledge_cached()
    except Exception:
        return ""

def generate_claude_report(farm_name, gender_data, survey_data, use_knowledge=True):
    # 이 함수는 yield를 쓰는 제너레이터라서 return "문구"는 호출 측에 전달되지 않는다 → 예외로 알린다
    # gender_data: {"거세우": {"shipment_stats":..., "yearly_breakdown":..., "profit_data":...}, "암소": {...}}
    # 출하 기록이 없는 성별은 호출 측(build_ai_report_yearly_breakdown 등)에서 이미 걸러지고 키 자체가 없다.
    # use_knowledge=False 면 전문자료 없이 Claude의 일반 지식만으로 작성한다 (빠르고 저렴, 근거 인용 없음).
    api_key = get_claude_api_key()
    if not api_key:
        raise ClaudeReportError("Anthropic API 키가 설정되지 않았습니다. Streamlit Secrets 또는 api_key.txt를 확인해주세요.")

    system_prompt = (
        "당신은 대한민국 최고의 한우 사양관리 수석 컨설턴트입니다. "
        "농가의 최근 3개년 출하성적(정량 데이터)과 현장 방문 사양관리 실태(정성 데이터)를 종합 분석하여 "
        "'진단 → 원인 → 처방 → 액션플랜' 흐름의 7단 구성 맞춤형 컨설팅 리포트를 마크다운으로 작성하세요. "
        "농가가 거세우와 암소를 함께 출하하는 경우 두 성별의 데이터가 각각 주어지니 반드시 성별을 구분해서 분석하고, "
        "한 성별 데이터만 주어졌다면 그 성별만 다루고 없는 성별을 언급하지 마세요."
    )

    knowledge = load_knowledge_base() if use_knowledge else ""
    if knowledge:
        system_prompt += (
            " 아래 [참고 전문자료]는 농협경제지주·농촌진흥청이 발간한 한우 사양관리 자료입니다. "
            "처방과 기준을 제시할 때 이 자료에 해당 내용이 있으면 반드시 근거로 삼고 어느 자료의 어떤 기준인지 밝히세요. "
            "자료에 없는 수치나 기준은 지어내지 말고, 일반적인 권장사항이라면 그렇다고 명시하세요."
        )

    # 시스템 블록 구성 = 프롬프트 캐시의 대상 구간.
    # 농가별로 바뀌는 데이터(messages)는 반드시 이 뒤에 와야 캐시가 유지된다.
    system_blocks = [{"type": "text", "text": system_prompt}]
    if knowledge:
        system_blocks.append({
            "type": "text",
            "text": f"[참고 전문자료]\n{knowledge}",
            # 여러 농가 리포트를 몰아서 만들 때 캐시가 살아있도록 1시간 유지 (기본값은 5분)
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        })

    gender_blocks = "\n\n".join(
        f"### {glabel} 출하성적\n"
        f"[출하성적 종합 통계 (전체 기간 통합 평균)]:\n{json.dumps(gd['shipment_stats'], ensure_ascii=False, indent=2)}\n\n"
        f"[연도별 출하성적 추이 및 등급 전체 분포 (전국 평균 대비, 연도 오름차순)]:\n{json.dumps(gd['yearly_breakdown'], ensure_ascii=False, indent=2)}\n\n"
        f"[수익성 분석 (전국 평균 대비 손익, \"계산_방식\" 필드에 실측치인지 추정치인지 명시됨)]:\n{json.dumps(gd['profit_data'], ensure_ascii=False, indent=2)}"
        for glabel, gd in gender_data.items()
    ) or "(이 농가는 등록된 출하성적이 없습니다)"

    prompt = f"""
[농가명]: {farm_name}

[출하 성별]: {", ".join(gender_data.keys()) if gender_data else "없음"}

{gender_blocks}

[현장 방문 조사표 실태 (사료급여, 축사환경, 농가 대화)]:
{json.dumps(relabel_survey_data(survey_data), ensure_ascii=False, indent=2)}

[보고서 작성 필수 7단 구성 가이드]
농장주가 이해하기 쉽고 현장에서 즉시 적용할 수 있도록 아래 목차에 맞추어 작성해 주세요:
# 1. 📋 종합 컨설팅 개요 배너 (농가명, 조사일, 컨설턴트, 핵심 평가)
# 2. ⚡ 핵심 진단 요약 (30초 요약 카드 3~4개: 성적 및 현장조사 핵심 이슈)
# 3. 📊 출하성적 전국 비교 및 수익성 임팩트 — 위 성별별 [연도별 출하성적 추이 및 등급 전체 분포] 데이터를 근거로 성별마다 연도별 표를 만들어 도체중·BMS·등지방·단면적 추이와, 1++/1+/1/2/3 등 육질등급·A/B/C 육량등급 전체 분포 변화를 전국 평균과 비교하세요. 두당/연간 수익 격차는 각 성별 [수익성 분석] 데이터의 값을 그대로 인용하고, "계산_방식"이 추정치라면 반드시 "~로 추정됩니다"처럼 추정임을 밝히세요. 해당 데이터에 없는 연도·수치·성별은 만들어내지 말고 언급하지 마세요.
# 4. 🔍 현장 사양관리 및 축사환경 실태 진단 (우방밀도, 환기, 성장단계별 사료 급여를 [양호/보통/미흡] 배지로 판정)
# 5. 💡 문제별 원인 분석 및 개선 처방 (1:1 매칭: [문제 현상] → [근본 원인] → [정밀 처방])
# 6. 🚀 실행 우선순위 로드맵 (1단계 즉시조치 1~2주, 2단계 기반구축 1~3개월, 3단계 성적개선 6개월~)
# 7. 📌 안내 및 출처 (농촌진흥청 국립축산과학원 사양표준 인용 및 축협 담당자 협의 권장 면책 문구)
"""

    client = anthropic.Anthropic(api_key=api_key)
    try:
        with client.messages.stream(
            model="claude-sonnet-5",
            # Sonnet 5는 최대 128K까지 되고, 실제로 생성한 만큼만 과금된다(한도를 높여도 그 자체로는
            # 비용이 늘지 않는다). 전문자료를 붙인 뒤 근거 인용이 늘어 12000으로는 잘려서 상향했다.
            max_tokens=32000,
            system=system_blocks,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
            # 토큰 한도에 걸려 잘린 응답을 완성본처럼 저장하지 않도록 막는다
            final = stream.get_final_message()
            if final.stop_reason == "max_tokens":
                raise ClaudeReportError(
                    "리포트가 최대 길이에 도달해 중간에 잘렸습니다. max_tokens를 올리거나 다시 시도해주세요."
                )
    except anthropic.AuthenticationError:
        raise ClaudeReportError("Anthropic API 키가 올바르지 않습니다. Streamlit Secrets 또는 api_key.txt를 확인해주세요.")
    except anthropic.RateLimitError:
        raise ClaudeReportError("Anthropic API 사용량 한도에 걸렸습니다. 잠시 후 다시 시도해주세요.")
    except anthropic.APIStatusError as e:
        raise ClaudeReportError(f"Claude API 오류가 발생했습니다 ({e.status_code}).\n상세: {e.message}")
    except anthropic.APIConnectionError:
        raise ClaudeReportError("Anthropic API에 연결하지 못했습니다. 네트워크 상태를 확인해주세요.")
    except ClaudeReportError:
        raise
    except Exception as e:
        raise ClaudeReportError(f"Claude 분석 중 오류 발생: {str(e)}")

def build_report_html(farm_name, report_markdown, report_mode=""):
    """AI 리포트 마크다운을 다운로드/인쇄 가능한 단독 HTML 문서로 변환

    report_mode("전문"/"일반")를 주면 브라우저 탭 제목에도 들어가, 두 방식을
    나란히 열어두고 비교할 때 어느 창이 어느 것인지 구분된다.
    """
    mode_suffix = f" ({report_mode})" if report_mode else ""
    body_html = md_lib.markdown(report_markdown, extensions=["tables", "nl2br", "fenced_code"])
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{farm_name} AI 컨설팅 리포트{mode_suffix}</title>
<style>
    body {{ font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #1e293b; line-height: 1.7; }}
    h1, h2, h3 {{ color: #1e3a8a; }}
    h1 {{ border-bottom: 3px solid #1e3a8a; padding-bottom: 10px; }}
    h2 {{ margin-top: 2rem; border-left: 5px solid #16a34a; padding-left: 10px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }}
    th {{ background-color: #eff6ff; color: #1e3a8a; }}
    tr:nth-child(even) {{ background-color: #f8fafc; }}
    blockquote {{ border-left: 4px solid #94a3b8; margin: 1rem 0; padding: 0.5rem 1rem; color: #64748b; background: #f8fafc; }}
    code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }}
    @media print {{ body {{ margin: 0; padding: 20px; }} }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""

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

def _build_page1_table(gdf, gender_key):
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

def _build_page2_table(gdf, gender_key):
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

def build_print_comparison_report_html(farm_name, farm_id):
    """기존 종합컨설팅 최종보고서와 동일한 A4 3페이지 인쇄용 출하성적 비교 리포트 생성 (전국 대비, 2023~2026)"""
    conn = get_db()
    all_df = pd.read_sql_query("""
        SELECT gender, slaughter_year, carcass_weight, bms, backfat, ribeye, month_age, grade_quality, grade_yield
        FROM shipment_records WHERE farm_id = ?
    """, conn, params=(farm_id,))
    conn.close()

    page1_sections = ""
    page2_sections = ""
    for gkey, glabel in PRINT_REPORT_GENDERS:
        gdf = all_df[all_df["gender"] == gkey]
        page1_sections += f"<h2>{glabel} — 연도별 도체 성적 요약 (농가 vs 전국)</h2>{_build_page1_table(gdf, gkey)}<div style='height:12px;'></div>"
        sample_note, table_html = _build_page2_table(gdf, gkey)
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

def build_farm_options(df, label_fn):
    """농가 선택 목록 {표시 이름: farm_id}. 표시 이름이 같은 농가가 둘 이상이면
    dict 키가 겹쳐 뒤의 농가가 앞의 농가를 덮어써서 선택할 수 없게 되므로 '#농가ID'를 붙여 구분한다."""
    options = {}
    for _, r in df.iterrows():
        label = label_fn(r)
        if label in options:
            label = f"{label} #{r['id']}"
        options[label] = r['id']
    return options

# -----------------------------------------------------------------------------
# 6. 사이드바: 농가 선택 및 메뉴
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"""
    <div class="sb-brand">
        <div class="sb-brand-mark">{cow_mark(42)}</div>
        <div class="sb-brand-body">
            <div class="sb-brand-org">대구축협 지도컨설팅</div>
            <div class="sb-brand-name">한우 스마트 컨설팅</div>
            <div class="sb-brand-desc">현장조사 · AI 진단 통합관리</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    conn = get_db()
    farms_df = pd.read_sql_query("SELECT * FROM farms ORDER BY id DESC", conn)
    surveys_df = pd.read_sql_query("""
        SELECT v.farm_id, fs.survey_data 
        FROM visits v 
        JOIN field_surveys fs ON v.id = fs.visit_id 
        WHERE fs.survey_data IS NOT NULL 
        ORDER BY v.visit_date ASC
    """, conn)
    conn.close()

    # 컬럼 부재 방어
    for col in ["farm_name", "owner_name", "region", "total_heads"]:
        if col not in farms_df.columns:
            farms_df[col] = ""

    # 방문조사표에 기록된 최근 지역 정보로 덮어쓰기
    if not surveys_df.empty:
        survey_region_map = {}
        for _, row in surveys_df.iterrows():
            try:
                s_data = json.loads(row['survey_data'])
                if s_data and s_data.get('region'):
                    survey_region_map[row['farm_id']] = s_data.get('region')
            except Exception:
                pass
        farms_df['region'] = farms_df.apply(
            lambda x: survey_region_map.get(x['id'], x['region']), axis=1
        )

    farm_options = build_farm_options(farms_df, lambda r: f"{r['farm_name']} ({r['owner_name'] or '대표자'}, {r['region'] or '지역'})")
    
    selected_label = st.selectbox("현재 컨설팅 농가 선택", list(farm_options.keys()) if farm_options else ["등록된 농가 없음"])
    selected_farm_id = farm_options.get(selected_label)

    with st.expander("➕ 신규 농가 등록"):
        n_code = st.text_input("조합원 번호", placeholder="예: M1234")
        n_name = st.text_input("농가명*", placeholder="예: 한우사랑농장")
        n_owner = st.text_input("대표자명", placeholder="홍길동")
        n_region = st.text_input("지역", placeholder="강원 횡성")
        n_type = st.selectbox("사육형태", ["비육우", "일관사육", "번식우"])
        n_heads = st.number_input("사육두수", min_value=0, value=100)

        # 이미 있는 농가를 실수로 또 등록하면 farm_id가 둘로 쪼개져서
        # 출하성적과 조사표가 영영 서로 연결되지 않는다 (과거에 실제로 겪은 문제).
        # 이름 또는 조합원번호가 기존 농가와 정확히 같으면 저장 전에 경고한다.
        name_key = n_name.strip()
        code_key = n_code.strip()
        dup_match = None
        if name_key or code_key:
            for _, r in farms_df.iterrows():
                existing_name = str(r.get('farm_name') or '').strip()
                existing_code = str(r.get('farm_code') or '').strip()
                if (name_key and existing_name == name_key) or (code_key and existing_code == code_key):
                    dup_match = r
                    break

        confirm_dup = True
        if dup_match is not None:
            st.warning(
                f"⚠️ 이미 등록된 농가와 일치합니다 — **{dup_match['farm_name']}**"
                f" ({dup_match['owner_name'] or '대표자 미입력'}, {dup_match['region'] or '지역 미입력'},"
                f" 조합원번호 {dup_match['farm_code'] or '미입력'}).\n\n"
                "같은 농가라면 여기서 다시 등록하지 말고, 위쪽 '현재 컨설팅 농가 선택'에서 이 농가를 고르세요."
                " 여기서 새로 저장하면 출하성적과 조사표가 서로 다른 농가로 쪼개져 연결되지 않습니다."
            )
            confirm_dup = st.checkbox("그래도 별개의 새 농가로 등록합니다")

        if st.button("신규 농가 저장", disabled=(dup_match is not None and not confirm_dup)):
            if n_name:
                c = get_db()
                try:
                    c.cursor().execute("""
                    INSERT INTO farms (farm_code, farm_name, owner_name, region, breeding_type, total_heads)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (code_key or f"F{int(datetime.now().timestamp())%10000}", n_name, n_owner, n_region, n_type, n_heads))
                    c.commit()
                except (sqlite3.IntegrityError, db_adapter.IntegrityError, ValueError) as e:
                    # farm_code는 UNIQUE라서, '그래도 등록'을 체크해도 같은 조합원번호로는 저장할 수 없다.
                    # Turso(libsql)는 모든 DB 오류를 ValueError로 던지고, Supabase 어댑터는 제약 위반을 모두
                    # IntegrityError로 던지므로 UNIQUE 위반만 골라 잡는다.
                    if not isinstance(e, sqlite3.IntegrityError) and "UNIQUE" not in str(e):
                        raise
                    st.error(
                        f"조합원번호 '{code_key or '(자동생성 번호)'}'가 이미 다른 농가에 등록되어 있어 저장하지 못했습니다."
                        " 별개의 농가라면 조합원번호를 다르게 입력해주세요."
                    )
                else:
                    notify_saved(f"{n_name} 농가 등록 완료!", "신규 농가 등록")
                    st.rerun()
                finally:
                    c.close()

    st.markdown("---")
    menu = st.radio(
        "컨설팅 프로세스",
        [
            "종합 현황 대시보드",
            "1단계 · 출하성적 비교분석",
            "2단계 · 현장방문조사",
            "3단계 · AI 리포트",
            "데이터 관리 · 백업"
        ]
    )

    st.markdown("""
    <div class="sb-foot">
        <div class="sb-foot-role">담당 컨설턴트</div>
        <div class="sb-foot-name">배성태</div>
        <div class="sb-foot-note">축산물품질평가원 이력제 · 한우컨설팅일지 연동</div>
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 메뉴 1: 종합 현황 대시보드
# -----------------------------------------------------------------------------
if menu == "종합 현황 대시보드":
    page_header("종합 현황 대시보드")
    show_flash()

    conn = get_db()
    total_farms = conn.execute("SELECT COUNT(*) FROM farms").fetchone()[0]
    total_visits = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    total_shipments = conn.execute("SELECT COUNT(*) FROM shipment_records").fetchone()[0]
    row_1plus_steer = conn.execute("SELECT ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(*), 1) FROM shipment_records WHERE gender='거세'").fetchone()
    avg_1plus_steer = row_1plus_steer[0] if row_1plus_steer and row_1plus_steer[0] else 0.0

    row_1plus_cow = conn.execute("SELECT ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(*), 1) FROM shipment_records WHERE gender='암'").fetchone()
    avg_1plus_cow = row_1plus_cow[0] if row_1plus_cow and row_1plus_cow[0] else 0.0

    farms_missing_survey_list = conn.execute("""
        SELECT f.farm_name FROM farms f
        WHERE EXISTS (SELECT 1 FROM shipment_records s WHERE s.farm_id = f.id)
        AND NOT EXISTS (
            SELECT 1 FROM visits v
            JOIN field_surveys fs ON fs.visit_id = v.id
            WHERE v.farm_id = f.id AND fs.survey_data IS NOT NULL
        )
    """).fetchall()
    farms_missing_survey = len(farms_missing_survey_list)
    
    farms_missing_shipment_list = conn.execute("""
        SELECT f.farm_name FROM farms f
        WHERE EXISTS (
            SELECT 1 FROM visits v
            JOIN field_surveys fs ON fs.visit_id = v.id
            WHERE v.farm_id = f.id AND fs.survey_data IS NOT NULL
        )
        AND NOT EXISTS (SELECT 1 FROM shipment_records s WHERE s.farm_id = f.id)
    """).fetchall()
    farms_missing_shipment = len(farms_missing_shipment_list)

    k1, k2, k3 = st.columns(3)
    k1.metric("총 관리 농가 수", f"{total_farms} 농가")
    k2.metric("누적 현장 방문 횟수", f"{total_visits} 회")
    k3.metric("누적 분석 출하 두수", f"{total_shipments} 두")
    
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    
    k4, k5, k6, k7 = st.columns(4)
    # 성별마다 자기 성별의 전국 1+이상 비율과 비교한다 (암소를 거세우 전국값 71.3%와 비교하던 오류 수정).
    # 기준 연도는 1년치가 다 채워진 작년 통계 (올해는 누계라 연중에 계속 변함)
    def _nat_1plus(gender_key):
        gq = NATIONAL_STATS.get(gender_key, {}).get("grade_quality", {})
        base_year = datetime.now().year - 1
        if not isinstance(gq.get(base_year), dict):
            base_year = nat_latest_year(gender_key, "grade_quality")
        return base_year, (gq.get(base_year) or {}).get("1+이상")

    for col, label, avg_val, gkey in [(k4, "거세우 1+이상 출현율", avg_1plus_steer, "거세"), (k5, "암소 1+이상 출현율", avg_1plus_cow, "암")]:
        base_year, nat_val = _nat_1plus(gkey)
        if nat_val is None:
            col.metric(label, f"{avg_val}%")
        else:
            # "(-16.9%)" 같은 전국 대비 격차를 값 문자열에 이어 붙이면 "48.0%"와
            # 똑같은 큰 검정 글씨로 나온다. delta= 인자를 쓰면 자동으로 값의
            # 절반 크기 + 음수는 빨간색(양수는 초록색)으로 렌더링된다.
            delta = round(avg_val - nat_val, 1)
            col.metric(label, f"{avg_val}%", delta=f"{delta}%", help=f"{base_year}년 전국 {label.split()[0]} 1+이상 출현율 {nat_val}%와 비교")
    
    k6.metric("출하성적만 있는 농가", f"{farms_missing_survey} 농가", help="출하성적은 등록되어 있으나, 현장 방문 조사표가 아직 작성되지 않은 농가 수입니다.")
    k7.metric("조사표만 있는 농가", f"{farms_missing_shipment} 농가", help="현장 방문 조사표는 있으나, 아직 축평원 출하성적 데이터가 수집되지 않은 농가 수입니다.")

    with st.expander("📌 누락 데이터 보유 농가 명단 확인 및 관리"):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**출하성적만 있고 조사표 없는 농가**")
            if farms_missing_survey_list:
                st.info(", ".join([r[0] for r in farms_missing_survey_list]) + "  \n*(2단계 메뉴에서 신규 조사표를 작성해주세요)*")
            else:
                st.success("해당 농가 없음")
        with col_b:
            st.markdown("**조사표만 있고 출하성적 없는 농가**")
            if farms_missing_shipment_list:
                st.warning(", ".join([r[0] for r in farms_missing_shipment_list]) + "  \n*(1단계 메뉴에서 성적을 수동 또는 엑셀로 추가해주세요)*")
            else:
                st.success("해당 농가 없음")

    st.markdown("---")

    current_year = datetime.now().year
    start_year = 2023

    trend_gender_label = st.radio("연도별 추이 · 집계표 기준 성별", ["거세우", "암소"], horizontal=True, key="trend_gender")
    trend_gender = "거세" if trend_gender_label == "거세우" else "암"

    yearly_df = pd.read_sql_query(f"""
    SELECT
        slaughter_year AS 연도,
        COUNT(DISTINCT farm_id) AS 농가수,
        COUNT(id) AS 출하두수,
        ROUND(AVG(carcass_weight), 1) AS 도체중_kg,
        ROUND(AVG(bms), 1) AS BMS,
        ROUND(AVG(ribeye), 1) AS 단면적_㎠,
        ROUND(AVG(backfat), 1) AS 등지방_mm,
        ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS "1+ 이상 출현율",
        ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS "C등급 출현율",
        ROUND(AVG(month_age), 1) AS 출하월령
    FROM shipment_records
    WHERE gender = ? AND slaughter_year BETWEEN {start_year} AND {current_year}
    GROUP BY slaughter_year
    ORDER BY slaughter_year ASC
    """, conn, params=(trend_gender,))
    conn.close()

    # 핸드오프 스펙: 추이 그래프와 집계표는 각각 테두리 있는 카드 안에 담는다
    c_left, c_right = st.columns([3, 2])
    with c_left.container(border=True):
        st.subheader(f"📈 연도별 성적 추이 ({trend_gender_label} · 방문농가 전체 vs 전국평균)")
        metric_sel = st.selectbox("비교 지표 선택", ["도체중_kg", "BMS", "단면적_㎠", "등지방_mm", "1+ 이상 출현율", "C등급 출현율", "출하월령"])
        years = list(range(start_year, current_year + 1))
        nat_g = NATIONAL_STATS.get(trend_gender, {})
        # 암소는 전국 육량등급(grade_yield) 통계가 없어서 .get()으로 안전하게 비운다
        nat_map = {
            "도체중_kg": [nat_g.get("도체중", {}).get(y) for y in years],
            "BMS": [nat_g.get("BMS", {}).get(y) for y in years],
            "단면적_㎠": [nat_g.get("단면적", {}).get(y) for y in years],
            "등지방_mm": [nat_g.get("등지방", {}).get(y) for y in years],
            "1+ 이상 출현율": [nat_g.get("grade_quality", {}).get(y, {}).get("1+이상") for y in years],
            "C등급 출현율": [nat_g.get("grade_yield", {}).get(y, {}).get("C") for y in years],
            "출하월령": [nat_g.get("출하월령", {}).get(y) for y in years],
        }
        c_df = pd.DataFrame({"연도": [f"{str(y)[2:]}년" for y in years], "전국 평균": nat_map[metric_sel]})
        if not yearly_df.empty:
            merged = pd.merge(pd.DataFrame({"연도": years}), yearly_df[["연도", metric_sel]], on="연도", how="left")
            c_df["방문농가 평균"] = merged[metric_sel]
        for col in ["전국 평균", "방문농가 평균"]:
            if col in c_df.columns:
                c_df[col] = c_df[col].apply(lambda x: round(float(x), 1) if pd.notna(x) else x)
        c_df.set_index("연도", inplace=True)
        import altair as alt
        c_df_reset = c_df.reset_index().melt('연도', var_name='구분', value_name='값').dropna(subset=['값'])

        series = ['방문농가 평균', '전국 평균']
        color_enc = alt.Color(
            '구분:N',
            scale=alt.Scale(domain=series, range=[CHART_FARM, CHART_NAT]),
            legend=alt.Legend(orient='bottom', title=None, direction='horizontal'),
        )
        # 그라디언트 영역의 기준선이 0으로 잡히면 선이 납작해져 추이가 안 보인다.
        # 실제 값 범위에 맞춰 y 도메인을 직접 잡고(아래 여유=영역, 위 여유=값 라벨) 고정한다.
        vals = c_df_reset['값']
        if not vals.empty:
            lo, hi = float(vals.min()), float(vals.max())
            span = (hi - lo) or max(abs(hi) * 0.1, 1.0)
            y_scale = alt.Scale(domain=[lo - span * 0.4, hi + span * 0.32], nice=False, clamp=True)
        else:
            y_scale = alt.Scale(zero=False)

        x_enc = alt.X('연도:N', axis=alt.Axis(labelAngle=0, title=None, labelFontSize=12), scale=alt.Scale(padding=0.14))
        y_enc = alt.Y('값:Q', title=metric_sel, scale=y_scale, axis=alt.Axis(labelFontSize=11, tickCount=5))
        farm_only = alt.FieldEqualPredicate(field='구분', equal='방문농가 평균')
        base = alt.Chart(c_df_reset)

        # 농가 선 아래 그라디언트: 전국선과 농가선을 한눈에 구분시키는 장치
        area = base.transform_filter(farm_only).mark_area(
            interpolate='monotone', opacity=0.22,
            color=alt.Gradient(
                gradient='linear', x1=0, x2=0, y1=0, y2=1,
                stops=[alt.GradientStop(color=CHART_FARM, offset=0),
                       alt.GradientStop(color=CHART_SURFACE, offset=1)],
            ),
        ).encode(x=x_enc, y=y_enc)

        lines = base.mark_line(strokeWidth=2.6, interpolate='monotone', strokeCap='round').encode(
            x=x_enc, y=y_enc, color=color_enc,
            strokeDash=alt.StrokeDash('구분:N', scale=alt.Scale(domain=series, range=[[0], [5, 4]]), legend=None),
        )

        points = base.mark_point(size=78, strokeWidth=2.2, filled=False, fill=CHART_SURFACE).encode(
            x=x_enc, y=y_enc, color=color_enc,
            tooltip=[alt.Tooltip('연도:N', title='연도'), alt.Tooltip('구분:N', title='구분'),
                     alt.Tooltip('값:Q', title=metric_sel, format='.1f')],
        )

        # 농가 값만 숫자로 박아둔다 (전국값까지 찍으면 라벨끼리 겹쳐 읽히지 않는다)
        labels = base.transform_filter(farm_only).mark_text(
            align='center', dy=-15, fontSize=11, fontWeight=600, color=CHART_FARM,
        ).encode(x=x_enc, y=y_enc, text=alt.Text('값:Q', format='.1f'))

        chart = alt.layer(area, lines, points, labels).properties(height=330)
        st.altair_chart(style_chart(chart), width="stretch", theme=None)

    with c_right.container(border=True):
        st.subheader(f"📋 연도별 전체 집계표 ({trend_gender_label})")
        st.caption("※ 괄호 ( ) 안의 수치는 해당 연도 전국 평균입니다.")
        if not yearly_df.empty:
            disp_df = yearly_df.copy().astype(object)
            for idx, row in disp_df.iterrows():
                y_val = int(row["연도"])

                def fmt(val, nat_val):
                    if pd.isna(val): return "-"
                    if nat_val is not None:
                        return f"{val:.1f} ({nat_val:.1f})"
                    return f"{val:.1f}"

                disp_df.at[idx, "도체중_kg"] = fmt(row["도체중_kg"], nat_g.get("도체중", {}).get(y_val))
                disp_df.at[idx, "BMS"] = fmt(row["BMS"], nat_g.get("BMS", {}).get(y_val))
                disp_df.at[idx, "단면적_㎠"] = fmt(row["단면적_㎠"], nat_g.get("단면적", {}).get(y_val))
                disp_df.at[idx, "등지방_mm"] = fmt(row["등지방_mm"], nat_g.get("등지방", {}).get(y_val))
                disp_df.at[idx, "1+ 이상 출현율"] = fmt(row["1+ 이상 출현율"], nat_g.get("grade_quality", {}).get(y_val, {}).get("1+이상"))
                disp_df.at[idx, "C등급 출현율"] = fmt(row["C등급 출현율"], nat_g.get("grade_yield", {}).get(y_val, {}).get("C"))
                disp_df.at[idx, "출하월령"] = fmt(row["출하월령"], nat_g.get("출하월령", {}).get(y_val))

            disp_df["연도"] = disp_df["연도"].astype(str).str[2:] + "년"
            # 전치하면 농가수·출하두수(정수)와 "469.8 (490.4)" 같은 문자열이 한 열에 섞여
            # Arrow 변환이 매번 실패하므로 표시용으로 전부 문자열로 맞춘다
            transposed_df = disp_df.sort_values(by="연도", ascending=False).set_index("연도").T.astype(str)
            st.dataframe(transposed_df, width="stretch")
        else:
            st.info("등록된 출하 성적이 없습니다. 농가 성적을 먼저 입력해주세요.")

    st.markdown("---")
    st.subheader("⚖️ 거세우 vs 암소 전체 누적 평균 비교")
    
    conn = get_db()
    compare_df = pd.read_sql_query("""
    SELECT 
        gender AS 성별,
        COUNT(id) AS 출하두수,
        ROUND(AVG(carcass_weight), 1) AS 도체중_kg,
        ROUND(AVG(bms), 1) AS BMS,
        ROUND(AVG(ribeye), 1) AS 단면적_㎠,
        ROUND(AVG(backfat), 1) AS 등지방_mm,
        ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) AS "1+ 이상 출현율",
        ROUND(AVG(month_age), 1) AS 출하월령
    FROM shipment_records
    GROUP BY gender
    ORDER BY gender
    """, conn)
    conn.close()

    if not compare_df.empty:
        cmp_col1, cmp_col2 = st.columns([1, 1])
        with cmp_col1.container(border=True):
            st.dataframe(compare_df.set_index("성별").style.format(precision=1), width="stretch")
        with cmp_col2.container(border=True):
            import altair as alt
            metrics_for_chart = ["도체중_kg", "BMS", "단면적_㎠", "등지방_mm", "1+ 이상 출현율", "출하월령"]
            cmp_metric = st.selectbox("비교 지표", metrics_for_chart, key="cmp_metric")
            chart_df = compare_df[["성별", cmp_metric]].copy()
            bar_x = alt.X('성별:N', axis=alt.Axis(labelAngle=0, title=None, labelFontSize=12, labelFontWeight=600))
            bar_y = alt.Y(f'{cmp_metric}:Q', title=None, axis=alt.Axis(labelFontSize=11, tickCount=4))
            bars = alt.Chart(chart_df).mark_bar(
                size=44, cornerRadiusTopLeft=7, cornerRadiusTopRight=7,
            ).encode(
                x=bar_x, y=bar_y,
                color=alt.Color('성별:N', scale=alt.Scale(domain=['거세', '암', '수'], range=[CHART_FARM, CHART_COW, CHART_BULL]), legend=None),
                tooltip=['성별', cmp_metric],
            )
            bar_labels = alt.Chart(chart_df).mark_text(
                dy=-11, fontSize=12, fontWeight=600, color=CHART_LABEL,
            ).encode(x=bar_x, y=bar_y, text=alt.Text(f'{cmp_metric}:Q', format='.1f'))
            chart = alt.layer(bars, bar_labels).properties(height=220)
            st.altair_chart(style_chart(chart), width="stretch", theme=None)

# -----------------------------------------------------------------------------
# 메뉴 2: 1단계 · 출하성적 비교분석
# -----------------------------------------------------------------------------
elif menu == "1단계 · 출하성적 비교분석":
    page_header("1단계 · 출하성적 추출 &amp; 전국 성적 1:1 비교")
    show_flash()

    if not selected_farm_id:
        st.warning("먼저 사이드바 '➕ 신규 농가 등록'으로 농가를 등록하거나, '현재 컨설팅 농가 선택'에서 등록된 농가를 골라주세요.")
    else:
        # 이 화면에서 조회/업로드하는 모든 성적이 어느 농가로 저장되는지
        # 매 순간 눈으로 확인할 수 있게 상단에 고정 배너로 띄운다.
        # (사이드바 선택을 깜빡 안 바꾸고 조회했다가 엉뚱한 농가에 쌓이는 사고 방지)
        cur_farm_row = farms_df[farms_df["id"] == selected_farm_id]
        cur_farm_name = cur_farm_row.iloc[0]["farm_name"] if not cur_farm_row.empty else "농가"
        cur_farm_code = cur_farm_row.iloc[0]["farm_code"] if not cur_farm_row.empty else ""
        cur_farm_region = cur_farm_row.iloc[0]["region"] if not cur_farm_row.empty else ""
        st.info(
            f"📌 지금부터 조회·업로드하는 출하성적은 **{cur_farm_name}** 농가"
            f"(조합원번호 {cur_farm_code or '미등록'}, {cur_farm_region or '지역 미입력'})로 저장됩니다."
            " 다른 농가라면 왼쪽 사이드바 '현재 컨설팅 농가 선택'에서 먼저 바꿔주세요."
        )

        # 입력 방식 선택: 개체이력번호 직접 입력 또는 엑셀 일괄 업로드
        tab_api, tab_excel = st.tabs(["⚡ 축평원 OpenAPI 실시간 조회", "📁 농가출하데이터.xlsx 엑셀 업로드"])

        with tab_api:
            st.write("개체이력번호(12자리)를 줄바꿈하여 입력하면 축산물품질평가원에서 도체성적을 실시간으로 가져옵니다.")
            animal_text = st.text_area("이력번호 입력", height=100, placeholder="002154889011\n002154889012\n002154889013")
            if "fetched_records_list" not in st.session_state:
                st.session_state.fetched_records_list = None

            if st.button("⚡ 축평원 성적 임시 조회"):
                nos = [s.strip() for s in animal_text.replace(',', '\n').split('\n') if len(s.strip()) >= 8]
                if not nos:
                    st.error("올바른 이력번호를 입력해주세요.")
                else:
                    bar = st.progress(0)
                    records = []
                    for i, no in enumerate(nos):
                        info = fetch_cattle_grade(no)
                        if info:
                            records.append(info)
                        bar.progress((i + 1) / len(nos))
                    
                    if records:
                        st.session_state.fetched_records_list = records
                        st.success(f"{len(records)}두의 데이터를 가져왔습니다. 아래 표에서 확인 후 최종 저장해주세요.")
                    else:
                        st.warning("조회된 데이터가 없습니다. (API 키가 누락되었거나 잘못된 이력번호일 수 있습니다.)")
                        st.session_state.fetched_records_list = None

            if st.session_state.fetched_records_list is not None:
                st.markdown("### 🔍 조회된 데이터 검토 및 선별")
                st.info("💡 불필요한 개체는 표 안에서 행을 선택(좌측 체크박스) 후 `Delete` 키나 우측 상단의 🗑️휴지통 아이콘을 눌러 지우시면 됩니다.")
                
                df_view = pd.DataFrame(st.session_state.fetched_records_list)
                edited_df = st.data_editor(df_view, num_rows="dynamic", width="stretch")

                st.caption(f"↳ 저장 시 **{cur_farm_name}** 농가로 {len(edited_df)}두가 적재됩니다.")
                col1, col2 = st.columns([1, 1])
                with col1:
                    save_clicked = st.button("💾 검토 완료 및 DB 최종 적재", width="stretch")
                with col2:
                    cancel_clicked = st.button("🔄 조회 목록 초기화", width="stretch")
                
                if cancel_clicked:
                    st.session_state.fetched_records_list = None
                    st.rerun()

                if save_clicked:
                    if not edited_df.empty:
                        conn = get_db()
                        cur = conn.cursor()
                        saved = 0
                        for _, row in edited_df.iterrows():
                            # 표에서 행을 추가만 하고 비워 두면 이력번호가 없어 NOT NULL 오류로 앱이 멈췄다 → 건너뜀
                            ano = normalize_animal_no(row.get('animal_no'))
                            if not ano:
                                continue
                            sdate = row.get("slaughter_date")
                            sdate = str(sdate) if isinstance(sdate, str) and sdate.strip() else "2025-01-01"
                            try: syear = int(sdate[:4])
                            except: syear = 2025
                            
                            cw = row.get('carcass_weight')
                            cw = cw if pd.notna(cw) and cw else 0
                            cost = row.get('costAmt')
                            cost = cost if pd.notna(cost) and cost else 0
                            total_price = int(cw * cost)

                            # 축평원 판정 성별(judgeSexNm)을 쓴다. 응답에 성별이 없을 때만 거세로 간주
                            gender = row.get('gender')
                            gender = gender if isinstance(gender, str) and gender.strip() else "거세"

                            # INSERT OR REPLACE 는 SQLite 전용이라 Postgres 와 같이 쓰는 ON CONFLICT 로 바꿨다.
                            # 이력번호가 이미 있으면 그 행을 새 값으로 고친다 (다른 농가에 있던 개체면 이 농가로 옮겨진다 — 예전과 같음)
                            cur.execute("""
                            INSERT INTO shipment_records (
                                farm_id, animal_no, gender, slaughter_date, slaughter_year, month_age,
                                carcass_weight, grade_quality, grade_yield, bms, backfat, ribeye, price_per_kg, total_price, data_source
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ekape_api')
                            ON CONFLICT(animal_no) DO UPDATE SET
                                farm_id = excluded.farm_id, gender = excluded.gender, slaughter_date = excluded.slaughter_date,
                                slaughter_year = excluded.slaughter_year, month_age = excluded.month_age,
                                carcass_weight = excluded.carcass_weight, grade_quality = excluded.grade_quality,
                                grade_yield = excluded.grade_yield, bms = excluded.bms, backfat = excluded.backfat,
                                ribeye = excluded.ribeye, price_per_kg = excluded.price_per_kg,
                                total_price = excluded.total_price, data_source = excluded.data_source
                            """, (
                                selected_farm_id, ano, gender.strip(), sdate, syear, row.get('month_age'),
                                row.get('carcass_weight'), row.get('grade_quality'), row.get('grade_yield'), row.get('bms'),
                                row.get('backfat'), row.get('ribeye'), cost, total_price
                            ))
                            saved += 1
                        conn.commit()
                        conn.close()
                        st.session_state.fetched_records_list = None
                        notify_saved(f"{saved}두의 출하성적이 데이터베이스에 누적 저장되었습니다!", "출하성적 API 저장")
                        st.rerun()
                    else:
                        st.warning("저장할 데이터가 없습니다.")

        with tab_excel:
            st.write("`농가출하데이터.xlsx` 파일을 드래그앤드롭하여 한 번에 수십~수백 두의 성적을 적재합니다.")
            up_file = st.file_uploader("엑셀 파일 선택 (.xlsx)", type=["xlsx"])
            if up_file is not None:
                try:
                    preview_df = pd.read_excel(up_file)
                except Exception as ex:
                    st.error(f"엑셀 읽기 오류: {ex}")
                    preview_df = None

                proceed_upload = True
                if preview_df is not None:
                    # 파일 안에 농가명/조합원명 컬럼이 있으면 현재 선택된 농가와 대조한다.
                    # (이력번호 API 조회는 이름 정보가 없어 대조가 불가능하지만, 엑셀은 파일에
                    # 이름이 실려 있는 경우가 많아 여기서만큼은 잘못된 농가 파일을 잡아낼 수 있다)
                    name_col = next((c for c in ["농가명", "조합원명", "성명", "대표자명"] if c in preview_df.columns), None)
                    if name_col:
                        file_names = {str(v).strip() for v in preview_df[name_col].dropna().unique() if str(v).strip()}
                        mismatched = file_names - {str(cur_farm_name).strip()}
                        if mismatched:
                            st.warning(
                                f"⚠️ 파일 안의 이름({', '.join(sorted(mismatched))})이 현재 선택된 농가"
                                f" **{cur_farm_name}**와(과) 다릅니다. 다른 농가 파일을 잘못 올린 건 아닌지 확인해주세요."
                            )
                            proceed_upload = st.checkbox(f"그래도 이 파일을 '{cur_farm_name}' 농가로 업로드합니다")

                    st.caption(f"↳ 저장 시 **{cur_farm_name}** 농가로 최대 {len(preview_df)}행이 적재됩니다.")

                if st.button("📥 엑셀 데이터 파싱 및 적재", disabled=(preview_df is None or not proceed_upload)):
                    try:
                        df = preview_df
                        # 컬럼 매핑
                        col_map = {
                            "이력번호": ["이력번호", "개체번호", "개체식별번호"],
                            "성별": ["성별", "구분"],
                            "도축일자": ["도축일자", "출하일자"],
                            "도체중": ["도체중", "도체중량"],
                            "육질등급": ["육질등급"],
                            "육량등급": ["육량등급"],
                            "BMS": ["근내지방도", "BMS"],
                            "등지방": ["등지방두께", "등지방"],
                            "단면적": ["등심단면적", "단면적"],
                            "월령": ["도축개월령", "출하월령"]
                        }
                        def find_col(keys):
                            for k in keys:
                                if k in df.columns: return k
                            return None

                        def num(v):
                            # 숫자 칸에 '-'·'' 같은 글자가 있으면 빈 값으로 둔다. SQLite 는 글자도 그냥 저장했지만
                            # Supabase(Postgres) 숫자 컬럼은 거부해서 엑셀 업로드 전체가 실패한다.
                            try:
                                f = float(str(v).replace(",", "").strip())
                            except (TypeError, ValueError):
                                return None
                            return None if pd.isna(f) else f

                        def grade_text(v):
                            # 빈 칸(NaN)을 str()하면 'nan'이라는 글자가 등급으로 저장되던 문제 방지
                            if v is None or (isinstance(v, float) and pd.isna(v)):
                                return None
                            v = str(v).strip()
                            return v or None

                        conn = get_db()
                        cur = conn.cursor()
                        saved_cnt = 0
                        for _, row in df.iterrows():
                            ano = normalize_animal_no(row.get(find_col(col_map["이력번호"])))
                            if not ano or len(ano) < 8: continue
                            # 예전엔 '거세'가 아니면 전부 '암'으로 저장해서 수소도 암소 통계에 섞였다
                            g_raw = row.get(find_col(col_map["성별"]))
                            g_raw = "" if g_raw is None or (isinstance(g_raw, float) and pd.isna(g_raw)) else str(g_raw).strip()
                            if not g_raw or "거세" in g_raw:
                                gender = "거세"
                            elif "암" in g_raw:
                                gender = "암"
                            elif "수" in g_raw:
                                gender = "수"
                            else:
                                gender = "암"
                            sdate = str(row.get(find_col(col_map["도축일자"]), "2025-01-01"))[:10]
                            try: syear = int(sdate[:4])
                            except: syear = 2025

                            # 엑셀엔 단가·금액이 없으므로 이미 있는 행의 price_per_kg/total_price 는 건드리지 않는다
                            # (예전 INSERT OR REPLACE 는 행을 통째로 바꿔 API로 받은 단가가 지워졌다)
                            cur.execute("""
                            INSERT INTO shipment_records (
                                farm_id, animal_no, gender, slaughter_date, slaughter_year, month_age,
                                carcass_weight, grade_quality, grade_yield, bms, backfat, ribeye, data_source
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'excel')
                            ON CONFLICT(animal_no) DO UPDATE SET
                                farm_id = excluded.farm_id, gender = excluded.gender, slaughter_date = excluded.slaughter_date,
                                slaughter_year = excluded.slaughter_year, month_age = excluded.month_age,
                                carcass_weight = excluded.carcass_weight, grade_quality = excluded.grade_quality,
                                grade_yield = excluded.grade_yield, bms = excluded.bms, backfat = excluded.backfat,
                                ribeye = excluded.ribeye, data_source = excluded.data_source
                            """, (
                                selected_farm_id, ano, gender, sdate, syear,
                                num(row.get(find_col(col_map["월령"]))),
                                num(row.get(find_col(col_map["도체중"]))),
                                grade_text(row.get(find_col(col_map["육질등급"]))),
                                grade_text(row.get(find_col(col_map["육량등급"]))),
                                num(row.get(find_col(col_map["BMS"]))),
                                num(row.get(find_col(col_map["등지방"]))),
                                num(row.get(find_col(col_map["단면적"])))
                            ))
                            saved_cnt += 1
                        conn.commit()
                        conn.close()
                        notify_saved(f"엑셀에서 {saved_cnt}두의 출하성적을 성공적으로 적재했습니다!", "출하성적 엑셀 저장")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"엑셀 처리 오류: {ex}")

        st.markdown("---")

        # 연도 및 성별 선택 (비교분석표 필터)
        filter_c1, filter_c2 = st.columns(2)
        with filter_c1:
            conn = get_db()
            year_rows = conn.execute("""
            SELECT DISTINCT slaughter_year FROM shipment_records
            WHERE farm_id = ? AND slaughter_year IS NOT NULL
            ORDER BY slaughter_year DESC
            """, (selected_farm_id,)).fetchall()
            available_years = [r["slaughter_year"] for r in year_rows]
            year_options = ["전체 (누적)"] + [str(y) for y in available_years]
            selected_year_label = st.selectbox("📅 비교 연도 선택", year_options)
            selected_year = None if selected_year_label == "전체 (누적)" else int(selected_year_label)
        
        with filter_c2:
            selected_gender_label = st.selectbox("🐂 성별 선택", ["전체", "거세", "암"])
            selected_gender = None if selected_gender_label == "전체" else selected_gender_label

        if available_years:
            pr_c1, pr_c2 = st.columns([3, 2])
            with pr_c1:
                st.caption("🖨️ 방문용 A4 인쇄 리포트: 2023~2026년 도체성적·등급출현율·달성률을 3페이지로 정리합니다.")
            with pr_c2:
                farm_row = farms_df[farms_df["id"] == selected_farm_id]
                farm_name_for_report = farm_row.iloc[0]["farm_name"] if not farm_row.empty else "농가"
                print_html = build_print_comparison_report_html(farm_name_for_report, selected_farm_id)
                st.download_button("🖨️ 인쇄용 비교 리포트(.html) 다운로드", data=print_html, file_name=f"{farm_name_for_report}_출하성적_비교_리포트.html", mime="text/html")
            st.markdown("---")

        # 1:1 비교분석표 및 수익성 분석
        
        # 성별 조건문 동적 생성 (개체별 상세 성적표용)
        gender_sql = f" AND gender = '{selected_gender}'" if selected_gender else ""

        # 전국 비교는 성별이 섞이면 의미가 없으므로 한 성별로만 한다.
        # '전체'를 고르면 거세우로 비교하되, 거세우 출하가 없는 농가는 암소로 비교한다.
        cmp_gender = selected_gender
        if not cmp_gender:
            steer_cnt = conn.execute(
                "SELECT COUNT(*) FROM shipment_records WHERE farm_id = ? AND gender = '거세'" + (" AND slaughter_year = ?" if selected_year else ""),
                (selected_farm_id, selected_year) if selected_year else (selected_farm_id,)
            ).fetchone()[0]
            cmp_gender = "거세" if steer_cnt > 0 else "암"
        cmp_gender_sql = f" AND gender = '{cmp_gender}'"

        if selected_year:
            stats_row = conn.execute(f"""
            SELECT
                COUNT(id) as total_count,
                ROUND(AVG(carcass_weight), 1) as avg_weight,
                ROUND(AVG(bms), 1) as avg_bms,
                ROUND(AVG(ribeye), 1) as avg_ribeye,
                ROUND(AVG(backfat), 1) as avg_backfat,
                ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as rate_1plus_above,
                ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as rate_c_grade,
                ROUND(AVG(month_age), 1) as avg_month_age
            FROM shipment_records
            WHERE farm_id = ? AND slaughter_year = ? {cmp_gender_sql}
            """, (selected_farm_id, selected_year)).fetchone()
        else:
            stats_row = conn.execute(f"""
            SELECT
                COUNT(id) as total_count,
                ROUND(AVG(carcass_weight), 1) as avg_weight,
                ROUND(AVG(bms), 1) as avg_bms,
                ROUND(AVG(ribeye), 1) as avg_ribeye,
                ROUND(AVG(backfat), 1) as avg_backfat,
                ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as rate_1plus_above,
                ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as rate_c_grade,
                ROUND(AVG(month_age), 1) as avg_month_age
            FROM shipment_records
            WHERE farm_id = ? {cmp_gender_sql}
            """, (selected_farm_id,)).fetchone()

        if selected_year:
            records_df = pd.read_sql_query(f"""
            SELECT animal_no AS 이력번호, gender AS 성별, slaughter_date AS 도축일자, carcass_weight AS 도체중_kg,
                   grade_quality AS 육질등급, grade_yield AS 육량등급, bms AS BMS, backfat AS 등지방_mm,
                   ribeye AS 단면적_㎠, month_age AS 출하월령
            FROM shipment_records WHERE farm_id = ? AND slaughter_year = ? {gender_sql} ORDER BY slaughter_date DESC
            """, conn, params=(selected_farm_id, selected_year))
        else:
            records_df = pd.read_sql_query(f"""
            SELECT animal_no AS 이력번호, gender AS 성별, slaughter_date AS 도축일자, carcass_weight AS 도체중_kg,
                   grade_quality AS 육질등급, grade_yield AS 육량등급, bms AS BMS, backfat AS 등지방_mm,
                   ribeye AS 단면적_㎠, month_age AS 출하월령
            FROM shipment_records WHERE farm_id = ? {gender_sql} ORDER BY slaughter_date DESC
            """, conn, params=(selected_farm_id,))
        conn.close()

        if stats_row and stats_row["total_count"] > 0:
            nat_gender_key = cmp_gender
            nat = NATIONAL_STATS[nat_gender_key]

            if selected_year and selected_year in nat["도체중"]:
                cy = selected_year
            else:
                cy = nat_latest_year(nat_gender_key) or 2025 # 최신 연도로 폴백

            year_caption = f"{selected_year}년" if selected_year else "전체 누적"
            gender_caption = {"거세": "거세우", "암": "암소"}.get(nat_gender_key, nat_gender_key)
            st.subheader(f"📊 출하성적 전국 1:1 비교분석표 ({gender_caption} 기준, {year_caption} · 전국 {cy}년 평균과 비교)")
            if not selected_gender:
                st.caption(f"※ 성별 '전체'를 선택해도 전국 비교는 성별이 섞이지 않도록 {gender_caption} 출하분만으로 계산합니다. 아래 개체별 성적표에는 전체 개체가 나옵니다.")

            def f1(val): return f"{val:.1f}" if val is not None and pd.notna(val) else "-"
            # 농가값이나 전국값이 없으면 차이를 None으로 둔다 (예전엔 0으로 처리돼 '우수'로 잘못 판정됨)
            def get_diff(v1, v2): return v1 - v2 if (v1 is not None and v2 is not None and pd.notna(v1) and pd.notna(v2)) else None
            def judge(diff, good, bad, good_if=lambda d: d >= 0): return "-" if diff is None else (good if good_if(diff) else bad)

            w_nat = nat["도체중"].get(cy)
            b_nat = nat["BMS"].get(cy)
            r_nat = nat["단면적"].get(cy)
            f_nat = nat["등지방"].get(cy)
            q_nat = nat.get("grade_quality", {}).get(cy, {}).get("1+이상")
            y_nat = nat.get("grade_yield", {}).get(cy, {}).get("C")
            m_nat = nat["출하월령"].get(cy)

            d_w = get_diff(stats_row["avg_weight"], w_nat)
            d_b = get_diff(stats_row["avg_bms"], b_nat)
            d_r = get_diff(stats_row["avg_ribeye"], r_nat)
            d_f = get_diff(stats_row["avg_backfat"], f_nat)
            d_q = get_diff(stats_row["rate_1plus_above"], q_nat)
            d_y = get_diff(stats_row["rate_c_grade"], y_nat)
            d_m = get_diff(stats_row["avg_month_age"], m_nat)
            comp_table = [
                {"평가 항목": "도체중 (kg)", "농가 성적": f1(stats_row["avg_weight"]), "전국 평균": f1(w_nat), "격차 (+/-)": f1(d_w), "진단": judge(d_w, "우수 (▲)", "미흡 (▼)")},
                {"평가 항목": "근내지방도 (BMS)", "농가 성적": f1(stats_row["avg_bms"]), "전국 평균": f1(b_nat), "격차 (+/-)": f1(d_b), "진단": judge(d_b, "우수 (▲)", "미흡 (▼)")},
                {"평가 항목": "등심단면적 (㎠)", "농가 성적": f1(stats_row["avg_ribeye"]), "전국 평균": f1(r_nat), "격차 (+/-)": f1(d_r), "진단": judge(d_r, "우수 (▲)", "미흡 (▼)")},
                {"평가 항목": "등지방두께 (mm)", "농가 성적": f1(stats_row["avg_backfat"]), "전국 평균": f1(f_nat), "격차 (+/-)": f1(d_f), "진단": judge(d_f, "적정", "과비주의 (과다)", lambda d: d <= 1.0)},
                {"평가 항목": "1+이상 출현율 (%)", "농가 성적": f1(stats_row["rate_1plus_above"]), "전국 평균": f1(q_nat), "격차 (+/-)": f1(d_q), "진단": judge(d_q, "우수 (▲)", "개선필요")},
                {"평가 항목": "C등급 출현율 (%)", "농가 성적": f1(stats_row["rate_c_grade"]), "전국 평균": f1(y_nat), "격차 (+/-)": f1(d_y), "진단": judge(d_y, "우수 (▼)", "개선필요 (▲)", lambda d: d <= 0)},
                {"평가 항목": "출하월령 (개월)", "농가 성적": f1(stats_row["avg_month_age"]), "전국 평균": f1(m_nat), "격차 (+/-)": f1(d_m), "진단": judge(d_m, "단기출하 (우수)", "지연출하", lambda d: d <= 0)}
            ]
            st.table(pd.DataFrame(comp_table))

            # 최근 3년 연도별 평가항목 추이 차트
            if len(available_years) >= 1:
                recent_years = sorted(available_years, reverse=True)[:3]
                recent_years = sorted(recent_years)  # 차트는 오름차순 표기

                conn3 = get_db()
                placeholders = ",".join(["?"] * len(recent_years))
                yearly_rows = conn3.execute(f"""
                SELECT slaughter_year AS 연도,
                    ROUND(AVG(carcass_weight), 1) as "도체중_kg",
                    ROUND(AVG(bms), 1) as "BMS",
                    ROUND(AVG(ribeye), 1) as "단면적_㎠",
                    ROUND(AVG(backfat), 1) as "등지방_mm",
                    ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as "1+ 이상 출현율",
                    ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as "C등급 출현율",
                    ROUND(AVG(month_age), 1) as "출하월령"
                FROM shipment_records
                WHERE farm_id = ? {cmp_gender_sql} AND slaughter_year IN ({placeholders})
                GROUP BY slaughter_year
                ORDER BY slaughter_year
                """, (selected_farm_id, *recent_years)).fetchall()
                conn3.close()
                farm_yearly_df = pd.DataFrame([dict(r) for r in yearly_rows])

                st.markdown("---")
                st.subheader(f"📈 최근 {len(recent_years)}년 연도별 평가항목 추이 ({recent_years[0]}~{recent_years[-1]}년)")
                trend_metric = st.selectbox(
                    "추이를 확인할 평가항목",
                    ["도체중_kg", "BMS", "단면적_㎠", "등지방_mm", "1+ 이상 출현율", "C등급 출현율", "출하월령"],
                    key="recent3_trend_metric"
                )
                nat_key_map = {
                    "도체중_kg": "도체중", "BMS": "BMS", "단면적_㎠": "단면적", "등지방_mm": "등지방", "출하월령": "출하월령"
                }
                trend_rows = []
                for y in recent_years:
                    if trend_metric == "1+ 이상 출현율":
                        nat_val = nat.get("grade_quality", {}).get(y, {}).get("1+이상")
                    elif trend_metric == "C등급 출현율":
                        nat_val = nat.get("grade_yield", {}).get(y, {}).get("C")
                    else:
                        nat_val = nat.get(nat_key_map[trend_metric], {}).get(y)

                    farm_val = None
                    if not farm_yearly_df.empty and y in farm_yearly_df["연도"].values:
                        farm_val = farm_yearly_df.loc[farm_yearly_df["연도"] == y, trend_metric].iloc[0]

                    trend_rows.append({"연도": f"{y}년", "농가 평균": farm_val, "전국 평균": nat_val})

                trend_df = pd.DataFrame(trend_rows).melt("연도", var_name="구분", value_name="값")
                import altair as alt
                trend_chart = alt.Chart(trend_df).mark_line(point=True, strokeWidth=3).encode(
                    x=alt.X('연도:N', axis=alt.Axis(labelAngle=0, title='')),
                    y=alt.Y('값:Q', title=trend_metric, scale=alt.Scale(zero=False)),
                    color=alt.Color('구분:N', scale=alt.Scale(range=['#1e3a8a', '#94a3b8']), legend=alt.Legend(orient='bottom', title=None))
                ).properties(height=320)
                st.altair_chart(trend_chart, width="stretch")

                st.markdown("---")
                with st.expander("🖨️ 최근 3년 전국 1:1 종합 비교분석표 보기 (인쇄용)"):
                    st.caption("※ 화면 캡처 또는 브라우저 인쇄(Ctrl+P)를 통해 농가 현장 컨설팅 리포트로 바로 활용하세요.")
                    comp_3yr_rows = []
                    for y in recent_years:
                        w_n = nat["도체중"].get(y)
                        b_n = nat["BMS"].get(y)
                        r_n = nat["단면적"].get(y)
                        f_n = nat["등지방"].get(y)
                        q_n = nat.get("grade_quality", {}).get(y, {}).get("1+이상")
                        y_n = nat.get("grade_yield", {}).get(y, {}).get("C")
                        m_n = nat["출하월령"].get(y)
                        
                        f_val = {"도체중_kg": "-", "BMS": "-", "단면적_㎠": "-", "등지방_mm": "-", "1+ 이상 출현율": "-", "C등급 출현율": "-", "출하월령": "-"}
                        if not farm_yearly_df.empty and y in farm_yearly_df["연도"].values:
                            f_row = farm_yearly_df.loc[farm_yearly_df["연도"] == y].iloc[0]
                            f_val = {k: f1(f_row[k]) for k in f_val.keys()}
                            
                        comp_3yr_rows.append({
                            "연도": f"{y}년", "구분": "🏆 농가 성적", "도체중 (kg)": f_val["도체중_kg"], "근내지방도 (BMS)": f_val["BMS"], 
                            "단면적 (㎠)": f_val["단면적_㎠"], "등지방 (mm)": f_val["등지방_mm"], "1+이상 (%)": f_val["1+ 이상 출현율"], 
                            "C등급 (%)": f_val["C등급 출현율"], "출하월령": f_val["출하월령"]
                        })
                        comp_3yr_rows.append({
                            "연도": f"{y}년", "구분": "📊 전국 평균", "도체중 (kg)": f1(w_n), "근내지방도 (BMS)": f1(b_n), 
                            "단면적 (㎠)": f1(r_n), "등지방 (mm)": f1(f_n), "1+이상 (%)": f1(q_n), 
                            "C등급 (%)": f1(y_n), "출하월령": f1(m_n)
                        })
                    if comp_3yr_rows:
                        df_3yr = pd.DataFrame(comp_3yr_rows).set_index(["연도", "구분"])
                        st.table(df_3yr)

            # 수익성 분석
            diff_w = d_w
            est_diff_head = int(diff_w * 21000) if diff_w is not None else 0 # kg당 평균 21,000원 기준
            est_total_diff = est_diff_head * stats_row["total_count"]

            st.markdown("#### 💰 음성공판장 기준 추정 수익성 임팩트")
            if diff_w is None:
                st.info("도체중 데이터(농가 또는 전국)가 없어 수익성을 추정할 수 없습니다.")
            elif est_total_diff >= 0:
                st.markdown(f"전국 평균 대비 **두당 약 +{est_diff_head:,}원**, 총 출하({stats_row['total_count']}두) 기준 <span class='profit-plus'>+{est_total_diff:,}원</span>의 추가 조수입을 달성하고 계십니다.", unsafe_allow_html=True)
            else:
                st.markdown(f"전국 평균 대비 **두당 약 {est_diff_head:,}원**, 총 출하 기준 <span class='profit-minus'>{est_total_diff:,}원</span>의 수익 손실이 발생하고 있어 사양관리 개선이 시급합니다.", unsafe_allow_html=True)

            st.markdown("---")
            st.subheader(f"📑 개체별 출하 상세 성적표 ({year_caption}, 총 {len(records_df)}두)")
            st.dataframe(records_df, width="stretch")
        elif selected_year:
            st.info(f"{selected_year}년에 등록된 출하 성적이 없습니다. 다른 연도를 선택하거나 위 입력창을 통해 데이터를 추가해주세요.")
        else:
            st.info("등록된 출하 성적이 없습니다. 위 입력창을 통해 이력번호 또는 엑셀을 업로드해주세요.")

# -----------------------------------------------------------------------------
# 메뉴 3: 2단계 · 현장방문조사 (한우컨설팅일지 실제 양식)
# -----------------------------------------------------------------------------
elif menu == "2단계 · 현장방문조사":
    page_header("2단계 · 현장 방문 조사표 입력")
    show_flash()

    form_mode = st.radio("작성 모드", ["🆕 신규 방문조사 작성", "✏️ 기존 방문조사 수정"], horizontal=True)

    edit_visit_id = None
    existing = {}

    if form_mode == "🆕 신규 방문조사 작성":
        if not selected_farm_id:
            st.warning("먼저 좌측 사이드바에서 농가를 선택해주세요.")
    else:
        conn = get_db()
        edit_farms_df = pd.read_sql_query("SELECT id, farm_name, owner_name FROM farms ORDER BY farm_name", conn)
        conn.close()

        if edit_farms_df.empty:
            st.warning("등록된 농가가 없습니다.")
        else:
            edit_farm_options = build_farm_options(edit_farms_df, lambda r: f"{r['farm_name']} ({r['owner_name'] or '조합원'})")
            default_edit_idx = list(edit_farm_options.values()).index(selected_farm_id) if selected_farm_id in edit_farm_options.values() else 0
            edit_farm_label = st.selectbox("✏️ 수정할 농가 선택", list(edit_farm_options.keys()), index=default_edit_idx)
            edit_target_farm_id = edit_farm_options[edit_farm_label]

            conn = get_db()
            past_visits_df = pd.read_sql_query(
                "SELECT v.id, v.visit_number, v.visit_date, s.survey_data FROM visits v LEFT JOIN field_surveys s ON s.visit_id = v.id WHERE v.farm_id = ? ORDER BY v.visit_number",
                conn, params=(edit_target_farm_id,)
            )
            conn.close()

            if past_visits_df.empty:
                st.info(f"'{edit_farm_label}' 농가의 방문 기록이 없습니다. '신규 방문조사 작성'으로 입력해주세요.")
            else:
                # 방문 횟수가 1회 이상이면 몇 차 방문을 수정할지도 선택
                visit_labels = [f"{row['visit_number']}차 ({row['visit_date']})" for _, row in past_visits_df.iterrows()]
                picked = st.selectbox("수정할 방문 회차 선택", visit_labels)
                picked_row = past_visits_df.iloc[visit_labels.index(picked)]
                edit_visit_id = int(picked_row['id'])
                if picked_row['survey_data']:
                    try:
                        existing = json.loads(picked_row['survey_data'])
                    except (TypeError, ValueError):
                        existing = {}
                if not existing:
                    st.caption("이 방문 기록은 상세 조사표(survey_data)가 비어있어 빈 양식으로 시작합니다 — 입력 후 저장하면 이 방문에 채워집니다.")

    show_form = (form_mode == "🆕 신규 방문조사 작성" and selected_farm_id) or edit_visit_id is not None
    if show_form:
        def gv(key, fallback):
            return existing.get(key, fallback)

        def gi(options, key, fallback):
            val = existing.get(key, fallback)
            return options.index(val) if val in options else 0

        default_date = datetime.now()
        if existing.get('visitDate'):
            try:
                default_date = datetime.strptime(str(existing['visitDate'])[:10], "%Y-%m-%d")
            except ValueError:
                pass

        # '1. 조사 기본정보'는 지역 선택 시 아래 날씨 정보가 즉시 갱신되도록 폼 밖에 둡니다
        # (st.form 안의 위젯은 '제출' 전까지 값이 갱신되지 않기 때문)
        s_dict = {}
        with st.expander("1. 조사 기본정보", expanded=True):
            r1_c1, r1_c2 = st.columns(2)
            s_dict['investigator'] = r1_c1.text_input("조사자 성명", value=gv('investigator', "컨설턴트 배성태"))
            s_dict['visitDate'] = str(r1_c2.date_input("조사일자", default_date))

            r2_c1, r2_c2 = st.columns(2)
            s_dict['memberName'] = r2_c1.text_input("조합원명", value=gv('memberName', ""))
            s_dict['memberId'] = r2_c2.text_input("조합원번호", value=gv('memberId', ""))

            s_dict['region'] = st.selectbox("지역 (선택 시 아래 '2. 날씨 정보' 섹션이 즉시 자동으로 채워집니다)", REGION_OPTIONS, index=gi(REGION_OPTIONS, 'region', REGION_OPTIONS[0]))
            s_dict['farmType'] = st.radio("전업여부", ["전업", "겸업"], horizontal=True, index=gi(["전업", "겸업"], 'farmType', "전업"))
            biz_opts = ["28개월 조기출하(회전율 최우선)", "30개월 이상 장기비육(육질 투플러스 최우선)", "복합"]
            s_dict['bizGoal'] = st.selectbox("🎯 농가 경영 목표 (출하 전략)", biz_opts, index=gi(biz_opts, 'bizGoal', biz_opts[0]))

        wd = WEATHER_DATA.get(s_dict['region'], {})

        def wv(key, wd_key):
            saved = gv(key, None)
            if saved not in (None, 0, 0.0):
                return float(saved)
            return float(wd.get(wd_key, 0.0))

        with st.form("site_survey_form"):

            with st.expander("2. 날씨 정보 (2025년 기준)", expanded=True):
                if not wd:
                    st.caption("등록된 지역이 아니라서 자동으로 채워지는 값이 없습니다. 직접 입력해주세요.")
                r3_c1, r3_c2 = st.columns(2)
                s_dict['dailyAvgTemp'] = r3_c1.number_input("연평균기온 (℃)", value=wv('dailyAvgTemp', 'avgTemp'))
                s_dict['highTemp'] = r3_c2.number_input("최고기온 (℃)", value=wv('highTemp', 'highTemp'))
                s_dict['lowTemp'] = r3_c1.number_input("최저기온 (℃)", value=wv('lowTemp', 'lowTemp'))
                s_dict['annualPrecip'] = r3_c2.number_input("평균강수량 (연간) (mm)", value=wv('annualPrecip', 'precip'))
                s_dict['avgWindSpeed'] = r3_c1.number_input("평균풍속 (m/s)", value=wv('avgWindSpeed', 'wind'))
                s_dict['avgHumidity'] = r3_c2.number_input("평균상대습도 (%)", value=wv('avgHumidity', 'humid'))

            with st.expander("3. 축산 사육환경", expanded=False):
                breeding_opts = ["일관사육","암소번식","비육전문(거)","비육전문(암)","비육전문(거,암)"]
                s_dict['breedingType'] = st.selectbox("사육형태", breeding_opts, index=gi(breeding_opts, 'breedingType', breeding_opts[0]))
                st.markdown("---")
                pen_size_opts = ["5X10","4X8","3X6","운동장","계류","기타"]
                pen_density_opts = ["높음","적정","낮음"]
                rc1, rc2, rc3 = st.columns(3)
                s_dict['fatteningPenSize'] = rc1.selectbox("비육우방 크기", pen_size_opts, index=gi(pen_size_opts, 'fatteningPenSize', pen_size_opts[0]))
                s_dict['fatteningPenDensity'] = rc1.selectbox("비육우방 밀도", pen_density_opts, index=gi(pen_density_opts, 'fatteningPenDensity', pen_density_opts[1]))
                s_dict['breedingPenSize'] = rc2.selectbox("번식우방 크기", pen_size_opts, index=gi(pen_size_opts, 'breedingPenSize', pen_size_opts[0]))
                s_dict['breedingPenDensity'] = rc2.selectbox("번식우방 밀도", pen_density_opts, index=gi(pen_density_opts, 'breedingPenDensity', pen_density_opts[1]))
                s_dict['calfPenSize'] = rc3.selectbox("송아지우방 크기", pen_size_opts, index=gi(pen_size_opts, 'calfPenSize', pen_size_opts[0]))
                s_dict['calfPenDensity'] = rc3.selectbox("송아지우방 밀도", pen_density_opts, index=gi(pen_density_opts, 'calfPenDensity', pen_density_opts[1]))

                st.markdown("---")
                yes_no_opts = ["여","부"]
                c_env1, c_env2 = st.columns(2)
                s_dict['bulkBin'] = c_env1.radio("벌크빈", yes_no_opts, horizontal=True, index=gi(yes_no_opts, 'bulkBin', "부"))
                s_dict['autoFeeder'] = c_env2.radio("자동급이시설", yes_no_opts, horizontal=True, index=gi(yes_no_opts, 'autoFeeder', "부"))
                s_dict['tmr'] = c_env1.radio("TMR 급여", yes_no_opts, horizontal=True, index=gi(yes_no_opts, 'tmr', "부"))
                s_dict['selfMix'] = c_env2.radio("자가배합", yes_no_opts, horizontal=True, index=gi(yes_no_opts, 'selfMix', "부"))
                s_dict['castrationAge'] = c_env1.number_input("거세시기 (개월)", value=int(gv('castrationAge', 0)))
                s_dict['castrationMethod'] = c_env2.radio("거세방법", ["무혈","유혈"], horizontal=True, index=gi(["무혈","유혈"], 'castrationMethod', "무혈"))
                floor_opts = ["우수","양호","미흡"]
                s_dict['floorCondition'] = c_env1.selectbox("축사바닥", floor_opts, index=gi(floor_opts, 'floorCondition', "양호"))
                s_dict['dewormingCount'] = c_env2.number_input("정기구충 (회/년)", value=int(gv('dewormingCount', 0)))

                st.markdown("---")
                st.markdown("**🔍 추가 정밀 진단 항목**")
                water_opts = ["매우 청결", "보통", "불량(이끼, 분변 오염 등)"]
                manure_opts = ["과도하게 묽음", "적정(모양 유지)", "과도하게 단단함"]
                yes_no2_opts = ["예", "아니오"]
                c_env3, c_env4 = st.columns(2)
                s_dict['waterQuality'] = c_env3.selectbox("💧 음수(물) 관리 실태", water_opts, index=gi(water_opts, 'waterQuality', water_opts[1]))
                s_dict['manureScore'] = c_env4.selectbox("💩 소 분변 상태", manure_opts, index=gi(manure_opts, 'manureScore', manure_opts[1]))
                s_dict['troughCleaning'] = st.radio("🍽️ 사조(밥통) 매일 청소 및 잔량 폐기 여부", yes_no2_opts, horizontal=True, index=gi(yes_no2_opts, 'troughCleaning', "예"))

            with st.expander("4. 사료급여", expanded=False):
                c_feed1, c_feed2 = st.columns(2)
                s_dict['feedOrder'] = c_feed1.text_input("급여순서", value=gv('feedOrder', ""), placeholder="예: 조사료 → 배합사료")
                s_dict['feedFrequency'] = c_feed2.number_input("급여횟수 (회/일)", value=int(gv('feedFrequency', 2)))
                forage_opts = ["우수(알팔파, 티모시 등 수입산 위주)", "보통(볏짚/라이그라스 혼합)", "미흡(수분 과다, 곰팡이 관찰)"]
                s_dict['forageQuality'] = st.selectbox("🌾 조사료의 품질(질) 평가", forage_opts, index=gi(forage_opts, 'forageQuality', forage_opts[1]))
                st.markdown("**(아래 표를 클릭하여 품목과 급여수준(낮음/적정/높음)을 직접 입력하세요)**")
                feed_index = ["배합사료 품목", "배합사료 급여수준", "조사료 품목", "조사료 급여수준", "첨가제 품목", "첨가제 급여수준"]
                feed_cols = [c['label'] for c in FEED_CATS]
                feed_df = None
                if existing.get('feed_matrix'):
                    try:
                        feed_df = pd.DataFrame(existing['feed_matrix']).reindex(index=feed_index, columns=feed_cols)
                    except (ValueError, TypeError):
                        feed_df = None
                if feed_df is None:
                    feed_df = pd.DataFrame(index=feed_index, columns=feed_cols)
                feed_df.fillna("", inplace=True)
                edited_feed = st.data_editor(feed_df, width="stretch")
                s_dict['feed_matrix'] = edited_feed.to_dict()

            with st.expander("5. 사육두수 현황", expanded=False):
                s_dict['countCow'] = st.number_input("번식우(암소) (두)", value=int(gv('countCow', 0)))
                s_dict['countSteer'] = st.number_input("거세우 (두)", value=int(gv('countSteer', 0)))
                s_dict['countGrowing'] = st.number_input("육성우 (두)", value=int(gv('countGrowing', 0)))
                s_dict['countCalf'] = st.number_input("송아지 (두)", value=int(gv('countCalf', 0)))
                s_dict['countOptimal'] = st.number_input("적정 사육두수 (두)", value=int(gv('countOptimal', 0)))

            with st.expander("6. 번식관리 / 7. 질병예방 / 8. 특이사항", expanded=False):
                ai_opts = ["자가 수정","수정사 의뢰"]
                s_dict['aiMethod'] = st.radio("인공수정 방법", ai_opts, horizontal=True, index=gi(ai_opts, 'aiMethod', ai_opts[0]))
                s_dict['calvingInterval'] = st.number_input("평균 분만간격 (개월)", value=float(gv('calvingInterval', 0.0)))
                s_dict['mortalityRate'] = st.number_input("최근 1년 폐사율 (%)", value=float(gv('mortalityRate', 0.0)))

                st.markdown("---")
                st.markdown("**🍼 송아지 포유 관리**")
                c_calf1, c_calf2 = st.columns(2)
                s_dict['weaningAge'] = c_calf1.number_input("송아지 이유 월령", value=float(gv('weaningAge', 0.0)), step=0.5)
                s_dict['artificialRearing'] = c_calf2.radio("인공포유 여부", yes_no2_opts, horizontal=True, index=gi(yes_no2_opts, 'artificialRearing', "아니오"))

                st.markdown("---")
                s_dict['consultingNotes'] = st.text_area("현장 점검 소견 및 컨설팅사항", value=gv('consultingNotes', ""), height=100)

            submitted = st.form_submit_button("💾 방문조사 수정사항 저장" if edit_visit_id else "💾 종합 현장 조사표 DB 저장")
            if submitted:
                conn = get_db()
                cur = conn.cursor()
                if edit_visit_id:
                    cur.execute("UPDATE visits SET visit_date = ?, consultant_name = ? WHERE id = ?",
                                (s_dict['visitDate'], s_dict['investigator'], edit_visit_id))
                    cur.execute("""
                    INSERT INTO field_surveys (visit_id, survey_data) VALUES (?, ?)
                    ON CONFLICT(visit_id) DO UPDATE SET survey_data = excluded.survey_data
                    """, (edit_visit_id, json.dumps(s_dict, ensure_ascii=False)))
                    conn.commit()
                    conn.close()
                    notify_saved(f"방문 기록(ID {edit_visit_id})이 수정되어 저장되었습니다!", "현장조사 수정 저장")
                    show_flash()
                else:
                    cur.execute("SELECT COALESCE(MAX(visit_number), 0) + 1 FROM visits WHERE farm_id = ?", (selected_farm_id,))
                    v_no = cur.fetchone()[0]
                    # lastrowid 는 Postgres 에 없어서 RETURNING 으로 새 방문 ID를 받는다 (SQLite 3.35+·Turso 도 지원)
                    cur.execute("INSERT INTO visits (farm_id, visit_number, visit_date, consultant_name) VALUES (?, ?, ?, ?) RETURNING id",
                                (selected_farm_id, v_no, s_dict['visitDate'], s_dict['investigator']))
                    v_id = cur.fetchone()[0]

                    cur.execute("""
                    INSERT INTO field_surveys (visit_id, survey_data)
                    VALUES (?, ?)
                    """, (v_id, json.dumps(s_dict, ensure_ascii=False)))
                    conn.commit()
                    conn.close()
                    notify_saved(f"{v_no}차 현장 방문 조사표가 DB에 성공적으로 통합 저장되었습니다!", "현장조사 신규 저장")
                    show_flash()

# -----------------------------------------------------------------------------
# 메뉴 4: 3단계 · AI 리포트
# -----------------------------------------------------------------------------
elif menu == "3단계 · AI 리포트":
    page_header("3단계 · AI 맞춤형 종합 컨설팅 보고서", "출하성적(정량)과 현장조사(정성)를 융합 분석하여 '진단 → 원인 → 처방' 7단 구성 리포트를 생성합니다.")
    show_flash()

    conn = get_db()
    farms_df = pd.read_sql_query("SELECT id, farm_name, owner_name FROM farms", conn)
    conn.close()

    if farms_df.empty:
        st.warning("등록된 농가가 없습니다. 농가를 먼저 등록해주세요.")
    else:
        farm_options = build_farm_options(farms_df, lambda r: f"{r['farm_name']} ({r['owner_name'] or '조합원'})")
        default_index = list(farm_options.values()).index(selected_farm_id) if selected_farm_id in farm_options.values() else 0

        st.markdown("### 🎯 리포트 대상 농가 선택")
        ai_target_farm_name = st.selectbox("분석할 농가를 선택하세요", list(farm_options.keys()), index=default_index)
        ai_target_farm_id = farm_options[ai_target_farm_name]

        st.markdown("---")
        # 리포트 생성 방식을 상황에 따라 고를 수 있게 버튼을 둘로 나눈다.
        # 전문자료 방식은 약 15만 토큰을 함께 보내므로 근거는 정확해지지만 느리고 비싸다.
        kb_ready = bool(load_knowledge_base())
        c_btn1, c_btn2, c_btn3 = st.columns([2, 2, 1])
        with c_btn1:
            gen_kb_click = st.button(
                "📚 전문자료 기반 리포트 생성",
                width="stretch",
                disabled=not kb_ready,
                help=("한우 컨설팅 길라잡이·자가TMR·육종가 기초지식을 근거로 처방합니다. "
                      "출처를 인용하지만 시간과 비용이 더 듭니다."
                      if kb_ready else
                      "knowledge/ 폴더를 찾지 못했습니다. build_knowledge.py를 먼저 실행하세요."),
            )
        with c_btn2:
            gen_plain_click = st.button(
                "✨ 일반 리포트 생성 (빠름)",
                width="stretch",
                help="Claude의 일반 지식만으로 작성합니다. 빠르고 저렴하지만 자료 근거 인용은 없습니다.",
            )
        with c_btn3:
            cancel_click = st.button("❌ 조회취소", width="stretch")

        st.caption(
            "엔진: Claude Sonnet 5 · "
            + ("📚 전문자료 준비됨" if kb_ready
               else "⚠️ 전문자료 없음 — build_knowledge.py 실행 필요")
        )

        gen_click = gen_kb_click or gen_plain_click
        use_knowledge = gen_kb_click

        # 생성된 리포트는 session_state에 보관한다. 다운로드 버튼을 누르면 스크립트가 다시 실행되는데,
        # 그때 gen_click이 False라서 리포트가 화면에서 사라지던 문제를 막기 위함
        if cancel_click:
            st.session_state.pop("ai_report", None)
            st.info("리포트 생성 작업이 취소(초기화) 되었습니다.")
        elif gen_click:
            st.session_state.pop("ai_report", None)
            conn = get_db()
            cur = conn.cursor()
            farm_info = cur.execute("SELECT * FROM farms WHERE id = ?", (ai_target_farm_id,)).fetchone()
            last_visit = cur.execute("""
            SELECT v.id, v.visit_number, v.visit_date, s.survey_data, s.consult_notes
            FROM visits v LEFT JOIN field_surveys s ON s.visit_id = v.id
            WHERE v.farm_id = ? ORDER BY v.visit_number DESC LIMIT 1
            """, (ai_target_farm_id,)).fetchone()

            # 거세우/암소를 모두 출하하는 농가가 많으므로(예: 절반 이상이 암소인 농가도 존재) 성별별로 각각 집계한다
            gender_data = {}
            for gkey, glabel in PRINT_REPORT_GENDERS:
                g_stats_row = cur.execute("""
                SELECT
                    COUNT(id) as total_count,
                    ROUND(AVG(carcass_weight), 1) as avg_weight,
                    ROUND(AVG(bms), 1) as avg_bms,
                    ROUND(AVG(backfat), 1) as avg_backfat,
                    ROUND(AVG(ribeye), 1) as avg_ribeye,
                    ROUND(AVG(month_age), 1) as avg_month_age,
                    ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as rate_1plus_above,
                    ROUND(SUM(CASE WHEN grade_yield = 'C' THEN 1 ELSE 0 END)*100.0/COUNT(id), 1) as rate_c_grade
                FROM shipment_records WHERE farm_id = ? AND gender = ?
                """, (ai_target_farm_id, gkey)).fetchone()
                if not g_stats_row or not g_stats_row["total_count"]:
                    continue  # 해당 성별 출하 기록이 없는 농가는 프롬프트에서 통째로 생략 (없는 데이터를 지어내지 않도록)

                g_shipment_dict = dict(g_stats_row)
                g_yearly_breakdown = build_ai_report_yearly_breakdown(ai_target_farm_id, gkey)
                g_profit_dict = build_ai_report_profit_estimate(ai_target_farm_id, gkey)
                nat_year_w = nat_latest_year(gkey)
                nat_w = NATIONAL_STATS.get(gkey, {}).get("도체중", {}).get(nat_year_w) if nat_year_w else None
                if g_shipment_dict["avg_weight"] is not None and nat_w:
                    g_profit_dict["diff_weight_per_head_kg"] = round(g_shipment_dict["avg_weight"] - nat_w, 1)

                gender_data[glabel] = {
                    "shipment_stats": g_shipment_dict,
                    "yearly_breakdown": g_yearly_breakdown,
                    "profit_data": g_profit_dict,
                }
            conn.close()

            farm_name = farm_info["farm_name"] if farm_info else "농가"

            # 어느 방식으로 생성 중인지 눈에 보이게 알린다 (나중에 리포트를 다시 볼 때 헷갈리지 않도록)
            if use_knowledge:
                st.caption("📚 전문자료(한우 컨설팅 길라잡이·자가TMR·육종가 기초지식)를 근거로 분석합니다.")
            else:
                st.caption("✨ 일반 모드 — Claude의 일반 지식만으로 분석합니다. (자료 근거 인용 없음)")

            with st.spinner(f"[{farm_name}] 농가의 출하성적과 현장조사 데이터를 Claude가 융합 분석 중입니다... (취소하려면 좌측 상단의 ✕ 또는 우측 상단 'Stop' 버튼 클릭)"):
                survey_dict = dict(last_visit) if last_visit else {}
                # survey_data는 JSON 문자열이라 그대로 넘기면 프롬프트에 이스케이프된 한 줄 문자열로 들어간다
                if isinstance(survey_dict.get("survey_data"), str):
                    try:
                        survey_dict["survey_data"] = json.loads(survey_dict["survey_data"])
                    except ValueError:
                        pass

                report_placeholder = st.empty()
                report_markdown = ""
                report_error = None
                try:
                    for chunk in generate_claude_report(farm_name, gender_data, survey_dict, use_knowledge):
                        report_markdown += chunk
                        report_placeholder.markdown(report_markdown + "▌")
                except ClaudeReportError as e:
                    report_error = str(e)
                report_placeholder.empty()

            if report_error:
                # 실패한 결과(빈 문자열·오류 문구·중간에 잘린 리포트)는 DB에 저장하지 않는다 → 기존 리포트가 덮어써지지 않음
                st.error(f"⚠️ 리포트 생성에 실패했습니다. 기존에 저장된 리포트는 그대로 유지됩니다.\n\n{report_error}")
                if report_markdown:
                    with st.expander("중단되기 전까지 생성된 내용 보기 (저장되지 않음)"):
                        st.markdown(report_markdown)
            elif not report_markdown.strip():
                st.error("⚠️ Claude가 빈 응답을 보냈습니다. 잠시 후 다시 시도해주세요. (저장하지 않았습니다)")
            else:
                if last_visit:
                    c = get_db()
                    # UNIQUE(visit_id, report_mode) 덕분에 같은 모드로 다시 만들 때만 덮어쓴다.
                    # 전문 → 일반 순으로 만들어도 앞의 전문 리포트가 남는다.
                    saved_mode = "전문" if use_knowledge else "일반"
                    # 시각은 SQLite CURRENT_TIMESTAMP 와 같은 UTC 문자열로 직접 넣는다 (Postgres 의 CURRENT_TIMESTAMP 는 형식이 다르다)
                    c.cursor().execute("""
                    INSERT INTO ai_reports (visit_id, report_mode, full_markdown, created_at) VALUES (?, ?, ?, ?)
                    ON CONFLICT(visit_id, report_mode) DO UPDATE SET full_markdown = excluded.full_markdown, created_at = excluded.created_at
                    """, (last_visit["id"], saved_mode, report_markdown, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
                    c.commit()
                    c.close()
                    notify_saved("AI 리포트가 DB에 저장되었습니다.", "AI 리포트 저장")
                    show_flash()
                else:
                    st.warning("이 농가는 방문 기록이 없어 리포트를 DB에 저장하지 않았습니다. 필요하면 아래에서 파일로 내려받으세요.")
                st.session_state["ai_report"] = {"farm_id": ai_target_farm_id, "farm_name": farm_name, "markdown": report_markdown, "use_knowledge": use_knowledge}

        saved_report = st.session_state.get("ai_report")
        if saved_report and saved_report["farm_id"] == ai_target_farm_id:
            farm_name = saved_report["farm_name"]
            report_markdown = saved_report["markdown"]
            # 두 방식의 결과를 번갈아 보며 비교할 때 어느 쪽인지 헷갈리지 않도록 표시한다.
            # 파일명에도 같은 꼬리표를 붙여야 두 방식을 연달아 받았을 때 서로 덮어쓰지 않는다.
            report_mode = "전문" if saved_report.get("use_knowledge") else "일반"
            st.caption("📚 전문자료 기반" if saved_report.get("use_knowledge") else "✨ 일반 모드")
            st.markdown(report_markdown)

            dl_c1, dl_c2 = st.columns(2)
            with dl_c1:
                st.download_button(f"📥 마크다운(.md) 다운로드 [{report_mode}]", data=report_markdown, file_name=f"{farm_name}_AI컨설팅리포트_{report_mode}.md")
            with dl_c2:
                report_html = build_report_html(farm_name, report_markdown, report_mode)
                st.download_button(f"🌐 HTML(.html) 다운로드 [{report_mode}]", data=report_html, file_name=f"{farm_name}_AI컨설팅리포트_{report_mode}.html", mime="text/html")

# -----------------------------------------------------------------------------
# 메뉴 5: 데이터 관리 · 백업
# -----------------------------------------------------------------------------
elif menu == "데이터 관리 · 백업":
    page_header("데이터 관리 · 누적 DB &amp; 엑셀 백업", "모든 컨설팅 기록과 출하 데이터를 안전하게 보관하고 언제든 엑셀/CSV로 내보냅니다.")
    show_flash()

    filter_choices = ["🔎 전체 보기"] + list(farm_options.keys())
    default_filter_idx = filter_choices.index(selected_label) if selected_label in filter_choices else 0
    filter_label = st.selectbox(
        "농가별로 조회 (좌측 사이드바에서 고른 농가가 기본 선택됩니다 — 리포트 만든 농가의 기록을 바로 확인할 때 유용합니다)",
        filter_choices, index=default_filter_idx
    )
    filter_farm_id = farm_options.get(filter_label)  # "전체 보기"면 None

    v_cols = "v.id AS 방문ID, v.farm_id AS 농가ID, f.farm_name, v.visit_number, v.visit_date, v.consultant_name, s.consult_notes, s.consultant_memo, s.facility_info, s.feed_info"
    r_cols = "r.id AS 리포트ID, v.farm_id AS 농가ID, f.farm_name, v.visit_date, r.report_type, r.report_mode, r.created_at, r.full_markdown"

    conn = get_db()
    if filter_farm_id:
        f_df = pd.read_sql_query("SELECT id AS 농가ID, farm_code, farm_name, owner_name, region, breeding_type, total_heads, created_at FROM farms WHERE id = ?", conn, params=(filter_farm_id,))
        s_df = pd.read_sql_query("SELECT s.animal_no, f.farm_name, s.gender, s.slaughter_date, s.carcass_weight, s.grade_quality, s.grade_yield, s.bms, s.backfat, s.ribeye FROM shipment_records s JOIN farms f ON s.farm_id = f.id WHERE s.farm_id = ? ORDER BY s.slaughter_date DESC", conn, params=(filter_farm_id,))
        v_df = pd.read_sql_query(f"SELECT {v_cols} FROM visits v JOIN farms f ON v.farm_id = f.id LEFT JOIN field_surveys s ON s.visit_id = v.id WHERE v.farm_id = ? ORDER BY v.visit_date DESC", conn, params=(filter_farm_id,))
        r_df = pd.read_sql_query(f"SELECT {r_cols} FROM ai_reports r JOIN visits v ON r.visit_id = v.id JOIN farms f ON v.farm_id = f.id WHERE v.farm_id = ? ORDER BY r.created_at DESC", conn, params=(filter_farm_id,))
    else:
        f_df = pd.read_sql_query("SELECT id AS 농가ID, farm_code, farm_name, owner_name, region, breeding_type, total_heads, created_at FROM farms", conn)
        s_df = pd.read_sql_query("SELECT s.animal_no, f.farm_name, s.gender, s.slaughter_date, s.carcass_weight, s.grade_quality, s.grade_yield, s.bms, s.backfat, s.ribeye FROM shipment_records s JOIN farms f ON s.farm_id = f.id ORDER BY s.slaughter_date DESC", conn)
        v_df = pd.read_sql_query(f"SELECT {v_cols} FROM visits v JOIN farms f ON v.farm_id = f.id LEFT JOIN field_surveys s ON s.visit_id = v.id ORDER BY v.visit_date DESC", conn)
        r_df = pd.read_sql_query(f"SELECT {r_cols} FROM ai_reports r JOIN visits v ON r.visit_id = v.id JOIN farms f ON v.farm_id = f.id ORDER BY r.created_at DESC", conn)
    conn.close()

    st.subheader("📋 전체 등록 농가 마스터")
    st.dataframe(f_df, width="stretch")

    st.subheader("🥩 전체 누적 출하 성적 데이터")
    st.dataframe(s_df, width="stretch")

    st.subheader("🚗 현장 방문 컨설팅 이력")
    st.caption("사양관리 실태(facility_info), 급여 현황(feed_info) 등 현장조사 원본 항목까지 전체 표시합니다. 수정은 '2단계 · 현장방문조사' 메뉴의 '기존 방문조사 수정' 모드를 이용하세요.")
    st.dataframe(v_df, width="stretch")

    st.subheader("🤖 AI 컨설팅 리포트 저장 이력")
    if r_df.empty:
        st.info("아직 저장된 AI 리포트가 없습니다. '3단계 · AI 리포트' 메뉴에서 생성하면 여기에 누적됩니다.")
    else:
        preview_df = r_df.drop(columns=["full_markdown"]).copy()
        preview_df["미리보기"] = r_df["full_markdown"].str.slice(0, 60) + "…"
        st.dataframe(preview_df, width="stretch")

        report_labels = [f"[{row['리포트ID']}] {row['farm_name']} · {row['visit_date']} · {row['report_mode']} 생성({row['created_at']})" for _, row in r_df.iterrows()]
        picked_label = st.selectbox("전체 내용을 볼 리포트 선택", report_labels)
        picked_row = r_df.iloc[report_labels.index(picked_label)]
        with st.expander(f"📄 {picked_row['farm_name']} 리포트 전체 내용", expanded=True):
            st.markdown(picked_row["full_markdown"])
        # 3단계 메뉴와 같은 서식의 단독 HTML로도 받을 수 있게 한다 (인쇄·농가 전달용)
        r_base = f"{picked_row['farm_name']}_AI리포트_{picked_row['report_mode']}_{picked_row['리포트ID']}"
        r_dl1, r_dl2 = st.columns(2)
        with r_dl1:
            st.download_button("📥 이 리포트 마크다운(.md) 다운로드", data=picked_row["full_markdown"], file_name=f"{r_base}.md", width="stretch")
        with r_dl2:
            st.download_button(
                "🌐 이 리포트 HTML(.html) 다운로드",
                data=build_report_html(picked_row["farm_name"], picked_row["full_markdown"], picked_row["report_mode"]),
                file_name=f"{r_base}.html", mime="text/html", width="stretch",
            )

    col1, col2, col3 = st.columns(3)
    col1.download_button("📥 농가 목록 CSV 다운로드", data=f_df.to_csv(index=False).encode('utf-8-sig'), file_name="농가목록_DB.csv")
    col2.download_button("📥 전체 출하성적 CSV 다운로드", data=s_df.to_csv(index=False).encode('utf-8-sig'), file_name="출하성적_전체_DB.csv")
    col3.download_button("📥 현장 방문 이력 CSV 다운로드", data=v_df.to_csv(index=False).encode('utf-8-sig'), file_name="현장방문이력_전체_DB.csv")

    # DB 전체(농가·방문·조사표·출하성적·AI 리포트)를 SQLite 파일 하나로 받는다. 수동 백업·DB 이관 원본용.
    # 클라우드 DB를 통째로 읽어 파일을 만드느라 몇 초 걸리므로, 메뉴를 열 때마다가 아니라 버튼을 눌렀을 때만 만든다.
    st.markdown("---")
    st.subheader("💾 전체 DB 파일 백업")
    st.caption("위 표들을 포함한 DB 전체를 .db 파일 하나로 내려받습니다. 조합원 정보가 들어 있으니 보관에 주의하세요.")
    if st.button("DB 파일 준비"):
        with st.spinner("DB 전체를 파일로 만드는 중..."):
            data, err = db_file_bytes()
        if err:
            st.error(err)
        else:
            st.session_state["_db_file"] = (data, datetime.now().strftime("%Y%m%d_%H%M"))
    if st.session_state.get("_db_file"):
        db_bytes, stamp = st.session_state["_db_file"]
        st.download_button(f"📥 consulting_{stamp}.db 다운로드 ({len(db_bytes) // 1024:,} KB)", data=db_bytes,
                           file_name=f"consulting_{stamp}.db", mime="application/octet-stream")
