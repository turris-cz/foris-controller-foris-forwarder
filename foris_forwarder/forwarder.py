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

from paho.mqtt.client import MQTTMessage

from .client import Client
from .configuration import Host as HostConf
from .configuration import Subordinate as SubordinateConf
from .logger import LoggingMixin


class Forwarder(LoggingMixin):
    """Class responsible for passing messages between host and a single subordinate"""

    logger = logging.getLogger(__file__)

    def wait_for_connected(self):
        """ Registers handlers and block until connected to both host and subordinate """
        self.register_message_handlers()
        self.wait_for_host_connected()
        self.wait_for_host_subscribed()
        self.wait_for_subordinate_connected()
        self.wait_for_subordinate_subscribed()

    def wait_for_host_connected(self):
        """ Starts to connect and wait till connected to host """

        self.debug("Establishing connection to host")

        event = threading.Event()
        prev_hook = self.host.connect_hook

        def connect(client, userdata, flags, rc):
            event.set()

        self.host.set_connect_hook(connect)

        self.host.connect()
        event.wait()
        self.host.set_connect_hook(prev_hook)  # Restore previous hook

        self.debug("Connection to host established")

    def wait_for_host_subscribed(self):
        """ Wait till subscribed to all required host topics """
        self.debug("Subscribing to host topics")

        event = threading.Event()
        prev_hook = self.host.subscribe_hook

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
        self.host.set_subscribe_hook(prev_hook)  # Restore previous hook

        self.debug("Subscribed to host topics")

    def wait_for_subordinate_connected(self):
        """ Starts to connect and wait till connected to subordinate """

        self.debug("Establishing connection to subordinate")
        event = threading.Event()
        prev_hook = self.subordinate.connect_hook

        def connect(client, userdata, flags, rc):
            event.set()

        self.subordinate.set_connect_hook(connect)

        self.subordinate.connect()
        event.wait()
        self.subordinate.set_connect_hook(prev_hook)  # Restore previous hook

        self.debug("Connection to subordinate established")

    def wait_for_subordinate_subscribed(self):
        """ Wait till subscribed to all required subordinate topics """

        self.debug("Subscribing to subordinates topics")
        event = threading.Event()
        prev_hook = self.subordinate.subscribe_hook

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
        self.host.set_subscribe_hook(prev_hook)  # Restore previous hook

        self.debug("Subscribed to subordinates topics")

    def __init__(self, host: HostConf, subordinate: SubordinateConf):
        """ Initializes forwarder """

        self.subordinate_to_host_lock = threading.Lock()
        self.host_to_subordinate_lock = threading.Lock()

        self.host = Client(host.client_settings(), f"{host.controller_id}->{subordinate.controller_id}")
        self.subordinate = Client(subordinate.client_settings(), f"{subordinate.controller_id}->{host.controller_id}")

        self.debug("Initialized")

    def register_message_handlers(self):
        """ Register message handlers for forwarding """

        # setting message hooks
        def host_to_subordinate(client, userdata, message: MQTTMessage):
            self.debug("Msg from host to subordinate (len=%d)", len(message.payload))
            # TODO handle disconnects
            with self.host_to_subordinate_lock:
                self.subordinate.publish(message.topic, message.payload)

        self.host.set_message_hook(host_to_subordinate)

        def subordinate_to_host(client, userdata, message: MQTTMessage):
            self.debug("Msg from subordinate to host (len=%d)", len(message.payload))
            # TODO handle disconnects
            with self.subordinate_to_host_lock:
                self.host.publish(message.topic, message.payload)

        self.subordinate.set_message_hook(subordinate_to_host)

    def start(self):
        """ Seth the hooks and starts to connect to both subordinate and host """
        self.debug("Setting hooks")

        self.register_message_handlers()

        # setting connect hooks
        def host_connect(client, userdata, flags, rc):
            if rc == 0:
                self.debug("Host connected -> subscribing for topics")
                self.host.subscribe(
                    [
                        (f"foris-controller/{self.subordinate.controller_id}/request/+/action/+", 0),
                        (f"foris-controller/{self.subordinate.controller_id}/request/+/list", 0),
                        (f"foris-controller/{self.subordinate.controller_id}/list", 0),
                        (f"foris-controller/{self.subordinate.controller_id}/schema", 0),
                    ]
                )

        self.host.set_connect_hook(host_connect)

        def subordinate_connect(client, userdata, flags, rc):
            if rc == 0:
                self.debug("Subordinate connected -> subscribing for topics")
                self.subordinate.subscribe(
                    [
                        (f"foris-controller/{self.subordinate.controller_id}/notification/+/action/+", 0),
                        (f"foris-controller/{self.subordinate.controller_id}/reply/+", 0),
                    ]
                )

        self.subordinate.set_connect_hook(subordinate_connect)

        # setting subscribe hooks
        def host_subscribe(client, userdata, mid, granted_qos):
            self.debug("Subscribed to host topics.")

        self.host.set_subscribe_hook(host_subscribe)

        def subordinate_subscribe(client, userdata, mid, granted_qos):
            self.debug("Subscribed to subordinate topics.")

        self.subordinate.set_subscribe_hook(subordinate_subscribe)

        # starting to connect
        self.debug("Connecting")
        self.host.connect()
        self.subordinate.connect()

    def __str__(self):
        return f"{self.host}-{self.subordinate}"

    def stop(self):
        """ Send request to disconnect """
        self.debug("Disconnecting")

        # setting logging hooks
        def disconnect_subordinate(client, userdata, rc):
            self.debug("Subordinate disconnected")

        def disconnect_host(client, userdata, rc):
            self.debug("Host disconnected")

        self.host.set_disconnect_hook(disconnect_host)
        self.subordinate.set_disconnect_hook(disconnect_subordinate)

        # Calling disconnect to eventually disconnect
        self.host.disconnect()
        self.subordinate.disconnect()

    def wait_for_disconnected(self):
        """ Disconnects and blocks until disconneted """

        self.debug("Waiting for disconnected")

        if self.subordinate.connected:
            subordinate_event = threading.Event()

            def disconnect_subordinate(client, userdata, rc):
                self.debug("Subordinate disconnected")
                subordinate_event.set()

            self.subordinate.set_disconnect_hook(disconnect_subordinate)
            self.subordinate.disconnect()

            subordinate_event.wait()

        if self.host.connected:
            host_event = threading.Event()

            def disconnect_host(client, userdata, rc):
                self.debug("Host disconnected")
                host_event.set()

            self.host.set_disconnect_hook(disconnect_host)
            self.host.disconnect()

            host_event.wait()

        self.debug("Disconnected")
