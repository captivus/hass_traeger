import sqlite3
import json
from datetime import datetime

def analyze_database(db_path, name):
    print(f"\n=== Analyzing {name} Database: {db_path} ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"\nTables: {[t[0] for t in tables]}")
    
    # For each table, get schema and sample data
    for table in tables:
        table_name = table[0]
        print(f"\n--- Table: {table_name} ---")
        
        # Get schema
        cursor.execute(f"PRAGMA table_info({table_name})")
        schema = cursor.fetchall()
        print("Schema:")
        for col in schema:
            print(f"  {col[1]} {col[2]} {'NOT NULL' if col[3] else 'NULL'} {'PK' if col[5] else ''}")
        
        # Get row count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"\nRow count: {count}")
        
        # Get sample data
        if count > 0:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
            samples = cursor.fetchall()
            print("\nSample data (first 5 rows):")
            for i, row in enumerate(samples):
                print(f"  Row {i+1}: {row}")
    
    conn.close()

# Analyze legacy database
analyze_database("/workspaces/hass_traeger/traeger-stream/data/traeger_data.db", "Legacy")

# Analyze new database
analyze_database("/workspaces/hass_traeger/traeger-monitor/data/traeger.db", "New")