#!/usr/bin/env python3
"""Analyze historical cook sessions to find those with 60+ minutes AND probe data."""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

db_path = Path("../traeger-stream/data/traeger_data.db")

def has_probe_data(payload_json):
    """Check if a message contains any probe data."""
    try:
        data = json.loads(payload_json)
        status = data.get('status', {})
        
        # Check legacy probe format
        if status.get('probe_con') == 1 and status.get('probe') is not None:
            return True
            
        # Check acc array for probes
        for acc in status.get('acc', []):
            if acc.get('con') == 1 and acc.get('type') in ['probe', 'btprobe']:
                # Verify actual temperature data exists
                if acc.get('type') == 'probe':
                    if acc.get('probe', {}).get('get_temp') is not None:
                        return True
                elif acc.get('type') == 'btprobe':
                    if acc.get('btprobe', {}).get('get_temp') is not None:
                        return True
                        
        return False
    except:
        return False

with sqlite3.connect(db_path) as conn:
    # Get all cook sessions
    cursor = conn.execute("""
        SELECT json_extract(payload, '$.status.cook_id') as cook_id, 
               COUNT(*) as total_messages,
               MIN(timestamp) as start,
               MAX(timestamp) as end
        FROM raw_messages 
        WHERE json_extract(payload, '$.status.cook_id') IS NOT NULL 
          AND json_extract(payload, '$.status.cook_id') != ''
        GROUP BY cook_id 
        ORDER BY start DESC
    """)
    
    print("Analyzing cook sessions for usefulness (60+ minutes WITH probe data)...")
    print("=" * 100)
    
    useful_cooks = []
    
    for row in cursor.fetchall():
        cook_id, total_messages, start, end = row
        duration_hours = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 3600
        
        # Skip if less than 1 hour
        if duration_hours < 1.0:
            continue
            
        # Check how many messages have probe data
        probe_cursor = conn.execute("""
            SELECT payload FROM raw_messages 
            WHERE json_extract(payload, '$.status.cook_id') = ?
        """, (cook_id,))
        
        messages_with_probes = 0
        probe_channels = set()
        
        for (payload,) in probe_cursor:
            if has_probe_data(payload):
                messages_with_probes += 1
                
                # Track which probe channels we see
                try:
                    data = json.loads(payload)
                    status = data.get('status', {})
                    
                    if status.get('probe_con') == 1:
                        probe_channels.add('legacy')
                        
                    for acc in status.get('acc', []):
                        if acc.get('con') == 1 and acc.get('type') in ['probe', 'btprobe']:
                            probe_channels.add(acc.get('channel', 'unknown'))
                except:
                    pass
        
        probe_percentage = (messages_with_probes / total_messages * 100) if total_messages > 0 else 0
        
        if probe_percentage > 50:  # At least 50% of messages should have probe data
            useful_cooks.append({
                'cook_id': cook_id,
                'duration_hours': duration_hours,
                'total_messages': total_messages,
                'messages_with_probes': messages_with_probes,
                'probe_percentage': probe_percentage,
                'probe_channels': list(probe_channels),
                'start': start,
                'end': end
            })
            
    # Print results
    print(f"\nFound {len(useful_cooks)} USEFUL cook sessions (60+ minutes with probe data):\n")
    
    for i, cook in enumerate(useful_cooks, 1):
        print(f"{i}. Cook ID: {cook['cook_id']}")
        print(f"   Duration: {cook['duration_hours']:.1f} hours")
        print(f"   Messages: {cook['total_messages']} total, {cook['messages_with_probes']} with probes ({cook['probe_percentage']:.1f}%)")
        print(f"   Probe channels: {', '.join(cook['probe_channels'])}")
        print(f"   Date: {cook['start'][:10]}")
        print()
    
    print("\nSummary:")
    print(f"- Total useful cook sessions: {len(useful_cooks)}")
    print(f"- Total duration: {sum(c['duration_hours'] for c in useful_cooks):.1f} hours")
    print(f"- Total messages with probe data: {sum(c['messages_with_probes'] for c in useful_cooks):,}")
    
    # Also check for cook sessions that are long but lack probe data
    cursor = conn.execute("""
        SELECT json_extract(payload, '$.status.cook_id') as cook_id, 
               COUNT(*) as total_messages,
               MIN(timestamp) as start,
               MAX(timestamp) as end
        FROM raw_messages 
        WHERE json_extract(payload, '$.status.cook_id') IS NOT NULL 
          AND json_extract(payload, '$.status.cook_id') != ''
        GROUP BY cook_id 
        HAVING (julianday(MAX(timestamp)) - julianday(MIN(timestamp))) * 24 >= 1.0
        ORDER BY start DESC
    """)
    
    long_cooks_without_probes = []
    for row in cursor.fetchall():
        cook_id, total_messages, start, end = row
        if not any(c['cook_id'] == cook_id for c in useful_cooks):
            duration_hours = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 3600
            long_cooks_without_probes.append((cook_id, duration_hours))
    
    if long_cooks_without_probes:
        print(f"\nNote: Found {len(long_cooks_without_probes)} cook sessions 60+ minutes WITHOUT sufficient probe data:")
        for cook_id, hours in long_cooks_without_probes:
            print(f"  - {cook_id}: {hours:.1f} hours (no probes or <50% messages with probes)")