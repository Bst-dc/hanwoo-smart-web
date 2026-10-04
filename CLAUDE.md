# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

한우 스마트 컨설팅 웹시스템 — a Streamlit app for 대구축협 한우 consulting: 이력제 출하성적 자동 추출 (livestock traceability API), 전국 평균 비교, 모바일 현장조사 입력, and Claude AI 리포트 생성. Deployed on Streamlit Cloud (URL at the top of `streamlit_app.py` and in the README).

- **All communication (chat, comments, UI text) defaults to Korean.**
- This folder was split out of the `G:\내 드라이브\한우\` repository on 2026-10-04 (`git subtree split`, history preserved). It is self-contained: nothing reads from sibling folders.

### Deployment layout (2026-10-04)

Streamlit Community Cloud's free tier allows only **one private app**, and that slot is used by the separate `testfarm` app. So the code is deployed from a **public** repo, and everything sensitive lives in a **private data repo** (`GITHUB_REPO` secret, default `Bst-dc/hanwoo-smart-consulting`):

- `data/consulting.db` backups — written by `persist_db()` via the GitHub contents API (`GITHUB_DB_PATH`).
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
- **DB**: `get_db()` connects to Turso (libSQL cloud) when `TURSO_DATABASE_URL` is in `st.secrets`, otherwise to the local SQLite file `data/consulting.db`. In cloud mode it returns a DictConnection/DictCursor wrapper, not a real `sqlite3.Connection` — the row class must not subclass `dict` (pandas iterates rows for values), and the wrapper must keep every DBAPI method pandas uses. Code that opens the local DB file must branch on `using_cloud_db()`. Tables: `farms` → `visits` → (`field_surveys`, `shipment_records`, `ai_reports`). `init_db()` runs on every import with idempotent `CREATE TABLE IF NOT EXISTS` + ad-hoc `ALTER TABLE ADD COLUMN` migrations — schema changes go directly in `init_db()`.
- External sources integrated in `streamlit_app.py`: KOSIS (`fetch_kosis_national_stats`, 24h cached), 축평원 eKAPE OpenAPI (`fetch_cattle_grade`), Anthropic Claude (`generate_claude_report`), and GitHub contents API for DB backup (`persist_db`; URL-encode Korean paths with `urllib.parse.quote`).
- AI reports ground themselves on `knowledge/*.md`, extracted from `reference/원본PDF/` by `build_knowledge.py` (run manually only when sources change). After re-extracting, upload the new files to the private data repo's `knowledge/` — the deployed app reads them from there.
- **`streamlit_app.py` cannot be imported directly** in a test process — it executes Streamlit UI calls at import time. `tests/test_dashboard_kpis.py` extracts SQL verbatim out of the source and runs it against an in-memory SQLite DB mirroring the schema; follow that pattern. Other files in `tests/` (`analyze_farms.py`, `check_schema.py`, `find_text.py`, `st_test.py`, `import_temp_survey.py`) are ad-hoc scripts, not tests.
- `src/` (legacy local REST API + vanilla JS SPA) and `github_pages/` (static LocalStorage-only version) are backup deployment targets, not where development happens.
- `import_all_data.py` / `check_data.py` bulk-load Excel backups from `reference/원본엑셀/`. Dedup scripts: `check_dupes.py`/`check_farms.py`/`check_linkage.py` are read-only; `fix_dupes.py`/`cleanup_dupes.py` are destructive with *different* preservation rules — never run both, and back up `data/consulting.db` first.
- `reference/` (gitignored) holds source material copied in from outside: `원본PDF/`, `원본엑셀/`, `통계자료/`, `과거리포트/` (contains 조합원 real names).
- Never commit `migrate.py` (Turso token in plaintext) or `dump.sql` (조합원 personal data); both are gitignored. Force push is blocked by `.claude/hooks/block_force_push.py`.
- Design docs live in `docs/01_...md`–`docs/06_...md`.
