import sqlite3

def check_db():
    conn = sqlite3.connect('data/consulting.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    for t in tables:
        print(f"Table: {t[0]}")
        cursor.execute(f"PRAGMA table_info({t[0]})")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
            
if __name__ == '__main__':
    check_db()
