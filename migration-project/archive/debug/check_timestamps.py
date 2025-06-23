import sqlite3
from datetime import datetime

conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

# Check the most recent messages
cursor.execute("""
    SELECT timestamp, json_extract(payload, '$.status.cook_id') as cook_id
    FROM raw_messages 
    ORDER BY timestamp DESC
    LIMIT 10
""")

print("=== MOST RECENT MESSAGES BY TIMESTAMP ===")
for ts, cook_id in cursor.fetchall():
    print(f"{ts} - {cook_id or '[No cook ID]'}")

# Check if test timestamps are in the future
now = datetime.utcnow()
cursor.execute("""
    SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
    FROM raw_messages 
    WHERE timestamp > datetime('now')
""")
future_count, min_future, max_future = cursor.fetchone()

print(f"\n=== FUTURE TIMESTAMPS ===")
print(f"Messages with future timestamps: {future_count}")
if future_count:
    print(f"Range: {min_future} to {max_future}")

# Get the actual time range for the real cook
cursor.execute("""
    SELECT MIN(timestamp), MAX(timestamp)
    FROM raw_messages 
    WHERE json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021750610370'
""")
cook_start, cook_end = cursor.fetchone()

print(f"\n=== REAL COOK TIME RANGE ===")
print(f"Start: {cook_start}")
print(f"End: {cook_end}")

conn.close()