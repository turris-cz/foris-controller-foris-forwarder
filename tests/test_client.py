import threading

from foris_forwarder.client import Client

TIMEOUT = 30.0


def test_connection(prepare_ca, connection_settings):
    process, settings = connection_settings
    client = Client("connection-test", settings)

    assert client.connected is False

    # add post_connect hook
    connect_event = threading.Event()

    def connect(client, userdata, flags, rc):
        connect_event.set()

    client.set_connect_hook(connect)

    # add post_disconnect hook
    disconnect_event = threading.Event()

    def disconnect(client, userdata, rc):
        disconnect_event.set()

    client.set_disconnect_hook(disconnect)

    # test connect
    client.connect()

    assert connect_event.wait(TIMEOUT)
    assert client.connected is True

    # test disconnect
    client.disconnect()

    assert disconnect_event.wait(TIMEOUT)
    assert client.connected is False

    # terminte message bus
    connect_event.clear()
    client.connect()

    assert connect_event.wait(TIMEOUT)
    assert client.connected is True

    disconnect_event.clear()
    process.kill()

    assert disconnect_event.wait(TIMEOUT)
    assert client.connected is False


def test_messaging(prepare_ca, connection_settings):
    process, settings = connection_settings

    # prepare listener
    client_listener = Client("listener", settings)
    subscribe_event = threading.Event()

    def subscribe(client, userdata, mid, granted_qos):
        subscribe_event.set()

    client_listener.set_subscribe_hook(subscribe)

    message_event = threading.Event()

    def message(client, userdata, message):
        message_event.set()

    client_listener.set_message_hook(message)

    # prepare publisher
    client_publisher = Client("publisher", settings)
    publish_event = threading.Event()

    def publish(client, userdata, mid):
        publish_event.set()

    client_publisher.set_publish_hook(publish)

    # wait till listener is subscribed
    client_listener.connect()
    client_listener.wait_until_connected(TIMEOUT)
    client_publisher.connect()
    client_publisher.wait_until_connected(TIMEOUT)

    # wait till listener is subscribed for topic
    assert client_listener.subscribe([("/messaging-test/+", 0)])
    assert subscribe_event.wait(TIMEOUT)

    # wait till publisher publishes a message
    assert client_publisher.publish("/messaging-test/first", {"some": "data"}) is not None
    assert publish_event.wait(TIMEOUT)

    # check that the message was obtained by the listener
    assert message_event.wait(TIMEOUT)
