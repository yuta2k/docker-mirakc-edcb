"""Docker HEALTHCHECK: EpgTimerSrv is running and, if enabled, HTTP answers.

The HTTP check passes when the port accepts a connection. A connection that
the access control list closes without an answer still proves the server is
up, so a user who removed 127.0.0.1 from HttpAccessControlList does not turn
the container unhealthy.
"""

import os
import re
import socket
import ssl
import sys

from . import ini

_PORT_RE = re.compile(r"\+?(?:(\[[^\]]+\]|[0-9.]+):)?(\d+)([a-z]*)")


def _running(name="EpgTimerSrv"):
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() == name:
                    return True
        except OSError:
            continue
    return False


def _scanning():
    """True while EpgDataCap_Bon scans channels (the first start waits for it)."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                args = f.read().split(b"\0")
        except OSError:
            continue
        if args and os.path.basename(args[0]) == b"EpgDataCap_Bon" and b"-chscan" in args:
            return True
    return False


def http_target(srv_ini):
    """Return (host, port, tls) of the first HTTP port, or None if HTTP is off."""
    enable = srv_ini.get("SET", "EnableHttpSrv")
    try:
        if enable is None or int(enable) == 0:
            return None
    except ValueError:
        return None
    spec = srv_ini.get("SET", "HttpPort") or "5510"
    first = spec.split(",")[0].strip()
    m = _PORT_RE.fullmatch(first)
    if not m:
        return None
    host = (m.group(1) or "127.0.0.1").strip("[]")
    # a wildcard address: connect over loopback of the same family
    # ("[::]:5510" listens on IPv6 only; "+5510" on both)
    if host == "0.0.0.0":
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    return host, int(m.group(2)), "s" in m.group(3)


def _probe(host, port, tls, timeout=5):
    # The access control list is applied before the TLS handshake and closes the
    # connection without an answer; a connection closed that way counts as up.
    closed = (ConnectionResetError, BrokenPipeError, ssl.SSLEOFError, ssl.SSLZeroReturnError)
    with socket.create_connection((host, port), timeout=timeout) as sock:
        try:
            if tls:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                sock = ctx.wrap_socket(sock)
            sock.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
            sock.recv(64)
        except closed:
            pass


def main(root="/var/local/edcb"):
    if not _running():
        if _scanning():
            # a first scan can take longer than the start period
            print("EpgTimerSrv is not running yet: scanning channels")
            return 0
        print("EpgTimerSrv is not running")
        return 1
    try:
        srv_ini = ini.IniFile.load(os.path.join(root, "EpgTimerSrv.ini"))
    except OSError:
        srv_ini = ini.IniFile()
    target = http_target(srv_ini)
    if target is None:
        print("EpgTimerSrv is running (HTTP is off)")
        return 0
    host, port, tls = target
    try:
        _probe(host, port, tls)
    except (OSError, ssl.SSLError) as e:
        print(f"EpgTimerSrv is running but HTTP {host}:{port} does not answer: {e}")
        return 1
    print(f"EpgTimerSrv is running, HTTP {host}:{port} answers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
