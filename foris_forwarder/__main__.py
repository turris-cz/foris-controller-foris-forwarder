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

import argparse
import logging
import pathlib
import re
import typing

import pkg_resources

logger = logging.getLogger(__file__)


def read_passwd_file(path: str) -> typing.Sequence[str]:
    """ Returns username and password from passwd file
    """
    with pathlib.Path(path).open("r") as f:
        match = re.match(r"^([^:]+):(.*)$", f.readlines()[0][:-1])
        if not match:
            raise ValueError(f"Incorrect file format '{path}'")
        return match.groups()


def directory_path(path: str) -> pathlib.Path:
    """ Checks whether file exists and is a directory"""
    parsed = pathlib.Path(path)
    if not parsed.is_dir():
        raise ValueError(f"`{path}` is not a directory")

    return parsed


def init_logging(debug: bool):
    logging_format = "%(levelname)s:%(name)s:%(message)"
    if debug:
        logging.basicConfig(level=logging.DEBUG, format=f"%(threadName)s: {logging.BASIC_FORMAT}")
    else:
        logging.basicConfig(format=logging_format)


def main():
    dist = pkg_resources.get_distribution("foris-forwarder")
    version = dist.version if dist else "?"

    parser = argparse.ArgumentParser(prog="foris-netboot-observer")
    parser.add_argument("-d", "--debug", dest="debug", action="store_true", default=False)
    parser.add_argument("--version", action="version", version=version)
    parser.add_argument(
        "--controller-id", type=lambda x: re.match(r"[0-9a-zA-Z]{16}", x).group().upper(), help="local controller id",
    )
    parser.add_argument("--host", dest="host", default="localhost")
    parser.add_argument("--port", dest="port", type=int, default=1883)
    parser.add_argument(
        "--passwd-file",
        type=lambda x: read_passwd_file(x),
        help="path to passwd file (first record will be used to authenticate)",
        default=None,
    )
    parser.add_argument(
        "--uci-config-dir",
        type=lambda x: directory_path(x),
        help="path to oci configs",
        default=pathlib.Path("/etc/config"),
    )
    parser.add_argument(
        "--fosquitto-dir",
        type=lambda x: directory_path(x),
        help="path to fosquitto subordinates dir",
        default=pathlib.Path("/etc/fosquitto/bridges"),
    )

    options = parser.parse_args()
    init_logging(options.debug)

    logger.debug("Version %s" % version)
