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

from abc import ABCMeta, abstractmethod


class LoggingMixin(metaclass=ABCMeta):
    @property
    @abstractmethod
    def logger(self):
        pass

    def warning(self, msg):
        self.logger.warning(f"{self}: {msg}")

    def debug(self, msg):
        self.logger.debug(f"{self}: {msg}")

    def info(self, msg):
        self.logger.info(f"{self}: {msg}")

    def error(self, msg):
        self.logger.error(f"{self}: {msg}")

    def critical(self, msg):
        self.logger.critical(f"{self}: {msg}")
