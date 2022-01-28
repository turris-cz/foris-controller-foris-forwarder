import json
import socket
import threading

import pytest
import zeroconf

from foris_forwarder.client import CertificateSettings, Client, PasswordSettings

TIMEOUT = 30.0


@pytest.fixture(scope="function")
def host_settings(mosquitto_host):
    process, username, password, port, *_ = mosquitto_host
    return (
        process,
        PasswordSettings("000000050000005A", port, username, password),
        PasswordSettings("000000050000006B", port, username, password),
    )


@pytest.fixture(scope="function")
def subordinate_settings(mosquitto_subordinate):
    process, port, token_key_path, token_crt_path, ca_path = mosquitto_subordinate
    return (
        process,
        CertificateSettings("000000050000005A", "localhost", port, ca_path, token_crt_path, token_key_path),
        CertificateSettings("000000050000006B", "localhost", port, ca_path, token_crt_path, token_key_path),
    )


@pytest.fixture(scope="function", params=["host", "subordinate"])
def connection_settings(request, host_settings, subordinate_settings):
    if request.param == "host":
        return host_settings
    elif request.param == "subordinate":
        return subordinate_settings

    raise RuntimeError(f"{request.param} not handled in connection_settings")


@pytest.fixture
def wait_for_disconnected():
    def func(client: Client):
        event = threading.Event()

        def disconnect(client, userdata, rc):
            event.set()

        client.set_disconnect_hook(disconnect)
        client.disconnect()

        if client.connected:
            assert event.wait(TIMEOUT)

    return func


@pytest.fixture(params=["new", "old"], scope="function")
def zconf_announcer(request):
    if request.param == "old":
        info = zeroconf.ServiceInfo(
            "_mqtt._tcp.local.",
            "000000050000006B.foris-controller._mqtt._tcp.local.",
            parsed_addresses=["127.0.0.1"],
            properties={"addresses": json.dumps(["127.0.0.1"])},
            port=11884,
        )

    elif request.param == "new":
        info = zeroconf.ServiceInfo(
            "_fosquitto._tcp.local.",
            "000000050000006B._fosquitto._tcp.local.",
            parsed_addresses=["127.0.0.1"],
            properties={"id": "000000050000006B"},
            port=11884,
            server=f"{socket.gethostname()}.local.",
        )

    zconf = zeroconf.Zeroconf()
    zconf.register_service(info)

    yield zconf

    zconf.close()
