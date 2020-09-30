import signal
import subprocess
import time

import prctl
import pytest
from foris_client.buses.mqtt import MqttListener, MqttSender

TIMEOUT = 30.0


@pytest.fixture(scope="function")
def foris_controller(connected_forwarder):
    controller_id = "000000050000006B"

    instance = subprocess.Popen(
        [
            "foris-controller",
            "-d",
            "-b",
            "mock",
            "mqtt",
            "--controller-id",
            controller_id,
            "--host",
            "127.0.0.1",
            "--port",
            "11880",
            "--zeroconf-enabled",
            "--zeroconf-port",
            "11884",
        ],
        preexec_fn=lambda: prctl.set_pdeathsig(signal.SIGKILL),
    )

    # try to send message to be sure that foris-controller is working
    sender = MqttSender("localhost", 11880, TIMEOUT)
    start = time.monotonic()

    while True:
        try:
            sender.send("about", "get", data=None, controller_id=controller_id)
            # message passed controller is connected
            break
        except Exception:
            if start + TIMEOUT > time.monotonic():
                time.sleep(0.5)
            else:
                raise
            time.sleep(0.2)

    yield instance, controller_id

    # cleanup
    instance.kill()

    instance.wait(TIMEOUT)


@pytest.fixture(scope="function")
def foris_sender(foris_controller):
    sender = MqttSender("127.0.0.1", 11883, TIMEOUT, credentials=("username", "password"))

    yield sender

    sender.disconnect()


@pytest.fixture(scope="function")
def foris_listener(foris_controller):
    output = []

    def write_to_output(data, controller_id):
        output.append(data)

    listener = MqttListener(
        "127.0.0.1", 11883, write_to_output, controller_id="000000050000006B", credentials=("username", "password")
    )

    yield listener, output

    listener.disconnect()
