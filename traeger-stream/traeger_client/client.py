"""Clean Traeger client for streaming grill data."""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Callable, Dict, Any
from urllib.parse import urlparse

import aiohttp
import paho.mqtt.client as mqtt
import ssl

from .models import GrillStatus, ProbeData, GrillState, GrillCommand
from .storage import DataStorage
from .xgboost_temperature_predictor import XGBoostTemperaturePredictor

logger = logging.getLogger(__name__)

CLIENT_ID = "2fuohjtqv1e63dckp5v84rau0j"
TIMEOUT = 60


class TraegerClient:
    """Clean async client for Traeger grills."""
    
    def __init__(self, username: str, password: str, enable_storage: bool = True, db_path: Optional[str] = None):
        self.username = username
        self.password = password
        
        # Authentication
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires = 0
        
        # MQTT
        self.mqtt_url: Optional[str] = None
        self.mqtt_url_expires = 0
        self.mqtt_client: Optional[mqtt.Client] = None
        self._mqtt_connected = False
        self.mqtt_thread_refreshing = False
        
        # Session
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Grills
        self.grills: List[Dict[str, Any]] = []
        self._grill_status: Dict[str, GrillStatus] = {}
        
        # Callbacks
        self._status_callbacks: List[Callable[[GrillStatus], None]] = []
        
        # Storage
        self.enable_storage = enable_storage
        self.storage: Optional[DataStorage] = None
        if enable_storage:
            self.storage = DataStorage(Path(db_path) if db_path else None)
            logger.info(f"Storage enabled with database: {self.storage.db_path}")
            
        # Temperature predictor
        self.predictor = XGBoostTemperaturePredictor(storage=self.storage if enable_storage else None)
            
        
    async def connect(self):
        """Connect to Traeger services."""
        self.session = aiohttp.ClientSession()
        await self._authenticate()
        await self._discover_grills()
        await self._connect_mqtt()
        
    async def disconnect(self):
        """Disconnect from services."""
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        if self.session:
            await self.session.close()
            
    async def _authenticate(self):
        """Authenticate with AWS Cognito."""
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
        
        async with self.session.post(
            "https://cognito-idp.us-west-2.amazonaws.com/",
            json=data,
            headers=headers
        ) as resp:
            result = await resp.json(content_type=None)
            
        if "AuthenticationResult" in result:
            auth = result["AuthenticationResult"]
            self.token = auth["IdToken"]
            self.refresh_token = auth.get("RefreshToken")
            self.token_expires = time.time() + auth["ExpiresIn"]
            logger.info("Authentication successful")
        else:
            raise Exception(f"Authentication failed: {result}")
            
    async def _refresh_auth(self):
        """Refresh authentication token if needed."""
        if time.time() > self.token_expires - 60:
            data = {
                "ClientId": CLIENT_ID,
                "AuthFlow": "REFRESH_TOKEN_AUTH",
                "AuthParameters": {
                    "REFRESH_TOKEN": self.refresh_token
                }
            }
            headers = {
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth"
            }
            
            async with self.session.post(
                "https://cognito-idp.us-west-2.amazonaws.com/",
                json=data,
                headers=headers
            ) as resp:
                result = await resp.json(content_type=None)
                
            if "AuthenticationResult" in result:
                auth = result["AuthenticationResult"]
                self.token = auth["IdToken"]
                self.refresh_token = auth.get("RefreshToken", self.refresh_token)
                self.token_expires = time.time() + auth["ExpiresIn"]
                logger.info("Token refreshed")
                
    async def _discover_grills(self):
        """Discover available grills."""
        await self._refresh_auth()
        
        headers = {"authorization": self.token}
        async with self.session.get(
            "https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/users/self",
            headers=headers
        ) as resp:
            data = await resp.json(content_type=None)
            
        self.grills = data.get("things", [])
        logger.info(f"Discovered {len(self.grills)} grills")
        
    async def _get_mqtt_url(self):
        """Get MQTT WebSocket URL."""
        if time.time() > self.mqtt_url_expires - 60:
            await self._refresh_auth()
            
            headers = {"Authorization": self.token}
            async with self.session.post(
                "https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/mqtt-connections",
                headers=headers
            ) as resp:
                data = await resp.json(content_type=None)
                
            self.mqtt_url = data["signedUrl"]
            self.mqtt_url_expires = data["expirationSeconds"] + time.time()
            logger.info("MQTT URL refreshed")
            
    async def _connect_mqtt(self):
        """Connect to MQTT broker."""
        await self._get_mqtt_url()
        
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
        parts = urlparse(self.mqtt_url)
        headers = {"Host": parts.netloc}
        path = f"{parts.path}?{parts.query}"
        self.mqtt_client.ws_set_options(path=path, headers=headers)
        
        # Connect
        self.mqtt_client.connect(parts.netloc, 443, keepalive=300)
        self.mqtt_client.loop_start()
        
        # Wait for connection
        for _ in range(10):
            if self._mqtt_connected:
                break
            await asyncio.sleep(1)
        else:
            raise Exception("MQTT connection timeout")
            
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        logger.info(f"MQTT connected: {rc}")
        self._mqtt_connected = True
        
        # Unsubscribe from all topics first to prevent duplicates
        client.unsubscribe("#")
        
        # Subscribe to all grills
        for grill in self.grills:
            topic = f"prod/thing/update/{grill['thingName']}"
            client.subscribe(topic)
            logger.info(f"Subscribed to topic: {topic}")
            
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """Handle MQTT disconnection."""
        logger.warning(f"MQTT disconnected: {rc}")
        self._mqtt_connected = False
        
    def _on_mqtt_message(self, client, userdata, message):
        """Handle MQTT messages."""
        try:
            # Parse grill ID from topic
            grill_id = message.topic.split("/")[-1]
            data = json.loads(message.payload)
            
            # Convert to GrillStatus
            status = self._parse_status(grill_id, data)
            self._grill_status[grill_id] = status
            
            # Save to database if storage is enabled
            if self.storage:
                try:
                    # Use the synchronous method directly since we're in a callback thread
                    self.storage._save_raw_message_sync(message.topic, message.payload.decode())
                    logger.info(f"Saved message to database: {message.topic} (DB: {self.storage.db_path})")
                except Exception as e:
                    logger.error(f"Error saving to database: {e}")
                    logger.exception("Full traceback:")
            
            # Notify callbacks
            for callback in self._status_callbacks:
                callback(status)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
            
    def _parse_status(self, thing_name: str, data: Dict[str, Any]) -> GrillStatus:
        """Parse raw status data into GrillStatus model."""
        status_data = data.get("status", {})
        
        # Find friendly name
        friendly_name = thing_name
        for grill in self.grills:
            if grill["thingName"] == thing_name:
                friendly_name = grill.get("friendlyName", thing_name)
                break
                
        # Map state
        state_map = {
            0: GrillState.OFFLINE,
            1: GrillState.IDLE,
            2: GrillState.STARTUP,
            3: GrillState.PREHEATING,
            4: GrillState.IGNITING,
            5: GrillState.SMOKING,
            6: GrillState.GRILLING,
            7: GrillState.COOLING,
            8: GrillState.SHUTDOWN,
        }
        state = state_map.get(status_data.get("system_status", 0), GrillState.ERROR)
        
        # Parse probes
        probes = []
        grill_temp = status_data.get("grill", 0)
        grill_set_temp = status_data.get("set", 0)
        ambient_temp = status_data.get("ambient", 70)
        cook_id = status_data.get("cook_id", "")
        
        for acc in status_data.get("acc", []):
            probe_type = acc.get("type")
            probe_id = acc.get("uuid", "")
            
            # Handle both wired probes and Bluetooth probes
            if probe_type == "probe":
                # Wired probe
                probe_data = acc.get("probe", {})
                current_temp = probe_data.get("get_temp")
                target_temp = probe_data.get("set_temp")
                channel = acc.get("channel", "")
                probe_name = f"Wired {channel.upper()}" if channel else f"Wired Probe {len(probes) + 1}"
                
                # Get prediction if temperatures are available
                predicted_time = None
                prediction_message = None
                temp_rate = None
                temp_acceleration = None
                if current_temp is not None and target_temp is not None and target_temp > 0:
                    # Get prediction
                    predicted_time, prediction_message, temp_rate, temp_acceleration = self.predictor.predict_time_to_target(
                        thing_name, cook_id, probe_id, current_temp, target_temp, 
                        grill_temp, grill_set_temp, ambient_temp
                    )
                
                probe = ProbeData(
                    id=probe_id,
                    name=probe_name,
                    temperature=current_temp,
                    target_temperature=target_temp,
                    is_connected=acc.get("con", False) == 1,
                    alarm_fired=probe_data.get("alarm_fired", 0) == 1,
                    battery_level=None,  # Wired probes don't have battery
                    ambient_temp=None,
                    predicted_time_to_target=predicted_time,
                    prediction_message=prediction_message,
                    temperature_rate=temp_rate,
                    temperature_acceleration=temp_acceleration
                )
                if predicted_time is not None:
                    print(f"DEBUG CLIENT: Probe {probe_id} has prediction: {predicted_time} minutes")
                else:
                    print(f"DEBUG CLIENT: Probe {probe_id} has NO prediction: {prediction_message}")
                probes.append(probe)
                
            elif probe_type == "btprobe":
                # Bluetooth probe
                btprobe_data = acc.get("btprobe", {})
                current_temp = btprobe_data.get("get_temp")
                target_temp = btprobe_data.get("set_temp")
                
                # Get prediction if temperatures are available
                predicted_time = None
                prediction_message = None
                temp_rate = None
                temp_acceleration = None
                if current_temp is not None and target_temp is not None and target_temp > 0:
                    # Get prediction
                    predicted_time, prediction_message, temp_rate, temp_acceleration = self.predictor.predict_time_to_target(
                        thing_name, cook_id, probe_id, current_temp, target_temp, 
                        grill_temp, grill_set_temp, ambient_temp
                    )
                
                probe = ProbeData(
                    id=probe_id,
                    name=f"BT Probe {len(probes) + 1}",
                    temperature=current_temp,
                    target_temperature=target_temp,
                    is_connected=acc.get("con", False) == 1,
                    alarm_fired=btprobe_data.get("alarm_fired", 0) == 1,
                    battery_level=btprobe_data.get("batt"),
                    ambient_temp=btprobe_data.get("ambient_temp"),
                    predicted_time_to_target=predicted_time,
                    prediction_message=prediction_message,
                    temperature_rate=temp_rate,
                    temperature_acceleration=temp_acceleration
                )
                if predicted_time is not None:
                    print(f"DEBUG CLIENT: Probe {probe_id} has prediction: {predicted_time} minutes")
                else:
                    print(f"DEBUG CLIENT: Probe {probe_id} has NO prediction: {prediction_message}")
                probes.append(probe)
                
        return GrillStatus(
            thing_name=thing_name,
            friendly_name=friendly_name,
            connected=status_data.get("connected", False),
            state=state,
            grill_temperature=status_data.get("grill"),
            set_temperature=status_data.get("set"),
            ambient_temperature=status_data.get("ambient"),
            cook_id=cook_id,
            probes=probes,
            fan_speed=status_data.get("fan_speed"),
            pellet_level=status_data.get("pellet_level"),
            cook_timer_seconds=status_data.get("cook_timer_remaining"),
            raw_status=data
        )
    
    def update_predictions(self, status: GrillStatus) -> GrillStatus:
        """Update predictions for an existing GrillStatus object."""
        # Create new probes list with updated predictions
        updated_probes = []
        
        for probe in status.probes:
            predicted_time = None
            prediction_message = None
            temp_rate = None
            temp_acceleration = None
            
            if probe.temperature is not None and probe.target_temperature is not None and probe.target_temperature > 0:
                # Get prediction - need to get cook_id from status somehow
                # For now, use grill ID as cook_id fallback
                cook_id = status.cook_id or status.thing_name
                predicted_time, prediction_message, temp_rate, temp_acceleration = self.predictor.predict_time_to_target(
                    status.thing_name, cook_id, probe.id, 
                    probe.temperature, probe.target_temperature,
                    status.grill_temperature, status.set_temperature, status.ambient_temperature
                )
            
            # Create new probe with updated predictions
            updated_probe = ProbeData(
                id=probe.id,
                name=probe.name,
                temperature=probe.temperature,
                target_temperature=probe.target_temperature,
                is_connected=probe.is_connected,
                alarm_fired=probe.alarm_fired,
                battery_level=probe.battery_level,
                ambient_temp=probe.ambient_temp,
                predicted_time_to_target=predicted_time,
                prediction_message=prediction_message,
                temperature_rate=temp_rate,
                temperature_acceleration=temp_acceleration
            )
            updated_probes.append(updated_probe)
        
        # Create new GrillStatus with updated probes
        return GrillStatus(
            thing_name=status.thing_name,
            friendly_name=status.friendly_name,
            connected=status.connected,
            state=status.state,
            grill_temperature=status.grill_temperature,
            set_temperature=status.set_temperature,
            ambient_temperature=status.ambient_temperature,
            cook_id=status.cook_id,
            probes=updated_probes,
            fan_speed=status.fan_speed,
            pellet_level=status.pellet_level,
            cook_timer_seconds=status.cook_timer_seconds,
            raw_status=status.raw_status
        )
    
    def add_status_callback(self, callback: Callable[[GrillStatus], None]):
        """Add callback for status updates."""
        self._status_callbacks.append(callback)
        
    def remove_status_callback(self, callback: Callable[[GrillStatus], None]):
        """Remove status callback."""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
            
    async def send_command(self, command: GrillCommand):
        """Send command to grill."""
        await self._refresh_auth()
        
        url = f"https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/things/{command.thing_name}/commands"
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }
        data = {"command": command.command}
        
        async with self.session.post(url, headers=headers, json=data) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Command failed: {resp.status} - {text}")
    
                
    def get_status(self, thing_name: str) -> Optional[GrillStatus]:
        """Get current status for a grill."""
        return self._grill_status.get(thing_name)
        
    def get_all_status(self) -> Dict[str, GrillStatus]:
        """Get status for all grills."""
        return self._grill_status.copy()
        
    def list_grills(self) -> List[Dict[str, str]]:
        """List available grills."""
        return [
            {
                "thing_name": g["thingName"],
                "friendly_name": g.get("friendlyName", g["thingName"])
            }
            for g in self.grills
        ]