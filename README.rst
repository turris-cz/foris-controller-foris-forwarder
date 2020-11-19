Foris forwarder
===============
Forwards Foris MQTT messages from/to subordinate message bus. It is also capable of discovering subordinates in the network using Zeroconf.

Requirements
============

* python3
* pyuci
* zeroconf
* paho-mqtt

Installation
============

via pip::
    pip install .

Usage
=====

to start the app you can::

    foris-forwarder --controller-id 0000000A00000214 --port 11883 --passwd-file /etc/fosquitto/credentials.plain --uci-config-dir /etc/config --fosquitto-dir /etc/fosquitto/bridges


Note that you can send USR1 signal to print connection status to foris-forwarder console::

    kill -s USR1 <pid_of_foris_forwarder>


Developer Docs
==============

Architecture
------------

Foris Forwarder forwards messages between multiple mqtt buses.

It connects local message bus with remote message buses (subordinates).
Forwarder starts two mqtt clients (per subordinate) and
passes messages between these two clients.

Client to local message bus is using username+password authentication.
Client to remote message buses is secured using client certificate.

It also uses zeroconf to update IPs of remote message buses when disconnected.
(Note that foris-controller is used to send announcements via zeroconf)


Testing
-------

Should be triggered withing gitlab CI

Requirements
############

* mosquitto binary (for mocking mosquitto server)
* python >= 3.6

Installation
############

via pip::

    pip install .[dev]


pre-commit
##########

Is used to trigger all required linters (flake8, black, mypy, ...)
Error can be found before the changes are pushed to the server.
You just need to add precommit git hook for that::

    pre-commit install -t pre-push

pytest
######

To run the test you can simply run pytest in the project root::

    pytest

If you want to skip some slow tests you can run::

    pytest -m "not slow"

To display extra verbose output you can use::

    pytest --log-cli-level DEBUG
