import socket
import threading

import pytest

from edcb_provision import healthcheck
from edcb_provision.ini import IniFile


def target(text):
    return healthcheck.http_target(IniFile(text))


def test_http_target():
    assert target("[SET]\n") is None
    assert target("[SET]\nEnableHttpSrv=0\nHttpPort=5510\n") is None
    assert target("[SET]\nEnableHttpSrv=1\n") == ("127.0.0.1", 5510, False)
    assert target("[SET]\nEnableHttpSrv=2\nHttpPort=5511s,5510\n") == ("127.0.0.1", 5511, True)
    assert target("[SET]\nEnableHttpSrv=1\nHttpPort=+5510,5520\n") == ("127.0.0.1", 5510, False)
    assert target("[SET]\nEnableHttpSrv=1\nHttpPort=192.168.0.2:5510\n") == ("192.168.0.2", 5510, False)
    assert target("[SET]\nEnableHttpSrv=1\nHttpPort=[::1]:5510r\n") == ("::1", 5510, False)
    # wildcards: loopback of the same family ("[::]:5510" is IPv6 only)
    assert target("[SET]\nEnableHttpSrv=1\nHttpPort=[::]:5510\n") == ("::1", 5510, False)
    assert target("[SET]\nEnableHttpSrv=1\nHttpPort=0.0.0.0:5510\n") == ("127.0.0.1", 5510, False)


def _server(handler):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        handler(conn)
        conn.close()
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1]


def test_probe_answer_and_acl_close():
    port = _server(lambda c: (c.recv(100), c.sendall(b"HTTP/1.1 200 OK\r\n\r\n")))
    healthcheck._probe("127.0.0.1", port, False)
    port = _server(lambda c: None)  # closed without an answer, like a denied ACL
    healthcheck._probe("127.0.0.1", port, False)


def test_probe_tls_closed_by_acl():
    # CivetWeb closes a denied connection before the TLS handshake
    port = _server(lambda c: None)
    healthcheck._probe("127.0.0.1", port, True)


def test_probe_refused():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(OSError):
        healthcheck._probe("127.0.0.1", port, False, timeout=1)
