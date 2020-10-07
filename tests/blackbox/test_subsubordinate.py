"""
Subsubordinate forwarding Setup

* mqtt host bus
* mqtt subordinate bus
* mqtt subsubordinate bus
* foris-controller on subsubordinate bus
* client on host bus
* forwarder between host bus and subordinate bus
* forwarder subordinate bus and subsubordinate bus

"""


def test_request_reply(super_foris_sender, foris_controller):
    _, controller_id = foris_controller

    # sends request and should receive a reply
    super_foris_sender.send("about", "get", data=None, controller_id=controller_id)

    # no need to do any further checks
    # exception would be raised here


def test_notification(super_foris_listener, foris_controller):
    listener, output = super_foris_listener

    # check advertizements (should be sent every second)
    listener.timeout = 2.0
    listener.listen()

    assert len(output) > 1
