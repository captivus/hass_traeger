import asyncio
import datetime
import json
import logging
import ssl
import threading
import time
import urllib
import uuid

import aiohttp
import async_timeout
import paho.mqtt.client as mqtt

CLIENT_ID = "2fuohjtqv1e63dckp5v84rau0j"
TIMEOUT = 60

_LOGGER: logging.Logger = logging.getLogger(__package__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(name)s %(levelname)s %(message)s')

class WebSocketError(Exception):
    pass

class InvalidWebSocketURLError(WebSocketError):
    pass

class Traeger:
    def __init__(self, username, password, request_library=aiohttp.ClientSession):
        self.username = username
        self.password = password
        self.mqtt_uuid = str(uuid.uuid1())
        self.mqtt_thread_running = False
        self.grills = []
        self.grill_status = {}
        self.grills_active = False
        self.loop = asyncio.get_event_loop()
        self.task = None
        self.mqtt_url = None
        self.mqtt_client = None
        self.access_token = None
        self.token = None
        self.refresh_token_value = None
        self.token_expires = 0
        self.mqtt_url_expires = time.time()
        self.request = request_library
        self.session = None
        self.grill_callbacks = {}
        self.mqtt_client_inloop = False
        self.autodisconnect = False

    async def initialize(self):
        self.session = aiohttp.ClientSession()
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
                    'REFRESH_TOKEN': self.refresh_token_value
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
        if (json_data is not None) and ("things" in json_data):
            self.grills = json_data["things"]
        else:
            _LOGGER.error("Failed to get grills: %s", json_data)
            self.grills = []

    async def get_grills(self):
        await self.update_grills()
        return self.grills

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
        if self.mqtt_client is not None:
            _LOGGER.debug(f"Start MQTT Loop Forever")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            while self.mqtt_thread_running:
                self.mqtt_client_inloop = True
                self.mqtt_client.loop_forever()
                self.mqtt_client_inloop = False
                while (
                    self.mqtt_url_remaining() < 60 or self.mqtt_thread_refreshing
                ) and self.mqtt_thread_running:
                    time.sleep(1)
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        _LOGGER.debug(f"Should be the end of the thread.")

    def mqtt_onconnect(self, client, userdata, flags, rc):
        _LOGGER.info("Connected with result code %s", rc)
        for grill in self.grills:
            topic = f"prod/thing/update/{grill['thingName']}"
            client.subscribe((topic, 1))

    def mqtt_onconnectfail(self, client, userdata):
        _LOGGER.warning("Grill Connect Failed! MQTT Client Kill.")
        loop = asyncio.get_event_loop()
        loop.create_task(self.kill())

    def mqtt_onsubscribe(self, client, userdata, mid, granted_qos):
        loop = asyncio.get_event_loop()
        for grill in self.grills:
            grill_id = grill["thingName"]
            if grill_id in self.grill_status:
                del self.grill_status[grill_id]
            loop.create_task(self.update_state(grill_id))

    def mqtt_onmessage(self, client, userdata, message):
        _LOGGER.debug(
            "grill_message: message.topic = %s, message.payload = %s",
            message.topic,
            message.payload,
        )
        _LOGGER.info(
            "Token Time Remaining:%s MQTT Time Remaining:%s",
            self.token_remaining(),
            self.mqtt_url_remaining(),
        )
        if message.topic.startswith("prod/thing/update/"):
            grill_id = message.topic[len("prod/thing/update/"):]
            self.grill_status[grill_id] = json.loads(message.payload)
            if grill_id in self.grill_callbacks:
                for callback in self.grill_callbacks[grill_id]:
                    callback()
            if not self.grills_active:
                for grill in self.grills:
                    grill_id = grill["thingName"]
                    state = self.get_state_for_device(grill_id)
                    if state is None:
                        return
                    if state["connected"]:
                        if 4 <= state["system_status"] <= 8:
                            self.grills_active = True

    def mqtt_onpublish(self, client, userdata, mid):
        _LOGGER.debug("OnPublish Callback. Client: %s userdata: %s mid: %s", client, userdata, mid)

    def mqtt_onunsubscribe(self, client, userdata, mid):
        _LOGGER.debug("OnUnsubscribe Callback. Client: %s userdata: %s mid: %s", client, userdata, mid)

    def mqtt_ondisconnect(self, client, userdata, rc):
        _LOGGER.debug("OnDisconnect Callback. Client: %s userdata: %s rc: %s", client, userdata, rc)

    def mqtt_onsocketopen(self, client, userdata, sock):
        _LOGGER.debug("Socket Open: Client: %s UserData: %s Sock: %s", client, userdata, sock)

    def mqtt_onsocketclose(self, client, userdata, sock):
        _LOGGER.debug("Socket Close: Client: %s UserData: %s Sock: %s", client, userdata, sock)

    def mqtt_onsocketregisterwrite(self, client, userdata, sock):
        _LOGGER.debug("Socket Register Write: Client: %s UserData: %s Sock: %s", client, userdata, sock)

    def mqtt_onsocketunregisterwrite(self, client, userdata, sock):
        _LOGGER.debug("Socket Unregister Write: Client: %s UserData: %s Sock: %s", client, userdata, sock)

    def get_state_for_device(self, thingName):
        if thingName not in self.grill_status:
            return None
        return self.grill_status[thingName]["status"]

    async def get_grill_status(self, timeout=10):
        await self.get_grills()
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

    async def get_mqtt_client(self):
        await self.refresh_mqtt_url()
        await self.check_websocket_url(self.mqtt_url)

        if self.mqtt_client is not None:
            _LOGGER.debug("ReInit Client")
        else:
            self.mqtt_client = mqtt.Client(transport="websockets")
            self.mqtt_client.on_connect = self.mqtt_onconnect
            self.mqtt_client.on_connect_fail = self.mqtt_onconnectfail
            self.mqtt_client.on_subscribe = self.mqtt_onsubscribe
            self.mqtt_client.on_message = self.mqtt_onmessage

            if _LOGGER.level <= logging.DEBUG:
                self.mqtt_client.enable_logger(_LOGGER)
                self.mqtt_client.on_publish = self.mqtt_onpublish
                self.mqtt_client.on_unsubscribe = self.mqtt_onunsubscribe
                self.mqtt_client.on_disconnect = self.mqtt_ondisconnect
                self.mqtt_client.on_socket_open = self.mqtt_onsocketopen
                self.mqtt_client.on_socket_close = self.mqtt_onsocketclose
                self.mqtt_client.on_socket_register_write = self.mqtt_onsocketregisterwrite
                self.mqtt_client.on_socket_unregister_write = self.mqtt_onsocketunregisterwrite

            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_default_certs()

            try:
                self.mqtt_client.tls_set_context(context)
            except Exception as e:
                _LOGGER.error("Error setting TLS context: %s", e)

            self.mqtt_client.reconnect_delay_set(min_delay=10, max_delay=160)

        mqtt_parts = urllib.parse.urlparse(self.mqtt_url)
        headers = {
            "Host": mqtt_parts.netloc,
        }
        path = "{}?{}".format(mqtt_parts.path, mqtt_parts.query)
        _LOGGER.debug("MQTT Path: %s", path)
        _LOGGER.debug("Headers: %s", headers)
        self.mqtt_client.ws_set_options(path=path, headers=headers)

        _LOGGER.info("Thread Active Count: %s", threading.active_count())

        retry_attempts = 0
        while retry_attempts < 5:
            try:
                _LOGGER.debug("Connecting to %s on port 443 with path %s...", mqtt_parts.netloc, path)
                self.mqtt_client.connect(mqtt_parts.netloc, 443, keepalive=300)
                _LOGGER.debug("Connection successful! Connected to %s on port 443.", mqtt_parts.netloc)
                break
            except Exception as e:
                retry_attempts += 1
                _LOGGER.error("Connection Failed: %s, retrying in %s seconds...", e, 2 ** retry_attempts)
                await asyncio.sleep(2 ** retry_attempts)
                if retry_attempts >= 5:
                    _LOGGER.error("Max retry attempts reached. Connection failed.")

        if not self.mqtt_thread_running:
            self.mqtt_thread = threading.Thread(target=self._mqtt_connect_func, daemon=True)
            self.mqtt_thread_running = True
            self.mqtt_thread.start()

        return self.mqtt_client

    async def check_websocket_url(self, url):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    _LOGGER.debug("Checking WebSocket URL: %s", url)
                    if response.status == 200:
                        _LOGGER.debug("WebSocket URL %s is accessible.", url)
                    else:
                        _LOGGER.error("WebSocket URL %s is not accessible. Status: %s", url, response.status)
                        _LOGGER.debug("Response Headers: %s", response.headers)
                        _LOGGER.debug("Response Text: %s", await response.text())
            except Exception as e:
                _LOGGER.error("Error checking WebSocket URL %s: %s", url, e)

    async def start(self, delay):
        await self.update_grills()
        self.grills_active = True
        _LOGGER.info("Call_Later in: %s seconds.", delay)
        self.task = self.loop.call_later(delay, self.syncmain)

    def syncmain(self):
        _LOGGER.debug("@Call_Later SyncMain CreatingTask for async Main.")
        asyncio.create_task(self.main())

    async def main(self):
        _LOGGER.debug("Current Main Loop Time: %s", time.time())
        _LOGGER.debug(
            "MQTT Logger Token Time Remaining:%s MQTT Time Remaining:%s",
            self.token_remaining(),
            self.mqtt_url_remaining(),
        )
        if self.mqtt_url_remaining() < 60:
            self.mqtt_thread_refreshing = True
            if self.mqtt_thread_running:
                self.mqtt_client.disconnect()
                self.mqtt_client = None
            await self.get_mqtt_client()
            self.mqtt_thread_refreshing = False
        _LOGGER.debug("Call_Later @: %s", self.mqtt_url_expires)
        delay = self.mqtt_url_remaining()
        if delay < 30:
            delay = 30
        self.task = self.loop.call_later(delay, self.syncmain)

    async def kill(self):
        if self.mqtt_thread_running:
            _LOGGER.info("Killing Task")
            _LOGGER.debug("Task Info: %s", self.task)
            self.task.cancel()
            _LOGGER.debug(
                "Task Info: %s TaskCancelled Status: %s", self.task, self.task.cancelled()
            )
            self.task = None
            self.mqtt_thread_running = False
            self.mqtt_client.disconnect()
            while self.mqtt_client_inloop:
                await asyncio.sleep(0.25)
            self.mqtt_url_expires = time.time()
            for grill in self.grills:
                grill_id = grill["thingName"]
                self.grill_status[grill_id]["status"]["connected"] = False
                for callback in self.grill_callbacks[grill_id]:
                    callback()
        else:
            _LOGGER.info("Task Already Dead")

    async def api_wrapper(self, method: str, url: str, data: dict = {}, headers: dict = {}) -> dict:
        _LOGGER.debug("Making %s request to %s with data %s and headers %s", method, url, data, headers)
        try:
            if aiohttp.ClientSession:
                async with async_timeout.timeout(TIMEOUT):
                    if method == "get":
                        async with self.session.get(url, headers=headers) as response:
                            if response.status == 200:
                                data = await response.read()
                                _LOGGER.debug("Received response: %s", data)
                                return json.loads(data)
                            else:
                                _LOGGER.error("Error response %s from %s", response.status, url)
                                if response.status == 404:
                                    raise InvalidWebSocketURLError("Invalid WebSocket URL")
                                return None

                    if method == "post_raw":
                        async with self.session.post(url, headers=headers, json=data) as response:
                            if response.status == 200:
                                return {}
                            else:
                                _LOGGER.error("Error response %s from %s", response.status, url)
                                if response.status == 404:
                                    raise InvalidWebSocketURLError("Invalid WebSocket URL")
                                return None

                    elif method == "post":
                        async with self.session.post(url, headers=headers, json=data) as response:
                            if response.status == 200:
                                data = await response.read()
                                _LOGGER.debug("Received response: %s", data)
                                return json.loads(data)
                            else:
                                _LOGGER.error("Error response %s from %s", response.status, url)
                                if response.status == 404:
                                    raise InvalidWebSocketURLError("Invalid WebSocket URL")
                                return None

        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, TypeError) as exception:
            _LOGGER.error("Error fetching information from %s - %s", url, exception)
            return None
        except Exception as exception:
            _LOGGER.error("Unexpected error occurred: %s", exception)
            raise WebSocketError("WebSocket error occurred") from exception

    async def close(self):
        if self.session:
            await self.session.close()
        _LOGGER.debug("Session closed")
