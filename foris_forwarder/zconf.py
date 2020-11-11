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
import json
import logging
import re
import typing

from zeroconf import ServiceBrowser, Zeroconf

from .logger import LoggingMixin


class Listener(LoggingMixin):
    TYPE = "_mqtt._tcp.local."
    NAME = "foris-controller"

    logger = logging.getLogger(__file__)

    @staticmethod
    def _extract_controller_id_from_name(name: str) -> typing.Optional[str]:
        match = re.match(fr"([^\.]+).{Listener.NAME}.{Listener.TYPE}", name)
        if not match:
            return None  # other service
        return match.group(1)

    @staticmethod
    def _extract_addresses(zconf: Zeroconf, name: str) -> typing.Optional[typing.List[ipaddress.IPv4Address]]:
        info = zconf.get_service_info(type, name)

        if b"addresses" not in info.properties:
            return None

        return [ipaddress.ip_address(ip) for ip in json.loads(info.properties[b"addresses"])]

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str):
        """ Called when service is removed (part of zconf API) """
        self.debug(f"Got message that service '{name}' was removed")

        controller_id = Listener._extract_controller_id_from_name(name)
        if not controller_id:  # other service
            return
        if self._remove_service_handler:
            self.debug(f"Calling remove handler with {controller_id}")
            self._remove_service_handler(controller_id)

    def update_service(self, zeroconf: Zeroconf, type: str, name: str):
        """ Called when service is updated (part of zconf API) """
        self.debug(f"Got message that service '{name}' was updated")

        controller_id = Listener._extract_controller_id_from_name(name)
        if not controller_id:  # other service
            return

        addresses = Listener._extract_addresses(zeroconf, name)
        if addresses and self._update_service_handler:
            self.debug(f"Calling update handler with ({controller_id}, {[str(e) for e in addresses]})")
            self._update_service_handler(controller_id, addresses)

    def add_service(self, zeroconf: Zeroconf, type: str, name: str):
        """ Called when service is added (part of zconf API) """

        self.debug(f"Got message that service {name} was registered")

        controller_id = Listener._extract_controller_id_from_name(name)
        if not controller_id:  # other service
            return

        addresses = Listener._extract_addresses(zeroconf, name)
        if addresses and self._add_service_handler:
            self.debug(f"Calling add handler with ({controller_id}, {[str(e) for e in addresses]})")
            self._add_service_handler(controller_id, addresses)

    def set_add_service_handler(
        self,
        handler: typing.Optional[typing.Callable[[str, typing.List[ipaddress.IPv4Address]], None]],
    ):
        """Sets add service handler
        :param handler: None or callable which takes controller_id(str) as argument
        """
        self.debug(f"Setting add handler to {handler}")

        self._add_service_handler = handler

    def set_update_service_handler(
        self,
        handler: typing.Optional[typing.Callable[[str, typing.List[ipaddress.IPv4Address]], None]],
    ):
        """Sets update service handler
        :param handler: None or callable which takes controller_id(str) as argument
        """
        self.debug(f"Setting update handler to {handler}")
        self._update_service_handler = handler

    def set_remove_service_handler(self, handler: typing.Optional[typing.Callable[[str], None]]):
        """Sets remove service handler
        :param handler: None or callable which takes controller_id(str) as argument
        """
        self.debug(f"Setting remove handler to {handler}")

        self._remove_service_handler = handler

    def __init__(self):
        self.debug("Staring zeroconf listener")
        self._add_service_handler: typing.Optional[
            typing.Callable[[str, typing.List[ipaddress.IPv4Address]], None]
        ] = None
        self._remove_service_handler: typing.Optional[typing.Callable[[str], None]] = None
        self._update_service_handler: typing.Optional[
            typing.Callable[[str, typing.List[ipaddress.IPv4Address]], None]
        ] = None

        self.zeroconf = Zeroconf()
        self.browser = ServiceBrowser(self.zeroconf, self.TYPE, self)

    def close(self):
        self.browser = None
        self.zeroconf.close()
        self.debug("Terminating zeroconf listener")

    def __del__(self):
        self.zeroconf.close()

    def __str__(self):
        return self.__class__.__name__
