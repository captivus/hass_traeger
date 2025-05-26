"""Test probe data from Traeger."""

import asyncio
import os
import json
from dotenv import load_dotenv
from traeger_client import TraegerClient

load_dotenv()

async def test():
    username = os.getenv("TRAEGER_USERNAME")
    password = os.getenv("TRAEGER_PASSWORD")
    
    if not username or not password:
        print("ERROR: Missing credentials")
        return
        
    client = TraegerClient(username, password)
    
    try:
        print("Connecting...")
        await client.connect()
        print("Connected successfully!")
        
        # Wait for some status updates
        print("\nWaiting for status updates...")
        await asyncio.sleep(5)
        
        # Get all status data
        all_status = client.get_all_status()
        
        for thing_name, status in all_status.items():
            print(f"\n=== Grill: {status.friendly_name} ({thing_name}) ===")
            print(f"State: {status.state.name}")
            print(f"Grill Temp: {status.grill_temperature}°F")
            
            # Show raw status data
            print("\nRaw status data:")
            print(json.dumps(status.raw_status, indent=2))
            
            # Check probe data specifically
            print(f"\nProbes found: {len(status.probes)}")
            for i, probe in enumerate(status.probes):
                print(f"\nProbe {i+1}:")
                print(f"  ID: {probe.id}")
                print(f"  Name: {probe.name}")
                print(f"  Temperature: {probe.temperature}")
                print(f"  Target: {probe.target_temperature}")
                print(f"  Connected: {probe.is_connected}")
                
            # Check accessories in raw data
            if "status" in status.raw_status and "acc" in status.raw_status["status"]:
                print(f"\nRaw accessories data:")
                for acc in status.raw_status["status"]["acc"]:
                    print(f"  Accessory: {json.dumps(acc, indent=4)}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test())