import ipaddress
import queue
import threading
import typing

from foris_forwarder.zconf import Listener

TIMEOUT = 30.0


def test_zconf(zconf_announcer):
    listener = Listener()

    added_queue = queue.Queue()
    removed_queue = queue.Queue()

    def added_handler(controller_id: str, addresses: typing.List[ipaddress.IPv4Address]):
        added_queue.put(controller_id)
        added_queue.put(addresses)

    def removed_handler(controller_id: str):
        removed_queue.put(controller_id)

    listener.set_add_service_handler(added_handler)
    listener.set_remove_service_handler(removed_handler)

    controller_id = added_queue.get(timeout=TIMEOUT)
    assert controller_id == "000000050000006B"
    addresses = added_queue.get(timeout=TIMEOUT)
    assert len(addresses) == 1
    assert addresses[0] == ipaddress.ip_address("127.0.0.1")

    zconf_announcer.close()

    controller_id = removed_queue.get(timeout=TIMEOUT)
    assert controller_id == "000000050000006B"
