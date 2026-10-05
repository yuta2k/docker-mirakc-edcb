#!/usr/bin/env python3
"""A fake Mirakurun / mirakc API server for tests (standard library only).

Serves fixed data for /api/tuners, /api/channels, /api/services, /api/status
and /api/version, and an endless stream of TS null packets for
/api/channels/<type>/<channel>/stream. Every request is logged as one line:

    ACCESS <method> <path> priority=<X-Mirakurun-Priority>

Used by pytest (FakeMirakurun) and by tests/integration (run as a script):

    python3 fake_mirakurun.py --port 40772 --scenario split [--log FILE]
"""

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# TS null packet (PID 0x1FFF)
NULL_PACKET = b"\x47\x1f\xff\x10" + b"\xff" * 184


def _tuner(index, types):
    return {
        "index": index,
        "name": f"tuner{index}",
        "types": types,
        "command": "",
        "pid": None,
        "users": [],
        "isAvailable": True,
        "isRemote": False,
        "isFree": True,
        "isUsing": False,
        "isFault": False,
    }


def _channel(type_, channel, name, services):
    return {
        "type": type_,
        "channel": channel,
        "name": name,
        "services": [
            {"id": nid * 100000 + sid, "serviceId": sid, "networkId": nid, "name": sname}
            for nid, sid, sname in services
        ],
    }


_GR = [
    _channel("GR", "27", "GR27", [(0x7FE0, 1024, "GR Service A")]),
    _channel("GR", "26", "GR26", [(0x7FE1, 1032, "GR Service B")]),
]
_BS = [
    _channel("BS", "BS01_0", "BS01_0", [(4, 101, "BS Service A")]),
    _channel("BS", "BS03_1", "BS03_1", [(4, 211, "BS Service B")]),
]
_CS = [
    _channel("CS", "CS2", "CS2", [(6, 296, "CS Service A")]),
]
_SKY = [
    _channel("SKY", "SKY1", "SKY1", [(1, 1001, "SKY Service A")]),
]

# Tuner layouts. "expected" is the classification of docs/v2/design.md 7.2
# (M: GR and BS/CS, T: GR only, S: BS/CS only; others are not counted).
SCENARIOS = {
    # tuners that receive both terrestrial and satellite only
    "dual": {
        "tuners": [_tuner(0, ["GR", "BS", "CS"]), _tuner(1, ["GR", "BS", "CS"])],
        "channels": _GR + _BS + _CS,
        "expected": {"M": 2, "T": 0, "S": 0},
    },
    # terrestrial-only and satellite-only tuners
    "split": {
        "tuners": [
            _tuner(0, ["GR"]),
            _tuner(1, ["GR"]),
            _tuner(2, ["GR"]),
            _tuner(3, ["BS", "CS"]),
            _tuner(4, ["BS", "CS"]),
        ],
        "channels": _GR + _BS + _CS,
        "expected": {"M": 0, "T": 3, "S": 2},
    },
    # all three kinds, including a tuner with BS but not CS
    "mixed": {
        "tuners": [
            _tuner(0, ["GR", "BS", "CS"]),
            _tuner(1, ["GR"]),
            _tuner(2, ["BS"]),
            _tuner(3, ["CS"]),
            _tuner(4, ["GR", "CS"]),
        ],
        "channels": _GR + _BS + _CS,
        "expected": {"M": 2, "T": 1, "S": 2},
    },
    # SKY-only tuners are not counted
    "sky": {
        "tuners": [_tuner(0, ["GR"]), _tuner(1, ["SKY"]), _tuner(2, ["BS", "CS", "SKY"])],
        "channels": _GR + _BS + _CS + _SKY,
        "expected": {"M": 0, "T": 1, "S": 1},
    },
}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "fake-mirakurun"

    def log_message(self, fmt, *args):  # replaced by _access()
        pass

    def _access(self):
        fake = self.server.fake
        priority = self.headers.get("X-Mirakurun-Priority", "-")
        line = f"ACCESS {self.command} {self.path} priority={priority}"
        with fake.lock:
            fake.requests.append(self.path)
            if fake.log:
                fake.log.write(line + "\n")
                fake.log.flush()

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._access()
        fake = self.server.fake
        if fake.delay:
            time.sleep(fake.delay)
        data = fake.data
        path = self.path.split("?", 1)[0]
        if path == "/api/tuners":
            return self._json(data["tuners"])
        if path == "/api/channels":
            return self._json(data["channels"])
        if path == "/api/services":
            services = []
            for ch in data["channels"]:
                for s in ch["services"]:
                    services.append({**s, "channel": {"type": ch["type"], "channel": ch["channel"]}})
            return self._json(services)
        if path == "/api/status":
            return self._json({"version": "fake", "process": {"pid": 0}})
        if path == "/api/version":
            return self._json({"current": "fake", "latest": "fake"})
        parts = path.split("/")
        # /api/channels/<type>/<channel>/stream
        if len(parts) == 6 and parts[1:3] == ["api", "channels"] and parts[5] == "stream":
            if not any(c["type"] == parts[3] and c["channel"] == parts[4] for c in data["channels"]):
                return self.send_error(404)
            return self._stream()
        self.send_error(404)

    def _stream(self):
        fake = self.server.fake
        with fake.lock:
            fake.streams += 1
            drop = fake.drop_after if fake.streams <= fake.drop_count else None
        self.send_response(200)
        self.send_header("Content-Type", "video/MP2T")
        self.end_headers()
        chunk = NULL_PACKET * 64
        sent = 0
        try:
            while not fake.stopping.is_set():
                if drop is not None and sent >= drop:
                    # drop the connection, like a restarted server
                    return
                self.wfile.write(chunk)
                sent += len(chunk)
                time.sleep(0.01)
        except (BrokenPipeError, ConnectionResetError):
            pass


class FakeMirakurun:
    """The server, run in a background thread.

    scenario: a key of SCENARIOS.
    drop_after / drop_count: the first drop_count streams are closed by the
        server after drop_after bytes (to test reconnecting).
    delay: seconds to wait before every response (to test time-outs).
    """

    def __init__(self, scenario="dual", host="127.0.0.1", port=0, *, drop_after=None, drop_count=1, delay=0, log=None):
        self.data = SCENARIOS[scenario]
        self.drop_after = drop_after
        self.drop_count = drop_count if drop_after is not None else 0
        self.delay = delay
        self.log = log
        self.lock = threading.Lock()
        self.requests = []
        self.streams = 0
        self.stopping = threading.Event()
        self.httpd = ThreadingHTTPServer((host, port), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.fake = self
        self.thread = None

    @property
    def port(self):
        return self.httpd.server_address[1]

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.stopping.set()
        self.httpd.shutdown()
        self.httpd.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=40772)
    p.add_argument("--scenario", choices=sorted(SCENARIOS), default="dual")
    p.add_argument("--drop-after", type=int, help="close the first stream(s) after this many bytes")
    p.add_argument("--drop-count", type=int, default=1, help="how many streams --drop-after applies to")
    p.add_argument("--delay", type=float, default=0, help="seconds to wait before every response")
    p.add_argument("--log", help="append the access log to this file (default: standard output)")
    args = p.parse_args(argv)
    log = open(args.log, "a", encoding="utf-8") if args.log else sys.stdout
    fake = FakeMirakurun(
        args.scenario,
        args.host,
        args.port,
        drop_after=args.drop_after,
        drop_count=args.drop_count,
        delay=args.delay,
        log=log,
    )
    print(f"fake-mirakurun: listening on {args.host}:{fake.port} (scenario {args.scenario})", file=sys.stderr, flush=True)
    try:
        fake.httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
