#!/usr/bin/env python3
"""Test data storage functionality."""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from traeger_client import TraegerClient, DataStorage

async def test_storage():
    """Test the storage functionality."""
    # Use test database
    db_path = Path("./test_data/test_traeger.db")
    db_path.parent.mkdir(exist_ok=True)
    
    # Test direct storage
    print("Testing direct storage...")
    storage = DataStorage(db_path)
    
    # Create test grill state
    from traeger_client.models import GrillState, ProbeData
    
    test_state = GrillState(
        grill_id="TEST123",
        grill_name="Test Grill",
        is_connected=True,
        firmware_version="1.0.0",
        ambient_temperature=72.0,
        grill_temperature=225.0,
        grill_set_temperature=225.0,
        probe_temperature=165.0,
        probe_set_temperature=165.0,
        probe_alarm_fired=False,
        pellet_level=75,
        fan_level=3,
        fan_mode="auto",
        fire_state="GRILLING",
        smoke_level=5,
        wifi_signal=-45,
        probes=[
            ProbeData(
                id="probe1",
                name="Meat Probe",
                temperature=165.0,
                target_temperature=165.0,
                is_connected=True,
                alarm_fired=False,
                battery_level=85,
                ambient_temp=72.0
            )
        ],
        raw_data={"test": "data"}
    )
    
    # Save state
    await storage.save_grill_state(test_state)
    print("✓ Saved test grill state")
    
    # Save raw message
    await storage.save_raw_message("test/topic", '{"test": "message"}')
    print("✓ Saved raw message")
    
    # Query data
    states = await storage.get_grill_states(grill_id="TEST123", limit=1)
    print(f"✓ Retrieved {len(states)} grill states")
    
    probes = await storage.get_probe_data(grill_id="TEST123", limit=1)
    print(f"✓ Retrieved {len(probes)} probe records")
    
    # Test export
    export_path = Path("./test_data/export")
    grill_count, probe_count = await storage.export_to_csv(export_path, grill_id="TEST123")
    print(f"✓ Exported {grill_count} grill states and {probe_count} probe records to CSV")
    
    # Test with real client (if credentials are provided)
    username = os.getenv("TRAEGER_USERNAME")
    password = os.getenv("TRAEGER_PASSWORD")
    
    if username and password:
        print("\nTesting with real Traeger client...")
        
        # Create client with storage enabled
        client = TraegerClient(username, password, enable_storage=True, db_path="./test_data/real_traeger.db")
        
        try:
            await client.connect()
            print("✓ Connected to Traeger")
            
            grills = client.list_grills()
            print(f"✓ Found {len(grills)} grills")
            
            # Wait for some data
            print("Waiting 30 seconds for data...")
            await asyncio.sleep(30)
            
            # Check if data was saved
            if client.storage:
                latest = await client.storage.get_latest_state(grills[0]["thing_name"])
                if latest:
                    print(f"✓ Latest data saved at {latest['timestamp']}")
                else:
                    print("✗ No data saved yet")
            
        finally:
            await client.disconnect()
    else:
        print("\nSkipping real client test (no credentials in environment)")
    
    print("\nStorage test complete!")

if __name__ == "__main__":
    asyncio.run(test_storage())