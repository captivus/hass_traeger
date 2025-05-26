"""Simple example of using the Traeger client."""

import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

from traeger_client import TraegerClient

load_dotenv()


async def main():
    # Get credentials
    username = os.getenv("TRAEGER_USERNAME")
    password = os.getenv("TRAEGER_PASSWORD")
    
    if not username or not password:
        print("Please set TRAEGER_USERNAME and TRAEGER_PASSWORD environment variables")
        return
        
    # Create client
    client = TraegerClient(username, password)
    
    # Define callback for status updates
    def on_status_update(status):
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {status.friendly_name}")
        print(f"  State: {status.state.name}")
        print(f"  Grill: {status.grill_temperature}°F (set: {status.grill_set_temperature}°F)")
        
        for i, probe in enumerate(status.probes):
            if probe.is_connected:
                print(f"  Probe {i+1}: {probe.temperature}°F (target: {probe.target_temperature}°F)")
                
        print(f"  Fan: {status.fan_speed}%")
        
    # Add callback
    client.add_status_callback(on_status_update)
    
    try:
        # Connect
        print("Connecting to Traeger...")
        await client.connect()
        
        # List grills
        grills = client.list_grills()
        print(f"\nFound {len(grills)} grills:")
        for grill in grills:
            print(f"  - {grill['friendly_name']} ({grill['thing_name']})")
            
        # Monitor for 5 minutes
        print("\nMonitoring... (Press Ctrl+C to stop)")
        await asyncio.sleep(300)
        
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())