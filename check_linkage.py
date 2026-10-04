import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "consulting.db")

def check_linkage():
    conn = sqlite3.connect(DB_PATH)
    
    query = """
    SELECT f1.id, f1.farm_name, f1.owner_name, 
           (SELECT COUNT(*) FROM visits WHERE farm_id = f1.id) as visits,
           (SELECT COUNT(*) FROM shipment_records WHERE farm_id = f1.id) as shipments
    FROM farms f1
    ORDER BY f1.farm_name
    """
    df = pd.read_sql_query(query, conn)
    
    with open(os.path.join(BASE_DIR, "farm_linkage.md"), "w", encoding="utf-8") as f:
        f.write(df.to_string())
    
    conn.close()

if __name__ == "__main__":
    check_linkage()
