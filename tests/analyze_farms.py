import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "consulting.db")

def run_analysis():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Farms with shipment records but NO visit/survey history
    query1 = """
    SELECT f.farm_name, COUNT(s.id) as shipment_count
    FROM farms f
    JOIN shipment_records s ON f.id = s.farm_id
    LEFT JOIN visits v ON f.id = v.farm_id
    WHERE v.id IS NULL
    GROUP BY f.id
    ORDER BY shipment_count DESC
    """
    cursor.execute(query1)
    res1 = cursor.fetchall()
    
    # 2. Farms with visit/survey history but NO shipment records
    query2 = """
    SELECT f.farm_name, COUNT(DISTINCT v.id) as visit_count
    FROM farms f
    JOIN visits v ON f.id = v.farm_id
    JOIN field_surveys fs ON v.id = fs.visit_id
    LEFT JOIN shipment_records s ON f.id = s.farm_id
    WHERE s.id IS NULL
    GROUP BY f.id
    ORDER BY visit_count DESC
    """
    cursor.execute(query2)
    res2 = cursor.fetchall()
    
    conn.close()
    
    # Create markdown output
    with open(os.path.join(BASE_DIR, "tests", "analysis_output.md"), "w", encoding="utf-8") as f:
        f.write("# 데이터 누락 교차 분석\n\n")
        
        f.write("## 1. 출하 성적은 있으나 현장 방문 이력이 없는 농가\n")
        f.write("> 출하 성적 데이터만 등록되어 있는 농가입니다.\n\n")
        f.write("| 농가명 | 등록된 출하성적 건수 |\n")
        f.write("|---|---|\n")
        if len(res1) > 0:
            for row in res1:
                f.write(f"| {row[0]} | {row[1]} 건 |\n")
        else:
            f.write("| 해당 농가 없음 | - |\n")
        f.write("\n\n")
        
        f.write("## 2. 현장 방문 이력은 있으나 출하 성적이 없는 농가\n")
        f.write("> 현장 방문 조사 기록만 존재하는 농가입니다.\n\n")
        f.write("| 농가명 | 등록된 방문 횟수 |\n")
        f.write("|---|---|\n")
        if len(res2) > 0:
            for row in res2:
                f.write(f"| {row[0]} | {row[1]} 회 |\n")
        else:
            f.write("| 해당 농가 없음 | - |\n")
        f.write("\n")

if __name__ == "__main__":
    run_analysis()
