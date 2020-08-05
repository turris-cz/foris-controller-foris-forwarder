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

logger = logging.getLogger(__file__)


class Settings:
    host: typing.Optional[str] = None
    port: int = 0
    ca_certs: typing.Optional[pathlib.Path] = None
    certfile: typing.Optional[pathlib.Path] = None
    keyfile: typing.Optional[pathlib.Path] = None
    username: typing.Optional[str] = None
    password: typing.Optional[str] = None


class CertificateSettings(Settings):
    def __init__(
        self, host: str, port: int, ca_certs: pathlib.Path, certfile: pathlib.Path, keyfile: pathlib.Path,
    ):
        self.host = host
        self.port = port
        self.ca_certs = ca_certs
        self.certfile = certfile
        self.keyfile = keyfile


class PasswordSettings(Settings):
    def __init__(self, port: int, username: str, password: str):
        self.host = "127.0.0.1"
        self.port = port
        self.username = username
        self.password = password


class Client:
    """ Class which handle connection to one message bus

        It listens to one mqtt bus and triggers a handler with incomming data
        It also uses a set of filter to filter messages which are sent as well
        as those which are received
    """

    RETRY_CONNECT_TIMEOUT = 30.0
    RETRY_CONNECT_INTERVAL = 0.5
    KEEPALIVE = 30

    def __init__(self, name: str, settings: Settings, listen_filters=[], send_filters=[]):
        self.name = name
        self.settings = settings
        self.post_connect_hook: typing.Optional[typing.Callable[[mqtt.Client, dict, dict, int], None]] = None
        self.post_disconnect_hook: typing.Optional[typing.Callable[[mqtt.Client, dict, int], None]] = None
        self._connected = threading.Event()
        self.client: typing.Optional[mqtt.Client] = None

    def __str__(self):
        return f"{self.name}-forwarder"

    def update(self, settings):
        raise NotImplementedError

    def set_post_connect_hook(self, hook: typing.Optional[typing.Callable[[mqtt.Client, dict, dict, int], None]]):
        self.post_connect_hook = hook

    def set_post_disconnect_hook(self, hook: typing.Optional[typing.Callable[[mqtt.Client, dict, int], None]]):
        self.post_disconnect_hook = hook

    @property
    def connected(self):
        return self._connected.is_set()

    def connect(self):

        self.client = mqtt.Client(client_id=str(self), clean_session=False)
        self.client.enable_logger()

        if self.settings.ca_certs and self.settings.certfile and self.settings.keyfile:
            self.client.tls_set(*map(str, (self.settings.ca_certs, self.settings.certfile, self.settings.keyfile)))
            self.client.tls_insecure_set(True)  # certificate is pinned the host name is not matching
        if self.settings.username and self.settings.password:
            self.client.username_pw_set(self.settings.username, self.settings.password)

        def on_connect(client, userdata, flags, rc):
            logger.debug(
                "Forwarded %s is trying to connect to %s:%d", self, self.settings.host, self.settings.port,
            )
            if rc == 0:
                logger.debug("Connected to %s - %s:%d", self, self.settings.host, self.settings.port)
                self._connected.set()
            else:
                logger.warning("Failed to connect to %s - %s:%d", self, self.settings.host, self.settings.port)

            if self.post_connect_hook:
                self.post_connect_hook(client, userdata, flags, rc)

        def on_disconnect(client, userdata, rc):
            if rc == 0:
                logger.debug("Disconnected from %s - %s:%d", self, self.settings.host, self.settings.port)

            self._connected.clear()

            if self.post_disconnect_hook:
                self.post_disconnect_hook(client, userdata, rc)

        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.connect_async(self.settings.host, self.settings.port, Client.KEEPALIVE)

        self.client.loop_start()

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
