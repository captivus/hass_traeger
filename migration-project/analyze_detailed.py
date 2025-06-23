import sqlite3
import json
from datetime import datetime

def analyze_raw_messages(db_path, name):
    print(f"\n=== {name} Raw Messages Analysis ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if raw_messages table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_messages';")
    if not cursor.fetchone():
        print("No raw_messages table found")
        conn.close()
        return
    
    # Get schema
    cursor.execute("PRAGMA table_info(raw_messages)")
    schema = cursor.fetchall()
    print("\nSchema:")
    for col in schema:
        print(f"  {col[1]} {col[2]} {'NOT NULL' if col[3] else 'NULL'} {'PK' if col[5] else ''}")
    
    # Get statistics
    cursor.execute("SELECT COUNT(*) FROM raw_messages")
    total_count = cursor.fetchone()[0]
    print(f"\nTotal raw messages: {total_count}")
    
    # Get date range
    cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM raw_messages")
    min_date, max_date = cursor.fetchone()
    print(f"Date range: {min_date} to {max_date}")
    
    # Get unique topics
    cursor.execute("SELECT DISTINCT topic FROM raw_messages")
    topics = [row[0] for row in cursor.fetchall()]
    print(f"\nUnique topics: {topics}")
    
    # Sample recent messages
    cursor.execute("SELECT * FROM raw_messages ORDER BY timestamp DESC LIMIT 3")
    samples = cursor.fetchall()
    print("\nMost recent 3 messages:")
    for i, row in enumerate(samples):
        print(f"\n  Message {i+1}:")
        print(f"    ID: {row[0]}")
        print(f"    Timestamp: {row[1]}")
        print(f"    Topic: {row[2]}")
        print(f"    Payload length: {len(row[3])} chars")
        if len(row) > 4:
            print(f"    State Index: {row[4]}")
    
    conn.close()

# Analyze legacy database
print("="*60)
print("LEGACY DATABASE ANALYSIS")
print("="*60)
analyze_raw_messages("/workspaces/hass_traeger/traeger-stream/data/traeger_data.db", "Legacy")

# Analyze new database
print("\n" + "="*60)
print("NEW DATABASE ANALYSIS")
print("="*60)
conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print(f"\nTables in new database: {[t[0] for t in tables]}")

# Check each table
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
    print(f"Row count: {count}")
    
    if count > 0 and table_name == "raw_messages":
        # Get date range
        cursor.execute(f"SELECT MIN(timestamp), MAX(timestamp) FROM {table_name}")
        min_date, max_date = cursor.fetchone()
        print(f"Date range: {min_date} to {max_date}")

conn.close()