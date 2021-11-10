#
# foris-forwarder
# Copyright (C) 2020 CZ.NIC, z.s.p.o. (http://www.nic.cz/)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
#

import logging
import pathlib
import threading
import typing

from paho.mqtt import client as mqtt

from .logger import LoggingMixin


class Settings:
    controller_id: str
    host: typing.Optional[str] = None
    port: int = 0
    ca_certs: typing.Optional[pathlib.Path] = None
    certfile: typing.Optional[pathlib.Path] = None
    keyfile: typing.Optional[pathlib.Path] = None
    username: typing.Optional[str] = None
    password: typing.Optional[str] = None


class CertificateSettings(Settings):
    def __init__(
        self,
        controller_id: str,
        host: str,
        port: int,
        ca_certs: pathlib.Path,
        certfile: pathlib.Path,
        keyfile: pathlib.Path,
    ):
        self.controller_id = controller_id
        self.host = host
        self.port = port
        self.ca_certs = ca_certs
        self.certfile = certfile
        self.keyfile = keyfile


class PasswordSettings(Settings):
    def __init__(self, controller_id: str, port: int, username: str, password: str):
        self.controller_id = controller_id
        self.host = "127.0.0.1"
        self.port = port
        self.username = username
        self.password = password


class Client(LoggingMixin):
    """Class which handle connection to one message bus (basically a wrapper arount MQTTClient)

    It listens to one mqtt bus and triggers a handler with incomming data
    It also uses a set of filter to filter messages which are sent as well
    as those which are received
    """

    DEFAULT_KEEPALIVE = 30

    logger = logging.getLogger(__file__)

    def __init__(self, settings: Settings, name: typing.Optional[str] = None, keepalive: int = DEFAULT_KEEPALIVE):
        self.name = name
        self.controller_id = settings.controller_id
        self.settings = settings
        self.connect_hook: typing.Optional[typing.Callable[[mqtt.Client, dict, dict, int], None]] = None
        self.disconnect_hook: typing.Optional[typing.Callable[[mqtt.Client, dict, int], None]] = None
        self.publish_hook: typing.Optional[typing.Callable[[mqtt.Client, dict, int], None]] = None
        self.subscribe_hook: typing.Optional[
            typing.Optional[typing.Callable[[mqtt.Client, dict, int, typing.List[int]], None]]
        ] = None
        self.unsubscribe_hook: typing.Optional[typing.Optional[typing.Callable[[mqtt.Client, dict, int], None]]] = None
        self.message_hook: typing.Optional[
            typing.Optional[typing.Callable[[mqtt.Client, dict, mqtt.MQTTMessage], None]]
        ] = None
        self._connected = threading.Event()
        self.client: typing.Optional[mqtt.Client] = None
        self.keepalive = keepalive

    def __str__(self):
        return f"{self.controller_id}"

    def update(self, settings):
        raise NotImplementedError

    def set_connect_hook(self, hook: typing.Optional[typing.Callable[[mqtt.Client, dict, dict, int], None]]):
        self.connect_hook = hook

    def set_disconnect_hook(self, hook: typing.Optional[typing.Callable[[mqtt.Client, dict, int], None]]):
        self.disconnect_hook = hook

    def set_publish_hook(self, hook: typing.Optional[typing.Callable[[mqtt.Client, dict, int], None]]):
        self.publish_hook = hook

    def set_subscribe_hook(
        self,
        hook: typing.Optional[typing.Callable[[mqtt.Client, dict, int, typing.List[int]], None]],
    ):
        self.subscribe_hook = hook

    def set_unsubscribe_hook(
        self,
        hook: typing.Optional[typing.Callable[[mqtt.Client, dict, int], None]],
    ):
        self.unsubscribe_hook = hook

    def set_message_hook(
        self,
        hook: typing.Optional[typing.Callable[[mqtt.Client, dict, mqtt.MQTTMessage], None]],
    ):
        self.message_hook = hook

    @property
    def connected(self):
        return bool(self.client) and self._connected.is_set()

    def wait_until_connected(self, timeout: typing.Optional[float] = None):
        """blocks current thread until client is connected"""
        self._connected.wait(timeout)

    def connect(self):

        self.client = mqtt.Client(client_id=self.name or str(self), clean_session=False)
        self.client.enable_logger(self.logger)

        if self.settings.ca_certs and self.settings.certfile and self.settings.keyfile:
            self.debug(f"ca_certs: '{self.settings.ca_certs}'")
            self.debug(f"certfile: '{self.settings.certfile}'")
            self.debug(f"keyfile: '{self.settings.keyfile}'")
            self.client.tls_set(*map(str, (self.settings.ca_certs, self.settings.certfile, self.settings.keyfile)))
            self.client.tls_insecure_set(True)  # certificate is pinned the host name is not matching
        if self.settings.username and self.settings.password:
            self.client.username_pw_set(self.settings.username, self.settings.password)

        def on_connect(client, userdata, flags, rc):
            self.debug(
                f"Forwarded trying to connect to {self.settings.host}:{self.settings.port}",
            )
            if rc == 0:
                self.debug(f"Connected to {self.settings.host}:{self.settings.port}")
                self._connected.set()
            else:
                self.warning(f"Failed to connect to {self.settings.host}:{self.settings.port}")

            if self.connect_hook:
                self.connect_hook(client, userdata, flags, rc)

        def on_disconnect(client, userdata, rc):
            if rc == 0:
                self.debug(f"Disconnected from {self.settings.host}:{self.settings.port}")

            self._connected.clear()

            if self.disconnect_hook:
                self.disconnect_hook(client, userdata, rc)

        def on_publish(client, userdata, mid):
            self.debug(f"Published (mid={mid}) was published")
            if self.publish_hook:
                self.publish_hook(client, userdata, mid)

        def on_subscribe(client, userdata, mid, granted_qos):
            self.debug(f"Subscribed (mid={mid}) was published")
            if self.subscribe_hook:
                self.subscribe_hook(client, userdata, mid, granted_qos)

        def on_unsubscribe(client, userdata, mid):
            self.debug(f"Unubscribed (mid={mid}) was published")
            if self.unsubscribe_hook:
                self.unsubscribe_hook(client, userdata, mid)

        def on_message(client, userdata, message: mqtt.MQTTMessage):
            self.debug(f"Message Received (len={len(message.payload)}) for topic `{message.topic}`")
            if self.message_hook:
                self.message_hook(client, userdata, message)

        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_publish = on_publish
        self.client.on_subscribe = on_subscribe
        self.client.on_unsubscribe = on_unsubscribe
        self.client.on_message = on_message
        self.client.connect_async(self.settings.host, self.settings.port, self.keepalive)

        self.client.loop_start()

    def publish(self, topic: str, data: str) -> typing.Optional[int]:
        """Publishes messages

        This doesn't mean that the message was acutally sent.
        on_publish hook should be checked to determined whether the message was sent
        """
        if self.connected and self.client is not None:
            message = self.client.publish(topic, data)
            # this doesn't mean that the message was publish (on_publish callback)
            if message.rc == mqtt.MQTT_ERR_SUCCESS:
                self.debug(f"Publishing message to '{topic}' (mid={message.mid})")
                return message.mid
            else:
                self.warning(f"Failed to publish message to '{topic}'", topic)
                return None
        else:
            self.warning(f"Disconnected, can't send message to '{topic}'")
            return None

    def subscribe(self, topics: typing.List[typing.Tuple[str, int]]) -> bool:
        """Subscibes to a topic

        This doesn't mean the client is subscribed for given topic.
        on_subscribe hook should be checked to determined whether the topic was subscribed
        """
        if self.connected and self.client is not None:
            (res, mid) = self.client.subscribe(topics)
            if res == mqtt.MQTT_ERR_SUCCESS:
                self.debug(f"Subscribed to '{topics}'")
                return True
            else:
                self.warning(f"Failed to subscribe to '{topics}'")
                return False
        else:
            self.warning(f"Disconnected, failed to subscribe to '{topics}'")
            return False

    def unsubscribe(self, topics: typing.List[str]) -> bool:
        """Unsubscibes from a topic

        This doesn't mean the client is unsubscribed for given topic.
        on_unsubscribe hook should be checked to determined whether the topic was subscribed
        """
        if self.connected and self.client is not None:
            (res, mid) = self.client.unsubscribe(topics)
            if res == mqtt.MQTT_ERR_SUCCESS:
                self.debug(f"Unsubscribed from '{topics}'")
                return True
            else:
                self.warning(f"Failed to unsubscribe from '{topics}'")
                return False
        else:
            self.warning("Disconnected, failed to unsubscribe from '{topics}'")
            return False

    def disconnect(self):
        """Closes connection and disconnects"""
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
        self.client = None
