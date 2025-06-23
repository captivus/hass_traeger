import sqlite3
from datetime import datetime, timedelta

# Debug why API is returning 0 records
conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

# Simulate API cutoff calculation
hours = 12
cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
print(f"Current time: {datetime.now().isoformat()}")
print(f"API cutoff for {hours} hours: {cutoff}")

# Check what records exist around this time
cursor.execute("""
    SELECT 
        timestamp,
        json_extract(payload, '$.status.cook_id') as cook_id,
        json_extract(payload, '$.status.grill') as grill_temp
    FROM raw_messages 
    ORDER BY timestamp DESC 
    LIMIT 10
""")

print(f"\nMost recent records in DB:")
for ts, cook_id, grill_temp in cursor.fetchall():
    print(f"  {ts} - {cook_id or '[No cook ID]'} - Grill: {grill_temp}°F")

# Test the API query directly
print(f"\nTesting API query: WHERE timestamp > '{cutoff}'")
cursor.execute("""
    SELECT COUNT(*)
    FROM raw_messages 
    WHERE timestamp > ?
""", (cutoff,))
api_count = cursor.fetchone()[0]
print(f"Records found by API query: {api_count}")

# Check timestamp formats
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
print(f"  Total: {total:,}")

# The issue might be that all timestamps are older than the cutoff
# Let's check timestamps vs cutoff
if latest < cutoff:
    print(f"\n❌ PROBLEM FOUND: Latest timestamp ({latest}) is older than cutoff ({cutoff})")
    print("This means ALL data is outside the time window!")
else:
    print(f"\n✅ Latest timestamp ({latest}) is newer than cutoff ({cutoff})")

conn.close()