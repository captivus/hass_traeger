#!/usr/bin/python3
# coding=utf-8

"""
Collects stats from traeger grills

Copyright 2020 by Keith Baker All rights reserved.
This file is part of the traeger python library,
and is released under the "GNU GENERAL PUBLIC LICENSE Version 2". 
Please see the LICENSE file that should have been included as part of this package.
"""

import os
import getpass
import pprint
import numbers
import json
import time
import socket
import asyncio
import logging

from dotenv import load_dotenv
from traeger.traeger_newnew import Traeger, WebSocketError, InvalidWebSocketURLError
import aiohttp

pp = pprint.PrettyPrinter(indent=4)

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

def unpack(base, value):
    if isinstance(value, numbers.Number):
        if isinstance(value, bool):
            value = int(value)
        return [(".".join(base), value)]
    elif isinstance(value, dict):
        return unpack_dict(base, value)
    elif isinstance(value, list):
        return unpack_list(base, value)
    return []

def unpack_list(base, thelist):
    result = []
    for n, v in enumerate(thelist):
        newbase = base.copy()
        newbase.append(str(n))
        result.extend(unpack(newbase, v))
    return result

def unpack_dict(base, thedict):
    result = []
    for k, v in thedict.items():
        if k == "custom_cook" and len(base) == 1:
            pass
        else:
            newbase = base.copy()
            newbase.append(k)
            result.extend(unpack(newbase, v))
    return result

def send_data_to_graphite(host, port, metric_path, value, timestamp):
    message = f"{metric_path} {value} {timestamp}\n"
    _LOGGER.debug(f"Sending data to Graphite: {message}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        sock.sendall(message.encode('utf-8'))

async def collect_data(config, traeger):
    while True:
        last_collect = time.time()
        _LOGGER.debug("Collecting grill data")

        try:
            grills_status = await traeger.get_grill_status()
            _LOGGER.debug(f"Grills Status: {grills_status}")

            grills = await traeger.get_grills()
            _LOGGER.debug(f"Grills: {grills}")

            for grill in grills:
                if grill["thingName"] not in grills_status:
                    _LOGGER.warning(f"Missing Data for {grill['thingName']}")

            for k, v in unpack_dict([], grills_status):
                metric_path = f"traeger.{k}"
                send_data_to_graphite(config["graphite_host"], int(config["graphite_port"]), metric_path, v, last_collect)

        except WebSocketError as e:
            _LOGGER.error(f"WebSocket error occurred: {e}")
            raise
        except Exception as e:
            _LOGGER.error(e)

        next_collect = last_collect + 60
        until_collect = next_collect - time.time()
        if until_collect > 0:
            _LOGGER.debug(f"Sleeping {until_collect}")
            await asyncio.sleep(until_collect)
        else:
            _LOGGER.debug(f"Late for next collection {until_collect}")

async def main():
    load_dotenv()

    config = {}
    config["username"] = os.getenv("TRAEGER_USERNAME") or input("username:")
    config["password"] = os.getenv("TRAEGER_PASSWORD") or getpass.getpass()
    config["graphite_port"] = os.getenv("GRAPHITE_PORT") or input("graphite port:")
    config["graphite_host"] = os.getenv("GRAPHITE_HOST") or input("graphite host:")

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                traeger = Traeger(config['username'], config['password'], request_library=session)
                await traeger.initialize()
                await collect_data(config, traeger)
        except InvalidWebSocketURLError as e:
            _LOGGER.error(f"Invalid WebSocket URL: {e}")
            _LOGGER.info("Refreshing MQTT URL and restarting data collection...")
            await traeger.refresh_mqtt_url()
            await asyncio.sleep(5)  # Wait a bit before retrying
        except WebSocketError as e:
            _LOGGER.error(f"WebSocket error occurred: {e}")
            _LOGGER.info("Restarting data collection due to WebSocket error...")
            await traeger.kill()  # Terminate the existing Traeger object
            await asyncio.sleep(5)  # Wait a bit before retrying
        except Exception as e:
            _LOGGER.error(f"Unexpected error occurred: {e}")
            break

if __name__ == "__main__":
    asyncio.run(main())