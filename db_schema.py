"""Supabase(PostgreSQL) 표 정의와, 백업 파일(.db)용 SQLite 표 정의.

streamlit_app.py 는 import 하면 화면을 그리기 시작하므로, 이관 스크립트(migrate_to_supabase.py)도
같이 쓸 수 있게 표 정의만 따로 둔다.

표 구조는 운영 DB(Turso, 2026-10-04 기준)를 그대로 따른다. streamlit_app.py 의 init_db() 에 적힌
SQLite 정의와는 몇 군데 다른데, 운영 DB 가 init_db() 보다 먼저 다른 스크립트로 만들어졌기 때문이다.
- shipment_records: 이력번호(animal_no) 하나가 전체에서 한 행 (init_db 는 농가+이력번호 기준이었다)
- field_surveys: created_at 컬럼이 있다 (init_db 는 updated_at) → 둘 다 둔다

Postgres 로 옮기며 바꾼 타입:
- 날짜·시각은 SQLite 처럼 'YYYY-MM-DD[ HH:MM:SS]' 문자열(TEXT)로 둔다. DATE 로 바꾸면 앱이 받는 값이
  문자열이 아니라 date 객체가 되어, 문자열 자르기·비교를 하는 코드가 조용히 달라진다.
- 실수 컬럼은 REAL 대신 NUMERIC. Postgres 의 round() 는 numeric 만 받아서, 앱의
  ROUND(AVG(carcass_weight), 1) 이 REAL/double 컬럼에서는 오류가 난다.
  (어댑터가 NUMERIC 결과를 int/float 로 돌려주므로 앱에서는 SQLite 때와 같은 값으로 보인다)
- 기본 시각은 SQLite CURRENT_TIMESTAMP 와 같은 UTC 'YYYY-MM-DD HH:MM:SS' 문자열.

RLS(행 수준 보안)를 켜 둔다. hanwoo 스키마는 Supabase API(PostgREST)에 노출하지 않지만,
혹시 노출 목록에 추가되더라도 정책이 없으니 anon/authenticated 키로는 아무것도 읽을 수 없다.
앱은 표 소유자(postgres) 계정으로 직접 접속하므로 RLS 의 영향을 받지 않는다.
"""

SCHEMA = "hanwoo"

# 외래키 순서(부모 → 자식). 이관·백업이 이 순서로 넣는다.
TABLES = ["farms", "visits", "field_surveys", "shipment_records", "ai_reports"]

_NOW = "to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"

PG_DDL = f"""
CREATE TABLE IF NOT EXISTS farms (
    id SERIAL PRIMARY KEY,
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
    created_at TEXT DEFAULT {_NOW}
);
CREATE TABLE IF NOT EXISTS visits (
    id SERIAL PRIMARY KEY,
    farm_id INTEGER NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    visit_number INTEGER NOT NULL DEFAULT 1,
    visit_date TEXT NOT NULL,
    consultant_name TEXT,
    status TEXT DEFAULT 'completed',
    created_at TEXT DEFAULT {_NOW}
);
CREATE TABLE IF NOT EXISTS field_surveys (
    id SERIAL PRIMARY KEY,
    visit_id INTEGER UNIQUE NOT NULL REFERENCES visits (id) ON DELETE CASCADE,
    facility_info TEXT,
    feed_info TEXT,
    consult_notes TEXT,
    consultant_memo TEXT,
    survey_data TEXT,
    created_at TEXT DEFAULT {_NOW},
    updated_at TEXT DEFAULT {_NOW}
);
CREATE TABLE IF NOT EXISTS shipment_records (
    id SERIAL PRIMARY KEY,
    farm_id INTEGER NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    animal_no TEXT UNIQUE NOT NULL,
    gender TEXT,
    slaughter_date TEXT,
    slaughter_year INTEGER,
    month_age NUMERIC,
    carcass_weight NUMERIC,
    grade_quality TEXT,
    grade_yield TEXT,
    bms NUMERIC,
    backfat NUMERIC,
    ribeye NUMERIC,
    price_per_kg NUMERIC,
    total_price NUMERIC,
    data_source TEXT DEFAULT 'manual',
    created_at TEXT DEFAULT {_NOW}
);
CREATE TABLE IF NOT EXISTS ai_reports (
    id SERIAL PRIMARY KEY,
    visit_id INTEGER NOT NULL REFERENCES visits (id) ON DELETE CASCADE,
    report_type TEXT DEFAULT 'final',
    report_mode TEXT NOT NULL DEFAULT '일반',
    full_markdown TEXT NOT NULL,
    created_at TEXT DEFAULT {_NOW},
    UNIQUE (visit_id, report_mode)
);
CREATE INDEX IF NOT EXISTS idx_visits_farm ON visits (farm_id);
CREATE INDEX IF NOT EXISTS idx_shipment_farm ON shipment_records (farm_id);
ALTER TABLE farms ENABLE ROW LEVEL SECURITY;
ALTER TABLE visits ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_surveys ENABLE ROW LEVEL SECURITY;
ALTER TABLE shipment_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_reports ENABLE ROW LEVEL SECURITY;
"""

# ensure_schema 가 이것들이 다 있으면 DDL 을 건너뛴다 (표 잠금을 잡지 않도록)
REQUIRED_COLUMNS = [
    ("farms", "region"), ("farms", "full_time"), ("farms", "side_job"),
    ("field_surveys", "survey_data"), ("field_surveys", "updated_at"),
    ("ai_reports", "report_mode"), ("ai_reports", "created_at"),
]

# 백업 파일(.db)용. 운영 DB(Turso)의 표 정의를 그대로 옮겨, 백업 파일이 이관 전과 같은 모양이 되게 한다.
# export_to_sqlite 가 두 번 실행하므로 IF NOT EXISTS 여야 한다.
SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS farms (id INTEGER PRIMARY KEY AUTOINCREMENT, farm_code TEXT UNIQUE, farm_name TEXT NOT NULL, owner_name TEXT, phone TEXT, address TEXT, region TEXT, full_time TEXT DEFAULT '전업', side_job TEXT, breeding_type TEXT DEFAULT '비육우', total_heads INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS visits (id INTEGER PRIMARY KEY AUTOINCREMENT, farm_id INTEGER NOT NULL, visit_number INTEGER NOT NULL DEFAULT 1, visit_date DATE NOT NULL, consultant_name TEXT, status TEXT DEFAULT 'completed', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (farm_id) REFERENCES farms (id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS field_surveys (id INTEGER PRIMARY KEY AUTOINCREMENT, visit_id INTEGER UNIQUE NOT NULL, facility_info TEXT, feed_info TEXT, consult_notes TEXT, consultant_memo TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, survey_data TEXT, updated_at DATETIME, FOREIGN KEY (visit_id) REFERENCES visits (id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS shipment_records (id INTEGER PRIMARY KEY AUTOINCREMENT, farm_id INTEGER NOT NULL, animal_no TEXT UNIQUE NOT NULL, gender TEXT, slaughter_date DATE, slaughter_year INTEGER, month_age INTEGER, carcass_weight REAL, grade_quality TEXT, grade_yield TEXT, bms INTEGER, backfat REAL, ribeye REAL, price_per_kg INTEGER, total_price INTEGER, data_source TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (farm_id) REFERENCES farms (id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS ai_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, visit_id INTEGER NOT NULL, report_type TEXT DEFAULT 'final', report_mode TEXT NOT NULL DEFAULT '일반', full_markdown TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (visit_id) REFERENCES visits (id) ON DELETE CASCADE, UNIQUE(visit_id, report_mode));
"""
