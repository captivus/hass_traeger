import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

# Simulate what the API does
hours = 24
cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
print(f"API cutoff time: {cutoff}")
print(f"Current time: {datetime.now().isoformat()}")

# Count messages after cutoff
cursor.execute("""
    SELECT COUNT(*)
    FROM raw_messages 
    WHERE timestamp > ?
""", (cutoff,))
count = cursor.fetchone()[0]
print(f"\nMessages after cutoff: {count}")

# Check what's actually in the DB
cursor.execute("""
    SELECT 
        MIN(timestamp) as earliest,
        MAX(timestamp) as latest,
        COUNT(*) as total
    FROM raw_messages
""")
earliest, latest, total = cursor.fetchone()
print(f"\nDatabase contains:")
print(f"  Earliest: {earliest}")
print(f"  Latest: {latest}")
print(f"  Total: {total}")

# The issue might be timestamp format comparison
cursor.execute("""
    SELECT COUNT(*)
    FROM raw_messages 
    WHERE datetime(timestamp) > datetime(?)
""", (cutoff,))
count_datetime = cursor.fetchone()[0]
print(f"\nUsing datetime() comparison: {count_datetime}")

conn.close()