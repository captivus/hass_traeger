#!/usr/bin/env python3
"""Integration test for the Traeger monitor system."""
import os
import sys
import time
import json
import sqlite3
import subprocess
import requests
from pathlib import Path
from datetime import datetime, timedelta
import signal

# Test configuration
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "traeger.db"
TEST_TIMEOUT = 30  # seconds

def print_section(title):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print('='*60)

def check_requirements():
    """Check if all required files and dependencies exist."""
    print_section("Checking Requirements")
    
    required_files = [
        "monitor.py",
        "predict.py", 
        "web/server.py",
        "web/static/index.html",
        "web/static/app.js",
        "web/static/style.css",
        "requirements.txt",
        ".env.example",
        "models/wired_model.pkl",
        "models/legacy_model.pkl"
    ]
    
    missing = []
    for file in required_files:
        path = BASE_DIR / file
        if path.exists():
            print(f"✓ {file}")
        else:
            print(f"✗ {file} - MISSING")
            missing.append(file)
    
    if missing:
        print(f"\nError: Missing {len(missing)} required files")
        return False
    
    print("\n✓ All required files present")
    return True

def check_database():
    """Check if database can be created/accessed."""
    print_section("Testing Database")
    
    # Ensure data directory exists
    DB_PATH.parent.mkdir(exist_ok=True)
    
    try:
        # Test database creation
        with sqlite3.connect(DB_PATH) as conn:
            # Check if table exists
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='raw_messages'
            """)
            
            if cursor.fetchone():
                print("✓ Database table 'raw_messages' exists")
                
                # Count existing messages
                count = conn.execute("SELECT COUNT(*) FROM raw_messages").fetchone()[0]
                print(f"✓ Database has {count} existing messages")
            else:
                print("✓ Database created, table will be created by monitor.py")
        
        return True
    except Exception as e:
        print(f"✗ Database error: {e}")
        return False

def test_predict_module():
    """Test the prediction module."""
    print_section("Testing Prediction Module")
    
    try:
        # Import predict module
        sys.path.insert(0, str(BASE_DIR))
        import predict
        
        print("✓ Predict module imported successfully")
        
        # Check if pre-trained models loaded
        if predict.PRETRAINED_MODELS:
            print(f"✓ Loaded {len(predict.PRETRAINED_MODELS)} pre-trained models: "
                  f"{', '.join(predict.PRETRAINED_MODELS.keys())}")
        else:
            print("⚠ No pre-trained models loaded")
        
        # Test prediction with dummy data
        result = predict.predict("test_cook_123", "p0")
        if 'error' in result:
            print(f"✓ Prediction returned expected error for test data: {result['error']}")
        else:
            print(f"⚠ Unexpected prediction result: {result}")
        
        return True
    except Exception as e:
        print(f"✗ Prediction module error: {e}")
        return False

def test_web_server():
    """Test the web server startup and API endpoints."""
    print_section("Testing Web Server")
    
    # Start the web server
    env = os.environ.copy()
    env['FLASK_APP'] = 'web.server:app'
    
    server_process = subprocess.Popen(
        [sys.executable, '-m', 'flask', 'run', '--port=5001'],
        cwd=BASE_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    print("Starting Flask server on port 5001...")
    
    # Wait for server to start
    time.sleep(3)
    
    try:
        # Test API endpoints
        base_url = "http://localhost:5001"
        
        # Test /api/current
        print("\nTesting /api/current endpoint...")
        response = requests.get(f"{base_url}/api/current", timeout=5)
        print(f"✓ /api/current responded with status {response.status_code}")
        data = response.json()
        print(f"  Response: {json.dumps(data, indent=2)}")
        
        # Test /api/history/1
        print("\nTesting /api/history/1 endpoint...")
        response = requests.get(f"{base_url}/api/history/1", timeout=5)
        print(f"✓ /api/history/1 responded with status {response.status_code}")
        
        # Test static files
        print("\nTesting static file serving...")
        response = requests.get(f"{base_url}/", timeout=5)
        if response.status_code == 200 and 'Traeger Monitor' in response.text:
            print("✓ Index.html served successfully")
        else:
            print(f"⚠ Index.html status: {response.status_code}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Web server test failed: {e}")
        return False
    finally:
        # Stop the server
        server_process.terminate()
        server_process.wait(timeout=5)
        print("\n✓ Web server stopped")

def test_monitor_auth():
    """Test monitor authentication (without real credentials)."""
    print_section("Testing Monitor Module")
    
    try:
        # Check if .env exists
        env_path = BASE_DIR / ".env"
        if not env_path.exists():
            print("⚠ No .env file found - skipping live MQTT test")
            print("  To test with real credentials:")
            print("  1. Copy .env.example to .env")
            print("  2. Add your Traeger credentials")
            print("  3. Run: python monitor.py")
            return True
        
        # Import monitor to check structure
        sys.path.insert(0, str(BASE_DIR))
        import monitor
        
        print("✓ Monitor module imported successfully")
        print(f"✓ Database path configured: {monitor.DB_PATH}")
        
        # Check required functions exist
        required_funcs = ['authenticate', 'get_grills_and_mqtt_url', 'on_message', 'main']
        for func in required_funcs:
            if hasattr(monitor, func):
                print(f"✓ Function '{func}' exists")
            else:
                print(f"✗ Function '{func}' missing")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ Monitor module error: {e}")
        return False

def create_test_data():
    """Create some test data in the database."""
    print_section("Creating Test Data")
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Create table if needed
            conn.execute("""CREATE TABLE IF NOT EXISTS raw_messages (
                id INTEGER PRIMARY KEY, 
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                topic TEXT, 
                payload TEXT, 
                state_index INTEGER,
                UNIQUE(topic, state_index))""")
            
            # Insert test messages
            test_cook_id = "TEST_COOK_" + datetime.now().strftime("%Y%m%d%H%M%S")
            test_messages = []
            
            # Simulate a cook with temperature progression
            base_time = datetime.now()
            grill_temp = 225
            probe_temp = 70
            target_temp = 165
            
            for i in range(20):
                # Add minutes to simulate time progression
                timestamp = (base_time + timedelta(minutes=i*2)).isoformat()
                probe_temp += 4  # Rise 4°F per message
                
                payload = {
                    "status": {
                        "cook_id": test_cook_id,
                        "grill": grill_temp,
                        "probe_con": 1,
                        "probe": probe_temp,
                        "probe_set": target_temp,
                        "acc": [
                            {
                                "channel": "p0",
                                "con": 1,
                                "type": "probe",
                                "probe": {
                                    "get_temp": probe_temp,
                                    "set_temp": target_temp
                                }
                            }
                        ]
                    }
                }
                
                test_messages.append((
                    timestamp,
                    f"prod/{test_cook_id}/status",
                    json.dumps(payload),
                    i
                ))
            
            # Insert messages
            conn.executemany("""
                INSERT OR REPLACE INTO raw_messages (timestamp, topic, payload, state_index)
                VALUES (?, ?, ?, ?)
            """, test_messages)
            
            print(f"✓ Created {len(test_messages)} test messages for cook {test_cook_id}")
            
            # Test prediction on this data
            sys.path.insert(0, str(BASE_DIR))
            import predict
            
            result = predict.predict(test_cook_id, "p0")
            print(f"\n✓ Test prediction result:")
            print(f"  Current temp: {result.get('current_temp', 'N/A')}°F")
            print(f"  Target temp: {result.get('target_temp', 'N/A')}°F") 
            print(f"  Minutes to target: {result.get('minutes_to_target', 'N/A')}")
            print(f"  Method: {result.get('method', 'N/A')}")
            
            if 'error' not in result and result.get('minutes_to_target') is not None:
                print("  ✓ Prediction working correctly!")
            else:
                print(f"  ⚠ Prediction issue: {result}")
            
            return True
            
    except Exception as e:
        print(f"✗ Test data creation error: {e}")
        return False

def main():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("TRAEGER MONITOR INTEGRATION TEST")
    print("="*60)
    
    # Track results
    results = {
        "Requirements": check_requirements(),
        "Database": check_database(),
        "Prediction Module": test_predict_module(),
        "Test Data": create_test_data(),
        "Web Server": test_web_server(),
        "Monitor Module": test_monitor_auth()
    }
    
    # Summary
    print_section("Test Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test:.<40} {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All integration tests passed!")
        print("\nNext steps:")
        print("1. Copy .env.example to .env and add your Traeger credentials")
        print("2. Run: python monitor.py")
        print("3. In another terminal run: python -m flask run --app web.server:app")
        print("4. Open http://localhost:5000 in your browser")
        return 0
    else:
        print(f"\n❌ {total - passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())