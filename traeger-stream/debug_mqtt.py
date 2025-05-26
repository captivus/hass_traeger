"""Debug script to test MQTT connection and message flow."""

import asyncio
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

from traeger_client import TraegerClient
from traeger_client.models import GrillCommand

# Enable detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Load environment
load_dotenv()

async def test_mqtt_connection():
    """Test MQTT connection and message reception."""
    username = os.getenv("TRAEGER_USERNAME")
    password = os.getenv("TRAEGER_PASSWORD")
    
    if not username or not password:
        print("ERROR: Please set TRAEGER_USERNAME and TRAEGER_PASSWORD")
        return
        
    print(f"Starting test at {datetime.now()}")
    print(f"Username: {username}")
    print("-" * 50)
    
    # Create client
    client = TraegerClient(username, password, enable_storage=False)
    
    # Track received messages
    messages_received = []
    
    def on_status_update(status):
        """Callback for status updates."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{timestamp}] RECEIVED STATUS UPDATE:")
        print(f"  Grill: {status.friendly_name} ({status.thing_name})")
        print(f"  State: {status.state.name}")
        print(f"  Grill Temp: {status.grill_temperature}°F")
        print(f"  Set Temp: {status.grill_set_temperature}°F")
        print(f"  Connected: {status.connected}")
        print(f"  Fan Speed: {status.fan_speed}%")
        messages_received.append(status)
        
    # Register callback
    client.add_status_callback(on_status_update)
    
    try:
        # Connect
        print("\nConnecting to Traeger services...")
        await client.connect()
        print("✓ Connected successfully")
        
        # List grills
        grills = client.list_grills()
        print(f"\nFound {len(grills)} grill(s):")
        for grill in grills:
            print(f"  - {grill['friendly_name']} ({grill['thing_name']})")
            
        # Check MQTT connection
        print(f"\nMQTT Connected: {client._mqtt_connected}")
        print(f"MQTT URL expires at: {datetime.fromtimestamp(client.mqtt_url_expires)}")
        
        # Request status updates
        print("\nRequesting status updates...")
        for grill in grills:
            cmd = GrillCommand.update_status(grill['thing_name'])
            print(f"  Sending update request to {grill['friendly_name']}...")
            await client.send_command(cmd)
            
        # Wait for messages
        print("\nWaiting for messages (60 seconds)...")
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < 60:
            await asyncio.sleep(1)
            
            # Print progress
            elapsed = (datetime.now() - start_time).seconds
            if elapsed % 10 == 0:
                print(f"  {elapsed}s elapsed, {len(messages_received)} messages received")
                
            # Send another update request every 20 seconds
            if elapsed % 20 == 0 and elapsed > 0:
                print("  Sending another status request...")
                for grill in grills:
                    cmd = GrillCommand.update_status(grill['thing_name'])
                    await client.send_command(cmd)
                    
        # Summary
        print("\n" + "=" * 50)
        print(f"TEST COMPLETE - Received {len(messages_received)} messages")
        
        if not messages_received:
            print("\nNO MESSAGES RECEIVED - Possible issues:")
            print("  1. MQTT connection failed")
            print("  2. Subscription topics incorrect")
            print("  3. Grill is offline")
            print("  4. Authentication/permission issues")
        else:
            print("\nMessage summary:")
            for i, msg in enumerate(messages_received):
                print(f"  {i+1}. {msg.friendly_name} - {msg.state.name} - {msg.grill_temperature}°F")
                
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await client.disconnect()
        print("\nDisconnected")


if __name__ == "__main__":
    asyncio.run(test_mqtt_connection())