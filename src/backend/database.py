# -*- coding: utf-8 -*-
"""
한우 스마트 컨설팅 데이터베이스 모듈 (SQLite 기반)
"""
import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "consulting.db")

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 농가 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS farms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farm_code TEXT UNIQUE,
        farm_name TEXT NOT NULL,
        owner_name TEXT,
        phone TEXT,
        address TEXT,
        breeding_type TEXT DEFAULT '비육우',
        total_heads INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. 방문 회차 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farm_id INTEGER NOT NULL,
        visit_number INTEGER NOT NULL DEFAULT 1,
        visit_date DATE NOT NULL,
        consultant_name TEXT,
        status TEXT DEFAULT 'completed',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farm_id) REFERENCES farms (id) ON DELETE CASCADE,
        UNIQUE(farm_id, visit_number)
    );
    """)

    # 3. 현장 방문 조사 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS field_surveys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visit_id INTEGER UNIQUE NOT NULL,
        feed_data TEXT,         -- JSON
        facility_data TEXT,     -- JSON
        health_data TEXT,       -- JSON
        farmer_dialogue TEXT,   -- 농가 대화 내용
        consultant_memo TEXT,   -- 컨설턴트 메모
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (visit_id) REFERENCES visits (id) ON DELETE CASCADE
    );
    """)

    # 4. 개체별 출하성적 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shipment_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farm_id INTEGER NOT NULL,
        animal_no TEXT NOT NULL,
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
        data_source TEXT DEFAULT 'api',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farm_id) REFERENCES farms (id) ON DELETE CASCADE,
        UNIQUE(farm_id, animal_no)
    );
    """)

    # 5. Claude AI 리포트 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visit_id INTEGER UNIQUE NOT NULL,
        diagnosis TEXT,
        root_causes TEXT,
        prescriptions TEXT,
        action_roadmap TEXT,
        full_markdown TEXT NOT NULL,
        model_used TEXT DEFAULT 'claude-sonnet',
        generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (visit_id) REFERENCES visits (id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
