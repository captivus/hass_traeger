#!/usr/bin/env python3
"""Check the structure of payload data in the database."""

import sqlite3
import json
from datetime import datetime, timedelta
import pytz

# Database path
DB_PATH = "data/traeger_data.db"
TIMEZONE = "America/Chicago"

def check_payload_structure():
    """Check the structure of payload data."""
    conn = sqlite3.connect(DB_PATH)
    
    # Get today's date
    local_tz = pytz.timezone(TIMEZONE)
    today = datetime.now(local_tz).date()
    start_time = local_tz.localize(datetime.combine(today, datetime.min.time()))
    start_utc = start_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    
    # Get a few sample payloads from today
    query = """
    SELECT timestamp, payload
    FROM raw_messages
    WHERE timestamp >= ?
    ORDER BY timestamp
    LIMIT 10
    """
    
    cursor = conn.cursor()
    cursor.execute(query, (start_utc,))
    rows = cursor.fetchall()
    
    print(f"Examining {len(rows)} sample payloads from today...")
    print("-" * 80)
    
    for i, (timestamp, payload_str) in enumerate(rows):
        print(f"\nPayload {i+1} at {timestamp}:")
        try:
            payload = json.loads(payload_str)
            
            # Pretty print the structure
            print(json.dumps(payload, indent=2))
            
            # Look for probe data in different possible locations
            if 'status' in payload:
                status = payload['status']
                print("\nStatus keys:", list(status.keys()))
                
                # Check for probe data
                for key in ['probe', 'probes', 'probe0', 'probe1']:
                    if key in status:
                        print(f"\nFound '{key}' in status:")
                        print(json.dumps(status[key], indent=2))
            
            print("-" * 80)
            
            if i >= 2:  # Just show first 3 for brevity
                break
                
        except Exception as e:
            print(f"Error parsing payload: {e}")
    
    conn.close()

if __name__ == "__main__":
    check_payload_structure()