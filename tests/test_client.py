import threading

from foris_forwarder.client import CertificateSettings, Client, PasswordSettings


def test_connection(prepare_ca, connection_settings):
    process, settings = connection_settings
    client = Client("certificate-test", settings)

    assert client.connected is False

    # add post_connect hook
    connect_event = threading.Event()

    def post_connect(client, userdata, flags, rc):
        connect_event.set()

    client.set_post_connect_hook(post_connect)

    # add post_disconnect hook
    disconnect_event = threading.Event()

    def post_disconnect(client, userdata, rc):
        disconnect_event.set()

    client.set_post_disconnect_hook(post_disconnect)

    # test connect
    client.connect()

    assert connect_event.wait(30.0)
    assert client.connected is True

    # test disconnect
    client.disconnect()

    assert disconnect_event.wait(30.0)
    assert client.connected is False

    # terminte message bus
    connect_event.clear()
    client.connect()

    assert connect_event.wait(30.0)
    assert client.connected is True

    process.kill()

    disconnect_event.clear()
    assert disconnect_event.wait(30.0)
    assert client.connected is False
