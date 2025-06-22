#!/usr/bin/env python3
"""Test pre-trained model predictions against historical data."""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from predict import predict, get_cook_data, get_probe_type

# Test configuration
HISTORICAL_DB = Path(__file__).parent.parent / "traeger-stream" / "data" / "traeger_data.db"
TARGET_DB = Path(__file__).parent / "data" / "traeger.db"

def copy_cook_to_test_db(cook_id):
    """Copy a historical cook to our test database."""
    # Create target directory if needed
    TARGET_DB.parent.mkdir(exist_ok=True)
    
    # Clear any existing data for this cook
    with sqlite3.connect(TARGET_DB) as target_conn:
        target_conn.execute("DELETE FROM raw_messages WHERE payload LIKE ?", 
                           (f'%"cook_id":"{cook_id}"%',))
    
    # Copy data from historical DB
    with sqlite3.connect(HISTORICAL_DB) as source_conn:
        rows = source_conn.execute("""
            SELECT timestamp, payload FROM raw_messages 
            WHERE payload LIKE ? ORDER BY timestamp
        """, (f'%"cook_id":"{cook_id}"%',))
        
        records = []
        for timestamp, payload in rows:
            records.append((timestamp, payload))
    
    # Insert into target DB with topic
    with sqlite3.connect(TARGET_DB) as target_conn:
        # Add topic to records
        records_with_topic = [(ts, f"prod/{cook_id}/status", payload) for ts, payload in records]
        target_conn.executemany(
            "INSERT INTO raw_messages (timestamp, topic, payload) VALUES (?, ?, ?)",
            records_with_topic
        )
    
    print(f"Copied {len(records)} messages for cook {cook_id}")

def test_early_predictions(cook_id, probe_channel):
    """Test predictions at various early stages of a cook."""
    print(f"\nTesting {cook_id} / {probe_channel}")
    
    # Get full cook data
    times, temps, targets, grill_temps = get_cook_data(cook_id, probe_channel)
    
    if not times:
        print(f"  No data found for {probe_channel}")
        return
    
    probe_type = get_probe_type(probe_channel)
    print(f"  Probe type: {probe_type}")
    print(f"  Total data points: {len(temps)}")
    print(f"  Cook duration: {(times[-1] - times[0]).total_seconds() / 60:.1f} minutes")
    print(f"  Target temp: {targets[0]}°F")
    
    # Test at different points (5, 10, 15, 20 data points)
    test_points = [5, 10, 15, 20]
    
    for n_points in test_points:
        if n_points > len(temps):
            continue
        
        # Simulate having only n_points of data
        # We need to temporarily limit the data returned by get_cook_data
        # For now, just make the prediction and note the method
        
        # Clear data cache to force reload
        from predict import DATA_CACHE
        cache_key = (cook_id, probe_channel)
        if cache_key in DATA_CACHE:
            del DATA_CACHE[cache_key]
        
        result = predict(cook_id, probe_channel)
        
        if 'error' not in result:
            elapsed = (times[n_points-1] - times[0]).total_seconds() / 60
            actual_remaining = None
            
            # Find actual time to target from point n_points
            for i in range(n_points, len(temps)):
                if temps[i] >= targets[0]:
                    actual_remaining = (times[i] - times[n_points-1]).total_seconds() / 60
                    break
            
            print(f"\n  At {n_points} points ({elapsed:.1f} min elapsed):")
            print(f"    Current temp: {temps[n_points-1]}°F")
            print(f"    Predicted: {result['minutes_to_target']} min")
            print(f"    Actual: {actual_remaining:.1f} min" if actual_remaining else "    Actual: Never reached")
            print(f"    Method: {result['method']}")
            print(f"    Message: {result['message']}")

def main():
    """Test pre-trained models on historical data."""
    # Ensure target DB exists
    TARGET_DB.parent.mkdir(exist_ok=True)
    
    if not TARGET_DB.exists():
        with sqlite3.connect(TARGET_DB) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    topic TEXT,
                    payload TEXT,
                    state_index INTEGER,
                    UNIQUE(topic, state_index)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON raw_messages(timestamp)")
    
    # Test cooks
    test_cases = [
        ("E8EB1B4C15021748620109", "legacy"),  # Legacy probe
        ("E8EB1B4C15021748620109", "p0"),      # Wired probe
        ("E8EB1B4C15021750610370", "p1"),      # Another wired probe
    ]
    
    for cook_id, probe_channel in test_cases:
        # Copy cook data to test DB
        copy_cook_to_test_db(cook_id)
        
        # Test predictions
        test_early_predictions(cook_id, probe_channel)

if __name__ == "__main__":
    main()