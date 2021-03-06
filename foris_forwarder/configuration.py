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

import copy
import ipaddress
import logging
import pathlib
import typing
from abc import ABCMeta, abstractmethod
from ipaddress import IPv4Address

from euci import EUci

from .client import CertificateSettings, PasswordSettings, Settings
from .logger import LoggingMixin


class BaseBus(LoggingMixin, metaclass=ABCMeta):
    logger = logging.getLogger(__file__)

    def __init__(self, controller_id: str):
        self.controller_id = controller_id

    def __str__(self):
        return f"{self.__class__.__name__}: {self.controller_id}"

    @abstractmethod
    def client_settings(self) -> Settings:
        pass


class Host(BaseBus):
    """Local bus"""

    enabled = True

    def __init__(self, controller_id: str, port: int, username: str, password: str):
        super().__init__(controller_id)
        self.port = port
        self.username = username
        self.password = password

    def client_settings(self) -> Settings:
        return PasswordSettings(
            self.controller_id,
            self.port,
            self.username,
            self.password,
        )


class Subordinate(BaseBus):
    """1st level buses"""

    def __init__(
        self,
        controller_id: str,
        ip: ipaddress.IPv4Address,
        port: int,
        enabled: bool,
        fosquitto_data_dir: pathlib.Path,
    ):
        super().__init__(controller_id)
        self.ip = ip
        self.port = port
        self.enabled = enabled

        self.fosquitto_data_dir = fosquitto_data_dir
        self.ca_path = fosquitto_data_dir / self.controller_id / "ca.crt"
        self.crt_path = fosquitto_data_dir / self.controller_id / "token.crt"
        self.key_path = fosquitto_data_dir / self.controller_id / "token.key"

        self.check_paths_exist()

    @property
    def address(self) -> str:
        return f"{self.ip}:{self.port}"

    def check_paths_exist(self):
        for path in (self.ca_path, self.crt_path, self.key_path):
            if not path.is_file():
                raise ValueError(f"File '{ path }' does not exist.")

    def client_settings(self) -> Settings:
        return CertificateSettings(
            self.controller_id,
            str(self.ip),
            self.port,
            self.ca_path,
            self.crt_path,
            self.key_path,
        )

    def clone_with_overrides(
        self,
        ip: typing.Optional[ipaddress.IPv4Address] = None,
        port: typing.Optional[int] = None,
    ) -> "Subordinate":
        return Subordinate(
            controller_id=self.controller_id,
            ip=ip or self.ip,
            port=port or self.port,
            enabled=self.enabled,
            fosquitto_data_dir=self.fosquitto_data_dir,
        )


class Subsubordinate:
    """2nd level buses"""

    def __init__(self, controller_id: str, via: str, enabled: bool):
        self.controller_id = controller_id
        self.via = via
        self.enabled = enabled

    def __str__(self):
        return f"{super.__str__(self)} (via {self.via})"


class Configuration(LoggingMixin):
    logger = logging.getLogger(__file__)

    def __init__(
        self,
        controller_id: str,
        port: int,
        username: str,
        password: str,
        config_dir: pathlib.Path,
        fosquitto_data_dir: pathlib.Path,
    ):
        self.config_dir = config_dir
        self.fosquitto_data_dir = fosquitto_data_dir

        self._subordinates: typing.Dict[str, Subordinate] = {}
        self._subsubordinates: typing.Dict[str, Subsubordinate] = {}

        self.debug("Loading Host")
        self._host = Host(controller_id, port, username, password)

        self.load_from_uci()

    def load_from_uci(self):
        with EUci(str(self.config_dir), str(self.config_dir)) as eu:

            # clean subordinates and subsubordinates
            self._subordinates = {}
            self._subsubordinates = {}

            # Load subordinates
            subordinates_uci = [k for k in eu.get("fosquitto") if eu.get("fosquitto", k) == "subordinate"]
            for controller_id in subordinates_uci:
                enabled = eu.get("fosquitto", controller_id, "enabled", dtype=bool, default=True)
                ip = eu.get(
                    "fosquitto",
                    controller_id,
                    "address",
                    dtype=IPv4Address,
                    default=IPv4Address("192.0.0.8"),  # IPv4 dummy address (according to IANA)
                )
                port = eu.get("fosquitto", controller_id, "port", dtype=int, default=11884)

                try:
                    subordinate = Subordinate(controller_id, ip, port, enabled, self.fosquitto_data_dir)
                except ValueError as exc:
                    self.warning(f"Error loading subordinate '{controller_id}': {exc}")
                    continue

                self.debug(f"Loading {subordinate}")
                self._subordinates[controller_id] = subordinate

            subsubordinates_uci = [k for k in eu.get("fosquitto") if eu.get("fosquitto", k) == "subsubordinate"]

            for controller_id in subsubordinates_uci:
                enabled = eu.get("fosquitto", controller_id, "enabled", dtype=bool, default=True)
                via = eu.get("fosquitto", controller_id, "via")

                if via not in self._subordinates:
                    self.warning(f"Error loading subsubordinate '{controller_id}': via '{via}' is not in subordinates")
                    continue
                subsubordinate = Subsubordinate(controller_id, via, enabled)
                self.debug("Loading {subsubordinate}")
                self._subsubordinates[controller_id] = subsubordinate

    @property
    def host(self) -> Host:
        """Returns the global configuration"""
        return copy.deepcopy(self._host)

    @property
    def subordinates(self) -> typing.Dict[str, Subordinate]:
        """List current subordinates"""
        return copy.deepcopy(self._subordinates)

    @property
    def subsubordinates(self) -> typing.Dict[str, Subsubordinate]:
        """List current subsubordinates"""
        return copy.deepcopy(self._subsubordinates)

    def __str__(self):
        return self.__class__.__name__
