#
# foris-controller
# Copyright (C) 2022 CZ.NIC, z.s.p.o. (http://www.nic.cz/)
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
    TYPE_OLD = "_mqtt._tcp.local."
    TYPE_NEW = "_fosquitto._tcp.local."
    NAME = "foris-controller"

    logger = logging.getLogger(__file__)

    @staticmethod
    def _extract(
        zconf: Zeroconf, type: str, name: str
    ) -> typing.Optional[typing.Tuple[str, typing.List[ipaddress.IPv4Address], int]]:
        """Used for new zconf settings"""

        if type != "_fosquitto._tcp.local.":
            return None

        info = zconf.get_service_info(type, name)

        if not info:
            # This means that service was unregister
            # and no info can be obtained
            # Try to at least extract controller id from name
            match = re.match(fr"(^[0-9a-fA-F]{{16}}).{Listener.TYPE_NEW}", name)
            controller_id = "" if not match else match.group(1)
            return (controller_id, [], 0)

        if not info.port or b"id" not in info.properties:
            return None

        controller_id = info.properties[b"id"].decode()

        if not re.match(r"^[0-9a-fA-F]{16}", controller_id):
            return None

        addresses = [ipaddress.ip_address(ip) for ip in info.addresses]

        return controller_id, addresses, info.port

    @staticmethod
    def _extract_controller_id_from_name(name: str) -> typing.Optional[str]:
        """Used for old zconf settings"""

        match = re.match(fr"([^\.]+).{Listener.NAME}.{Listener.TYPE_OLD}", name)
        if not match:
            return None  # other service
        return match.group(1)

    @staticmethod
    def _extract_addresses_and_port(
        zconf: Zeroconf, type: str, name: str
    ) -> typing.Optional[typing.Tuple[typing.List[ipaddress.IPv4Address], int]]:
        """Used for old zconf settings"""

        info = zconf.get_service_info(type, name)

        if not info or not info.port or b"addresses" not in info.properties:
            return None

        return [ipaddress.ip_address(ip) for ip in json.loads(info.properties[b"addresses"])], int(info.port)

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str):
        """Called when service is removed (part of zconf API)"""
        self.debug(f"Got message that service '{name}' was removed")

        extracted = self._extract(zeroconf, type, name)
        if not extracted:
            # try old method
            controller_id = Listener._extract_controller_id_from_name(name)
            if not controller_id:  # other service
                return
        else:
            controller_id, _, _ = extracted

        if self._remove_service_handler:
            if controller_id:
                self.debug(f"Calling remove handler {controller_id}")
                self._remove_service_handler(controller_id)
            else:
                self.info("Couldn't obtain controller_id from zconf while removing service")

    def update_service(self, zeroconf: Zeroconf, type: str, name: str):
        """Called when service is updated (part of zconf API)"""
        self.debug(f"Got message that service '{name}' was updated")

        extracted = self._extract(zeroconf, type, name)
        if not extracted:
            # try old method
            controller_id = Listener._extract_controller_id_from_name(name)
            if not controller_id:  # other service
                return
            addresses, port = Listener._extract_addresses_and_port(zeroconf, type, name)
        else:
            controller_id, addresses, port = extracted

        if addresses and self._update_service_handler:
            self.debug(f"Calling update handler ({controller_id}, {[str(e) for e in addresses]} :{port})")
            self._update_service_handler(controller_id, addresses, port)

    def add_service(self, zeroconf: Zeroconf, type: str, name: str):
        """Called when service is added (part of zconf API)"""

        self.debug(f"Got message that service {name} was registered")

        extracted = self._extract(zeroconf, type, name)
        if not extracted:
            # try old method
            controller_id = Listener._extract_controller_id_from_name(name)
            if not controller_id:  # other service
                return
            addresses, port = Listener._extract_addresses_and_port(zeroconf, type, name)
        else:
            controller_id, addresses, port = extracted

        if addresses and self._add_service_handler:
            self.debug(f"Calling add handler ({controller_id}, {[str(e) for e in addresses]} :{port})")
            self._add_service_handler(controller_id, addresses, port)

    def set_add_service_handler(
        self,
        handler: typing.Optional[typing.Callable[[str, typing.List[ipaddress.IPv4Address], int], None]],
    ):
        """Sets add service handler
        :param handler: None or callable which takes controller_id(str) as argument
        """
        self.debug(f"Setting add handler to {handler}")

        self._add_service_handler = handler

    def set_update_service_handler(
        self,
        handler: typing.Optional[typing.Callable[[str, typing.List[ipaddress.IPv4Address], int], None]],
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
            typing.Callable[[str, typing.List[ipaddress.IPv4Address], int], None]
        ] = None
        self._remove_service_handler: typing.Optional[typing.Callable[[str], None]] = None
        self._update_service_handler: typing.Optional[
            typing.Callable[[str, typing.List[ipaddress.IPv4Address], int], None]
        ] = None

        self.zeroconf = Zeroconf()
        service_types = [self.TYPE_NEW, self.TYPE_OLD]
        self.debug(f"Listening for: {service_types}")
        self.browser = ServiceBrowser(self.zeroconf, service_types, self)

    def close(self):
        self.browser = None
        self.zeroconf.close()
        self.debug("Terminating zeroconf listener")

    def __del__(self):
        self.zeroconf.close()

    def __str__(self):
        return self.__class__.__name__
