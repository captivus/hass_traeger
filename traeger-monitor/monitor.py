#!/usr/bin/env python3
"""Ultra-simple Traeger monitor - collects MQTT data and saves to SQLite."""

import os
import json
import time
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

import boto3
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
CLIENT_ID = "2fuohjtqv1e63dckp5v84rau0j"
DB_PATH = Path("data/traeger.db")


class TraegerMonitor:
    """Simple monitor that saves MQTT messages to SQLite."""
    
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.token = None
        self.mqtt_client = None
        self.grills = []
        self.running = True
        self.mqtt_connected = False
        
        # Ensure data directory exists
        DB_PATH.parent.mkdir(exist_ok=True)
        
        # Initialize database
        self._init_db()
        
    def _init_db(self):
        """Initialize SQLite database."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    state_index INTEGER
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON raw_messages(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON raw_messages(topic)")
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_topic_state 
                ON raw_messages(topic, state_index)
                WHERE state_index IS NOT NULL
            """)
            conn.commit()
        logger.info(f"Database initialized at {DB_PATH}")
        
    def authenticate(self):
        """Authenticate with AWS Cognito."""
        import requests
        
        data = {
            "ClientMetadata": {},
            "AuthParameters": {
                "PASSWORD": self.password,
                "USERNAME": self.username,
            },
            "AuthFlow": "USER_PASSWORD_AUTH",
            "ClientId": CLIENT_ID,
        }
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
        }
        
        response = requests.post(
            "https://cognito-idp.us-west-2.amazonaws.com/",
            json=data,
            headers=headers
        )
        result = response.json()
        
        if "AuthenticationResult" in result:
            auth = result["AuthenticationResult"]
            self.token = auth["IdToken"]
            self.token_expires = time.time() + auth["ExpiresIn"]
            logger.info("Authentication successful")
        else:
            raise Exception(f"Authentication failed: {result}")
            
    def _discover_grills(self):
        """Discover available grills."""
        import requests
        
        headers = {"authorization": self.token}
        response = requests.get(
            "https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/users/self",
            headers=headers
        )
        data = response.json()
        
        self.grills = data.get("things", [])
        logger.info(f"Found {len(self.grills)} grills")
        for grill in self.grills:
            logger.info(f"  - {grill.get('friendlyName', 'Unknown')} ({grill['thingName']})")
            
    def _get_mqtt_url(self):
        """Get MQTT WebSocket URL."""
        import requests
        
        headers = {"Authorization": self.token}
        response = requests.post(
            "https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/mqtt-connections",
            headers=headers
        )
        data = response.json()
        return data["signedUrl"]
        
    def connect_mqtt(self):
        """Connect to MQTT broker."""
        import ssl
        from urllib.parse import urlparse
        
        # Discover grills first
        self._discover_grills()
        
        # Get MQTT URL
        mqtt_url = self._get_mqtt_url()
        
        # Create MQTT client
        self.mqtt_client = mqtt.Client(transport="websockets")
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        
        # Configure TLS
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_default_certs()
        self.mqtt_client.tls_set_context(context)
        
        # Parse WebSocket URL
        parts = urlparse(mqtt_url)
        headers = {"Host": parts.netloc}
        path = f"{parts.path}?{parts.query}"
        self.mqtt_client.ws_set_options(path=path, headers=headers)
        
        # Connect
        self.mqtt_client.connect(parts.netloc, 443, keepalive=300)
        self.mqtt_client.loop_start()
        
        # Wait for connection
        for _ in range(10):
            if self.mqtt_connected:
                break
            time.sleep(1)
        else:
            raise Exception("MQTT connection timeout")
            
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        logger.info(f"MQTT connected: {rc}")
        self.mqtt_connected = True
        
        # Subscribe to all grills
        for grill in self.grills:
            topic = f"prod/thing/update/{grill['thingName']}"
            client.subscribe(topic)
            logger.info(f"Subscribed to topic: {topic}")
            
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """Handle MQTT disconnection."""
        logger.warning(f"MQTT disconnected: {rc}")
        
    def _on_mqtt_message(self, client, userdata, message):
        """Handle MQTT messages - just save to database."""
        try:
            payload = message.payload.decode()
            data = json.loads(payload)
            
            # Extract state index for deduplication
            state_index = data.get("stateIndex")
            
            # Save to database
            with sqlite3.connect(DB_PATH) as conn:
                try:
                    conn.execute(
                        """INSERT INTO raw_messages (topic, payload, state_index) 
                           VALUES (?, ?, ?)""",
                        (message.topic, payload, state_index)
                    )
                    conn.commit()
                    logger.info(f"Saved message: {message.topic} (state_index: {state_index})")
                except sqlite3.IntegrityError:
                    # Duplicate state_index - skip
                    logger.debug(f"Skipped duplicate: {message.topic} (state_index: {state_index})")
                    
        except Exception as e:
            logger.error(f"Error processing message: {e}")
        
    def run(self):
        """Main run loop."""
        logger.info("Starting Traeger Monitor")
        
        # Authenticate
        self.authenticate()
        
        # Connect to MQTT
        self.connect_mqtt()
        
        # Keep running
        while self.running:
            time.sleep(1)
            

def main():
    """Main entry point."""
    username = os.getenv("TRAEGER_USERNAME")
    password = os.getenv("TRAEGER_PASSWORD")
    
    if not username or not password:
        logger.error("Missing TRAEGER_USERNAME or TRAEGER_PASSWORD environment variables")
        return
        
    monitor = TraegerMonitor(username, password)
    
    try:
        monitor.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        monitor.running = False


if __name__ == "__main__":
    main()