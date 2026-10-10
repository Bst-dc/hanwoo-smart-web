# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

한우 스마트 컨설팅 웹시스템 — a Streamlit app for 대구축협 한우 consulting: 이력제 출하성적 자동 추출 (livestock traceability API), 전국 평균 비교, 모바일 현장조사 입력, and Claude AI 리포트 생성. Deployed on an AWS Lightsail server (URL at the top of `streamlit_app.py`, in the README, and below).

- **All communication (chat, comments, UI text) defaults to Korean.**
- This folder was split out of the `G:\내 드라이브\한우\` repository on 2026-10-04 (`git subtree split`, history preserved). It is self-contained: nothing reads from sibling folders.

### Deployment layout (2026-10-04, server move 2026-10-10)

Live app: https://consulting.3-38-225-111.sslip.io/ — AWS Lightsail server (2026-10-10) that also hosts 시험농장; Docker/Caddy config and runbook live in `../aws-deploy/` (`README_배포.md`). The server pulls `main` of public repo `Bst-dc/hanwoo-smart-web` every 2 minutes and rebuilds, so a push deploys. Image is **Python 3.12** — `libsql-experimental` has no wheels for 3.14. The old Streamlit Cloud app (https://hanwoo-smart-web-rfkwappjmj7yr4xv6ahuwes.streamlit.app/) runs in parallel until it is shut down.

Streamlit Community Cloud's free tier allows only **one private app**, and that slot is used by the separate `testfarm` app. So the code is deployed from a **public** repo, and everything sensitive lives in a **private data repo** (`GITHUB_REPO` secret, default `Bst-dc/hanwoo-smart-consulting`):

- `data/consulting.db` backups — written by `persist_db()` via the GitHub contents API (`GITHUB_DB_PATH`). In cloud modes the file is a snapshot of the cloud DB (Supabase: `db_adapter.export_to_sqlite` with `db_schema.SQLITE_DDL`).
- `knowledge/*.md` — extracted from third-party publications (copyright), read at runtime by `_fetch_remote_knowledge_files()` when the local `knowledge/` folder is absent.

Both are gitignored here and must **never** be committed to the public code repo; nor may personal data (조합원 names, numbers) or keys appear in code/comments. `GITHUB_TOKEN` needs Contents read/write on the data repo. Local branch `private-history` holds the pre-publication history (contains the DB) and tracks the data repo — never push it to the public `origin`.

## Commands

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py        # local dev server
python -m unittest discover tests     # run tests
python -m unittest tests.test_dashboard_kpis   # run a single test module
```

Local secrets go in `.streamlit/secrets.toml` (gitignored; only `.streamlit/config.toml` is tracked). Claude API key can also be `api_key.txt`; KOSIS/eKAPE keys can be `kosis_key.txt`/`ekape_key.txt` in this folder — see the `get_*_api_key()` functions in `streamlit_app.py` (secrets.toml → local file → env var).

## Architecture

- `streamlit_app.py` is a single monolithic script — the entire running application (UI, DB access, API calls, AI prompt construction). It's organized into numbered sections marked by `# ----` comment banners. When editing, find the relevant numbered section rather than assuming separate modules exist.
- **DB**: `get_db()` picks, in order: **Supabase** when `DATABASE_URL` is set (secrets or env) → **Turso** (libSQL cloud) when `TURSO_DATABASE_URL` is in `st.secrets` → local SQLite file `data/consulting.db`. Supabase is the same project as the 시험농장(testfarm) app; this app's tables live in the **`hanwoo` schema** (never touch `sunsan`/`goa`). The Turso branch is kept only as a fallback during the 2026-10 move — remove it (and `libsql-experimental`) once Supabase has run cleanly for a while.
  - Supabase goes through `db_adapter.py` (copied from 시험농장 and adapted): it makes psycopg2 behave like sqlite3 — translates `?`, `PRAGMA`, `sqlite_master`, mixed-case aliases; per-statement SAVEPOINT; connection pool; **600s SELECT cache** invalidated on this process's writes (edits made elsewhere, e.g. the Supabase dashboard, show up after ≤10 min). It does **not** translate `INSERT OR REPLACE` or `lastrowid` — write `INSERT ... ON CONFLICT(...) DO UPDATE` and `RETURNING id`, which work on all three backends.
  - Postgres DDL is in `db_schema.py` (`PG_DDL`; dates stay TEXT, real-valued columns are NUMERIC because Postgres `round()` rejects double). `init_db()` holds the SQLite DDL + migrations for Turso/local — a schema change must go in **both**. `shipment_records` is unique on `animal_no` alone (production shape).
  - In Turso mode `get_db()` returns a DictConnection/DictCursor wrapper; in Supabase mode a `db_adapter.Connection`. Neither is a real `sqlite3.Connection`: row classes must not subclass `dict` (pandas iterates rows for values), and wrappers must keep every DBAPI method pandas uses. Code that opens the local DB file must branch on `using_cloud_db()` (true for both clouds).
  - Tables: `farms` → `visits` → (`field_surveys`, `shipment_records`, `ai_reports`).
  - `migrate_to_supabase.py <file.db> --run` replaces the `hanwoo` schema from a `.db` file (get one from the app's 데이터 관리 · 백업 → DB 파일 준비) and diffs every cell.
- External sources integrated in `streamlit_app.py`: KOSIS (`fetch_kosis_national_stats`, 24h cached), 축평원 eKAPE OpenAPI (`fetch_cattle_grade`), Anthropic Claude (`generate_claude_report`), and GitHub contents API for DB backup (`persist_db`; URL-encode Korean paths with `urllib.parse.quote`).
- AI reports ground themselves on `knowledge/*.md`, extracted from `reference/원본PDF/` by `build_knowledge.py` (run manually only when sources change). After re-extracting, upload the new files to the private data repo's `knowledge/` — the deployed app reads them from there.
- **`streamlit_app.py` cannot be imported directly** in a test process — it executes Streamlit UI calls at import time. `tests/test_dashboard_kpis.py` extracts SQL verbatim out of the source and runs it against an in-memory SQLite DB mirroring the schema; follow that pattern. Other files in `tests/` (`analyze_farms.py`, `check_schema.py`, `find_text.py`, `st_test.py`, `import_temp_survey.py`) are ad-hoc scripts, not tests.
- `src/` (legacy local REST API + vanilla JS SPA) and `github_pages/` (static LocalStorage-only version) are backup deployment targets, not where development happens.
- `import_all_data.py` / `check_data.py` bulk-load Excel backups from `reference/원본엑셀/`. Dedup scripts: `check_dupes.py`/`check_farms.py`/`check_linkage.py` are read-only; `fix_dupes.py`/`cleanup_dupes.py` are destructive with *different* preservation rules — never run both, and back up `data/consulting.db` first.
- `reference/` (gitignored) holds source material copied in from outside: `원본PDF/`, `원본엑셀/`, `통계자료/`, `과거리포트/` (contains 조합원 real names).
- Never commit `migrate.py` (Turso token in plaintext) or `dump.sql` (조합원 personal data); both are gitignored. Force push is blocked by `.claude/hooks/block_force_push.py`.
- Design docs live in `docs/01_...md`–`docs/06_...md`.
