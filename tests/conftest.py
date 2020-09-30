import ipaddress
import os
import pathlib
import shutil
import subprocess

import pytest

from foris_forwarder.configuration import Host, Subordinate
from foris_forwarder.forwarder import Forwarder

BASE_DIR = pathlib.Path(__file__).parent
CA_PATH = pathlib.Path("/tmp/mosquitto-ca")
MOSQUITTO_PATH = os.environ.get("MOSQUITTO_PATH", "/usr/sbin/mosquitto")
MOSQUITTO_PASSWD_PATH = os.environ.get("MOSQUITTO_PASSWD_PATH", "/usr/bin/mosquitto_passwd")
TOKEN_PATH = pathlib.Path("/tmp/mosquitto-token")
TIMEOUT = 30.0


@pytest.fixture(scope="session")
def prepare_ca():
    """ Prepares CA and its certificates """
    os.makedirs(CA_PATH, exist_ok=True)
    subprocess.run(["tar", "xzf", str(BASE_DIR / "data/ca/remote.tar.gz"), "-C", str(CA_PATH)])
    yield CA_PATH

    try:
        shutil.rmtree(CA_PATH, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture(scope="session")
def token_dir(prepare_ca):

    target_dir = TOKEN_PATH / "000000050000006B"
    os.makedirs(target_dir, exist_ok=True)
    shutil.copy(prepare_ca / "remote" / "ca.crt", target_dir / "ca.crt")
    shutil.copy(prepare_ca / "remote" / "02.crt", target_dir / "token.crt")
    shutil.copy(prepare_ca / "remote" / "02.key", target_dir / "token.key")

    yield TOKEN_PATH

    try:
        shutil.rmtree(TOKEN_PATH, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture(scope="function")
def mosquitto_host():
    """ Mocks mqtt host server (listens on localhost, password authentication) """
    PASSWORD = "password"
    USERNAME = "username"
    PORT = 11883
    CONFIG_PATH = "/tmp/mosquitto-host.conf"
    PASSWORD_FILE_PATH = "/tmp/mosquitto-host.password"
    PERSISTENCE_FILE_PATH = "/tmp/mosquitto-host.db"

    # prepare password file
    with open(PASSWORD_FILE_PATH, "w"):
        pass
    subprocess.run([MOSQUITTO_PASSWD_PATH, "-b", PASSWORD_FILE_PATH, USERNAME, PASSWORD])

    # prepare config file
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
password_file {PASSWORD_FILE_PATH}
allow_anonymous false

port {PORT}
bind_address localhost
"""
        )

    # start process
    instance = subprocess.Popen([MOSQUITTO_PATH, "-v", "-c", CONFIG_PATH])

    yield instance, USERNAME, PASSWORD, PORT

    # cleanup
    instance.kill()

    for path in (PASSWORD_FILE_PATH, CONFIG_PATH, PERSISTENCE_FILE_PATH):
        try:
            os.unlink(path)
        except Exception:
            pass

    instance.wait(TIMEOUT)


@pytest.fixture(scope="function")
def mosquitto_subordinate(prepare_ca):
    """ Mocks mqtt subordinate (listens on network uses certificates)"""
    PORT = 11884
    CONFIG_PATH = "/tmp/mosquitto-subordinate.conf"
    CRT_PATH = prepare_ca / "remote/01.crt"
    KEY_PATH = prepare_ca / "remote/01.key"
    CA_PATH = prepare_ca / "remote/ca.crt"
    CRL_PATH = prepare_ca / "remote/ca.crl"
    TOKEN_CRT_PATH = prepare_ca / "remote/02.crt"
    TOKEN_KEY_PATH = prepare_ca / "remote/02.key"
    PERSISTENCE_FILE_PATH = "/tmp/mosquitto-subordinate.db"

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
allow_anonymous true

port 11880  # should be unique
bind_address 127.0.0.1

listener {PORT} 0.0.0.0
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

    # start process
    instance = subprocess.Popen([MOSQUITTO_PATH, "-v", "-c", CONFIG_PATH])

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
def forwarder(token_dir, mosquitto_host, mosquitto_subordinate):
    _, username, password, host_port = mosquitto_host
    host_conf = Host("000000050000005A", host_port, username, password)

    _, subordinate_port, token_key_path, token_crt_path, ca_path = mosquitto_subordinate
    subordinate_conf = Subordinate(
        "000000050000006B",
        ipaddress.ip_address("127.0.0.1"),
        subordinate_port,
        True,
        token_dir,
    )

    return Forwarder(host_conf, subordinate_conf)


@pytest.fixture(scope="function")
def connected_forwarder(forwarder):
    forwarder.start()
    forwarder.wait_for_ready()

    yield forwarder

    forwarder.stop()
    forwarder.wait_for_disconnected()
