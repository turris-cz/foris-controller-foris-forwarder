#
# foris-controller
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
import re
import typing

from zeroconf import ServiceBrowser, Zeroconf

from .logger import LoggingMixin


class Listener(LoggingMixin):
    TYPE = "_mqtt._tcp.local."
    NAME = "foris-controller"
    TIMEOUT = 5000  # 5 seconds

    logger = logging.getLogger(__file__)

    @staticmethod
    def _extract_controller_id_from_name(name: str) -> typing.Optional[str]:
        match = re.match(fr"([^\.]+).{Listener.NAME}.{Listener.TYPE}", name)
        if not match:
            return None  # other service
        return match.group(1)

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str):
        """ Called when service is removed (part of zconf API) """
        self.debug("Got message that service %s was removed", name)

        controller_id = Listener._extract_controller_id_from_name(name)
        if not controller_id:  # other service
            return
        if self._remove_service_handler:
            self.debug("Calling remove handler with (%s)", controller_id)
            self._remove_service_handler(controller_id)

    def add_service(self, zeroconf: Zeroconf, type: str, name: str):
        """ Called when service is added (part of zconf API) """

        self.debug("Got message that service %s was registered", name)

        controller_id = Listener._extract_controller_id_from_name(name)
        if not controller_id:  # other service
            return

        info = zeroconf.get_service_info(type, name)
        addresses = [ipaddress.ip_address(ip) for ip in info.addresses]
        if self._add_service_handler:
            self.debug("Calling add handler with (%s, %s)", controller_id, addresses)
            self._add_service_handler(controller_id, addresses)

    def set_add_service_handler(
        self, handler: typing.Optional[typing.Callable[[str, typing.List[ipaddress.IPv4Address]], None]]
    ):
        """Sets add service handler
        :param handler: None or callable which takes controller_id(str) as argument
        """
        self.debug("Setting add handler to %s", handler)

        self._add_service_handler = handler

    def set_remove_service_handler(self, handler: typing.Optional[typing.Callable[[str], None]]):
        """Sets remove service handler
        :param handler: None or callable which takes controller_id(str) as argument
        """
        self.debug("Setting remove handler to %s", handler)

        self._remove_service_handler = handler

    def __init__(self):
        self.debug("Staring zeroconf listener")
        self._add_service_handler: typing.Optional[typing.Callable[[str, ipaddress.IPv4Address], None]] = None
        self._remove_service_handler: typing.Optional[typing.Callable[[str], None]] = None

        self.zeroconf = Zeroconf()
        self.browser = ServiceBrowser(self.zeroconf, self.TYPE, self)

    def close(self):
        self.browser = None
        self.zeroconf.close()
        self.debug("Terminating zeroconf listener")

    def __del__(self):
        self.zeroconf.close()
