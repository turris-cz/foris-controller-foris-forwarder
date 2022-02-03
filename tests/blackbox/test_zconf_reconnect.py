"""
Zconf test setup

* mqtt host bus
* mqtt subordinate bus
* mqtt alternative subordinate message bus
* foris-controller on subordinate bus
* foris-controller on alternative subordinate bus
* client on host bus
* forwarder between host bus and subordinate bus

"""

import getpass
import os
import pathlib
import shutil
import signal
import subprocess
import time

import prctl
import pytest
from foris_client.buses.base import ControllerMissing
from foris_client.buses.mqtt import MqttListener, MqttSender

MOSQUITTO_PATH = os.environ.get("MOSQUITTO_PATH", "/usr/sbin/mosquitto")
TIMEOUT = 30.0
ZCONF_TIMEOUT = 60.0 * 3  # three minutes


@pytest.fixture(scope="function")
def mosquitto_subordinate_alternative(prepare_ca):
    """Mocks mqtt alternative subordinate (listens on network uses certificates)"""
    PORT = 11891
    CONFIG_PATH = "/tmp/mosquitto-subordinate-alternative.conf"
    CRT_PATH = prepare_ca / "remote/01.crt"
    KEY_PATH = prepare_ca / "remote/01.key"
    CA_PATH = prepare_ca / "remote/ca.crt"
    CRL_PATH = prepare_ca / "remote/ca.crl"
    TOKEN_CRT_PATH = prepare_ca / "remote/02.crt"
    TOKEN_KEY_PATH = prepare_ca / "remote/02.key"
    PERSISTENCE_FILE_PATH = "/tmp/mosquitto-subordinate-alternative.db"

    # pepare config file
    with open(CONFIG_PATH, "w") as f:
        f.write(
            f"""\
log_type error
log_type warning
log_dest stderr
per_listener_settings true
autosave_interval 0
persistence true
persistence_file {PERSISTENCE_FILE_PATH}
queue_qos0_messages true

user {getpass.getuser()}

listener 11890 127.0.0.1
allow_anonymous true

listener {PORT} 0.0.0.0
allow_anonymous false
protocol mqtt
tls_version tlsv1.2
use_identity_as_username true
cafile {CA_PATH}
certfile {CRT_PATH}
keyfile {KEY_PATH}
#crlfile {CRL_PATH}  # TODO crlfile have only 30 days before expiring
require_certificate true
"""
        )

    args = ["-c", CONFIG_PATH]
    if os.environ.get("FF_TEST_DEBUG", "0") == "1":
        args.append("-v")

    # start process
    instance = subprocess.Popen([MOSQUITTO_PATH] + args)

    yield instance, PORT, TOKEN_KEY_PATH, TOKEN_CRT_PATH, CA_PATH

    # cleanup
    instance.kill()

    for path in (CONFIG_PATH, PERSISTENCE_FILE_PATH):
        try:
            os.unlink(path)
        except Exception:
            pass

    instance.wait(TIMEOUT)


@pytest.fixture(scope="function")
def foris_controller1(mosquitto_subordinate):
    controller_id = "000000050000006B"

    args = [
        "foris-controller",
        "-b",
        "mock",
        "mqtt",
        "--controller-id",
        controller_id,
        "--host",
        "127.0.0.1",
        "--port",
        "11880",
        "--announcer-period",
        "0",
    ]
    if os.environ.get("FF_TEST_DEBUG", "0") == "1":
        args.insert(1, "-d")

    instance = subprocess.Popen(
        args,
        preexec_fn=lambda: prctl.set_pdeathsig(signal.SIGKILL),
    )

    # try to send message to be sure that foris-controller is working
    start = time.monotonic()

    while True:
        try:
            sender = MqttSender("localhost", 11880, TIMEOUT)
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
def foris_controller2(mosquitto_subordinate_alternative, running_forwarder):
    controller_id = "000000050000006B"

    args = [
        "foris-controller",
        "-b",
        "mock",
        "mqtt",
        "--controller-id",
        controller_id,
        "--host",
        "127.0.0.1",
        "--port",
        "11890",
        "--zeroconf-enabled",
        "--zeroconf-port",
        "11891",
        "--announcer-period",
        "0",
    ]
    if os.environ.get("FF_TEST_DEBUG", "0") == "1":
        args.insert(1, "-d")

    instance = subprocess.Popen(
        args,
        preexec_fn=lambda: prctl.set_pdeathsig(signal.SIGKILL),
    )

    yield instance, controller_id

    # cleanup
    instance.kill()
    instance.wait(TIMEOUT)


@pytest.fixture(scope="function")
def uci_config_dir():
    path = pathlib.Path("/tmp/forwarder_config")
    os.makedirs(str(path), exist_ok=True)

    with (path / "fosquitto").open("w") as f:
        f.write(
            """\
config global 'global'
    option debug '0'

config local 'local'
    option port '11883'

config remote 'remote'
    option port '11882'
    option enabled '1'

config subordinate '000000050000006B'
    option address '127.0.0.1'
    option port '11884'
    option enabled '1'
"""
        )

    yield path

    try:
        shutil.rmtree(str(path), ignore_errors=True)
    except Exception:
        pass


@pytest.fixture(scope="function")
def running_forwarder(uci_config_dir, token_dir, mosquitto_host, mosquitto_subordinate):
    controller_id = "000000050000006B"

    instance = subprocess.Popen(
        [
            "foris-forwarder",
            "-d",
            "--controller-id",
            controller_id,
            "--port",
            "11883",
            "--uci-config-dir",
            str(uci_config_dir),
            "--fosquitto-dir",
            str(token_dir),
            "--passwd-file",
            "/tmp/mosquitto-host.plain",
        ],
        preexec_fn=lambda: prctl.set_pdeathsig(signal.SIGKILL),
    )

    yield instance, controller_id

    # cleanup
    instance.kill()
    instance.wait(TIMEOUT)


@pytest.mark.slow
def test_zconf_reconnect(foris_sender, foris_controller1, mosquitto_subordinate, foris_controller2):
    controller_instance, controller_id = foris_controller1

    # sends request and should receive a reply
    foris_sender.send("about", "get", data=None, controller_id=controller_id)

    # Terminte subordinate message bus (link is broken) and controller
    controller_instance.kill()
    mosquitto_subordinate[0].kill()

    # should receive an exception
    with pytest.raises(ControllerMissing):
        foris_sender.send("about", "get", data=None, controller_id=controller_id)

    recovered = False
    # Now wait for reconnect to alternative bus with significant timeout
    waiting_started = time.monotonic()
    while time.monotonic() - ZCONF_TIMEOUT < waiting_started:
        try:
            foris_sender.send("about", "get", data=None, controller_id=controller_id)
            recovered = True
            break
        except ControllerMissing:
            pass

    assert recovered
