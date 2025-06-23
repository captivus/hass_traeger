import sqlite3
from datetime import datetime

print("=== POST-MIGRATION VALIDATION ===\n")

# Connect to new database
conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

# 1. Check total count
cursor.execute("SELECT COUNT(*) FROM raw_messages")
total_count = cursor.fetchone()[0]
print(f"1. Total message count: {total_count}")
print(f"   Expected: ~6,225 ✓" if 6200 <= total_count <= 6250 else "   Expected: ~6,225 ❌")

# 2. Check for duplicate state_indexes
cursor.execute("""
    SELECT state_index, COUNT(*) as count 
    FROM raw_messages 
    WHERE state_index IS NOT NULL 
    GROUP BY state_index 
    HAVING count > 1
""")
duplicates = cursor.fetchall()
print(f"\n2. Duplicate state_indexes: {len(duplicates)}")
print(f"   Expected: 0 {'✓' if len(duplicates) == 0 else '❌'}")
if duplicates:
    print("   First 5 duplicates:", duplicates[:5])

# 3. Check date range
cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM raw_messages")
min_date, max_date = cursor.fetchone()
print(f"\n3. Date range:")
print(f"   Earliest: {min_date}")
print(f"   Latest: {max_date}")
print(f"   Range expanded: {'✓' if '2025-05-26' in min_date else '❌'}")

# 4. Messages by date
cursor.execute("""
    SELECT DATE(timestamp) as date, COUNT(*) as count
    FROM raw_messages
    GROUP BY date
    ORDER BY date
    LIMIT 10
""")
print(f"\n4. First 10 days of data:")
for row in cursor.fetchall():
    print(f"   {row[0]}: {row[1]} messages")

# 5. Check state_index continuity
cursor.execute("""
    SELECT MIN(state_index), MAX(state_index) 
    FROM raw_messages 
    WHERE state_index IS NOT NULL
""")
min_idx, max_idx = cursor.fetchone()
print(f"\n5. State index range: {min_idx} to {max_idx}")

conn.close()
print("\n✅ Validation complete!")