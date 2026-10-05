#!/usr/bin/env python3
"""A fake "EpgDataCap_Bon -d <BonDriver> -chscan" for tests (standard library only).

Does what EDCB's channel scan leaves behind, without tuners: reads the
BonDriver's ini (<lib>/<BonDriver>.ini), gets /api/channels from the server it
names, numbers the spaces like BonDriver_LinuxMirakc (a new space whenever
the type changes) and writes

- Setting/<BonDriver without .so>(LinuxMirakc).ChSet4.txt, one row per
  service, UTF-8 with a BOM;
- Setting/ChSet5.txt, merged like EDCB does: the services found replace
  their entries, which resets the EPG and search flags to 1.

Environment:
    FAKE_EDCB_ROOT   EDCB root (default /var/local/edcb)
    FAKE_EDCB_LIB    BonDriver folder (default /usr/local/lib/edcb)
    FAKE_CHSCAN_LOG  append one line per run: "CHSCAN <BonDriver>"
    FAKE_CHSCAN      ok (default) | empty (no services found) | fail (exit
                     early, write nothing) | hang (never finish)
"""

import json
import os
import sys
import time
import urllib.request

BOM = b"\xef\xbb\xbf"


def read_ini(path):
    conf = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith(";"):
                conf[key.strip()] = value.strip().strip('"')
    return conf


def scan(conf):
    url = f"http://{conf['SERVER_HOST']}:{conf['SERVER_PORT']}/api/channels"
    with urllib.request.urlopen(url, timeout=5) as resp:
        channels = json.load(resp)
    rows = []
    space = -1
    previous = None
    ch = 0
    for c in channels:
        if c["type"] != previous:
            space += 1
            ch = 0
            previous = c["type"]
        for s in c["services"]:
            onid = s["networkId"]
            tsid = (onid * 16 + space * 256 + ch) & 0xFFFF
            rows.append((c["name"], s["name"], f"Fake {c['type']}", space, ch, onid, tsid, s["serviceId"]))
        ch += 1
    return rows


def merge_chset5(path, rows):
    entries = {}
    order = []
    bom = True
    try:
        with open(path, "rb") as f:
            data = f.read()
        bom = data.startswith(BOM) or not data
        for line in data.removeprefix(BOM).decode("utf-8").splitlines():
            f = line.split("\t")
            if len(f) >= 9:
                key = (int(f[2]), int(f[3]), int(f[4]))
                if key not in entries:
                    order.append(key)
                entries[key] = f
    except FileNotFoundError:
        pass
    added = False
    for _, service, network, _, _, onid, tsid, sid in rows:
        key = (onid, tsid, sid)
        if key not in entries:
            added = True
        entries[key] = [service, network, str(onid), str(tsid), str(sid), "1", "0", "1", "1"]
    keys = sorted(entries) if added else order
    body = "".join("\t".join(entries[k]) + "\n" for k in keys).encode()
    with open(path + ".tmp", "wb") as f:
        f.write((BOM if bom else b"") + body)
    os.replace(path + ".tmp", path)


def main(argv):
    if "-chscan" not in argv or "-d" not in argv:
        print("usage: fake_epgdatacap.py -d <BonDriver> -chscan", file=sys.stderr)
        return 2
    bon = argv[argv.index("-d") + 1]
    root = os.environ.get("FAKE_EDCB_ROOT", "/var/local/edcb")
    lib = os.environ.get("FAKE_EDCB_LIB", "/usr/local/lib/edcb")
    mode = os.environ.get("FAKE_CHSCAN", "ok")
    log = os.environ.get("FAKE_CHSCAN_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"CHSCAN {bon}\n")
    if mode == "fail":
        print("Failed to start channel scan")
        return 0
    if mode == "hang":
        while True:
            time.sleep(1)

    rows = scan(read_ini(os.path.join(lib, bon + ".ini"))) if mode != "empty" else []
    for i, row in enumerate(rows):
        # the status line EDCB rewrites with "\r", then the progress line
        print(f'\rSig:0.00 D:0 S:0 sp:{row[3]} ch:{row[4]} ChScan "{row[0]}" {i + 1}/{len(rows)} remain 0 sec', flush=True)
    setting = os.path.join(root, "Setting")
    os.makedirs(setting, exist_ok=True)
    stem = bon[: -len(".so")] if bon.endswith(".so") else bon
    body = "".join(
        f"{name}\t{service}\t{network}\t{space}\t{ch}\t{onid}\t{tsid}\t{sid}\t1\t0\t1\t0\n"
        for name, service, network, space, ch, onid, tsid, sid in rows
    )
    with open(os.path.join(setting, f"{stem}(LinuxMirakc).ChSet4.txt"), "wb") as f:
        f.write(BOM + body.encode())
    merge_chset5(os.path.join(setting, "ChSet5.txt"), rows)
    print("Completed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
