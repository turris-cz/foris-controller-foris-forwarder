import threading

from foris_forwarder.client import Client

TIMEOUT = 30.0


def test_connection(
    mosquitto_host,
    mosquitto_subordinate,
    prepare_ca,
    connection_settings,
    wait_for_disconnected,
):
    process, settings, _ = connection_settings
    client = Client(settings, keepalive=5)

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
    process.wait()

    assert disconnect_event.wait(TIMEOUT)
    assert client.connected is False

    wait_for_disconnected(client)


def test_messaging(mosquitto_host, mosquitto_subordinate, prepare_ca, connection_settings, wait_for_disconnected):
    process, settings1, settings2 = connection_settings

    # prepare listener
    client_listener = Client(settings1)
    subscribe_event = threading.Event()

    def subscribe(client, userdata, mid, granted_qos):
        subscribe_event.set()

    client_listener.set_subscribe_hook(subscribe)

    message_event = threading.Event()

    def message(client, userdata, message):
        message_event.set()

    client_listener.set_message_hook(message)

    # prepare publisher
    client_publisher = Client(settings2)
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
    assert client_publisher.publish("/messaging-test/first", '{"some": "data"}') is not None
    assert publish_event.wait(TIMEOUT)

    # check that the message was obtained by the listener
    assert message_event.wait(TIMEOUT)

    # unsubscribe and wait to be sure that message is not recieved
    unsubscribe_event = threading.Event()

    def unsubscribe(client, userdata, mid):
        unsubscribe_event.set()

    client_listener.set_unsubscribe_hook(unsubscribe)

    assert client_listener.unsubscribe(["/messaging-test/+"])
    assert unsubscribe_event.wait(TIMEOUT)

    message_event.clear()
    publish_event.clear()

    assert client_publisher.publish("/messaging-test/first", '{"some": "data"}') is not None
    assert publish_event.wait(TIMEOUT)
    assert not message_event.wait(2.0)  # no message should be recieved in 2 seconds

    # cleanup
    wait_for_disconnected(client_publisher)
    wait_for_disconnected(client_listener)

    process.kill()
    process.wait()
