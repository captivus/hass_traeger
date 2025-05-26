"""Test connection to Traeger."""

import asyncio
import os
from dotenv import load_dotenv
from traeger_client import TraegerClient

load_dotenv()

async def test():
    username = os.getenv("TRAEGER_USERNAME")
    password = os.getenv("TRAEGER_PASSWORD")
    
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password) if password else 'None'}")
    
    if not username or not password:
        print("ERROR: Missing credentials")
        return
        
    client = TraegerClient(username, password)
    
    try:
        print("Connecting...")
        await client.connect()
        print("Connected successfully!")
        
        grills = client.list_grills()
        print(f"Found {len(grills)} grills:")
        for grill in grills:
            print(f"  - {grill}")
            
    except Exception as e:
        print(f"Connection failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test())