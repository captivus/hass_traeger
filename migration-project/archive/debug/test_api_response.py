import requests
import json

# Test what the API returns for current data
try:
    # Get current data
    resp = requests.get('http://localhost:5000/api/current')
    current = resp.json()
    print("=== CURRENT API RESPONSE ===")
    print(json.dumps(current, indent=2))
    
    # Get history for last hour
    resp = requests.get('http://localhost:5000/api/history/1')
    history = resp.json()
    
    print("\n=== HISTORY API RESPONSE (last 3 messages) ===")
    for i, msg in enumerate(history[-3:]):
        print(f"\nMessage {i+1}:")
        print(f"  Timestamp: {msg.get('timestamp')}")
        print(f"  Grill: {msg.get('grill_temp')}°F")
        print(f"  Probes: {msg.get('probes')}")
        
except Exception as e:
    print(f"Error: {e}")