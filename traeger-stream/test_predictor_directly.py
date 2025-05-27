#!/usr/bin/env python3
"""Test the predictor directly with database data."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import json

from traeger_client.storage import DataStorage
from traeger_client.simple_temperature_predictor import SimpleTemperaturePredictor
from traeger_client.client import TraegerClient

async def test_predictor():
    """Load data from database and test predictor."""
    # Initialize storage
    storage = DataStorage(Path("./data/traeger_data.db"))
    
    # Get last 24 hours of data
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)
    
    print(f"Loading data from {start_time} to {end_time}")
    
    # Fetch raw messages
    raw_messages = await storage.get_raw_messages(
        start_time=start_time,
        end_time=end_time
    )
    
    print(f"Found {len(raw_messages)} messages")
    
    # Initialize predictor
    predictor = SimpleTemperaturePredictor()
    
    # Create a client just to use its parser
    client = TraegerClient("dummy", "dummy", enable_storage=False)
    
    # Process messages and extract probe data
    probe_data = {}
    message_count = 0
    
    for msg in raw_messages:
        try:
            payload = json.loads(msg['payload'])
            if 'status' not in payload:
                continue
                
            thing_name = msg['topic'].split('/')[3]
            status = client._parse_status(thing_name, payload)
            # Parse timestamp from string
            timestamp = datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00')).timestamp()
            
            message_count += 1
            
            # Add probe readings to predictor
            for probe in status.probes:
                if probe.temperature is not None:
                    predictor.add_reading(probe.id, probe.temperature, timestamp)
                    
                    # Track probe data for analysis
                    if probe.id not in probe_data:
                        probe_data[probe.id] = {
                            'name': probe.name,
                            'readings': [],
                            'target': probe.target_temperature
                        }
                    
                    probe_data[probe.id]['readings'].append({
                        'time': datetime.fromtimestamp(timestamp),
                        'temp': probe.temperature,
                        'target': probe.target_temperature
                    })
                    
        except Exception as e:
            print(f"Error parsing message: {e}")
            continue
    
    print(f"\nProcessed {message_count} status messages")
    print(f"\nProbe data summary:")
    
    # Analyze each probe
    for probe_id, data in probe_data.items():
        readings = data['readings']
        if not readings:
            continue
            
        print(f"\n{'='*60}")
        print(f"Probe: {data['name']} (ID: {probe_id})")
        print(f"Total readings: {len(readings)}")
        
        # Get temperature range
        temps = [r['temp'] for r in readings]
        print(f"Temperature range: {min(temps):.1f}°F to {max(temps):.1f}°F")
        
        # Get current values
        current = readings[-1]
        print(f"Current temperature: {current['temp']:.1f}°F")
        print(f"Target temperature: {current['target']}°F")
        
        # Show last 10 readings
        print(f"\nLast 10 readings:")
        for r in readings[-10:]:
            print(f"  {r['time'].strftime('%H:%M:%S')}: {r['temp']:.1f}°F")
        
        # Calculate temperature change over full data period
        if len(readings) >= 2:
            first = readings[0]
            last = readings[-1]
            time_diff = (last['time'].timestamp() - first['time'].timestamp())
            temp_diff = last['temp'] - first['temp']
            rate = (temp_diff / time_diff) * 60 if time_diff > 0 else 0
            print(f"\nFull data period:")
            print(f"  First reading: {first['time'].strftime('%Y-%m-%d %H:%M:%S')} at {first['temp']:.1f}°F")
            print(f"  Last reading: {last['time'].strftime('%Y-%m-%d %H:%M:%S')} at {last['temp']:.1f}°F")
            print(f"  Duration: {time_diff/3600:.1f} hours")
            print(f"  Temperature change: {temp_diff:.1f}°F")
            print(f"  Average rate: {rate:.2f}°F/minute")
        
        # Make prediction
        if current['target'] is not None and current['temp'] < current['target']:
            print(f"\nMaking prediction...")
            
            # Show what the predictor has
            if probe_id in predictor.temp_history:
                history = predictor.temp_history[probe_id]
                print(f"Predictor has {len(history)} data points")
                if len(history) > 5:
                    print("First 5 readings in predictor:")
                    for i in range(5):
                        t, temp = history[i]
                        print(f"  {datetime.fromtimestamp(t).strftime('%H:%M:%S')}: {temp:.1f}°F")
                    print("Last 5 readings in predictor:")
                    for i in range(-5, 0):
                        t, temp = history[i]
                        print(f"  {datetime.fromtimestamp(t).strftime('%H:%M:%S')}: {temp:.1f}°F")
            
            predicted_time, message, rate, acceleration = predictor.predict_time_to_target(probe_id, current['target'])
            
            if predicted_time is not None:
                print(f"Prediction: {predicted_time:.1f} minutes to reach {current['target']}°F")
                if rate is not None:
                    print(f"Current rate: {rate:.2f}°F/minute")
                if acceleration is not None:
                    print(f"Current acceleration: {acceleration:.3f}°F/minute²")
            else:
                print(f"No prediction available: {message}")
                if rate is not None:
                    print(f"Current rate: {rate:.2f}°F/minute")
                if acceleration is not None:
                    print(f"Current acceleration: {acceleration:.3f}°F/minute²")

if __name__ == "__main__":
    asyncio.run(test_predictor())