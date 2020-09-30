from ipaddress import ip_address as ip

from foris_forwarder.supervisor import ForwarderSupervisor


def test_ip_workflow(forwarder, mosquitto_subordinate):
    # stop message bus
    mosquitto_subordinate[0].kill()
    mosquitto_subordinate[0].wait()

    fs = ForwarderSupervisor(forwarder)
    assert fs.ips == [ip("127.0.0.1")], "Localhost (forwarder fixture)"
    assert fs.current_ip == ip("127.0.0.1")

    fs.zconf_update([ip("192.168.1.1")])
    assert fs.ips == [ip("192.168.1.1"), ip("127.0.0.1")], "One addded"
    assert fs.current_ip == ip("127.0.0.1")

    fs.zconf_update([ip("192.168.2.1"), ip("192.168.2.2")])
    assert fs.ips == [ip("192.168.2.1"), ip("192.168.2.2"), ip("192.168.1.1"), ip("127.0.0.1")], "Sonner added first"
    assert fs.current_ip == ip("127.0.0.1")

    fs._ips[ip("192.168.2.1")].fail_count = 2
    assert fs.ips == [ip("192.168.2.2"), ip("192.168.1.1"), ip("127.0.0.1"), ip("192.168.2.1")], "Most attempts last"
    assert fs.current_ip == ip("127.0.0.1")

    fs.check()
    assert fs.current_ip == ip("127.0.0.1")

    # check whether next address will be used
    fs.current_ip_start -= ForwarderSupervisor.NEXT_IP_TIMEOUT * 2
    fs.check()
    assert fs.current_ip == ip("192.168.2.2")

    fs.terminate()
