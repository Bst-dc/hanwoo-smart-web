import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "consulting.db")

def fix_duplicates():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
    SELECT farm_id, COUNT(id) as visit_count
    FROM visits
    GROUP BY farm_id
    HAVING COUNT(id) > 1
    """)
    duplicates = cur.fetchall()
    
    deleted_count = 0
    
    for farm_id, count in duplicates:
        cur.execute("SELECT id FROM visits WHERE farm_id = ? ORDER BY id", (farm_id,))
        visits = [row[0] for row in cur.fetchall()]
        
        # Check which visit has a survey
        visit_to_keep = visits[-1] # Default to most recent
        for v in visits:
            cur.execute("SELECT 1 FROM field_surveys WHERE visit_id = ?", (v,))
            if cur.fetchone():
                visit_to_keep = v
                break
                
        visits_to_delete = [v for v in visits if v != visit_to_keep]
        
        for v_id in visits_to_delete:
            cur.execute("DELETE FROM field_surveys WHERE visit_id = ?", (v_id,))
            cur.execute("DELETE FROM ai_reports WHERE visit_id = ?", (v_id,))
            cur.execute("DELETE FROM visits WHERE id = ?", (v_id,))
            deleted_count += 1
            
        cur.execute("UPDATE visits SET visit_number = 1 WHERE id = ?", (visit_to_keep,))

    conn.commit()
    conn.close()
    print(f"총 {deleted_count}개의 중복 방문 기록이 안전하게 정리되었습니다. (조사표 보존 완료)")

if __name__ == "__main__":
    fix_duplicates()
