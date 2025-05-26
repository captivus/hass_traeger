"""Analyze temperature data from Traeger grill to understand patterns for ML prediction."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def extract_probe_data(db_path: Path):
    """Extract probe temperature data from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all messages
    cursor.execute("""
        SELECT timestamp, payload 
        FROM raw_messages 
        WHERE topic LIKE '%update%'
        ORDER BY timestamp
    """)
    
    data = []
    for row in cursor.fetchall():
        timestamp_str, payload = row
        try:
            payload_data = json.loads(payload)
            status = payload_data.get('status', {})
            
            # Extract probe data
            acc = status.get('acc', [])
            for probe in acc:
                if probe.get('type') == 'btprobe':
                    probe_data = probe.get('btprobe', {})
                    data.append({
                        'timestamp': timestamp_str,
                        'channel': probe.get('channel'),
                        'temperature': probe_data.get('get_temp'),
                        'target_temperature': probe_data.get('set_temp'),
                        'ambient_temp': probe_data.get('ambient_temp'),
                        'grill_temp': status.get('grill'),
                        'grill_set_temp': status.get('set'),
                    })
        except json.JSONDecodeError:
            continue
    
    conn.close()
    return pd.DataFrame(data)


def analyze_temperature_curves(df: pd.DataFrame):
    """Analyze temperature curves to understand heating patterns."""
    # Convert timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Sort by timestamp
    df = df.sort_values('timestamp')
    
    # Calculate time deltas
    df['time_delta'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds()
    
    # Group by channel to analyze each probe separately
    for channel in df['channel'].unique():
        probe_df = df[df['channel'] == channel].copy()
        
        # Calculate temperature rate of change
        probe_df['temp_rate'] = probe_df['temperature'].diff() / probe_df['time_delta'].diff()
        
        # Find sessions where temperature is increasing towards target
        probe_df['session'] = (probe_df['time_delta'].diff() > 300).cumsum()  # New session if gap > 5 min
        
        print(f"\nAnalysis for {channel}:")
        print(f"Temperature range: {probe_df['temperature'].min():.1f} - {probe_df['temperature'].max():.1f}°F")
        print(f"Average temp rate when heating: {probe_df[probe_df['temp_rate'] > 0]['temp_rate'].mean():.2f}°F/sec")
        
        # Plot temperature curves
        plt.figure(figsize=(12, 6))
        for session in probe_df['session'].unique()[:5]:  # Plot first 5 sessions
            session_df = probe_df[probe_df['session'] == session]
            if len(session_df) > 10:  # Only plot sessions with enough data
                plt.plot(session_df['time_delta'] / 60, session_df['temperature'], 
                        label=f'Session {session}', alpha=0.7)
        
        plt.xlabel('Time (minutes)')
        plt.ylabel('Temperature (°F)')
        plt.title(f'Temperature Curves for {channel}')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(f'temp_analysis_{channel}.png')
        plt.close()
        
    return df


def extract_features_for_ml(df: pd.DataFrame):
    """Extract features for machine learning model."""
    features = []
    
    for channel in df['channel'].unique():
        probe_df = df[df['channel'] == channel].copy()
        
        # Group by cooking sessions
        probe_df['session'] = (probe_df['time_delta'].diff() > 300).cumsum()
        
        for session in probe_df['session'].unique():
            session_df = probe_df[probe_df['session'] == session]
            
            if len(session_df) < 5:  # Skip sessions with too little data
                continue
                
            # Extract features for each time point
            for i in range(1, len(session_df)):
                current = session_df.iloc[i]
                prev = session_df.iloc[i-1]
                
                # Only include data points where we're heating towards a target
                if (current['target_temperature'] is not None and 
                    current['temperature'] < current['target_temperature']):
                    
                    feature = {
                        'current_temp': current['temperature'],
                        'target_temp': current['target_temperature'],
                        'temp_diff': current['target_temperature'] - current['temperature'],
                        'grill_temp': current['grill_temp'],
                        'grill_set_temp': current['grill_set_temp'],
                        'ambient_temp': current['ambient_temp'],
                        'time_elapsed': current['time_delta'] - session_df.iloc[0]['time_delta'],
                        'temp_rate': (current['temperature'] - prev['temperature']) / 
                                   (current['time_delta'] - prev['time_delta']) if current['time_delta'] != prev['time_delta'] else 0,
                    }
                    
                    # Calculate time to target (our label)
                    # Find when temperature reaches target
                    future_df = session_df[session_df.index > current.name]
                    reached = future_df[future_df['temperature'] >= current['target_temperature']]
                    
                    if not reached.empty:
                        time_to_target = reached.iloc[0]['time_delta'] - current['time_delta']
                        feature['time_to_target'] = time_to_target
                        features.append(feature)
    
    return pd.DataFrame(features)


if __name__ == "__main__":
    db_path = Path("./data/traeger_data.db")
    
    print("Extracting probe data...")
    df = extract_probe_data(db_path)
    print(f"Found {len(df)} data points")
    
    print("\nAnalyzing temperature curves...")
    analyzed_df = analyze_temperature_curves(df)
    
    print("\nExtracting features for ML...")
    features_df = extract_features_for_ml(analyzed_df)
    print(f"Extracted {len(features_df)} feature samples")
    
    # Save features for training
    features_df.to_csv('temperature_features.csv', index=False)
    print("\nFeatures saved to temperature_features.csv")
    
    # Display feature statistics
    print("\nFeature statistics:")
    print(features_df.describe())