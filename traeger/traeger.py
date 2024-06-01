"""
Library to interact with traeger grills

Copyright 2020 by Keith Baker All rights reserved.
This file is part of the traeger python library,
and is released under the "GNU GENERAL PUBLIC LICENSE Version 2".
Please see the LICENSE file that should have been included as part of this package.
"""

import asyncio
import datetime
import json
import logging
import socket
import ssl
import threading
import time
import traceback
import urllib
import uuid

import aiohttp
import async_timeout
import paho.mqtt.client as mqtt
import requests

CLIENT_ID = "2fuohjtqv1e63dckp5v84rau0j"
TIMEOUT = 60


_LOGGER: logging.Logger = logging.getLogger(__package__)


class Traeger:
    def __init__(self, username, password, request_library=requests):
        self.username = username
        self.password = password
        self.mqtt_uuid = str(uuid.uuid1())
        self.mqtt_thread_running = False
        self.mqtt_thread_refreshing = False
        self.grills = []
        self.grill_status = {}
        self.grills_active = False
        self.loop = asyncio.get_event_loop()
        self.task = None
        self.mqtt_url = None
        self.mqtt_client = None
        self.grill_status = {}
        self.access_token = None
        self.token = None
        self.refresh_token_value = None  # Initialize here
        self.token_expires = 0
        self.mqtt_url_expires = time.time()
        self.request = request_library
        if request_library == aiohttp.ClientSession:
            self.session = aiohttp.ClientSession()
        else:
            self.session = None
        self.grill_callbacks = {}
        self.mqtt_client_inloop = False
        self.autodisconnect = False

    async def initialize(self):
        await self.do_cognito()

    def token_remaining(self):
        return self.token_expires - time.time()

    async def do_cognito(self):
        t = datetime.datetime.utcnow()
        amzdate = t.strftime("%Y%m%dT%H%M%SZ")
        response = await self.api_wrapper(
            "post",
            "https://cognito-idp.us-west-2.amazonaws.com/",
            data={
                "ClientMetadata": {},
                "AuthParameters": {
                    "PASSWORD": self.password,
                    "USERNAME": self.username,
                },
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": CLIENT_ID,
            },
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Date": amzdate,
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            },
        )
        if response and 'AuthenticationResult' in response:
            self.token = response['AuthenticationResult']['IdToken']
            self.refresh_token_value = response['AuthenticationResult'].get('RefreshToken')
            self.token_expires = time.time() + response['AuthenticationResult']['ExpiresIn']
            _LOGGER.info('Initial token obtained successfully.')
        else:
            _LOGGER.error("Failed to authenticate with Cognito: %s", response)
            raise Exception("Initial authentication failed")

    async def refresh_token(self):
        if self.token_remaining() < 60:
            if not self.refresh_token_value:
                _LOGGER.error("Cannot refresh token: REFRESH_TOKEN is missing")
                return

            url = 'https://cognito-idp.us-west-2.amazonaws.com/'
            data = {
                'ClientId': CLIENT_ID,
                'AuthFlow': 'REFRESH_TOKEN_AUTH',
                'AuthParameters': {
                    'REFRESH_TOKEN': self.refresh_token_value  # Use renamed attribute
                }
            }
            headers = {
                'Content-Type': 'application/x-amz-json-1.1',
                'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth'
            }

            try:
                async with self.session.post(url, json=data, headers=headers) as response:
                    _LOGGER.debug(f"Response status: {response.status}")
                    _LOGGER.debug(f"Response headers: {response.headers}")
                    response_text = await response.text()
                    _LOGGER.debug(f"Response text: {response_text}")

                    if response.status == 200 and response.headers['Content-Type'] == 'application/x-amz-json-1.1':
                        response_data = json.loads(response_text)
                        if 'AuthenticationResult' in response_data:
                            self.token = response_data['AuthenticationResult']['IdToken']
                            self.refresh_token_value = response_data['AuthenticationResult'].get('RefreshToken', self.refresh_token_value)
                            self.token_expires = time.time() + response_data['AuthenticationResult']['ExpiresIn']
                            _LOGGER.info('Token refreshed successfully.')
                        else:
                            raise Exception('Failed to refresh token: AuthenticationResult not found in response')
                    else:
                        raise Exception(f'Unexpected response: {response.status} {response_text}')
            except Exception as e:
                _LOGGER.error(f'Error refreshing token: {e}')

    async def get_user_data(self):
        await self.refresh_token()
        user_data = await self.api_wrapper(
            "get",
            "https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/users/self",
            headers={"authorization": self.token},
        )
        if user_data is None:
            _LOGGER.error("Failed to get user data.")
        return user_data


    async def send_command(self, thingName, command):
        _LOGGER.debug("Send Command Topic: %s, Send Command: %s", thingName, command)
        await self.refresh_token()
        await self.api_wrapper(
            "post_raw",
            "https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/things/{}/commands".format(
                thingName
            ),
            data={"command": command},
            headers={
                "Authorization": self.token,
                "Content-Type": "application/json",
                "Accept-Language": "en-us",
                "User-Agent": "Traeger/11 CFNetwork/1209 Darwin/20.2.0",
            },
        )

    async def update_state(self, thingName):
        await self.send_command(thingName, "90")

    async def set_temperature(self, thingName, temp):
        await self.send_command(thingName, "11,{}".format(temp))

    async def set_probe_temperature(self, thingName, temp):
        await self.send_command(thingName, "14,{}".format(temp))

    async def set_switch(self, thingName, switchval):
        await self.send_command(thingName, str(switchval))

    async def shutdown_grill(self, thingName):
        await self.send_command(thingName, "17")

    async def set_timer_sec(self, thingName, time_s):
        await self.send_command(thingName, "12,{}".format(time_s))

    async def update_grills(self):
        json_data = await self.get_user_data()
        if json_data and "things" in json_data:
            self.grills = json_data["things"]
        else:
            _LOGGER.error("Failed to get grills: %s", json_data)
            self.grills = []  # Default to an empty list if the response is invalid


    async def get_grills(self):
        await self.update_grills()
        return self.grills

    # def get_grills(self):
    #     return self.grills

    def set_callback_for_grill(self, grill_id, callback):
        if grill_id not in self.grill_callbacks:
            self.grill_callbacks[grill_id] = []
        self.grill_callbacks[grill_id].append(callback)

    def mqtt_url_remaining(self):
        return self.mqtt_url_expires - time.time()

    async def refresh_mqtt_url(self):
        await self.refresh_token()
        if self.mqtt_url_remaining() < 60:
            try:
                mqtt_request_time = time.time()
                json = await self.api_wrapper(
                    "post",
                    "https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/mqtt-connections",
                    headers={"Authorization": self.token},
                )
                self.mqtt_url_expires = json["expirationSeconds"] + mqtt_request_time
                self.mqtt_url = json["signedUrl"]
            except KeyError as exception:
                _LOGGER.error(
                    "Key Error Failed to Parse MQTT URL %s - %s",
                    json,
                    exception,
                )
            except Exception as exception:
                _LOGGER.error(
                    "Other Error Failed to Parse MQTT URL %s - %s",
                    json,
                    exception,
                )
        _LOGGER.debug(f"MQTT URL:{self.mqtt_url} Expires @:{self.mqtt_url_expires}")

    def _mqtt_connect_func(self):
        if self.mqtt_client != None:
            _LOGGER.debug(f"Start MQTT Loop Forever")
            while self.mqtt_thread_running:
                self.mqtt_client_inloop = True
                self.mqtt_client.loop_forever()
                self.mqtt_client_inloop = False
                while (
                    self.mqtt_url_remaining() < 60 or self.mqtt_thread_refreshing
                ) and self.mqtt_thread_running:
                    time.sleep(1)
        _LOGGER.debug(f"Should be the end of the thread.")

    def on_connect(self, client, userdata, flags, rc):
        print(f"Connected with result code {rc}")
        for grill in self.grills:
            topic = f"prod/thing/update/{grill['thingName']}"
            client.subscribe((topic, 1))

    def on_disconnect(self, client, userdata, rc):
        print(f"Disconnected with result code {rc}")

    def on_message(self, client, userdata, msg):
        print(f"Received message: {msg.topic} {msg.payload}")
        try:
            payload = json.loads(msg.payload)
            thing_name = payload.get("thingName")
            if thing_name:
                self.grill_status[thing_name] = payload
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON: {e}")

    async def get_grill_status(self, timeout=10):
        await self.get_grills()  # Fetch grills from the API
        client = await self.get_mqtt_client()
        for grill in self.grills:
            if grill["thingName"] in self.grill_status:
                del self.grill_status[grill["thingName"]]
            client.subscribe(("prod/thing/update/{}".format(grill["thingName"]), 1))
        for grill in self.grills:
            remaining = timeout
            while not grill["thingName"] in self.grill_status and remaining > 0:
                await asyncio.sleep(1)
                remaining -= 1
        return self.grill_status

    # async def get_grill_status(self, timeout=10):
    #     await self.get_grills()  # Fetch grills from the API
    #     client = await self.get_mqtt_client()
    #     for grill in self.grills:
    #         if grill["thingName"] in self.grill_status:
    #             del self.grill_status[grill["thingName"]]
    #         client.subscribe(("prod/thing/update/{}".format(grill["thingName"]), 1))
    #     for grill in self.grills:
    #         remaining = timeout
    #         while not grill["thingName"] in self.grill_status and remaining > 0:
    #             await asyncio.sleep(1)
    #             remaining -= 1
    #     return self.grill_status
    
    # async def get_grill_status(self, timeout=10):
    #     client = await self.get_mqtt_client()
    #     for grill in self.grills:
    #         if grill["thingName"] in self.grill_status:
    #             del self.grill_status[grill["thingName"]]
    #         client.subscribe(("prod/thing/update/{}".format(grill["thingName"]), 1))
    #     for grill in self.grills:
    #         remaining = timeout
    #         while not grill["thingName"] in self.grill_status and remaining > 0:
    #             time.sleep(1)
    #             remaining -= 1
    #     return self.grill_status

    
    async def get_mqtt_client(self):
        await self.refresh_mqtt_url()
        if self.mqtt_client is not None:
            _LOGGER.debug("ReInit Client")
        else:
            self.mqtt_client = mqtt.Client(transport="websockets")
            self.mqtt_client.on_connect = self.mqtt_onconnect
            self.mqtt_client.on_connect_fail = self.mqtt_onconnectfail
            self.mqtt_client.on_subscribe = self.mqtt_onsubscribe
            self.mqtt_client.on_message = self.mqtt_onmessage

            if _LOGGER.level <= 10:  # Add these callbacks only if our logging is Debug or less.
                self.mqtt_client.enable_logger(_LOGGER)
                self.mqtt_client.on_publish = self.mqtt_onpublish  # We don't publish to MQTT
                self.mqtt_client.on_unsubscribe = self.mqtt_onunsubscribe
                self.mqtt_client.on_disconnect = self.mqtt_ondisconnect
                self.mqtt_client.on_socket_open = self.mqtt_onsocketopen
                self.mqtt_client.on_socket_close = self.mqtt_onsocketclose
                self.mqtt_client.on_socket_register_write = self.mqtt_onsocketregisterwrite
                self.mqtt_client.on_socket_unregister_write = self.mqtt_onsocketunregisterwrite

            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self.mqtt_client.tls_set_context(context)
            self.mqtt_client.reconnect_delay_set(min_delay=10, max_delay=160)
            
        mqtt_parts = urllib.parse.urlparse(self.mqtt_url)
        headers = {
            "Host": mqtt_parts.netloc,
        }
        path = "{}?{}".format(mqtt_parts.path, mqtt_parts.query)
        self.mqtt_client.ws_set_options(path=path, headers=headers)
        
        _LOGGER.info(f"Thread Active Count: {threading.active_count()}")
        try:
            _LOGGER.debug(f"Connecting to {mqtt_parts.netloc} on port 443 with path {path}...")
            self.mqtt_client.connect(mqtt_parts.netloc, 443, keepalive=300)
            _LOGGER.debug(f"Connection successful! Connected to {mqtt_parts.netloc} on port 443.")
        except Exception as e:
            _LOGGER.error(f"Connection Failed: {e}")

        if not self.mqtt_thread_running:
            self.mqtt_thread = threading.Thread(target=self._mqtt_connect_func)
            self.mqtt_thread_running = True
            self.mqtt_thread.start()
        
        return self.mqtt_client

    def mqtt_onconnect(self, client, userdata, flags, rc):
        _LOGGER.info("Grill Connected")
        for grill in self.grills:
            grill_id = grill["thingName"]
            if grill_id in self.grill_status:
                del self.grill_status[grill_id]
            client.subscribe(("prod/thing/update/{}".format(grill_id), 1))

    def mqtt_onconnectfail(self, client, userdata):
        _LOGGER.warning("Grill Connect Failed! MQTT Client Kill.")
        asyncio.run(self.kill())  # Shutdown if we aren't getting anywhere.

    def mqtt_onsubscribe(self, client, userdata, mid, granted_qos):
        for grill in self.grills:
            grill_id = grill["thingName"]
            if grill_id in self.grill_status:
                del self.grill_status[grill_id]
            asyncio.run(self.update_state(grill_id))

    def mqtt_onmessage(self, client, userdata, message):
        _LOGGER.debug(
            "grill_message: message.topic = %s, message.payload = %s",
            message.topic,
            message.payload,
        )
        _LOGGER.info(
            f"Token Time Remaining:{self.token_remaining()} MQTT Time Remaining:{self.mqtt_url_remaining()}"
        )
        if message.topic.startswith("prod/thing/update/"):
            grill_id = message.topic[len("prod/thing/update/") :]
            self.grill_status[grill_id] = json.loads(message.payload)
            if grill_id in self.grill_callbacks:
                for callback in self.grill_callbacks[grill_id]:
                    callback()
            if self.grills_active == False:  # Go see if any grills are doing work.
                for grill in self.grills:  # If nobody is working next MQTT refresh
                    grill_id = grill["thingName"]  # It'll call kill.
                    state = self.get_state_for_device(grill_id)
                    if state is None:
                        return
                    if state["connected"]:
                        if 4 <= state["system_status"] <= 8:
                            self.grills_active = True

    def mqtt_onpublish(self, client, userdata, mid):
        _LOGGER.debug(f"OnPublish Callback. Client: {client} userdata: {userdata} mid: {mid}")

    def mqtt_onunsubscribe(self, client, userdata, mid):
        _LOGGER.debug(f"OnUnsubscribe Callback. Client: {client} userdata: {userdata} mid: {mid}")

    def mqtt_ondisconnect(self, client, userdata, rc):
        _LOGGER.debug(f"OnDisconnect Callback. Client: {client} userdata: {userdata} rc: {rc}")

    def mqtt_onsocketopen(self, client, userdata, sock):
        _LOGGER.debug(f"Sock.Open.Report...Client: {client} UserData: {userdata} Sock: {sock}")

    def mqtt_onsocketclose(self, client, userdata, sock):
        _LOGGER.debug(f"Sock.Clse.Report...Client: {client} UserData: {userdata} Sock: {sock}")

    def mqtt_onsocketregisterwrite(self, client, userdata, sock):
        _LOGGER.debug(f"Sock.Regi.Write...Client: {client} UserData: {userdata} Sock: {sock}")

    def mqtt_onsocketunregisterwrite(self, client, userdata, sock):
        _LOGGER.debug(f"Sock.UnRg.Write...Client: {client} UserData: {userdata} Sock: {sock}")

    def get_state_for_device(self, thingName):
        if thingName not in self.grill_status:
            return None
        return self.grill_status[thingName]["status"]

    def get_details_for_device(self, thingName):
        if thingName not in self.grill_status:
            return None
        return self.grill_status[thingName]["details"]

    def get_limits_for_device(self, thingName):
        if thingName not in self.grill_status:
            return None
        return self.grill_status[thingName]["limits"]

    def get_settings_for_device(self, thingName):
        if thingName not in self.grill_status:
            return None
        return self.grill_status[thingName]["settings"]

    def get_features_for_device(self, thingName):
        if thingName not in self.grill_status:
            return None
        return self.grill_status[thingName]["features"]

    def get_cloudconnect(self, thingName):
        if thingName not in self.grill_status:
            return False
        return self.mqtt_thread_running

    def get_units_for_device(self, thingName):
        state = self.get_state_for_device(thingName)
        if state is None:
            return "°F"
        if state["units"] == 0:
            return "°C"
        else:
            return "°F"

    def get_details_for_accessory(self, thingName, accessory_id):
        state = self.get_state_for_device(thingName)
        if state is None:
            return None
        for accessory in state["acc"]:
            if accessory["uuid"] == accessory_id:
                return accessory
        return None

    def grill_connect(self, client, userdata, flags, rc):
        pass

    def grill_message(self, client, userdata, message):
        if message.topic.startswith("prod/thing/update/"):
            grill_id = message.topic[len("prod/thing/update/") :]
            self.grill_status[grill_id] = json.loads(message.payload)

    async def start(self, delay):
        await self.update_grills()
        self.grills_active = True
        _LOGGER.info(f"Call_Later in: {delay} seconds.")
        self.task = self.loop.call_later(delay, self.syncmain)

    def syncmain(self):
        _LOGGER.debug(f"@Call_Later SyncMain CreatingTask for async Main.")
        asyncio.create_task(self.main())

    async def main(self):
        _LOGGER.debug(f"Current Main Loop Time: {time.time()}")
        _LOGGER.debug(
            f"MQTT Logger Token Time Remaining:{self.token_remaining()} MQTT Time Remaining:{self.mqtt_url_remaining()}"
        )
        if self.mqtt_url_remaining() < 60:
            self.mqtt_thread_refreshing = True
            if self.mqtt_thread_running:
                self.mqtt_client.disconnect()
                self.mqtt_client = None
            await self.get_mqtt_client()
            self.mqtt_thread_refreshing = False
        _LOGGER.debug(f"Call_Later @: {self.mqtt_url_expires}")
        delay = self.mqtt_url_remaining()
        if delay < 30:
            delay = 30
        self.task = self.loop.call_later(delay, self.syncmain)

    async def kill(self):
        if self.mqtt_thread_running:
            _LOGGER.info(f"Killing Task")
            _LOGGER.debug(f"Task Info: {self.task}")
            self.task.cancel()
            _LOGGER.debug(
                f"Task Info: {self.task} TaskCancelled Status: {self.task.cancelled()}"
            )
            self.task = None
            self.mqtt_thread_running = False
            self.mqtt_client.disconnect()
            while self.mqtt_client_inloop:  # Wait for disconnect to finish
                await asyncio.sleep(0.25)
            self.mqtt_url_expires = time.time()
            for (
                grill
            ) in self.grills:  # Mark the grill(s) disconnected so they report unavail.
                grill_id = grill["thingName"]  # Also hit the callbacks to update HA
                self.grill_status[grill_id]["status"]["connected"] = False
                for callback in self.grill_callbacks[grill_id]:
                    callback()
        else:
            _LOGGER.info(f"Task Already Dead")

    async def api_wrapper(self, method: str, url: str, data: dict = {}, headers: dict = {}) -> dict:
        """Get information from the API."""
        _LOGGER.debug(f"Making {method} request to {url} with data {data} and headers {headers}")
        try:
            if aiohttp.ClientSession:
                async with async_timeout.timeout(TIMEOUT):
                    if method == "get":
                        async with self.session.get(url, headers=headers) as response:
                            if response.status == 200:
                                data = await response.read()
                                _LOGGER.debug(f"Received response: {data}")
                                return json.loads(data)
                            else:
                                _LOGGER.error(f"Error response {response.status} from {url}")
                                return None

                    if method == "post_raw":
                        async with self.session.post(url, headers=headers, json=data):
                            return {}  # Handle post_raw response if needed

                    elif method == "post":
                        async with self.session.post(url, headers=headers, json=data) as response:
                            if response.status == 200:
                                data = await response.read()
                                _LOGGER.debug(f"Received response: {data}")
                                return json.loads(data)
                            else:
                                _LOGGER.error(f"Error response {response.status} from {url}")
                                return None

        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, TypeError, Exception) as exception:
            _LOGGER.error("Error fetching information from %s - %s", url, exception)
            return None


    # async def api_wrapper(self, method: str, url: str, data: dict = {}, headers: dict = {}) -> dict:
    #     """Get information from the API."""
    #     _LOGGER.debug(f"Making {method} request to {url} with data {data} and headers {headers}")
    #     try:
    #         if self.request == aiohttp.ClientSession:
    #             async with async_timeout.timeout(TIMEOUT):
    #                 if method == "get":
    #                     async with self.session.get(url, headers=headers) as response:
    #                         data = await response.read()
    #                         _LOGGER.debug(f"Received response: {data}")
    #                         return json.loads(data)

    #                 if method == "post_raw":
    #                     async with self.session.post(url, headers=headers, json=data):
    #                         return {}  # Handle post_raw response if needed

    #                 elif method == "post":
    #                     async with self.session.post(url, headers=headers, json=data) as response:
    #                         data = await response.read()
    #                         _LOGGER.debug(f"Received response: {data}")
    #                         return json.loads(data)

    #         else:  # Handling requests library
    #             if method == "get":
    #                 response = self.request.get(url, headers=headers, timeout=TIMEOUT)
    #                 response.raise_for_status()
    #                 _LOGGER.debug(f"Received response: {response.text}")
    #                 return response.json()

    #             elif method == "post_raw":
    #                 self.request.post(url, headers=headers, json=data, timeout=TIMEOUT)
    #                 return {}  # Handle post_raw response if needed

    #             elif method == "post":
    #                 response = self.request.post(url, headers=headers, json=data, timeout=TIMEOUT)
    #                 response.raise_for_status()
    #                 _LOGGER.debug(f"Received response: {response.text}")
    #                 return response.json()

    #     except requests.RequestException as exception:
    #         _LOGGER.error("Error fetching information from %s - %s", url, exception)

    #     except asyncio.TimeoutError as exception:
    #         _LOGGER.error("Timeout error fetching information from %s - %s", url, exception)

    #     except (KeyError, TypeError) as exception:
    #         _LOGGER.error("Error parsing information from %s - %s\n%s", url, exception, traceback.format_exc())

    #     except (aiohttp.ClientError, socket.gaierror) as exception:
    #         _LOGGER.error("Error fetching information from %s - %s", url, exception)

    #     except Exception as exception:  # pylint: disable=broad-except
    #         _LOGGER.error("Something really wrong happened! - %s", exception)

    async def close(self):
        if self.session:
            await self.session.close()
        _LOGGER.debug("Session closed")
