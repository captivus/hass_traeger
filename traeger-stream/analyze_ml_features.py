#!/usr/bin/env python3
"""Analyze available features for ML-based temperature prediction."""

import sqlite3
import pandas as pd
import json
import numpy as np
from datetime import datetime, timedelta
import pytz
import matplotlib.pyplot as plt
import seaborn as sns

# Database path
DB_PATH = "data/traeger_data.db"
TIMEZONE = "America/Chicago"

def extract_all_features():
    """Extract all available features from the database."""
    conn = sqlite3.connect(DB_PATH)
    
    # Get all data from the last week
    local_tz = pytz.timezone(TIMEZONE)
    end_time = datetime.now(local_tz)
    start_time = end_time - timedelta(days=7)
    
    start_utc = start_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    end_utc = end_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    
    query = """
    SELECT timestamp, payload
    FROM raw_messages
    WHERE timestamp >= ? AND timestamp < ?
    ORDER BY timestamp
    """
    
    df = pd.read_sql_query(query, conn, params=(start_utc, end_utc))
    conn.close()
    
    print(f"Found {len(df)} messages from last 7 days")
    
    # Extract all features
    features = []
    for _, row in df.iterrows():
        try:
            payload = json.loads(row['payload'])
            status = payload.get('status', {})
            
            # Only process if probe is connected
            if status.get('probe_con', 0) == 1 and status.get('probe', 0) > 0:
                timestamp = pd.to_datetime(row['timestamp']).tz_localize('UTC').tz_convert(TIMEZONE)
                
                feature_dict = {
                    'timestamp': timestamp,
                    # Probe features
                    'probe_temp': status.get('probe', 0),
                    'probe_target': status.get('probe_set', 0),
                    
                    # Grill features
                    'grill_temp': status.get('grill', 0),
                    'grill_set': status.get('set', 0),
                    'grill_mode': status.get('grill_mode', 0),
                    
                    # Environmental
                    'ambient_temp': status.get('ambient', 0),
                    
                    # Control features
                    'smoke_mode': status.get('smoke', 0),
                    'keepwarm': status.get('keepwarm', 0),
                    
                    # System state
                    'system_status': status.get('system_status', 0),
                    'errors': status.get('errors', 0),
                    
                    # Cook info
                    'cook_id': status.get('cook_id', ''),
                    'in_custom': status.get('in_custom', 0),
                    
                    # Additional accessories
                    'acc_count': len(status.get('acc', [])),
                }
                
                # Extract pellet level if available
                feature_dict['pellet_level'] = status.get('pellet_level', -1)
                
                features.append(feature_dict)
                
        except Exception as e:
            continue
    
    features_df = pd.DataFrame(features)
    print(f"Extracted {len(features_df)} data points with probe readings")
    
    return features_df

def analyze_feature_correlations(df):
    """Analyze correlations between features and temperature change rate."""
    # Calculate temperature change rate
    df = df.sort_values('timestamp')
    df['probe_temp_delta'] = df['probe_temp'].diff()
    df['time_delta'] = df['timestamp'].diff().dt.total_seconds() / 60  # minutes
    df['probe_rate'] = df['probe_temp_delta'] / df['time_delta']
    
    # Calculate temperature differentials
    df['grill_probe_diff'] = df['grill_temp'] - df['probe_temp']
    df['grill_set_diff'] = df['grill_set'] - df['grill_temp']
    df['probe_target_diff'] = df['probe_target'] - df['probe_temp']
    
    # Clean up infinite/NaN values
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=['probe_rate'])
    
    # Filter out unrealistic rates
    df = df[(df['probe_rate'] > -10) & (df['probe_rate'] < 10)]
    
    # Select numeric features for correlation
    numeric_features = [
        'probe_temp', 'grill_temp', 'grill_set', 'ambient_temp',
        'grill_probe_diff', 'grill_set_diff', 'probe_target_diff',
        'smoke_mode', 'probe_rate'
    ]
    
    # Calculate correlations
    corr_matrix = df[numeric_features].corr()
    
    # Plot correlation heatmap
    plt.figure(figsize=(10, 8))
    sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0, 
                square=True, linewidths=1, cbar_kws={"shrink": .8})
    plt.title('Feature Correlations with Temperature Change Rate')
    plt.tight_layout()
    plt.savefig('feature_correlations.png')
    print("Saved correlation heatmap to feature_correlations.png")
    
    # Print top correlations with probe_rate
    probe_rate_corr = corr_matrix['probe_rate'].sort_values(ascending=False)
    print("\nTop correlations with probe temperature rate:")
    for feature, corr in probe_rate_corr.items():
        if feature != 'probe_rate':
            print(f"{feature:20s}: {corr:6.3f}")
    
    return df, corr_matrix

def analyze_cooking_patterns(df):
    """Analyze different cooking patterns based on grill settings."""
    # Group by grill temperature settings
    df['grill_temp_range'] = pd.cut(df['grill_set'], 
                                     bins=[0, 200, 250, 300, 350, 400, 500],
                                     labels=['<200', '200-250', '250-300', '300-350', '350-400', '400+'])
    
    # Calculate average probe rate by grill temp range
    avg_rates = df.groupby('grill_temp_range')['probe_rate'].agg(['mean', 'std', 'count'])
    print("\nAverage probe temperature rate by grill setting:")
    print(avg_rates)
    
    # Analyze impact of temperature differential
    plt.figure(figsize=(10, 6))
    scatter = plt.scatter(df['grill_probe_diff'], df['probe_rate'], 
                         c=df['grill_set'], cmap='hot', alpha=0.5)
    plt.xlabel('Grill-Probe Temperature Difference (°F)')
    plt.ylabel('Probe Temperature Rate (°F/min)')
    plt.title('Temperature Rate vs Temperature Differential')
    plt.colorbar(scatter, label='Grill Set Temp (°F)')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('temp_differential_impact.png')
    print("Saved temperature differential analysis to temp_differential_impact.png")

def main():
    # Extract features
    print("Extracting features from database...")
    df = extract_all_features()
    
    if df.empty:
        print("No data found")
        return
    
    # Save raw features
    df.to_csv('ml_features_raw.csv', index=False)
    print(f"Saved {len(df)} raw feature records to ml_features_raw.csv")
    
    # Analyze correlations
    print("\nAnalyzing feature correlations...")
    df_analyzed, corr_matrix = analyze_feature_correlations(df)
    
    # Analyze cooking patterns
    print("\nAnalyzing cooking patterns...")
    analyze_cooking_patterns(df_analyzed)
    
    # Feature statistics
    print("\n=== Feature Statistics ===")
    feature_cols = ['probe_temp', 'grill_temp', 'grill_set', 'ambient_temp', 
                    'grill_probe_diff', 'probe_rate']
    print(df_analyzed[feature_cols].describe())
    
    # Save analyzed features
    df_analyzed.to_csv('ml_features_analyzed.csv', index=False)
    print(f"\nSaved {len(df_analyzed)} analyzed records to ml_features_analyzed.csv")

if __name__ == "__main__":
    main()