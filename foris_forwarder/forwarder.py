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
import threading

from .client import Client
from .configuration import Host as HostConf
from .configuration import Subordinate as SubordinateConf
from .logger import LoggingMixin


class Forwarder(LoggingMixin):
    """ Class responsible for passing messages between host and a single subordinate
    """

    logger = logging.getLogger(__file__)

    def _connect_host(self):
        """ Connects to host and blocks till connected """
        self.debug("Establishing connection to host")

        event = threading.Event()

        def connect(client, userdata, mid, granted_qos):
            event.set()

        self.host.set_connect_hook(connect)

        self.host.connect()
        event.wait()
        self.host.set_connect_hook(None)  # Unset hook

        self.debug("Connection to host established")

    def _subscribe_host(self):
        event = threading.Event()
        self.debug("Subscribing to host topics")

        def subscribe(client, userdata, mid, granted_qos):
            event.set()

        self.host.set_subscribe_hook(subscribe)

        self.host.subscribe(
            [
                (f"foris-controller/{self.subordinate.controller_id}/request/+/action/+", 0),
                (f"foris-controller/{self.subordinate.controller_id}/request/+/list", 0),
                (f"foris-controller/{self.subordinate.controller_id}/list", 0),
                (f"foris-controller/{self.subordinate.controller_id}/schema", 0),
            ]
        )
        event.wait()
        self.host.set_subscribe_hook(None)  # Unset hook
        self.debug("Subscribed to host topics")

    def _connect_subordinate(self):
        """ Connects to subordinate and blocks till connected """

        self.debug("Establishing connection to subordinate")
        event = threading.Event()

        def connect(client, userdata, mid, granted_qos):
            event.set()

        self.subordinate.set_connect_hook(connect)

        self.subordinate.connect()
        event.wait()
        self.subordinate.set_connect_hook(None)  # Unset hook

        self.debug("Connection to subordinate established")

    def _subscribe_subordinate(self):
        self.debug("Subscribing to subordinates topics")
        event = threading.Event()

        def subscribe(client, userdata, mid, granted_qos):
            event.set()

        self.subordinate.set_subscribe_hook(subscribe)

        self.subordinate.subscribe(
            [
                (f"foris-controller/{self.subordinate.controller_id}/notification/+/action/+", 0),
                (f"foris-controller/{self.subordinate.controller_id}/reply/+", 0),
            ]
        )
        event.wait()
        self.host.set_subscribe_hook(None)  # Unset hook

        self.debug("Subscribed to subordinates topics")

    def __init__(self, host: HostConf, subordinate: SubordinateConf):
        """ Initializes forwarder and waits till connected """

        self.host = Client(host.client_settings(), f"{host.controller_id}->{subordinate.controller_id}")
        self.subordinate = Client(subordinate.client_settings(), f"{subordinate.controller_id}->{host.controller_id}")

        self.debug("Starting")

        def host_to_subordinate(client, userdata, message):
            self.subordinate.publish(message.topic, message.payload)

        self.host.set_message_hook(host_to_subordinate)

        def subordinate_to_host(client, userdata, message):
            self.host.publish(message.topic, message.payload)

        self.subordinate.set_message_hook(subordinate_to_host)

        self._connect_host()
        self._subscribe_host()

        self._connect_subordinate()
        self._subscribe_subordinate()

        self.debug("Ready")

    def __str__(self):
        return f"{self.host}-{self.subordinate}"

    def disconnect(self):
        """ Disconnects and blocks until disconneted """

        self.debug("Disconnecting")

        subordinate_event = None
        host_event = None
        if self.subordinate.connected:
            subordinate_event = threading.Event()

            def disconnect_subordinate(client, userdata, rc):
                subordinate_event.set()

            self.subordinate.set_disconnect_hook(disconnect_subordinate)
            self.subordinate.disconnect()

            subordinate_event.wait()

        if self.host.connected:
            host_event = threading.Event()

            def disconnect_host(client, userdata, rc):
                host_event.set()

            self.host.set_disconnect_hook(disconnect_host)
            self.host.disconnect()

            host_event.wait()

        self.debug("Disconnected")
