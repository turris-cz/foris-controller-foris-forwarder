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

import abc
import logging
import queue
import threading
import time
import typing

from paho.mqtt.client import MQTT_ERR_SUCCESS, MQTTMessage

from .client import Client
from .configuration import Host as HostConf
from .configuration import Subordinate as SubordinateConf
from .configuration import Subsubordinate as SubsubordinateConf
from .logger import LoggingMixin

SLEEP_STEP = 0.2
QUEUE_TIMEOUT = 10.0


class QueueItem(metaclass=abc.ABCMeta):
    priority = 0

    def __init__(self):
        self.attempt_number = 0
        self.first_attempt = time.monotonic()
        self.last_attempt = self.first_attempt

    def retry(self):
        self.attempt_number += 1
        self.last_attempt = time.monotonic()

    @abc.abstractmethod
    def perform(self, client: Client, timeout: typing.Optional[float] = None) -> typing.Optional[bool]:
        pass


class Connect(QueueItem):
    priority = 10

    def perform(self, client: Client, timeout: typing.Optional[float] = None) -> typing.Optional[bool]:
        event = threading.Event()

        res = {}

        def connect(client, userdata, flags, rc):
            res["rc"] = rc
            event.set()

        prev_hook = client.connect_hook
        client.set_connect_hook(connect)
        client.connect()

        finished = event.wait(timeout)
        client.set_connect_hook(prev_hook)

        return res["rc"] == MQTT_ERR_SUCCESS if finished else None


class Disconnect(QueueItem):
    priority = 10

    def perform(self, client: Client, timeout: typing.Optional[float] = None) -> typing.Optional[bool]:
        event = threading.Event()

        res = {}

        def disconnect(client, userdata, rc):
            res["rc"] = rc
            event.set()

        prev_hook = client.disconnect_hook
        client.set_disconnect_hook(disconnect)
        client.disconnect()

        finished = event.wait(timeout)
        client.set_disconnect_hook(prev_hook)

        return res["rc"] == MQTT_ERR_SUCCESS if finished else None


class Publish(QueueItem):
    priority = 1

    def __init__(self, message: MQTTMessage):
        super().__init__()
        self.message = message

    def perform(self, client: Client, timeout: typing.Optional[float] = None) -> typing.Optional[bool]:
        event = threading.Event()

        def publish(client, userdata, mid):
            event.set()

        prev_hook = client.publish_hook
        client.set_publish_hook(publish)
        client.publish(self.message.topic, self.message.payload)

        finished = event.wait(timeout)
        client.set_publish_hook(prev_hook)

        return True if finished else None


class Subscribe(QueueItem):
    priority = 5

    def __init__(self, topics_with_qos: typing.List[typing.Tuple[str, int]]):
        super().__init__()
        self.topics_with_qos = topics_with_qos

    def perform(self, client: Client, timeout: typing.Optional[float] = None) -> typing.Optional[bool]:
        event = threading.Event()

        def subscribe(client, userdata, mid, granted_qos):
            event.set()

        prev_hook = client.subscribe_hook
        client.set_subscribe_hook(subscribe)
        if not client.subscribe(self.topics_with_qos):
            return False

        finished = event.wait(timeout)
        client.set_subscribe_hook(prev_hook)

        return True if finished else None


class Unsubscribe(QueueItem):
    priority = 5

    def __init__(self, topics: typing.List[str]):
        super().__init__()
        self.topics = topics

    def perform(self, client: Client, timeout: typing.Optional[float] = None) -> typing.Optional[bool]:
        event = threading.Event()

        def unsubscribe(client, userdata, mid):
            event.set()

        prev_hook = client.unsubscribe_hook
        client.set_unsubscribe_hook(unsubscribe)
        if not client.unsubscribe(self.topics):
            return False

        finished = event.wait(timeout)
        client.set_unsubscribe_hook(prev_hook)

        return True if finished else None


class Forwarder(LoggingMixin):
    """Class responsible for passing messages between host and a single subordinate"""

    logger = logging.getLogger(__file__)

    def __init__(
        self,
        host_conf: HostConf,
        subordinate_conf: SubordinateConf,
        subsubordinate_confs: typing.List[SubsubordinateConf] = None,
    ):
        """Initializes forwarder"""

        self.host_conf = host_conf
        self.host = Client(
            host_conf.client_settings(),
            f"{host_conf.controller_id}->{subordinate_conf.controller_id}",
        )
        self.subordinate_conf = subordinate_conf
        self.subordinate = Client(
            subordinate_conf.client_settings(),
            f"{subordinate_conf.controller_id}->{host_conf.controller_id}",
        )
        self.subsubordinate_confs: typing.List[SubsubordinateConf] = subsubordinate_confs or []

        # initialize forwarder threads and queues
        self.host_queue: queue.Queue[typing.Union[QueueItem, bool]] = queue.Queue()
        self.host_queue_worker = threading.Thread(
            name="host-queue-worker",
            target=self.handle_host_queue,
            daemon=True,
        )

        self.subordinate_queue: queue.Queue[typing.Union[QueueItem, bool]] = queue.Queue()
        self.subordinate_queue_worker = threading.Thread(
            name="subordinate-queue-worker",
            target=self.handle_subordinate_queue,
            daemon=True,
        )
        self.register_message_handlers()
        self.host_ready = False
        self.subordinate_ready = False

        self.debug("Workers initialized")

        self.subordinate_queue.put(Connect())
        self.host_queue.put(Connect())
        self.plan_subscribe(subordinate_conf.controller_id)
        for subsubordinate_conf in self.subsubordinate_confs:
            self.plan_subscribe(subsubordinate_conf.controller_id)
        self.host_queue.put(True)  # Initialized
        self.subordinate_queue.put(True)  # Initialized

        self.debug("Planned to establish connection and topic subscription")

    @property
    def ready(self):
        return self.subordinate_ready and self.host_ready

    @staticmethod
    def suboridnate_topics_for_controller(
        controller_id: str,
    ) -> typing.List[typing.Tuple[str, int]]:
        return [
            (f"foris-controller/{controller_id}/notification/+/action/+", 0),
            (f"foris-controller/{controller_id}/reply/+", 0),
        ]

    @staticmethod
    def host_topics_for_controller(controller_id: str) -> typing.List[typing.Tuple[str, int]]:
        return [
            (f"foris-controller/{controller_id}/request/+/action/+", 0),
            (f"foris-controller/{controller_id}/request/+/list", 0),
            (f"foris-controller/{controller_id}/list", 0),
            (f"foris-controller/{controller_id}/schema", 0),
        ]

    def __str__(self):
        return f"{self.host}->{self.subordinate}"

    def handle_subordinate_queue(self):
        self.debug("Subordinate queue handler started")
        while True:
            item: typing.Optional[QueueItem] = self.subordinate_queue.get()
            self.subordinate_queue.task_done()

            if item is True:
                self.subordinate_ready = True
                continue

            if item is False:
                self.subordinate_ready = False
                # terminating on empty message
                return
            # TODO perhaps flush the queue if connection fails
            item.perform(self.subordinate, timeout=QUEUE_TIMEOUT)

    def handle_host_queue(self):
        self.debug("Host queue feeder started")
        while True:
            item: typing.Optional[QueueItem] = self.host_queue.get()
            self.host_queue.task_done()

            if item is True:
                self.host_ready = True
                continue

            if item is False:
                self.host_ready = False
                # terminating on empty message
                return
            # TODO perhaps flush the queue if connection fails
            item.perform(self.host, timeout=QUEUE_TIMEOUT)

    def register_message_handlers(self):
        """Register message handlers for forwarding"""

        # setting message hooks
        def host_to_subordinate(client, userdata, message: MQTTMessage):
            self.debug(f"Msg from host to subordinate (len={len(message.payload)})")
            self.subordinate_queue.put(Publish(message))

        self.host.set_message_hook(host_to_subordinate)

        self.register_subordinate_message_handlers()

    def register_subordinate_message_handlers(self):
        """Registers subordinate message handlers"""

        def subordinate_to_host(client, userdata, message: MQTTMessage):
            self.debug(f"Msg from subordinate to host (len={len(message.payload)})")
            self.host_queue.put(Publish(message))

        self.subordinate.set_message_hook(subordinate_to_host)

    def plan_subscribe(self, controller_id: str):
        self.host_queue.put(Subscribe(Forwarder.host_topics_for_controller(controller_id)))
        self.subordinate_queue.put(Subscribe(Forwarder.suboridnate_topics_for_controller(controller_id)))

    def plan_unsubscribe(self, controller_id: str):
        self.host_queue.put(Unsubscribe([e[0] for e in Forwarder.host_topics_for_controller(controller_id)]))
        self.subordinate_queue.put(
            Unsubscribe([e[0] for e in Forwarder.suboridnate_topics_for_controller(controller_id)])
        )

    def start(self):
        """Seth the hooks and starts to connect to both subordinate and host"""

        # start the workers
        self.debug("Starting workers")
        self.host_queue_worker.start()
        self.subordinate_queue_worker.start()

    def stop(self):
        """Send request to disconnect"""
        self.debug("Stopping")

        # Disconnect
        self.host_queue.put(Disconnect())
        self.subordinate_queue.put(Disconnect())

        # Terminate workers
        self.host_queue.put(False)
        self.subordinate_queue.put(False)

    def wait_for_ready(self, timeout: typing.Optional[float] = None) -> bool:

        start = time.monotonic()
        while not self.ready:
            if timeout:
                if time.monotonic() - start > timeout:
                    return False
            time.sleep(SLEEP_STEP)

        return True

    def wait_for_disconnected(self, timeout: typing.Optional[float] = None) -> bool:

        start = time.monotonic()
        while self.subordinate.connected or self.host.connected:
            if timeout:
                if time.monotonic() - start > timeout:
                    return False
            time.sleep(SLEEP_STEP)

        return True

    def reload_subordinate(self, subordinate_conf: SubordinateConf):
        self.debug(f"Reloading subordinate {subordinate_conf} ({subordinate_conf.ip}:{subordinate_conf.port})")

        # disconnect current subordinate
        self.subordinate_queue.put(Disconnect())

        # wait till subordinate disconnected
        while self.subordinate.connected:
            time.sleep(SLEEP_STEP)

        self.debug("Current Subordinate disconnected")

        # Clear suboridnate queue
        try:
            while self.subordinate_queue.get(False):
                self.subordinate_queue.task_done()
        except queue.Empty:
            pass

        self.subordinate_conf = subordinate_conf
        self.subordinate = Client(
            subordinate_conf.client_settings(),
            f"{subordinate_conf.controller_id}->{self.host_conf.controller_id}",
        )

        # new subordinate message handlers needs to be registered
        self.register_subordinate_message_handlers()
        self.debug("Message handlers connected")
        self.subordinate_queue.put(Connect())
        self.subordinate_queue.put(
            Subscribe(Forwarder.suboridnate_topics_for_controller(subordinate_conf.controller_id))
        )

        self.debug("Planning for new topic subscription")
        for subsubordinate_conf in self.subsubordinate_confs:
            self.subordinate_queue.put(
                Subscribe(Forwarder.suboridnate_topics_for_controller(subsubordinate_conf.controller_id))
            )
