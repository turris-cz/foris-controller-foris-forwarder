import pathlib

from foris_forwarder import configuration

UCI_DIR = pathlib.Path(__file__).parent / "uci"
FOSQUITO_DIR = pathlib.Path(__file__).parent / "fosquitto"


def test_uci():
    conf = configuration.Configuration(
        "0000000000000001",
        11883,
        "username",
        "password",
        UCI_DIR,
        FOSQUITO_DIR,
    )

    assert conf.host.controller_id == "0000000000000001"
    assert conf.host.username == "username"
    assert conf.host.password == "password"

    assert len(conf.subordinates) == 1
    controller_id, subordinate = list(conf.subordinates.items())[0]
    assert subordinate.enabled is True
    assert subordinate.controller_id == controller_id == "0000000A00000214"
    assert subordinate.address == "192.168.15.158:11884"

    assert len(conf.subsubordinates) == 1
    controller_id, subsubordinate = list(conf.subsubordinates.items())[0]
    assert subsubordinate.enabled is True
    assert subsubordinate.controller_id == controller_id == "1100D858D7001A2E"
    assert subsubordinate.via == "0000000A00000214"
