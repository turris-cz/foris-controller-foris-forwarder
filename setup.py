#!/usr/bin/env python

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

from setuptools import setup

DESCRIPTION = """
Forwards Foris MQTT messages from/to subordinate message bus.
It is also capable of discovering subordinates in the network using Zeroconf.
"""

setup(
    name="foris-forwarder",
    version="0.0.0",
    author="CZ.NIC, z.s.p.o. (http://www.nic.cz/)",
    author_email="stepan.henek@nic.cz",
    packages=["foris_forwarder"],
    url="https://gitlab.nic.cz/turris/foris-controller/foris-forwarder",
    license="GPLv3",
    description=DESCRIPTION,
    long_description=open("README.rst").read(),
    install_requires=["paho-mqtt", "zeroconf", "pyuci @ git+https://gitlab.labs.nic.cz/turris/pyuci.git",],
    setup_requires=["pytest-runner"],
    extras_require={"dev": ["pre-commit", "flake8", "black", "isort",]},
    tests_require=["pytest",],
    entry_points={"console_scripts": ["foris-forwarder = foris_forwarder.__main__:main"]},
)
