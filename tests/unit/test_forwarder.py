import threading
import uuid

from foris_forwarder.client import Client
from foris_forwarder.forwarder import Forwarder

TIMEOUT = 30.0


def wait_for_connected(client: Client):
    event = threading.Event()

    def connect(client, userdata, mid, granted_qos):
        event.set()

    client.set_connect_hook(connect)
    client.connect()

    assert event.wait(TIMEOUT)


def test_notification(host_settings, subordinate_settings, forwarder, wait_for_disconnected):
    """ Notifications should be send by the subordinate and received by the host """
    _, host_settings, _ = host_settings
    host_settings.controller_id = "1111111111111111"
    host_client = Client(host_settings)

    _, subordinate_settings, _ = subordinate_settings
    subordinate_settings.controller_id = "2222222222222222"
    subordinate_client = Client(subordinate_settings)

    subscribe_event = threading.Event()

    def subscribe(client, userdata, mid, granted_qos):
        subscribe_event.set()

    host_client.set_subscribe_hook(subscribe)

    stored_message = {}
    message_event = threading.Event()

    def message(client, userdata, message):
        stored_message["payload"] = message.payload
        stored_message["topic"] = message.topic
        message_event.set()

    host_client.set_message_hook(message)

    wait_for_connected(host_client)
    wait_for_connected(subordinate_client)

    host_client.subscribe([(f"foris-controller/{forwarder.subordinate.controller_id}/notification/+/action/+", 0)])
    assert subscribe_event.wait(TIMEOUT)

    subordinate_client.publish(
        f"foris-controller/{forwarder.subordinate.controller_id}/notification/mod/action/act",
        b'{"some": "notification"}',
    )

    assert message_event.wait(TIMEOUT)

    assert (
        stored_message["topic"] == f"foris-controller/{forwarder.subordinate.controller_id}/notification/mod/action/act"
    )
    assert stored_message["payload"] == b'{"some": "notification"}'

    wait_for_disconnected(host_client)
    wait_for_disconnected(subordinate_client)


def test_request(host_settings, subordinate_settings, forwarder, wait_for_disconnected):
    """ Requests should be sent by the host and received by the subordinate """
    _, host_settings, _ = host_settings
    host_settings.controller_id = "3333333333333333"
    host_client = Client(host_settings)

    _, subordinate_settings, _ = subordinate_settings
    subordinate_settings.controller_id = "4444444444444444"
    subordinate_client = Client(subordinate_settings)

    subscribe_event = threading.Event()

    def subscribe(client, userdata, mid, granted_qos):
        subscribe_event.set()

    subordinate_client.set_subscribe_hook(subscribe)

    stored_message = {}
    message_event = threading.Event()

    def message(client, userdata, message):
        stored_message["payload"] = message.payload
        stored_message["topic"] = message.topic
        message_event.set()

    subordinate_client.set_message_hook(message)

    wait_for_connected(host_client)
    wait_for_connected(subordinate_client)

    subordinate_client.subscribe([(f"foris-controller/{forwarder.subordinate.controller_id}/request/+/action/+", 0)])
    assert subscribe_event.wait(TIMEOUT)

    host_client.publish(
        f"foris-controller/{forwarder.subordinate.controller_id}/request/mod/action/act",
        b'{"some": "request"}',
    )

    assert message_event.wait(TIMEOUT)

    assert stored_message["topic"] == f"foris-controller/{forwarder.subordinate.controller_id}/request/mod/action/act"
    assert stored_message["payload"] == b'{"some": "request"}'

    wait_for_disconnected(host_client)
    wait_for_disconnected(subordinate_client)


def test_reply(host_settings, subordinate_settings, forwarder, wait_for_disconnected):
    """ Replies should be sent by the subordinate and received by the host """
    _, host_settings, _ = host_settings
    host_settings.controller_id = "5555555555555555"
    host_client = Client(host_settings)

    _, subordinate_settings, _ = subordinate_settings
    subordinate_settings.controller_id = "6666666666666666"
    subordinate_client = Client(subordinate_settings)

    subscribe_event = threading.Event()

    def subscribe(client, userdata, mid, granted_qos):
        subscribe_event.set()

    host_client.set_subscribe_hook(subscribe)

    stored_message = {}
    message_event = threading.Event()

    def message(client, userdata, message):
        stored_message["payload"] = message.payload
        stored_message["topic"] = message.topic
        message_event.set()

    host_client.set_message_hook(message)

    wait_for_connected(host_client)
    wait_for_connected(subordinate_client)

    host_client.subscribe([(f"foris-controller/{forwarder.subordinate.controller_id}/reply/+", 0)])
    assert subscribe_event.wait(TIMEOUT)

    reply_uuid = uuid.uuid4()

    subordinate_client.publish(
        f"foris-controller/{forwarder.subordinate.controller_id}/reply/{reply_uuid}",
        b'{"some": "reply"}',
    )

    assert message_event.wait(TIMEOUT)

    assert stored_message["topic"] == f"foris-controller/{forwarder.subordinate.controller_id}/reply/{reply_uuid}"
    assert stored_message["payload"] == b'{"some": "reply"}'

    wait_for_disconnected(host_client)
    wait_for_disconnected(subordinate_client)
