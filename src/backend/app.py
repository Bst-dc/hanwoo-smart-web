# -*- coding: utf-8 -*-
"""
한우 스마트 컨설팅 통합 웹 플랫폼 백엔드 서버 (Python 내장 HTTP / REST API)
"""
import os
import sys
import json
import secrets
import sqlite3
import mimetypes
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 모듈 경로 추가
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(CURRENT_DIR)

import database
import ekape_api
import kosis_api
import claude_service

PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
FRONTEND_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "frontend")
ACCESS_TOKEN_FILE = os.path.join(PROJECT_ROOT, "access_token.txt")


def get_access_token():
    """cloudflared 터널 등으로 외부에 노출될 수 있는 서버라 공유 토큰으로 /api/* 를 보호한다.
    env var -> 로컬 파일 순으로 찾고, 없으면 새로 생성해 파일에 저장한다."""
    env_token = os.environ.get("HANWOO_ACCESS_TOKEN")
    if env_token:
        return env_token.strip()
    if os.path.exists(ACCESS_TOKEN_FILE):
        with open(ACCESS_TOKEN_FILE, "r", encoding="utf-8") as f:
            token = f.read().strip()
            if token:
                return token
    token = secrets.token_urlsafe(24)
    with open(ACCESS_TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token)
    return token


ACCESS_TOKEN = get_access_token()

class HanwooWebHandler(BaseHTTPRequestHandler):
    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _is_authorized(self):
        return self.headers.get("X-Access-Token") == ACCESS_TOKEN

    def _reject_unauthorized(self):
        self._send_json({"error": "인증 토큰이 필요합니다."}, 401)

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 1. API 엔드포인트 처리 (농가 개인정보가 오가므로 토큰 필수)
        if path.startswith("/api/"):
            if not self._is_authorized():
                self._reject_unauthorized()
                return

        if path == "/api/dashboard":
            self.handle_get_dashboard()
            return
        elif path == "/api/farms":
            self.handle_get_farms()
            return
        elif path.startswith("/api/farms/"):
            farm_id = int(path.split("/")[-1])
            self.handle_get_farm_detail(farm_id)
            return
        elif path.startswith("/api/reports/"):
            visit_id = int(path.split("/")[-1])
            self.handle_get_report(visit_id)
            return

        # 2. 정적 웹 파일 서빙 (HTML, CSS, JS)
        if path == "/" or path == "":
            file_path = os.path.join(FRONTEND_DIR, "index.html")
        else:
            rel_path = path.lstrip("/")
            file_path = os.path.join(FRONTEND_DIR, rel_path)

        if os.path.exists(file_path) and os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            self.send_response(200)
            self.send_header("Content-Type", mime_type or "application/octet-stream")
            self._set_cors_headers()
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/") and not self._is_authorized():
            self._reject_unauthorized()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        
        try:
            body_data = json.loads(post_body) if post_body else {}
        except:
            body_data = {}

        if path == "/api/farms":
            self.handle_create_farm(body_data)
        elif path == "/api/shipment/lookup":
            self.handle_lookup_shipments(body_data)
        elif path == "/api/survey/save":
            self.handle_save_survey(body_data)
        elif path == "/api/report/generate":
            self.handle_generate_report(body_data)
        else:
            self.send_response(404)
            self.end_headers()

    # --- 핸들러 구현 ---

    def handle_get_dashboard(self):
        conn = database.get_db_connection()
        cursor = conn.cursor()

        # 1. KPI 카드 집계
        cursor.execute("SELECT COUNT(*) FROM farms")
        total_farms = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM visits")
        total_visits = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM shipment_records")
        total_shipments = cursor.fetchone()[0]

        cursor.execute("""
        SELECT ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1)
        FROM shipment_records
        """)
        row = cursor.fetchone()
        avg_1plus_rate = row[0] if row and row[0] is not None else 0.0

        # 2. 방문 농가 전체의 연도별 평균 성적 집계
        cursor.execute("""
        SELECT 
            slaughter_year AS year,
            gender,
            COUNT(DISTINCT farm_id) AS farm_count,
            COUNT(id) AS head_count,
            ROUND(AVG(carcass_weight), 1) AS avg_weight,
            ROUND(AVG(bms), 1) AS avg_bms,
            ROUND(AVG(backfat), 1) AS avg_backfat,
            ROUND(AVG(ribeye), 1) AS avg_ribeye,
            ROUND(AVG(month_age), 1) AS avg_month_age,
            ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END) * 100.0 / COUNT(id), 1) AS rate_1plus_above,
            ROUND(SUM(CASE WHEN grade_quality = '1++' THEN 1 ELSE 0 END) * 100.0 / COUNT(id), 1) AS rate_1plus_plus
        FROM shipment_records
        WHERE gender = '거세' AND slaughter_year BETWEEN 2023 AND 2026
        GROUP BY slaughter_year, gender
        ORDER BY slaughter_year ASC
        """)
        yearly_averages = [dict(r) for r in cursor.fetchall()]

        # 3. 최근 컨설팅 방문 이력 (최근 5건)
        cursor.execute("""
        SELECT v.id, v.farm_id, f.farm_name, v.visit_number, v.visit_date, v.consultant_name, v.status,
               (SELECT COUNT(*) FROM ai_reports r WHERE r.visit_id = v.id) as has_report
        FROM visits v
        JOIN farms f ON v.farm_id = f.id
        ORDER BY v.visit_date DESC, v.id DESC
        LIMIT 5
        """)
        recent_visits = [dict(r) for r in cursor.fetchall()]

        conn.close()

        self._send_json({
            "kpi": {
                "total_farms": total_farms,
                "total_visits": total_visits,
                "total_shipments": total_shipments,
                "avg_1plus_rate": avg_1plus_rate
            },
            "yearly_averages": yearly_averages,
            "national_benchmarks": kosis_api.NATIONAL_BENCHMARKS["거세"],
            "recent_visits": recent_visits
        })

    def handle_get_farms(self):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT f.*, 
               (SELECT COUNT(*) FROM visits v WHERE v.farm_id = f.id) as visit_count,
               (SELECT COUNT(*) FROM shipment_records s WHERE s.farm_id = f.id) as shipment_count
        FROM farms f
        ORDER BY f.id DESC
        """)
        farms = [dict(r) for r in cursor.fetchall()]
        conn.close()
        self._send_json(farms)

    def handle_create_farm(self, data):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        farm_code = data.get("farm_code") or f"F{int(datetime.now().timestamp())%10000}"
        cursor.execute("""
        INSERT INTO farms (farm_code, farm_name, owner_name, phone, address, breeding_type, total_heads)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            farm_code,
            data.get("farm_name", "신규농가"),
            data.get("owner_name", ""),
            data.get("phone", ""),
            data.get("address", ""),
            data.get("breeding_type", "비육우"),
            int(data.get("total_heads", 0))
        ))
        farm_id = cursor.lastrowid
        conn.commit()
        conn.close()
        self._send_json({"success": True, "farm_id": farm_id, "farm_code": farm_code})

    def handle_get_farm_detail(self, farm_id):
        conn = database.get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM farms WHERE id = ?", (farm_id,))
        farm = cursor.fetchone()
        if not farm:
            conn.close()
            self._send_json({"error": "농가를 찾을 수 없습니다."}, 404)
            return

        # 출하 성적 집계
        cursor.execute("""
        SELECT 
            COUNT(id) as total_count,
            ROUND(AVG(carcass_weight), 1) as avg_weight,
            ROUND(AVG(bms), 1) as avg_bms,
            ROUND(AVG(backfat), 1) as avg_backfat,
            ROUND(AVG(ribeye), 1) as avg_ribeye,
            ROUND(AVG(month_age), 1) as avg_month_age,
            ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END) * 100.0 / COUNT(id), 1) as rate_1plus_above,
            ROUND(SUM(CASE WHEN grade_quality = '1++' THEN 1 ELSE 0 END) * 100.0 / COUNT(id), 1) as rate_1plus_plus
        FROM shipment_records
        WHERE farm_id = ? AND gender = '거세'
        """, (farm_id,))
        stats = dict(cursor.fetchone() or {})

        # 전국 비교표 생성
        comparisons = kosis_api.compare_farm_with_national(stats, year=2025, gender="거세")

        # 개체 목록 (최근 20두)
        cursor.execute("""
        SELECT * FROM shipment_records WHERE farm_id = ? ORDER BY slaughter_date DESC LIMIT 20
        """, (farm_id,))
        records = [dict(r) for r in cursor.fetchall()]

        # 방문 이력 및 현장조사
        cursor.execute("""
        SELECT v.*, s.feed_data, s.facility_data, s.health_data, s.farmer_dialogue, s.consultant_memo,
               (SELECT r.id FROM ai_reports r WHERE r.visit_id = v.id) as report_id
        FROM visits v
        LEFT JOIN field_surveys s ON s.visit_id = v.id
        WHERE v.farm_id = ?
        ORDER BY v.visit_number DESC
        """, (farm_id,))
        visits = [dict(r) for r in cursor.fetchall()]

        conn.close()

        self._send_json({
            "farm": dict(farm),
            "stats": stats,
            "comparisons": comparisons,
            "records": records,
            "visits": visits
        })

    def handle_lookup_shipments(self, data):
        farm_id = data.get("farm_id")
        animal_numbers = data.get("animal_numbers", [])
        if not farm_id or not animal_numbers:
            self._send_json({"error": "farm_id와 animal_numbers가 필요합니다."}, 400)
            return

        conn = database.get_db_connection()
        cursor = conn.cursor()

        saved_count = 0
        fetched_records = []
        for ano in animal_numbers:
            grade_info = ekape_api.get_cattle_grade(ano)
            if grade_info:
                fetched_records.append(grade_info)
                # 도축일자 파싱
                s_date = grade_info.get("slaughter_date") or "2025-01-01"
                try:
                    s_year = int(s_date[:4])
                except:
                    s_year = 2025

                cursor.execute("""
                INSERT OR REPLACE INTO shipment_records (
                    farm_id, animal_no, gender, slaughter_date, slaughter_year, month_age,
                    carcass_weight, grade_quality, grade_yield, bms, backfat, ribeye, price_per_kg, total_price, data_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    farm_id,
                    grade_info["animal_no"],
                    "거세",
                    s_date,
                    s_year,
                    grade_info.get("month_age"),
                    grade_info.get("carcass_weight"),
                    grade_info.get("grade_quality"),
                    grade_info.get("grade_yield"),
                    grade_info.get("bms"),
                    grade_info.get("backfat"),
                    grade_info.get("ribeye"),
                    grade_info.get("costAmt"),
                    int((grade_info.get("carcass_weight") or 0) * (grade_info.get("costAmt") or 0)),
                    "ekape_api"
                ))
                saved_count += 1

        conn.commit()
        conn.close()

        self._send_json({
            "success": True,
            "requested": len(animal_numbers),
            "saved_count": saved_count,
            "records": fetched_records
        })

    def handle_save_survey(self, data):
        farm_id = data.get("farm_id")
        visit_date = data.get("visit_date") or datetime.now().strftime("%Y-%m-%d")
        consultant_name = data.get("consultant_name", "배성태 컨설턴트")

        conn = database.get_db_connection()
        cursor = conn.cursor()

        # 1. 새 방문 생성 (또는 기존 방문 연계)
        cursor.execute("SELECT COALESCE(MAX(visit_number), 0) + 1 FROM visits WHERE farm_id = ?", (farm_id,))
        next_visit_no = cursor.fetchone()[0]

        cursor.execute("""
        INSERT INTO visits (farm_id, visit_number, visit_date, consultant_name)
        VALUES (?, ?, ?, ?)
        """, (farm_id, next_visit_no, visit_date, consultant_name))
        visit_id = cursor.lastrowid

        # 2. 현장조사 데이터 저장
        cursor.execute("""
        INSERT INTO field_surveys (visit_id, feed_data, facility_data, health_data, farmer_dialogue, consultant_memo)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            visit_id,
            json.dumps(data.get("feed_data", {}), ensure_ascii=False),
            json.dumps(data.get("facility_data", {}), ensure_ascii=False),
            json.dumps(data.get("health_data", {}), ensure_ascii=False),
            data.get("farmer_dialogue", ""),
            data.get("consultant_memo", "")
        ))

        conn.commit()
        conn.close()

        self._send_json({"success": True, "visit_id": visit_id, "visit_number": next_visit_no})

    def handle_generate_report(self, data):
        farm_id = data.get("farm_id")
        visit_id = data.get("visit_id")

        conn = database.get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM farms WHERE id = ?", (farm_id,))
        farm = dict(cursor.fetchone() or {})
        farm_name = farm.get("farm_name", "농가")

        # 출하성적 요약
        cursor.execute("""
        SELECT 
            COUNT(id) as total_count,
            ROUND(AVG(carcass_weight), 1) as avg_weight,
            ROUND(AVG(bms), 1) as avg_bms,
            ROUND(AVG(backfat), 1) as avg_backfat,
            ROUND(AVG(ribeye), 1) as avg_ribeye,
            ROUND(AVG(month_age), 1) as avg_month_age,
            ROUND(SUM(CASE WHEN grade_quality IN ('1++', '1+') THEN 1 ELSE 0 END) * 100.0 / COUNT(id), 1) as rate_1plus_above,
            ROUND(SUM(CASE WHEN grade_quality = '1++' THEN 1 ELSE 0 END) * 100.0 / COUNT(id), 1) as rate_1plus_plus
        FROM shipment_records
        WHERE farm_id = ? AND gender = '거세'
        """, (farm_id,))
        shipment_stats = dict(cursor.fetchone() or {})

        # 비교분석표
        comparisons = kosis_api.compare_farm_with_national(shipment_stats, year=2025, gender="거세")

        # 현장 조사 데이터
        cursor.execute("SELECT * FROM field_surveys WHERE visit_id = ?", (visit_id,))
        survey_row = cursor.fetchone()
        survey_data = dict(survey_row) if survey_row else {}

        # Claude 리포트 생성
        markdown_report = claude_service.generate_consulting_report(farm_name, shipment_stats, survey_data, comparisons)

        # DB 저장
        cursor.execute("""
        INSERT OR REPLACE INTO ai_reports (visit_id, full_markdown)
        VALUES (?, ?)
        """, (visit_id, markdown_report))

        conn.commit()
        conn.close()

        self._send_json({
            "success": True,
            "visit_id": visit_id,
            "report_markdown": markdown_report
        })

    def handle_get_report(self, visit_id):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_reports WHERE visit_id = ?", (visit_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            self._send_json(dict(row))
        else:
            self._send_json({"error": "리포트를 찾을 수 없습니다."}, 404)

def run_server(port=8080):
    database.init_db()
    server_address = ("", port)
    httpd = HTTPServer(server_address, HanwooWebHandler)
    print(f"==================================================")
    print(f" 한우 스마트 컨설팅 통합 웹 플랫폼 서버 구동 완료!")
    print(f" 로컬 주소: http://localhost:{port}/?token={ACCESS_TOKEN}")
    print(f" 모바일 접속: http://[내_PC_IP]:{port}/?token={ACCESS_TOKEN}")
    print(f" (반드시 위 token= 이 붙은 주소로 접속해야 데이터가 보입니다.")
    print(f"  cloudflared 터널 주소도 뒤에 ?token={ACCESS_TOKEN} 를 붙여서 공유하세요.)")
    print(f"==================================================")
    httpd.serve_forever()

if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)
