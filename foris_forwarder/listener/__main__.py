#
# foris-forwarder
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

import argparse
import ipaddress
import logging
import time
import typing

import pkg_resources

from ..zconf import Listener

logger = logging.getLogger(__name__)


def main():
    dist = pkg_resources.get_distribution("foris-forwarder")
    version = dist.version if dist else "?"

    parser = argparse.ArgumentParser(prog="foris-forwarder-listener")
    parser.add_argument("--version", action="version", version=version)
    parser.add_argument("-d", "--debug", dest="debug", action="store_true", default=False)
    options = parser.parse_args()

    logging_format = "%(levelname)s:%(name)s:%(message)s"
    if options.debug:
        logging.basicConfig(level=logging.DEBUG, format=f"%(threadName)s: {logging.BASIC_FORMAT}")
    else:
        logging.basicConfig(format=logging_format)

    logger.info("Starting Foris Forwarder Listener (%s)" % version)

    # run listener
    listener = Listener()

    def handler_gen(name: str):
        def handler(controller_id: str, addresses: typing.List[ipaddress.IPv4Address] = [], port: int = 0):
            print(f"{name}: {controller_id} {addresses or ''} {port or ''}")

        return handler

    listener.set_add_service_handler(handler_gen("add"))
    listener.set_remove_service_handler(handler_gen("remove"))
    listener.set_update_service_handler(handler_gen("update"))

    while True:
        time.sleep(1)


if __file__ == "__main__":
    main()
