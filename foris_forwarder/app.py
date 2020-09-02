#
# foris-forwarder
# Copyright (C) 2020 CZ.NIC, z.s.p.o. (http://www.nic.cz/)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
#

import ipaddress
import logging
import pathlib
import time
import typing
from abc import ABCMeta

from .configuration import Configuration
from .forwarder import Forwarder
from .logger import LoggingMixin
from .supervisor import ForwarderSupervisor
from .zconf import Listener as ZconfListener


class SingletonAppMeta(ABCMeta):  # ABCMeta is metaclass of LoggingMixin (it needs to be used here as well)
    """ Make sure that there is only one app instance created """

    instance_created: bool = False

    def __call__(cls, *args, **kwargs):
        if SingletonAppMeta.instance_created:
            raise RuntimeError("App instance already created")

        SingletonAppMeta.instance_created = True
        return super().__call__(*args, **kwargs)


class App(LoggingMixin, metaclass=SingletonAppMeta):  # type: ignore
    """The main application which should connect all parts of forwarder together
    * manages forwarders
    * updates configuration from uci config
    * updates configuration from zeroconf
    """

    WAIT_LOOP_PERIOD = 0.200

    logger = logging.getLogger(__file__)

    def __init__(
        self,
        controller_id: str,
        port: int,
        username: str,
        password: str,
        uci_config_dir: pathlib.Path,
        fosquitto_dir: pathlib.Path,
    ):
        """Instantiates a Foris Forwarder app
        :param controller_id: name of the host foris-controller
        :param port: port where to connect to local foris-controller (a.k.a host)
        :param username: username used to access local foris-controller
        :param password: password used to access local foris-controller
        :param uci_config_dir: destinaton where required uci configs are stored
        :param fosquitto_dir: path to directory with mosquitto certificates
        """
        self.configuration = Configuration(controller_id, port, username, password, uci_config_dir, fosquitto_dir)
        self._supervisors: typing.Dict[str, ForwarderSupervisor] = {}

    def run(self) -> typing.NoReturn:

        # Create forwarders
        for controller_id, subordinate in self.configuration.subordinates.items():
            self._supervisors[controller_id] = ForwarderSupervisor(Forwarder(self.configuration.host, subordinate))

        # initiate zconf
        zconf_listener = ZconfListener()

        # hook to zconf listener to update list of ips
        def zconf_handler(controller_id: str, addresses: typing.List[ipaddress.IPv4Address]):
            supervisor = self._supervisors.get(controller_id)
            if supervisor:
                supervisor.zconf_update(addresses)

        zconf_listener.set_add_service_handler(zconf_handler)

        while True:
            start_at = time.monotonic()

            # TODO check for update configurations

            # Update supervisors state
            for supervisors in self._supervisors.values():
                supervisors.check()

            # sleep for required interval
            sleep_for = start_at + App.WAIT_LOOP_PERIOD - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)