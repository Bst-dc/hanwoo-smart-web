# CLAUDE.md

한우 스마트 컨설팅 웹시스템: 대구축협 한우 컨설팅용 앱. 하는 일은 다음과 같다.
- 이력제 출하성적 자동 추출
- 전국 평균 비교
- 현장조사 입력
- Claude AI 리포트

**대화·주석·화면 문구는 모두 한국어로 쓴다.**

## 지금 운영 구조 (2026-11 기준)

- **앱**: FastAPI `api/` + 화면 `web/`(빌드 없는 vanilla JS). 서버 컨테이너 이름은 `consulting-next`.
- **주소**: https://consulting.3-38-225-111.sslip.io/ (같은 앱이 `consulting-next.…` 주소로도 열린다).
- **옛 Streamlit 앱**은 2026-10-15에 내렸다.
  - 실행 가능한 전체는 git 태그 `legacy-streamlit` 에 있다. 되돌리는 스크립트는 없으니 필요하면 이 태그에서 다시 빌드한다.
  - `tests/legacy_snapshot/streamlit_app_legacy.py` 는 규칙 비교 시험 전용이다. 실행하지 않는다.
  - Streamlit Community Cloud 앱은 2026-10-16에 모두 지웠다.
- **배포**: AWS Lightsail 서버(시험농장·출하성적 분석앱과 같이 씀).
  - 서버가 공개 저장소 `Bst-dc/hanwoo-smart-web` 의 `main` 을 2분마다 받아 새로 빌드한다. **즉 `main` 에 푸시하면 곧 배포된다.**
  - 이미지는 Python 3.12.
  - 서버 Docker·Caddy 설정과 운영 안내는 `../aws-deploy/README_배포.md` 에 있다. 이 저장소의 `deploy/consulting-next/setup.sh` 는 처음 설치할 때만 쓴다.
  - 서버 Caddyfile 은 `mv` 하지 말고 내용만 덮어쓴다(caddy 컨테이너가 파일 하나를 bind-mount 한다).
- **작업 방식**: `main` 에서 바로 작업한다. force push 는 `.claude/hooks/block_force_push.py` 가 막는다.
  - 이 훅은 한 Bash 명령에 `git` 과 함께 `[ -f`·`rm -f` 같은 글자가 있으면 force push 로 잘못 알고 막는다. 그럴 때는 명령을 나눈다.

## 폴더

| 경로 | 내용 |
|---|---|
| `api/main.py` | 앱 시작점. 로그 미들웨어, 처리 안 된 예외 → 500(화면에는 오류 종류 이름만 보임), `/api/health`, 라우터 등록, `web/` 정적 파일 제공 |
| `api/routers/` | 화면별 API: auth, farms, dashboard, shipments, shipment_input, surveys, reports, data |
| `api/services/` | 실제 처리: 대시보드, 출하성적, eKAPE(`ekape.py`), 현장조사·조사표, AI 리포트(`ai_report.py`·`report_data.py`), 데이터 관리 |
| `api/config.py` | 설정값. 환경변수 → `.streamlit/secrets.toml` 순서로 읽는다. `CONSULTING_LOCAL_ONLY`, `CONSULTING_DB_PATH` 도 여기서 처리 |
| `api/db.py` | DB 연결. 요청마다 열고 닫는다(`get_conn`) |
| `api/backup.py` | 저장한 뒤 Supabase 전체를 SQLite 로 떠서 비공개 저장소 `data/consulting.db` 로 올림. 무료 요금제의 유일한 복구 수단 |
| `api/auth.py`, `api/limits.py` | 접속 비밀번호(`APP_PASSWORD`) 세션 쿠키, 요청 제한 |
| `web/` | `index.html`·`app.js`·`api.js`·`charts.js`(Chart.js)·`farmpicker.js`·`survey_draft.js`·`print_compare.js`(인쇄 창), 화면별 `web/pages/*.js` |
| `db_adapter.py` | psycopg2 를 sqlite3 처럼 쓰게 해 주는 층(아래 참고). 원본은 시험농장 저장소에 있다 |
| `db_schema.py` | Postgres DDL(`PG_DDL`), SQLite DDL(`SQLITE_DDL`), 필수 표·칸 목록 |
| `tools/` | `sync_notes.py`(한우노트 업로드), `fix_gender.py`, `fix_shipments.py` |
| `tests/` | `test_*.py` 가 시험이다. `analyze_farms.py`·`check_schema.py`·`find_text.py`·`st_test.py`·`import_temp_survey.py` 는 일회성 스크립트라 시험이 아니다 |
| `docs/01_…md`–`06_…md` | 설계 문서(옛 앱 기준 내용 포함) |
| `src/`, `github_pages/` | 옛 예비 배포본. 개발하지 않는다 |
| 맨 위 `check_*.py`, `fix_dupes.py`, `cleanup_dupes.py`, `import_all_data.py`, `migrate_to_supabase.py`, `build_knowledge.py` | 손으로 돌리는 데이터 정리 스크립트(아래 참고) |

## 명령

이 PC 의 기본 Python 에는 fastapi·psycopg2 가 없다. scratchpad 에 venv 를 만들어 쓴다.

```bash
python -m venv <scratchpad>/venv && <scratchpad>/venv/Scripts/python -m pip install -r api/requirements.txt
```

```bash
CONSULTING_LOCAL_ONLY=1 DATABASE_URL= <venv>/Scripts/python -m unittest discover tests
```

- 시험은 **반드시 `CONSULTING_LOCAL_ONLY=1`** 로 돌린다. 그래야 운영 Supabase 에 시험 데이터가 들어가지 않는다. 2026-11-06 기준 160건 통과.
- 한 모듈만 돌릴 때: `python -m unittest tests.test_db_adapter`.
- `tests/test_survey_draft_js.py` 는 node 가 있을 때만 돈다.
- 로컬 실행은 저장소 맨 위 폴더에서 `uvicorn api.main:app --reload` 로 한다. `DATABASE_URL` 이 없으면 로컬 `data/consulting.db` 를 쓴다.
- 로컬 비밀값은 `.streamlit/secrets.toml` 에 둔다(gitignore 됨). 앱이 읽는 이름:
  - `DATABASE_URL`, `APP_PASSWORD`, `SESSION_SECRET`, `COOKIE_SECURE`, `CORS_ORIGINS`
  - `ANTHROPIC_API_KEY`, `EKAPE_API_KEY`, `KOSIS_API_KEY`
  - `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BRANCH`, `ENABLE_API_DOCS`

## DB

- **운영은 Supabase**: 시험농장과 같은 프로젝트의 **`hanwoo` 스키마**를 쓴다. `sunsan`·`goa` 스키마는 절대 건드리지 않는다.
  - 접속은 pooler(Supavisor, 세션 모드)를 거친다.
  - `DATABASE_URL` 이 없거나 `CONSULTING_LOCAL_ONLY=1` 이면 로컬 SQLite 를 쓴다.
  - Turso 는 쓰지 않는다(코드에서도 빠짐).
- **표**: `farms` → `visits` → (`field_surveys`, `shipment_records`, `ai_reports`).
  - `shipment_records` 는 `animal_no` 하나로만 유일하다.
- **스키마를 바꿀 때**는 `db_schema.py` 의 `PG_DDL` 과 SQLite 쪽을 **둘 다** 고친다.
  - 날짜는 TEXT, 실수 칸은 NUMERIC 이다(Postgres `round()` 가 double 을 받지 않음).
  - Supabase 에서는 `api/db.py` 가 프로세스마다 한 번 `ensure_schema` 로 점검한다.
- **`db_adapter.py` 가 하는 일**:
  - `?` 자리표시자, `PRAGMA`, `sqlite_master`, 대소문자 섞인 별칭을 Postgres 용으로 바꾼다.
  - 명령마다 SAVEPOINT 를 건다.
  - 연결 풀을 둔다.
  - **SELECT 결과를 600초 캐시**한다. 이 프로세스의 쓰기는 캐시를 바로 비우지만, Supabase 대시보드처럼 밖에서 고친 값은 최대 10분 뒤에 보인다.
- **`db_adapter.py` 가 바꿔 주지 않는 것**:
  - `INSERT OR REPLACE` 와 `lastrowid` 는 바꿔 주지 않는다. `INSERT … ON CONFLICT(…) DO UPDATE` 와 `RETURNING id` 를 쓴다.
  - 행 클래스는 `dict` 를 상속하면 안 된다(pandas 가 값 대신 키를 읽음). 연결 래퍼는 pandas 가 쓰는 DBAPI 메서드를 모두 갖춰야 한다.
- **끊긴 연결 (2026-11-06 장애)**: Supavisor 가 쉬던 연결을 끊으면 psycopg2 는 `DatabaseError: server closed the connection unexpectedly` 를 내고 `closed` 를 0 으로 둘 수 있다.
  - `_connection_lost()` 가 이를 잡아 그 연결을 버리고, 쓰기가 없던 조회는 한 번 다시 시도한다.
  - 5분 넘게 쉰 연결은 재사용하지 않는다.
  - 시험: `tests/test_db_adapter.py` 의 `DeadConnectionTest`. 이 부분을 고칠 때는 시험농장 쪽 `db_adapter.py` 도 같이 본다.
- **`hanwoo.shipment_alerts` 는 이 앱의 표가 아니다.**
  - 출하성적 이상 농가 분석앱이 쓰고(역할 `analysis_writer`), 이 앱은 읽기만 한다. 출하성적 화면의 근내지방도 신호 카드가 이 표를 쓴다. 표나 권한이 없으면 카드를 숨기고 경고만 남긴다.
  - `PG_DDL` 과 백업에 들어 있지 않다. 그래서 `migrate_to_supabase.py <file.db> --run`(DROP SCHEMA … CASCADE 로 스키마를 통째로 바꿈)을 돌리면 이 표와 `analysis_writer` 권한, `farms` 조회 정책이 같이 지워진다. 그 뒤에는 분석앱의 `deploy/supabase_alerts.sql` 을 다시 실행하고 분석앱에서 '보내기'를 다시 누른다.

## 외부 연동

- **축평원 eKAPE OpenAPI**(`api/services/ekape.py`): 출하성적.
- **KOSIS**(`api/national_stats.py`): 전국 평균.
- **Anthropic Claude**(`api/services/ai_report.py`): AI 리포트. 근거 자료는 두 가지다.
  - `knowledge/*.md`(전문자료, 주 근거): `build_knowledge.py` 로 `reference/원본PDF/` 에서 뽑는다. 자료가 바뀔 때만 손으로 돌리고, 새로 뽑은 파일은 비공개 저장소 `knowledge/` 에 올린다. 서버는 거기서 읽는다.
  - `한우노트/`(옵시디언 보관함, 보조 근거): 전문자료와 어긋나면 전문자료가 우선이다. 고친 뒤 `python tools/sync_notes.py` 로 미리보기를 하고, `--run` 으로 비공개 저장소에 올린다. 서버는 10분 안에 읽는다.
- **GitHub contents API**(`api/backup.py`·`ai_report.py`): 비공개 데이터 저장소(`GITHUB_REPO`, 기본 `Bst-dc/hanwoo-smart-consulting`)를 쓴다. 한글 경로는 `urllib.parse.quote` 로 인코딩한다.

## 공개 저장소에 절대 올리지 않는 것

코드 저장소는 **공개**다. 민감한 것은 모두 비공개 데이터 저장소나 로컬에만 둔다(gitignore 됨).

- `data/consulting.db`, `knowledge/`, `한우노트/`(제3자 출판물 발췌·저작권)
- `reference/`(원본 PDF·엑셀·통계·과거 리포트, 조합원 실명 포함)
- `migrate.py`(Turso 토큰 평문), `dump.sql`(조합원 개인정보)
- `api_key.txt`·`access_token.txt` 같은 키 파일, `.streamlit/secrets.toml`

코드나 주석에도 조합원 이름·번호·키를 쓰지 않는다. 로컬 브랜치 `private-history` 는 공개 전 이력(DB 포함)이라 `origin` 에 절대 푸시하지 않는다.

## 데이터 정리 스크립트 (로컬 SQLite 대상, 손으로만 실행)

- `import_all_data.py` / `check_data.py`: `reference/원본엑셀/` 의 엑셀 백업을 한꺼번에 넣고 확인한다.
- `check_dupes.py`·`check_farms.py`·`check_linkage.py`·`check_nulls.py`: 읽기만 한다.
- `fix_dupes.py`·`cleanup_dupes.py`: **데이터를 지운다.** 두 스크립트는 무엇을 남길지 규칙이 서로 달라서 둘 다 돌리면 안 된다. 돌리기 전에 `data/consulting.db` 를 백업한다.
- `migrate_to_supabase.py <file.db> --run`: `.db` 파일로 `hanwoo` 스키마를 통째로 바꾸고 모든 칸을 대조한다. `.db` 파일은 앱의 데이터 관리 화면에서 받는다. 위 `shipment_alerts` 주의를 꼭 본다.

## 화면 디자인 (2026-11-01)

- **공통 기준**: 한우 업무 시스템 공통 기준을 따른다(`../시험농장/DESIGN.md`, `hanwoo-portal/theme/hanwoo-theme.css`).
  - 중립 회색 바탕, 잉크색 단추, IBM Plex Sans KR.
  - 장부 녹색(`accent`)은 데이터와 '고른 표시'에만 쓴다.
  - 모서리 6px/4px(`web/index.html` 의 `@theme` 토큰). **이모지는 쓰지 않는다.**
  - 앱 고유색은 노랑: 머리글 윗줄·'컨' 표시·지금 여기 표시·고른 탭 밑줄.
- **뼈대**(13인치 패드·PC 기준): 공통 머리글(시스템 바로가기·로그아웃) 아래 본문이 있다.
  - 1280px(xl) 이상: 왼쪽 사이드바에 농가 목록을 늘 펼친다.
  - 그보다 좁으면: 위쪽 한 줄의 농가 선택 단추를 쓴다.
  - 메뉴는 본문 위 탭이고, 본문 폭은 최대 1440px. 폰은 깨지지만 않게만 유지한다.
- **인쇄 창**(`web/print_compare.js`)은 인쇄물이라 색을 그대로 둔다.
- **Chart.js 4**: 같은 캔버스에 다시 그리기 전에 이전 차트를 먼저 지운다(`Chart.getChart(canvas)?.destroy()`).

## 운영 확인·장애 진단

1. **배포 반영**: `curl https://consulting.3-38-225-111.sslip.io/<파일>.js | grep <새 코드>`. 화면 파일은 로그인 없이 받아진다.
2. **`/api/health` 는 DB 에 붙지 않는다.** 그래서 DB 가 끊겨도 항상 정상으로 나온다. DB 를 확인하려면 로그인한 브라우저에서 `fetch('/api/farms')` 처럼 실제 API 를 부른다.
3. **500 화면에는 오류 종류 이름만 나온다.** 원인을 보려면:
   - 서버 로그: 서버에서 `cd /opt/hanwoo/deploy && sudo docker compose logs --tail 100 consulting-next`
   - Supabase 쪽: 프로젝트 상태와 로그(supavisor·postgres)
4. **자동 배포 기록**: `journalctl -u hanwoo-update -n 50`
