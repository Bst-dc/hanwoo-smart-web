import pandas as pd
import sqlite3
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "consulting.db")
TSV_PATH = os.path.join(BASE_DIR, "tests", "temp_survey.tsv")

def get_db():
    return sqlite3.connect(DB_PATH)

def import_temp_survey():
    if not os.path.exists(TSV_PATH):
        print(f"File not found: {TSV_PATH}")
        return
    print(f"Reading {TSV_PATH}...")
    df = pd.read_csv(TSV_PATH, sep='\t', engine='python')
    
    conn = get_db()
    cur = conn.cursor()
    saved = 0
    for _, row in df.iterrows():
        farm_name = str(row.get("조합원명", "기본농가")).strip()
        cur.execute("SELECT id FROM farms WHERE farm_name = ?", (farm_name,))
        farm_res = cur.fetchone()
        
        member_no = row.get("조합원번호")
        code = f"M{int(member_no)}" if pd.notna(member_no) else f"V_temp_{saved}"

        if farm_res: 
            farm_id = farm_res[0]
            # Update region, full_time, breeding_type if provided
            region = str(row.get("지역", "")).strip()
            full_time = str(row.get("전업여부", "")).strip()
            breeding_type = str(row.get("사육형태", "")).strip()
            # update farm code just in case
            cur.execute("UPDATE farms SET farm_code=?, region=?, full_time=?, breeding_type=? WHERE id=?", 
                        (code, region if region != "nan" else "", full_time if full_time != "nan" else "", breeding_type if breeding_type != "nan" else "", farm_id))
        else:
            region = str(row.get("지역", "")).strip()
            full_time = str(row.get("전업여부", "")).strip()
            breeding_type = str(row.get("사육형태", "")).strip()
            cur.execute("INSERT INTO farms (farm_code, farm_name, region, full_time, breeding_type) VALUES (?, ?, ?, ?, ?)", 
                        (code, farm_name, region if region != "nan" else "", full_time if full_time != "nan" else "", breeding_type if breeding_type != "nan" else ""))
            farm_id = cur.lastrowid

        v_date = str(row.get("조사일자", "2026-09-01"))[:10]
        consultant = "배성태" # Default
        
        cur.execute("SELECT COALESCE(MAX(visit_number), 0) + 1 FROM visits WHERE farm_id = ?", (farm_id,))
        v_no = cur.fetchone()[0]
        cur.execute("INSERT INTO visits (farm_id, visit_number, visit_date, consultant_name) VALUES (?, ?, ?, ?)",
                    (farm_id, v_no, v_date, consultant))
        v_id = cur.lastrowid
        
        def safe_str(val):
            return "" if pd.isna(val) else str(val).strip()

        facility_dict = {
            "steer_pen": safe_str(row.get("비육우방 크기")), "steer_density": safe_str(row.get("비육우방 밀도")),
            "cow_pen": safe_str(row.get("번식우방 크기")), "cow_density": safe_str(row.get("번식우방 밀도")),
            "calf_pen": safe_str(row.get("송아지우방 크기")), "calf_density": safe_str(row.get("송아지우방 밀도"))
        }
        feed_dict = {
            "order": safe_str(row.get("급여순서")), "times": safe_str(row.get("급여횟수")),
            "calf": safe_str(row.get("송아지 배합사료 품목")), "growing": safe_str(row.get("육성우 배합사료 품목")), 
            "early": safe_str(row.get("비육전기 배합사료 품목")), "late": safe_str(row.get("비육후기 배합사료 품목")), 
            "cow": safe_str(row.get("번식우 배합사료 품목"))
        }
        notes = safe_str(row.get("내용"))
        # We can also put everything else inside survey_data JSON
        survey_data = row.dropna().to_dict()
        
        cur.execute("""
        INSERT INTO field_surveys (visit_id, facility_info, feed_info, consult_notes, survey_data)
        VALUES (?, ?, ?, ?, ?)
        """, (v_id, json.dumps(facility_dict, ensure_ascii=False), json.dumps(feed_dict, ensure_ascii=False), notes, json.dumps(survey_data, ensure_ascii=False)))
        saved += 1
    conn.commit()
    conn.close()
    print(f"Survey records saved: {saved}")

if __name__ == "__main__":
    import_temp_survey()
