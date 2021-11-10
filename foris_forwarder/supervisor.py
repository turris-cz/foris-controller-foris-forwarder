import ipaddress
import logging
import threading
import time
import typing

from .configuration import Subordinate as SubordinateConf
from .forwarder import Forwarder
from .logger import LoggingMixin


class ForwarderSupervisor(LoggingMixin):
    """Operations which should be performed with the forwared should be put here

    It should handle reconnects and determine to what (ip, port) to connect
    """

    NEXT_IP_TIMEOUT = 30.0  # in seconds
    ZCONF_BUFFER_COUNT = 100

    class NetlocStat:
        """Netloc triage statistics used for sorting netloc in the list"""

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

        # (IP, port) -> (failed_attempt_count, time)
        # initalizes with subordinate netloc
        self._netlocs: typing.Dict[typing.Tuple[ipaddress.IPv4Address, int], ForwarderSupervisor.NetlocStat] = {
            (
                ipaddress.ip_address(self.forwarder.subordinate.settings.host),
                self.forwarder.subordinate.settings.port,
            ): ForwarderSupervisor.NetlocStat(0, 0.0)
        }
        self.current_netloc: typing.Tuple[ipaddress.IPv4Address, int] = self.netlocs[0]
        self.current_netloc_start: float = time.monotonic()

        # start forwarder in background
        self.forwarder.start()

    def terminate(self):
        """causes that forwarder eventually terminates"""
        self.debug("Supervisor terminating")

        self.forwarder.stop()

    def zconf_update(self, ips: typing.List[ipaddress.IPv4Address], port: int):
        """update ips obtained using zconf"""
        now = time.monotonic()

        self.info(f"Got addresses from zconf: {[str(e) for e in ips]} :{port}")

        with self.lock:
            # merge two lists
            for ip in ips:
                count = self._netlocs.get((ip, port), ForwarderSupervisor.NetlocStat(0, 0.0)).fail_count
                self._netlocs[(ip, port)] = ForwarderSupervisor.NetlocStat(count, now)

            # sort and fit to buffer
            sorted_netlocs = sorted(((ip, stat) for ip, stat in self._netlocs.items()), key=lambda x: x[1])[
                : ForwarderSupervisor.ZCONF_BUFFER_COUNT
            ]
            res = {}
            for (ip, port), stat in sorted_netlocs:
                res[(ip, port)] = stat

            self._netlocs = res

    @property
    def netlocs(self) -> typing.List[typing.Tuple[ipaddress.IPv4Address, int]]:
        """Return current network locations where subordinate server might be running

        Addresses with better score first (min fail_count + most reacent)
        """
        with self.lock:
            return [e[0] for e in sorted([(k, v) for k, v in self._netlocs.items()], key=lambda x: x[1])]

    def subsubordinates_config_update(self, subordinates):
        # TODO
        raise NotImplementedError()

    def subordinate_config_update(self, subordinate_conf: SubordinateConf):
        self.forwarder.reload_subordinate(subordinate_conf)

    def check(self):
        now = time.monotonic()

        if self.forwarder.subordinate.connected:
            # clean attempts for current netloc to keep working address high in the list
            with self.lock:
                self.current_netloc_start = now
                record = self._netlocs.get(self.current_netloc)
                if record:
                    record.fail_count = 0
                    record.when = time.monotonic()
            return

        with self.lock:
            if self.current_netloc_start + ForwarderSupervisor.NEXT_IP_TIMEOUT < now:
                # time up, lets use new netloc
                record = self._netlocs.get(self.current_netloc)
                if record:
                    record.fail_count += 1

                # Lets try new address
                self.current_netloc = self.netlocs[0]
                self.current_netloc_start = now

                # Reload subordinate with a new config
                ip, port = self.current_netloc
                new_config = self.forwarder.subordinate_conf.clone_with_overrides(ip=ip, port=port)
                self.forwarder.reload_subordinate(new_config)

    def __str__(self):
        return f"supervisor-{self.forwarder.subordinate.controller_id}"
