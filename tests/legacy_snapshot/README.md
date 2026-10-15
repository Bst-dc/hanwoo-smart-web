# 옛 Streamlit 앱 보관본 (시험 기준용)

`streamlit_app_legacy.py` 는 2026-10-15 에 운영에서 내린 Streamlit 앱(`streamlit_app.py`)의 마지막 모습이다.
앱으로 실행하지 않는다. 새 앱(`api/`)이 옛 앱과 같은 SQL·규칙인지 확인하는 시험(`test_db_adapter.py`, `test_dashboard_kpis.py`)이 소스 텍스트만 읽는다.
실행 가능한 원본 전체는 git 태그 `legacy-streamlit` 에서 꺼낸다: `git checkout legacy-streamlit`.
