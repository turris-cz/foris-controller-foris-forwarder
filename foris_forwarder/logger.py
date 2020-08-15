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

    def warning(self, template, *args, **kwargs):
        self.logger.warning(f"%s: {template}", self, *args, **kwargs)

    def debug(self, template, *args, **kwargs):
        self.logger.debug(f"%s: {template}", self, *args, **kwargs)

    def info(self, template, *args, **kwargs):
        self.logger.info(f"%s: {template}", self, *args, **kwargs)

    def error(self, template, *args, **kwargs):
        self.logger.error(f"%s: {template}", self, *args, **kwargs)

    def critical(self, template, *args, **kwargs):
        self.logger.critical(f"%s: {template}", self, *args, **kwargs)
