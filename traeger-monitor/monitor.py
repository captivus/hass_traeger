#!/usr/bin/env python3
"""Ultra-simple Traeger monitor - MQTT → SQLite in ~80 lines."""
import os, json, time, sqlite3, ssl, logging
from pathlib import Path
from urllib.parse import urlparse
import requests
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

CLIENT_ID = "2fuohjtqv1e63dckp5v84rau0j"
DB_PATH = Path("data/traeger.db")
DB_PATH.parent.mkdir(exist_ok=True)

# Initialize database
with sqlite3.connect(DB_PATH) as conn:
    conn.execute("""CREATE TABLE IF NOT EXISTS raw_messages (
        id INTEGER PRIMARY KEY, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        topic TEXT, payload TEXT, state_index INTEGER,
        UNIQUE(topic, state_index))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON raw_messages(timestamp)")

def authenticate(username, password):
    """Get auth token from AWS Cognito."""
    response = requests.post("https://cognito-idp.us-west-2.amazonaws.com/", 
        json={"AuthParameters": {"USERNAME": username, "PASSWORD": password},
              "AuthFlow": "USER_PASSWORD_AUTH", "ClientId": CLIENT_ID},
        headers={"Content-Type": "application/x-amz-json-1.1",
                 "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth"})
    result = response.json()
    if "AuthenticationResult" not in result:
        raise Exception(f"Auth failed: {result}")
    return result["AuthenticationResult"]["IdToken"]

def get_grills_and_mqtt_url(token):
    """Get grill list and MQTT WebSocket URL."""
    # Get grills
    response = requests.get("https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/users/self",
                          headers={"authorization": token})
    grills = response.json().get("things", [])
    # Get MQTT URL
    response = requests.post("https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/mqtt-connections",
                           headers={"Authorization": token})
    mqtt_url = response.json()["signedUrl"]
    return grills, mqtt_url

def on_message(client, userdata, message):
    """Save MQTT messages to SQLite."""
    try:
        payload = message.payload.decode()
        data = json.loads(payload)
        state_index = data.get("stateIndex")
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR IGNORE INTO raw_messages (topic, payload, state_index) VALUES (?, ?, ?)",
                        (message.topic, payload, state_index))
        logger.info(f"Saved: {message.topic} (state: {state_index})")
    except Exception as e:
        logger.error(f"Error: {e}")

def main():
    username = os.getenv("TRAEGER_USERNAME")
    password = os.getenv("TRAEGER_PASSWORD")
    if not username or not password:
        logger.error("Set TRAEGER_USERNAME and TRAEGER_PASSWORD")
        return
    
    # Authenticate and get connection info
    token = authenticate(username, password)
    grills, mqtt_url = get_grills_and_mqtt_url(token)
    logger.info(f"Found {len(grills)} grills")
    
    # Setup MQTT client
    parts = urlparse(mqtt_url)
    client = mqtt.Client(transport="websockets")
    client.on_message = on_message
    client.on_connect = lambda c, u, f, rc: [c.subscribe(f"prod/thing/update/{g['thingName']}") 
                                              for g in grills] and logger.info(f"Connected: {rc}")
    
    # Configure TLS and WebSocket
    context = ssl.create_default_context()
    client.tls_set_context(context)
    client.ws_set_options(path=f"{parts.path}?{parts.query}", headers={"Host": parts.netloc})
    
    # Connect and run
    client.connect(parts.netloc, 443, keepalive=300)
    logger.info("Starting monitor...")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")

if __name__ == "__main__":
    main()