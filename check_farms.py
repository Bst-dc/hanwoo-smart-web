import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "consulting.db")

def check_farms():
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT * FROM farms
    """
    df = pd.read_sql_query(query, conn)
    
    with open(os.path.join(BASE_DIR, "farms_all.md"), "w", encoding="utf-8") as f:
        f.write(df.to_string())
    conn.close()

if __name__ == "__main__":
    check_farms()
