from ipaddress import ip_address as ip

from foris_forwarder.supervisor import ForwarderSupervisor


def test_ip_workflow(forwarder, mosquitto_subordinate):
    # stop message bus
    mosquitto_subordinate[0].kill()
    mosquitto_subordinate[0].wait()

    fs = ForwarderSupervisor(forwarder)
    assert fs.netlocs == [(ip("127.0.0.1"), 11884)], "Localhost (forwarder fixture)"
    assert fs.current_netloc == (ip("127.0.0.1"), 11884)

    fs.zconf_update([ip("192.168.1.1")], 11883)
    assert fs.netlocs == [(ip("192.168.1.1"), 11883), (ip("127.0.0.1"), 11884)], "One addded"
    assert fs.current_netloc == (ip("127.0.0.1"), 11884)

    fs.zconf_update([ip("192.168.2.1"), ip("192.168.2.2")], 11880)
    assert fs.netlocs == [
        (ip("192.168.2.1"), 11880),
        (ip("192.168.2.2"), 11880),
        (ip("192.168.1.1"), 11883),
        (ip("127.0.0.1"), 11884),
    ], "Last added first"
    assert fs.current_netloc == (ip("127.0.0.1"), 11884)

    fs._netlocs[ip("192.168.2.1"), 11880].fail_count = 2
    assert fs.netlocs == [
        (ip("192.168.2.2"), 11880),
        (ip("192.168.1.1"), 11883),
        (ip("127.0.0.1"), 11884),
        (ip("192.168.2.1"), 11880),
    ], "Most attempts last"
    assert fs.current_netloc == (ip("127.0.0.1"), 11884)

    fs.check()
    assert fs.current_netloc == (ip("127.0.0.1"), 11884)

    # check whether next address will be used
    fs.current_netloc_start -= ForwarderSupervisor.NEXT_IP_TIMEOUT * 2
    fs.check()
    assert fs.current_netloc == (ip("192.168.2.2"), 11880)

    fs.terminate()
