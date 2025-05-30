#!/usr/bin/env python3
"""Analyze today's cook data for probe temperature prediction improvement."""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import pytz
import json
import matplotlib.pyplot as plt
import numpy as np

# Database path
DB_PATH = "data/traeger_data.db"
TIMEZONE = "America/Chicago"

def get_todays_data():
    """Extract today's cook data from the database."""
    conn = sqlite3.connect(DB_PATH)
    
    # Get timezone-aware today's date
    local_tz = pytz.timezone(TIMEZONE)
    today = datetime.now(local_tz).date()
    start_time = local_tz.localize(datetime.combine(today, datetime.min.time()))
    end_time = start_time + timedelta(days=1)
    
    # Convert to UTC for database query
    start_utc = start_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    end_utc = end_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"Querying data from {start_time} to {end_time} (local time)")
    print(f"UTC range: {start_utc} to {end_utc}")
    
    # Query the database
    query = """
    SELECT timestamp, payload
    FROM raw_messages
    WHERE timestamp >= ? AND timestamp < ?
    ORDER BY timestamp
    """
    
    df = pd.read_sql_query(query, conn, params=(start_utc, end_utc))
    conn.close()
    
    print(f"Found {len(df)} messages for today")
    return df

def extract_probe_data(df):
    """Extract probe temperature data from raw messages."""
    probe_data = []
    
    for _, row in df.iterrows():
        try:
            payload = json.loads(row['payload'])
            status = payload.get('status', {})
            
            # Look for probe data
            if 'probe' in status:
                probe_info = status['probe']
                # Convert timestamp to local time
                timestamp = pd.to_datetime(row['timestamp']).tz_localize('UTC').tz_convert(TIMEZONE)
                
                # Extract probe 0 data (main probe)
                if isinstance(probe_info, list) and len(probe_info) > 0:
                    probe0 = probe_info[0]
                    if probe0.get('con'):  # Connected
                        data_point = {
                            'timestamp': timestamp,
                            'temperature': probe0.get('temp'),
                            'target': probe0.get('set'),
                            'alarm_type': probe0.get('alarm', {}).get('type') if 'alarm' in probe0 else None
                        }
                        probe_data.append(data_point)
        except Exception as e:
            continue
    
    probe_df = pd.DataFrame(probe_data)
    print(f"Extracted {len(probe_df)} probe data points")
    
    # Remove None values
    probe_df = probe_df.dropna(subset=['temperature'])
    print(f"After removing None values: {len(probe_df)} data points")
    
    return probe_df

def find_cook_sessions(probe_df):
    """Identify distinct cook sessions based on probe target temperature."""
    sessions = []
    current_session = None
    
    for i, row in probe_df.iterrows():
        if row['target'] is not None and row['target'] > 0:
            if current_session is None or current_session['target'] != row['target']:
                # New session
                if current_session is not None:
                    sessions.append(current_session)
                current_session = {
                    'start': row['timestamp'],
                    'end': row['timestamp'],
                    'target': row['target'],
                    'start_temp': row['temperature'],
                    'end_temp': row['temperature'],
                    'data_points': 1
                }
            else:
                # Continue current session
                current_session['end'] = row['timestamp']
                current_session['end_temp'] = row['temperature']
                current_session['data_points'] += 1
    
    if current_session is not None:
        sessions.append(current_session)
    
    print(f"\nFound {len(sessions)} cook sessions:")
    for i, session in enumerate(sessions):
        duration = (session['end'] - session['start']).total_seconds() / 60
        print(f"Session {i+1}: Target={session['target']}°F, "
              f"Start={session['start_temp']}°F, End={session['end_temp']}°F, "
              f"Duration={duration:.1f} min, Points={session['data_points']}")
    
    return sessions

def main():
    # Get today's data
    df = get_todays_data()
    if df.empty:
        print("No data found for today")
        return
    
    # Extract probe data
    probe_df = extract_probe_data(df)
    if probe_df.empty:
        print("No probe data found")
        return
    
    # Find cook sessions
    sessions = find_cook_sessions(probe_df)
    
    # Look for the 165°F session
    target_session = None
    for session in sessions:
        if session['target'] == 165:
            target_session = session
            break
    
    if target_session:
        print(f"\nFound 165°F target session!")
        print(f"Duration: {(target_session['end'] - target_session['start']).total_seconds() / 60:.1f} minutes")
        print(f"Temperature range: {target_session['start_temp']}°F to {target_session['end_temp']}°F")
        
        # Extract data for this session
        session_data = probe_df[
            (probe_df['timestamp'] >= target_session['start']) &
            (probe_df['timestamp'] <= target_session['end'])
        ].copy()
        
        # Calculate time in minutes from start
        session_data['minutes'] = (session_data['timestamp'] - session_data['timestamp'].iloc[0]).dt.total_seconds() / 60
        
        # Save for further analysis
        session_data.to_csv('todays_165_cook.csv', index=False)
        print(f"\nSaved {len(session_data)} data points to todays_165_cook.csv")
        
        # Quick plot
        plt.figure(figsize=(12, 6))
        plt.plot(session_data['minutes'], session_data['temperature'], 'b-', label='Actual Temperature')
        plt.axhline(y=165, color='r', linestyle='--', label='Target (165°F)')
        plt.xlabel('Time (minutes)')
        plt.ylabel('Temperature (°F)')
        plt.title('Today\'s Cook: Temperature vs Time')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig('todays_cook_curve.png')
        print("Saved temperature curve to todays_cook_curve.png")
        
    else:
        print("\nNo 165°F target session found in today's data")
        print("Available targets:", [s['target'] for s in sessions])

if __name__ == "__main__":
    main()