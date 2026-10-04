import pandas as pd
import sqlite3
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "consulting.db")

path_shipment = os.path.join(BASE_DIR, "reference", "원본엑셀", "농가출하데이터.xlsx")
path_survey = os.path.join(BASE_DIR, "reference", "원본엑셀", "한우현장조사_백업_20260916_2217.xlsx")

def get_db():
    return sqlite3.connect(DB_PATH)

def import_shipment():
    if not os.path.exists(path_shipment):
        print(f"File not found: {path_shipment}")
        return
    print(f"Reading {path_shipment}...")
    df = pd.read_excel(path_shipment, sheet_name='데이터', engine='openpyxl')
    
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
        "월령": ["도축개월령", "출하월령"],
        "농가명": ["최종농장주", "농가명", "농장명"]
    }
    def find_col(keys):
        for k in keys:
            if k in df.columns: return k
        return None
        
    conn = get_db()
    cur = conn.cursor()
    saved = 0
    for _, row in df.iterrows():
        farm_name_val = str(row.get(find_col(col_map.get("농가명", ["농가명"])), "기본농가")).strip()
        # Farm 찾기 또는 생성
        cur.execute("SELECT id FROM farms WHERE farm_name = ?", (farm_name_val,))
        farm_res = cur.fetchone()
        if farm_res:
            farm_id = farm_res[0]
        else:
            cur.execute("INSERT INTO farms (farm_code, farm_name) VALUES (?, ?)", (f"F_{saved}", farm_name_val))
            farm_id = cur.lastrowid

        ano = str(row.get(find_col(col_map["이력번호"]), "")).replace("-", "").strip()
        if not ano or len(ano) < 8: continue
        gender = "거세" if "거세" in str(row.get(find_col(col_map["성별"]), "거세")) else "암"
        sdate = str(row.get(find_col(col_map["도축일자"]), "2025-01-01"))[:10]
        try: syear = int(sdate[:4])
        except: syear = 2025
        
        cur.execute("""
        INSERT OR REPLACE INTO shipment_records (
            farm_id, animal_no, gender, slaughter_date, slaughter_year, month_age,
            carcass_weight, grade_quality, grade_yield, bms, backfat, ribeye, data_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'excel_batch')
        """, (
            farm_id, ano, gender, sdate, syear,
            row.get(find_col(col_map["월령"])),
            row.get(find_col(col_map["도체중"])),
            str(row.get(find_col(col_map["육질등급"]), "")).strip(),
            str(row.get(find_col(col_map["육량등급"]), "")).strip(),
            row.get(find_col(col_map["BMS"])),
            row.get(find_col(col_map["등지방"])),
            row.get(find_col(col_map["단면적"]))
        ))
        saved += 1
    conn.commit()
    conn.close()
    print(f"Shipment records saved: {saved}")

def import_survey():
    if not os.path.exists(path_survey):
        print(f"File not found: {path_survey}")
        return
    print(f"Reading {path_survey}...")
    df = pd.read_excel(path_survey, engine='openpyxl')
    
    conn = get_db()
    cur = conn.cursor()
    saved = 0
    for _, row in df.iterrows():
        # 컬럼 매핑: 실제 백업 엑셀 헤더는 "조합원명"/"조사일자"/"조사자 성명"이다
        # ("농가명"/"컨설턴트" 컬럼은 존재하지 않아 항상 기본값으로 빠지는 버그가 있었음)
        farm_name = str(row.get("조합원명", "기본농가")).strip()
        cur.execute("SELECT id FROM farms WHERE farm_name = ?", (farm_name,))
        farm_res = cur.fetchone()
        if farm_res: farm_id = farm_res[0]
        else:
            member_no = row.get("조합원번호")
            code = f"M{int(member_no)}" if pd.notna(member_no) else f"V_{saved}"
            cur.execute("INSERT INTO farms (farm_code, farm_name) VALUES (?, ?)", (code, farm_name))
            farm_id = cur.lastrowid

        v_date = str(row.get("조사일자", "2026-09-01"))[:10]
        consultant = str(row.get("조사자 성명", "배성태")).strip()
        
        cur.execute("SELECT COALESCE(MAX(visit_number), 0) + 1 FROM visits WHERE farm_id = ?", (farm_id,))
        v_no = cur.fetchone()[0]
        cur.execute("INSERT INTO visits (farm_id, visit_number, visit_date, consultant_name) VALUES (?, ?, ?, ?)",
                    (farm_id, v_no, v_date, consultant))
        v_id = cur.lastrowid
        
        facility_dict = {
            "steer_pen": str(row.get("비육우방크기", "")), "steer_density": str(row.get("비육우방밀도", "")),
            "cow_pen": str(row.get("번식우방크기", "")), "cow_density": str(row.get("번식우방밀도", "")),
            "calf_pen": str(row.get("송아지우방크기", "")), "calf_density": str(row.get("송아지우방밀도", ""))
        }
        feed_dict = {
            "order": str(row.get("급여순서", "")), "times": str(row.get("급여횟수", "")),
            "calf": str(row.get("송아지사료", "")), "growing": str(row.get("육성우사료", "")), 
            "early": str(row.get("비육전기사료", "")), "late": str(row.get("비육후기사료", "")), 
            "cow": str(row.get("번식우사료", "")), "eval": str(row.get("사료평가", ""))
        }
        notes = str(row.get("특이사항", ""))
        memo = str(row.get("개선처방", ""))
        
        cur.execute("""
        INSERT INTO field_surveys (visit_id, facility_info, feed_info, consult_notes, consultant_memo)
        VALUES (?, ?, ?, ?, ?)
        """, (v_id, json.dumps(facility_dict, ensure_ascii=False), json.dumps(feed_dict, ensure_ascii=False), notes, memo))
        saved += 1
    conn.commit()
    conn.close()
    print(f"Survey records saved: {saved}")

if __name__ == "__main__":
    import_shipment()
    import_survey()
