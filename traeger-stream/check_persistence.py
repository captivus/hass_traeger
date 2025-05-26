#!/usr/bin/env python3
"""Check if data persistence is working."""

import sqlite3
from pathlib import Path

# Default database location
db_path = Path("./data/traeger_data.db")

if db_path.exists():
    print(f"✅ Database found at: {db_path}")
    print(f"   Size: {db_path.stat().st_size / 1024:.1f} KB")
    
    # Connect and check tables
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check grill states
    cursor.execute("SELECT COUNT(*) FROM grill_states")
    grill_count = cursor.fetchone()[0]
    print(f"\n📊 Grill States: {grill_count} records")
    
    if grill_count > 0:
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM grill_states")
        min_time, max_time = cursor.fetchone()
        print(f"   Date range: {min_time} to {max_time}")
        
        # Show latest entry
        cursor.execute("SELECT timestamp, grill_name, grill_temperature, grill_set_temperature FROM grill_states ORDER BY timestamp DESC LIMIT 1")
        latest = cursor.fetchone()
        print(f"   Latest: {latest[0]} - {latest[1]} at {latest[2]}°F (set: {latest[3]}°F)")
    
    # Check probe data
    cursor.execute("SELECT COUNT(*) FROM probe_data")
    probe_count = cursor.fetchone()[0]
    print(f"\n🌡️  Probe Data: {probe_count} records")
    
    if probe_count > 0:
        cursor.execute("SELECT timestamp, probe_name, temperature, target_temperature FROM probe_data ORDER BY timestamp DESC LIMIT 1")
        latest = cursor.fetchone()
        print(f"   Latest: {latest[0]} - {latest[1]} at {latest[2]}°F (target: {latest[3]}°F)")
    
    # Check raw messages
    cursor.execute("SELECT COUNT(*) FROM raw_messages")
    raw_count = cursor.fetchone()[0]
    print(f"\n📨 Raw Messages: {raw_count} records")
    
    conn.close()
else:
    print(f"❌ No database found at: {db_path}")
    print("   Run the app to start collecting data!")

print("\n💡 Tips:")
print("   - The database is created automatically when you run the app")
print("   - Data is saved every time the grill sends an update (usually every few seconds)")
print("   - Check the Streamlit app sidebar for storage status")
print("   - Use the 'Historical Data' tab to view and export saved data")