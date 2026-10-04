import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "consulting.db")

def check_duplicates():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
    SELECT f.farm_name, f.id, COUNT(v.id) as visit_count
    FROM visits v
    JOIN farms f ON v.farm_id = f.id
    GROUP BY v.farm_id
    HAVING COUNT(v.id) > 1
    """)
    duplicates = cur.fetchall()
    
    if not duplicates:
        print("중복된 방문 이력이 없습니다.")
    else:
        print(f"중복 방문 이력이 있는 농가 수: {len(duplicates)}")
        for row in duplicates:
            farm_name, farm_id, count = row
            print(f"- {farm_name} (ID: {farm_id}): {count}번 방문 기록됨")
            
            # 벙문 내역 상세 조회
            cur.execute("SELECT id, visit_date, visit_number FROM visits WHERE farm_id = ? ORDER BY id", (farm_id,))
            visits = cur.fetchall()
            for v in visits:
                # 현장조사표 존재 여부
                cur.execute("SELECT 1 FROM field_surveys WHERE visit_id = ?", (v[0],))
                has_survey = bool(cur.fetchone())
                print(f"   * Visit ID {v[0]}: 날짜 {v[1]}, 회차 {v[2]}, 현장조사표 {'있음' if has_survey else '없음'}")
                
    conn.close()

if __name__ == "__main__":
    check_duplicates()
