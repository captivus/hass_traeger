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
            
            # Convert timestamp to local time
            timestamp = pd.to_datetime(row['timestamp']).tz_localize('UTC').tz_convert(TIMEZONE)
            
            # Method 1: Check the simple probe fields
            if 'probe' in status and 'probe_set' in status:
                if status.get('probe_con', 0) == 1:  # Probe connected
                    data_point = {
                        'timestamp': timestamp,
                        'temperature': status['probe'],
                        'target': status['probe_set'],
                        'alarm_fired': status.get('probe_alarm_fired', 0),
                        'grill_temp': status.get('grill'),
                        'grill_set': status.get('set'),
                        'ambient': status.get('ambient')
                    }
                    probe_data.append(data_point)
            
            # Method 2: Also check acc array for more detailed probe info
            acc_list = status.get('acc', [])
            for acc in acc_list:
                if acc.get('type') == 'probe' and acc.get('con') == 1:
                    probe_info = acc.get('probe', {})
                    if 'get_temp' in probe_info:
                        # This might be more detailed, but let's stick with method 1 for consistency
                        pass
                        
        except Exception as e:
            continue
    
    probe_df = pd.DataFrame(probe_data)
    print(f"Extracted {len(probe_df)} probe data points")
    
    return probe_df

def find_165_cook_session(probe_df):
    """Find the cook session where target was 165°F."""
    # Filter for 165°F target
    target_165 = probe_df[probe_df['target'] == 165].copy()
    
    if target_165.empty:
        print("No data found with 165°F target")
        return None
    
    # Find continuous sessions (gaps > 5 minutes indicate new session)
    target_165 = target_165.sort_values('timestamp')
    target_165['time_diff'] = target_165['timestamp'].diff()
    target_165['new_session'] = target_165['time_diff'] > pd.Timedelta(minutes=5)
    target_165['session_id'] = target_165['new_session'].cumsum()
    
    # Find the longest session
    session_lengths = target_165.groupby('session_id').agg({
        'timestamp': ['min', 'max', 'count'],
        'temperature': ['min', 'max']
    })
    
    print("\n165°F cook sessions found:")
    for session_id, data in session_lengths.iterrows():
        duration = (data[('timestamp', 'max')] - data[('timestamp', 'min')]).total_seconds() / 60
        print(f"Session {session_id}: {duration:.1f} minutes, "
              f"{data[('temperature', 'min')]}°F to {data[('temperature', 'max')]}°F, "
              f"{data[('timestamp', 'count')]} data points")
    
    # Get the longest session
    longest_session_id = session_lengths[('timestamp', 'count')].idxmax()
    session_data = target_165[target_165['session_id'] == longest_session_id].copy()
    
    return session_data

def analyze_temperature_curve(session_data):
    """Analyze the temperature curve and calculate derivatives."""
    # Sort by timestamp and reset index
    session_data = session_data.sort_values('timestamp').reset_index(drop=True)
    
    # Calculate time in minutes from start
    start_time = session_data['timestamp'].iloc[0]
    session_data['minutes'] = (session_data['timestamp'] - start_time).dt.total_seconds() / 60
    
    # Calculate first derivative (rate of change)
    # Use rolling window for smoother derivative
    window = 5
    session_data['temp_smooth'] = session_data['temperature'].rolling(window, center=True).mean()
    session_data['time_delta'] = session_data['minutes'].diff()
    session_data['temp_delta'] = session_data['temp_smooth'].diff()
    session_data['temp_rate'] = session_data['temp_delta'] / session_data['time_delta']
    
    # Calculate second derivative (acceleration)
    session_data['rate_delta'] = session_data['temp_rate'].diff()
    session_data['temp_accel'] = session_data['rate_delta'] / session_data['time_delta']
    
    # Clean up NaN values
    session_data = session_data.dropna(subset=['temp_rate', 'temp_accel'])
    
    return session_data

def create_analysis_plots(session_data):
    """Create comprehensive analysis plots."""
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    
    # Plot 1: Temperature vs Time
    ax1 = axes[0]
    ax1.plot(session_data['minutes'], session_data['temperature'], 'b-', label='Actual Temp', alpha=0.5)
    ax1.plot(session_data['minutes'], session_data['temp_smooth'], 'r-', label='Smoothed Temp', linewidth=2)
    ax1.axhline(y=165, color='g', linestyle='--', label='Target (165°F)')
    ax1.set_xlabel('Time (minutes)')
    ax1.set_ylabel('Temperature (°F)')
    ax1.set_title('Temperature Curve')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: First Derivative (Rate)
    ax2 = axes[1]
    ax2.plot(session_data['minutes'], session_data['temp_rate'], 'g-', label='Temp Rate')
    ax2.axhline(y=0, color='k', linestyle='-', alpha=0.3)
    ax2.set_xlabel('Time (minutes)')
    ax2.set_ylabel('Rate (°F/min)')
    ax2.set_title('Temperature Rate (First Derivative)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Second Derivative (Acceleration)
    ax3 = axes[2]
    ax3.plot(session_data['minutes'], session_data['temp_accel'], 'm-', label='Temp Acceleration')
    ax3.axhline(y=0, color='k', linestyle='-', alpha=0.3)
    ax3.set_xlabel('Time (minutes)')
    ax3.set_ylabel('Acceleration (°F/min²)')
    ax3.set_title('Temperature Acceleration (Second Derivative)')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('temperature_analysis.png', dpi=150)
    print("Saved analysis plots to temperature_analysis.png")
    
    # Create a zoomed plot of the approach to target
    fig2, ax = plt.subplots(figsize=(10, 6))
    
    # Focus on last 30 minutes before reaching target
    target_reached_idx = session_data[session_data['temperature'] >= 165].index[0] if any(session_data['temperature'] >= 165) else len(session_data)-1
    start_idx = max(0, target_reached_idx - 30)  # 30 data points before
    
    zoom_data = session_data.iloc[start_idx:target_reached_idx+5]
    
    ax.plot(zoom_data['minutes'], zoom_data['temperature'], 'b-', marker='o', label='Temperature')
    ax.axhline(y=165, color='r', linestyle='--', label='Target')
    
    # Add rate annotations
    for i in range(0, len(zoom_data), 5):
        if i < len(zoom_data):
            rate = zoom_data.iloc[i]['temp_rate']
            ax.annotate(f'{rate:.2f}°F/min', 
                       xy=(zoom_data.iloc[i]['minutes'], zoom_data.iloc[i]['temperature']),
                       xytext=(5, 5), textcoords='offset points', fontsize=8)
    
    ax.set_xlabel('Time (minutes)')
    ax.set_ylabel('Temperature (°F)')
    ax.set_title('Final Approach to Target Temperature')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('final_approach.png', dpi=150)
    print("Saved final approach plot to final_approach.png")

def analyze_prediction_accuracy(session_data):
    """Analyze how accurate predictions would be at different points."""
    results = []
    
    # For each point in the cook, predict time to target
    target_temp = 165
    
    for i in range(20, len(session_data) - 1):  # Start after 20 points for stability
        current = session_data.iloc[i]
        current_temp = current['temperature']
        current_rate = current['temp_rate']
        current_accel = current['temp_accel']
        current_time = current['minutes']
        
        if current_temp >= target_temp:
            continue
            
        # Simple linear prediction
        if current_rate > 0:
            linear_prediction = (target_temp - current_temp) / current_rate
        else:
            linear_prediction = np.inf
        
        # Quadratic prediction (considering acceleration)
        # Using kinematic equation: d = vt + 0.5at²
        # target_temp - current_temp = current_rate * t + 0.5 * current_accel * t²
        if current_accel != 0:
            # Quadratic formula
            a = 0.5 * current_accel
            b = current_rate
            c = -(target_temp - current_temp)
            discriminant = b**2 - 4*a*c
            
            if discriminant >= 0:
                t1 = (-b + np.sqrt(discriminant)) / (2*a)
                t2 = (-b - np.sqrt(discriminant)) / (2*a)
                # Take the positive, smaller value
                quad_prediction = min(t for t in [t1, t2] if t > 0) if any(t > 0 for t in [t1, t2]) else np.inf
            else:
                quad_prediction = np.inf
        else:
            quad_prediction = linear_prediction
        
        # Find actual time to target
        future_data = session_data[session_data['minutes'] > current_time]
        target_reached = future_data[future_data['temperature'] >= target_temp]
        
        if not target_reached.empty:
            actual_time = target_reached.iloc[0]['minutes'] - current_time
        else:
            actual_time = np.inf
        
        results.append({
            'time': current_time,
            'temp': current_temp,
            'rate': current_rate,
            'accel': current_accel,
            'linear_pred': linear_prediction,
            'quad_pred': quad_prediction,
            'actual': actual_time,
            'linear_error': abs(linear_prediction - actual_time) if actual_time != np.inf else np.inf,
            'quad_error': abs(quad_prediction - actual_time) if actual_time != np.inf else np.inf
        })
    
    results_df = pd.DataFrame(results)
    results_df = results_df[results_df['actual'] != np.inf]  # Only keep predictions where we know the outcome
    
    return results_df

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
    
    # Find 165°F cook session
    session_data = find_165_cook_session(probe_df)
    if session_data is None:
        print("No 165°F cook session found")
        return
    
    # Analyze temperature curve
    print("\nAnalyzing temperature curve...")
    analyzed_data = analyze_temperature_curve(session_data)
    
    # Save the analyzed data
    analyzed_data.to_csv('analyzed_165_cook.csv', index=False)
    print(f"Saved analyzed data to analyzed_165_cook.csv")
    
    # Create analysis plots
    create_analysis_plots(analyzed_data)
    
    # Analyze prediction accuracy
    print("\nAnalyzing prediction accuracy...")
    predictions_df = analyze_prediction_accuracy(analyzed_data)
    
    if not predictions_df.empty:
        # Calculate statistics
        print("\nPrediction accuracy statistics:")
        print(f"Linear prediction mean error: {predictions_df['linear_error'].mean():.1f} minutes")
        print(f"Quadratic prediction mean error: {predictions_df['quad_error'].mean():.1f} minutes")
        
        # Plot prediction errors over time
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(predictions_df['time'], predictions_df['linear_error'], 'b-', label='Linear Error')
        ax.plot(predictions_df['time'], predictions_df['quad_error'], 'r-', label='Quadratic Error')
        ax.set_xlabel('Time (minutes)')
        ax.set_ylabel('Prediction Error (minutes)')
        ax.set_title('Prediction Error vs Time')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig('prediction_errors.png')
        print("Saved prediction error plot to prediction_errors.png")
        
        predictions_df.to_csv('prediction_analysis.csv', index=False)
        print("Saved prediction analysis to prediction_analysis.csv")
    
    # Summary statistics
    print("\n=== Cook Summary ===")
    print(f"Total duration: {analyzed_data['minutes'].max():.1f} minutes")
    print(f"Starting temperature: {analyzed_data['temperature'].iloc[0]:.1f}°F")
    print(f"Final temperature: {analyzed_data['temperature'].iloc[-1]:.1f}°F")
    print(f"Average rate: {analyzed_data['temp_rate'].mean():.2f}°F/min")
    print(f"Max rate: {analyzed_data['temp_rate'].max():.2f}°F/min")
    print(f"Average acceleration: {analyzed_data['temp_accel'].mean():.3f}°F/min²")

if __name__ == "__main__":
    main()