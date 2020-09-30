import ipaddress
import logging
import threading
import time
import typing

from .forwarder import Forwarder
from .logger import LoggingMixin


class ForwarderSupervisor(LoggingMixin):
    """Operations which should be performed with the forwared should be put here

    It should handle reconnects and determine to what ip to connect
    """

    NEXT_IP_TIMEOUT = 5.0  # in seconds
    ZCONF_BUFFER_COUNT = 100

    class IpStat:
        """ Ip triage statistics used for sorting ips in the list """

        def __init__(self, fail_count: int, when: float):
            self.fail_count = fail_count
            self.when = when

        def __eq__(self, other):
            return self.fail_count == other.fail_count and self.when == other.when

        def __gt__(self, other):
            return not (self.__eq__(other)) and not (self.__lt__(other))

        def __lt__(self, other):
            if self.fail_count == other.fail_count:
                return self.when > other.when  # youngest first
            else:
                return self.fail_count < other.fail_count  # lowest count first

        def __str__(self):
            return f"{self.fail_count}-{self.when}"

    logger = logging.getLogger(__file__)

    def __init__(self, forwarder: Forwarder):
        self.subordinate_controller_id = forwarder.subordinate.controller_id
        self.forwarder = forwarder
        self.lock = threading.RLock()
        self.connected = False

        # IP -> (failed_attempt_count, time)
        # initalizes with subordinate ip
        self._ips: typing.Dict[ipaddress.IPv4Address, ForwarderSupervisor.IpStat] = {
            ipaddress.ip_address(self.forwarder.subordinate.settings.host): ForwarderSupervisor.IpStat(0, 0.0)
        }
        self.current_ip: ipaddress.IPv4Address = self.ips[0]
        self.current_ip_start: float = time.monotonic()

        # start forwarder in background
        self.forwarder.start()

    def terminate(self):
        """ causes that forwarder eventually terminates """
        self.debug("Supervisor terminating")

        self.forwarder.stop()

    def zconf_update(self, ips: typing.List[ipaddress.IPv4Address]):
        """ update ips obtained using zconf """
        now = time.monotonic()

        self.debug("Got addresses from zconf %s", map(str, ips))

        with self.lock:
            # merge two lists
            for ip in ips:
                count = self._ips.get(ip, ForwarderSupervisor.IpStat(0, 0.0)).fail_count
                self._ips[ip] = ForwarderSupervisor.IpStat(count, now)

            # sort and fit to buffer
            sorted_ips = sorted(((ip, stat) for ip, stat in self._ips.items()), key=lambda x: x[1])[
                : ForwarderSupervisor.ZCONF_BUFFER_COUNT
            ]
            res = {}
            for ip, stat in sorted_ips:
                res[ip] = stat

            self._ips = res

    @property
    def ips(self) -> typing.List[ipaddress.IPv4Address]:
        """Return current list of zconf IP addresses

        Addresses with better score first (min fail_count + most reacent)
        """
        with self.lock:
            return [e[0] for e in sorted([(k, v) for k, v in self._ips.items()], key=lambda x: x[1])]

    def subsubordinates_config_update(self, subordinates):
        # TODO
        raise NotImplementedError()

    def subordinate_config_update(self):
        # TODO
        raise NotImplementedError()

    def check(self):
        now = time.monotonic()

        if self.forwarder.subordinate.connected:
            # clean attempts for current ip to keep working address high in the list
            with self.lock:
                self.current_ip_start = now
                record = self._ips.get(self.current_ip)
                if record:
                    record.fail_count = 0
                    record.when = time.monotonic()
            return

        with self.lock:
            if self.current_ip_start + ForwarderSupervisor.NEXT_IP_TIMEOUT < now:
                # time up, lets use new ip_address
                record = self._ips.get(self.current_ip)
                if record:
                    record.fail_count += 1

                # Lets try new address
                self.current_ip = self.ips[0]
                self.current_ip_start = now

    def __str__(self):
        return f"supervisor-{self.forwarder.subordinate.controller_id}"
