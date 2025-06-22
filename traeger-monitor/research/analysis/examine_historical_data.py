#!/usr/bin/env python3
"""Examine historical cook data from legacy Traeger Stream database."""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

db_path = Path("../traeger-stream/data/traeger_data.db")

with sqlite3.connect(db_path) as conn:
    # List cook sessions
    cursor = conn.execute("""
        SELECT json_extract(payload, '$.status.cook_id') as cook_id, 
               COUNT(*) as count,
               MIN(timestamp) as start,
               MAX(timestamp) as end
        FROM raw_messages 
        WHERE json_extract(payload, '$.status.cook_id') IS NOT NULL 
          AND json_extract(payload, '$.status.cook_id') != ''
        GROUP BY cook_id 
        ORDER BY start DESC 
        LIMIT 10
    """)
    
    print("Cook Sessions in Historical Database:")
    print("-" * 80)
    cooks = []
    for row in cursor:
        cook_id, count, start, end = row
        duration = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 3600
        cooks.append((cook_id, count, duration))
        print(f"Cook ID: {cook_id}")
        print(f"  Messages: {count}")
        print(f"  Duration: {duration:.1f} hours")
        print(f"  Start: {start}")
        print(f"  End: {end}")
        print()
    
    # Examine probe data structure for most recent cook
    if cooks:
        cook_id = cooks[0][0]
        print(f"\nExamining probe data structure for cook: {cook_id}")
        print("-" * 80)
        
        cursor = conn.execute("""
            SELECT payload 
            FROM raw_messages 
            WHERE json_extract(payload, '$.status.cook_id') = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (cook_id,))
        
        row = cursor.fetchone()
        if row:
            data = json.loads(row[0])
            status = data.get('status', {})
            
            print("\nDirect probe fields:")
            print(f"  probe: {status.get('probe')}")
            print(f"  probe_set: {status.get('probe_set')}")
            print(f"  probe_con: {status.get('probe_con')}")
            
            print("\nAcc array:")
            acc_array = status.get('acc', [])
            for i, acc in enumerate(acc_array):
                print(f"\n  Accessory {i}:")
                print(f"    type: {acc.get('type')}")
                print(f"    channel: {acc.get('channel')}")
                print(f"    con: {acc.get('con')}")
                
                if acc.get('type') == 'probe':
                    probe_data = acc.get('probe', {})
                    print(f"    probe.get_temp: {probe_data.get('get_temp')}")
                    print(f"    probe.set_temp: {probe_data.get('set_temp')}")
                elif acc.get('type') == 'btprobe':
                    probe_data = acc.get('btprobe', {})
                    print(f"    btprobe.get_temp: {probe_data.get('get_temp')}")
                    print(f"    btprobe.set_temp: {probe_data.get('set_temp')}")
                    print(f"    btprobe.batt: {probe_data.get('batt')}")