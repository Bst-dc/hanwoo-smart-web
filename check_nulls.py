import sqlite3
import pandas as pd

conn = sqlite3.connect('data/consulting.db')
tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)

for t in tables['name']:
    print(f"--- Table: {t} ---")
    df = pd.read_sql_query(f'SELECT * FROM "{t}";', conn)
    missing = df.isnull().sum()
    empty_strings = (df == '').sum()
    
    total = len(df)
    print(f"Total Rows: {total}")
    for col in df.columns:
        m = missing[col]
        e = empty_strings.get(col, 0)
        if m > 0 or e > 0:
            print(f"  Column '{col}' is missing: {m} (Null/NaN) and {e} (Empty string) / {total}")
    print()
conn.close()
