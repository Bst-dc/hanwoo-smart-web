# 🐂 한우 스마트 컨설팅 통합 웹 플랫폼

농가 이력제 기반 출하성적 자동 추출, 전국 평균 성적과의 1:1 비교분석표, 모바일 현장 방문조사(사양관리·농가대화) 입력, Claude AI 연동 종합 진단 리포트 생성, 그리고 방문 농가 전체 누적 데이터베이스 및 연도별 평균 성적 대시보드를 제공하는 올인원 웹 시스템입니다.

**운영 중 배포 주소**: https://consulting.3-38-225-111.sslip.io/

> **저장소 구성** — 이 코드 저장소는 공개이고, 조합원 개인정보가 든 DB 백업과 AI 리포트용 전문자료(knowledge/*.md)는
> 비공개 데이터 저장소(`GITHUB_REPO` secret)에만 둡니다. 앱이 실행 중에 GitHub API로 읽고 씁니다.

---

## 📂 폴더 구조 안내

```
한우_스마트컨설팅_웹시스템/
├── 📄 README.md                    # 플랫폼 전체 개요 및 사용 가이드
├── 📄 100프로_무료배포_가이드.md      # Streamlit Cloud / GitHub Pages 무료 배포 매뉴얼
├── ⭐ streamlit_app.py              # [메인 앱] Streamlit Cloud에 배포 중인 운영 서비스 전체
├── ⚙️ requirements.txt              # streamlit_app.py 실행에 필요한 파이썬 패키지 목록
├── 📁 .streamlit/                   # Streamlit 테마·서버 설정(config.toml) 및 API 키(secrets.toml, gitignore 처리)
├── 📁 data/
│   └── consulting.db               # 로컬용 SQLite DB (저장소엔 올리지 않음 — 운영 DB는 Turso, 백업은 비공개 데이터 저장소)
├── 📁 docs/                         # [상세 설계 문서 6종]
│   ├── 01_시스템_개요_및_통합아키텍처_설계서.md
│   ├── 02_데이터베이스_및_누적DB_설계서.md
│   ├── 03_이력제_출하성적추출_및_전국비교_설계서.md
│   ├── 04_모바일_현장정보수집_UIUX_설계서.md
│   ├── 05_Claude_AI_분석엔진_및_프롬프트_설계서.md
│   └── 06_누적통계_대시보드_및_평균성적분석_설계서.md
├── 📁 github_pages/                 # [대안 배포] 서버 없이 동작하는 정적 웹 버전
│   ├── index.html / style.css / app.js   # LocalStorage 기반 경량 현장조사 입력 도구
├── 📁 src/                          # [레거시] 로컬 PC 실행용 자체 REST API 서버 + SPA 프론트엔드
│   ├── backend/                    # Python HTTP 서버 (app.py, database.py, ekape_api.py, kosis_api.py, claude_service.py)
│   └── frontend/                   # index.html, css/style.css, js/app.js
├── ⚙️ run_app.bat                   # [레거시] src/backend 로컬 실행 + Cloudflare 터널로 외부 접속 지원
├── 🔧 import_all_data.py            # 엑셀(출하성적/현장조사 백업) → SQLite 일괄 적재 스크립트
├── 🔧 check_data.py                 # 엑셀 원본 데이터 컬럼/샘플 확인용 점검 스크립트
└── 🔑 api_key.txt                   # (gitignore 처리) 로컬 실행용 Claude API 키 보관 파일
```

> ⭐ 현재 실제 운영·개발이 이루어지는 곳은 **`streamlit_app.py`** 하나입니다. `src/`(로컬 서버) 와 `github_pages/`(정적 페이지)는 각각 "인터넷 없이 자체 서버로 운영" / "서버 없이 브라우저에만 저장" 같은 특수한 상황을 위한 대안 배포판입니다.

---

## 🚀 실행 방법

### 방법 1: Streamlit Cloud 운영 서비스 접속 (권장)
별도 설치 없이 바로 사용하려면 위의 배포 주소로 접속하면 됩니다. PC, 스마트폰, 태블릿 어디서든 24시간 무료로 이용 가능합니다.

### 방법 2: 로컬에서 Streamlit 앱 직접 실행
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```
Claude API 키는 `.streamlit/secrets.toml`에 다음과 같이 등록합니다.
```toml
ANTHROPIC_API_KEY = "sk-ant-api03-본인의_클로드_API키"
```

### 방법 3(레거시): `run_app.bat` 더블클릭 — 자체 서버 + 외부 접속 터널
1. `run_app.bat`을 더블클릭하면 `src/backend/app.py`가 로컬 8080 포트에서 실행되고 PC 브라우저(`http://localhost:8080`)가 자동으로 열립니다.
2. 콘솔에 표시되는 `https://xxxx.trycloudflare.com` 주소로 외부 스마트폰(LTE/5G)에서도 접속할 수 있습니다.

배포 방법에 대한 더 자세한 단계별 가이드는 [`100프로_무료배포_가이드.md`](100프로_무료배포_가이드.md)를 참고하세요.

---

## 💡 주요 기능

1. **📊 한우 통계 대시보드**
   - 관리 농가 수, 누적 방문 횟수, 총 출하 두수, 평균 1+이상 출현율 등 KPI 실시간 집계 (미조사 농가 수 포함).
   - **전국 평균 vs 방문 농가 전체 평균**의 연도별(2023~2026) 성적 추이 비교 그래프.

2. **🐄 이력제 출하성적 추출 & 전국 1:1 비교분석표**
   - 개체이력번호(12자리) 입력 시 축평원 OpenAPI로 도체중·BMS·등급·월령·경락단가를 자동 추출해 DB에 영구 적재.
   - 전국 평균 대비 격차(+/-) 및 진단 평가(우수/과비주의/미흡 등) 자동 산출.
   - 3개년 종합 비교표 및 A4 인쇄용 출하성적 비교 리포트 다운로드 지원.

3. **📝 모바일 현장 방문조사 입력**
   - 터치식 평점 버튼(양호/보통/미흡)으로 사양관리 실태·축사 환경을 빠르게 기록.
   - AI 심화 진단 항목 및 음성 인식(STT)으로 상담 내용을 텍스트로 자동 입력.

4. **🤖 Claude AI 종합 분석 리포트**
   - 출하성적 정량 데이터 + 현장조사 정성 데이터를 결합해 "진단 → 원인 → 처방 → 액션플랜" 리포트를 실시간 스트리밍으로 생성.
   - HTML/PDF 다운로드 및 인쇄 출력 지원.

---

## 🔧 데이터 관리 스크립트

- `import_all_data.py`: 로컬 엑셀 원본(농가출하데이터, 현장조사 백업)을 읽어 `data/consulting.db`에 일괄 적재합니다. 경로가 로컬 PC 기준으로 하드코딩되어 있으므로 실행 전 파일 상단의 `path_shipment`, `path_survey`, `BASE_DIR` 값을 환경에 맞게 수정하세요.
- `check_data.py`: 위 엑셀 원본 파일의 컬럼 구성과 샘플 데이터를 콘솔에 출력해 임포트 전 데이터 구조를 점검합니다.

---

## 📚 설계 문서

시스템 아키텍처, DB 스키마, API 연동, UI/UX, AI 프롬프트 설계, 대시보드 설계에 대한 상세 문서는 [`docs/`](docs/) 폴더의 6개 설계서를 참고하세요.
