"""Channel files of EDCB: ChSet4 (per BonDriver) and ChSet5 (all services).

Both are tab separated, one service per line, UTF-8 with a BOM when EDCB
creates them (Common/ParseText.h). EDCB only reads lines that contain a tab;
the others are dropped here as well.

ChSet4 columns: channel name, service name, network name, space, ch, ONID,
TSID, SID, service type, partial, view flag, remote control ID.
ChSet5 columns: service name, network name, ONID, TSID, SID, service type,
partial, EPG capture flag, search flag (Common/ParseTextInstances.cpp).
"""

import hashlib
import json
import re

BOM = b"\xef\xbb\xbf"

# ChSet4 / ChSet5 column indexes
C4_SPACE = 3
C5_ONID, C5_TSID, C5_SID = 2, 3, 4
C5_EPGCAP, C5_SEARCH = 7, 8

TERRESTRIAL = {"GR"}
SATELLITE = {"BS", "CS"}


_INT_RE = re.compile(rb"\s*([+-]?[0-9]+)")


def _int(field):
    """Like EDCB's NextTokenToInt (wcstol): the leading number, otherwise 0."""
    m = _INT_RE.match(field)
    return int(m.group(1)) if m else 0


def split_lines(data):
    """Return (has_bom, lines). Lines keep their line endings; lines without
    a tab (which EDCB ignores) are dropped."""
    has_bom = data.startswith(BOM)
    if has_bom:
        data = data[len(BOM) :]
    lines = [line for line in data.splitlines(keepends=True) if b"\t" in line]
    return has_bom, lines


def _fields(line):
    return line.rstrip(b"\r\n").split(b"\t")


def _ending(lines):
    """The line ending used by the file (LF when unknown)."""
    for line in lines:
        if line.endswith(b"\r\n"):
            return b"\r\n"
        if line.endswith(b"\n"):
            return b"\n"
    return b"\n"


def join_lines(lines, ending=b"\n"):
    out = []
    for line in lines:
        if not line.endswith(b"\n"):
            line += ending
        out.append(line)
    return BOM + b"".join(out)


# ----- spaces -----


def spaces(channels):
    """The channel type of every tuning space, as the BonDriver assigns them.

    BonDriver_LinuxMirakc (InitChannel) starts a new space whenever the type
    differs from the previous channel of /api/channels, so GR, BS, GR gives
    three spaces (facts.md F4).
    """
    result = []
    previous = None
    for c in channels:
        if c["type"] != previous:
            result.append(c["type"])
            previous = c["type"]
    return result


def channels_hash(channels):
    """Hash of the type and channel order of /api/channels (design.md 8.1)."""
    data = json.dumps([[c["type"], c["channel"]] for c in channels], separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


# ----- ChSet4 -----


def count_rows(data):
    return len(split_lines(data)[1])


def split(scan, space_types):
    """Split a scanned ChSet4 by kind (design.md 8.3).

    scan: the ChSet4 written by the channel scan (bytes).
    space_types: the result of spaces() for /api/channels at scan time.
    Returns ({"M": bytes, "T": bytes, "S": bytes}, rows per kind, warnings).
    M has every row; T the rows of terrestrial spaces; S the rows of
    satellite spaces. Rows are copied unchanged (space and ch included).
    """
    _, lines = split_lines(scan)
    ending = _ending(lines)
    rows = {"M": [], "T": [], "S": []}
    unknown = set()
    for line in lines:
        f = _fields(line)
        space = _int(f[C4_SPACE]) if len(f) > C4_SPACE else -1
        rows["M"].append(line)
        if 0 <= space < len(space_types):
            t = space_types[space]
            if t in TERRESTRIAL:
                rows["T"].append(line)
            elif t in SATELLITE:
                rows["S"].append(line)
        else:
            unknown.add(space)
    warnings = []
    if unknown:
        warnings.append(
            f"space {', '.join(str(s) for s in sorted(unknown))} of the scan is not in /api/channels; "
            "those rows are kept for the dual tuners only"
        )
    files = {kind: join_lines(lines_, ending) for kind, lines_ in rows.items()}
    return files, {kind: len(v) for kind, v in rows.items()}, warnings


# ----- ChSet5 -----


def _service_key(f):
    return (_int(f[C5_ONID]), _int(f[C5_TSID]), _int(f[C5_SID]))


def service_flags(data):
    """{(ONID, TSID, SID): (EPG capture flag, search flag)} of a ChSet5."""
    flags = {}
    for line in split_lines(data)[1]:
        f = _fields(line)
        if len(f) > C5_SEARCH:
            flags.setdefault(_service_key(f), (f[C5_EPGCAP].strip(), f[C5_SEARCH].strip()))
    return flags


def restore_flags(data, flags):
    """Put the given flags back into a ChSet5.

    The channel scan of EDCB replaces the entries of the services it finds,
    which resets their EPG capture and search flags (ChSetUtil.cpp SaveChSet,
    CParseChText5::AddCh). Returns (new bytes, number of services changed).
    """
    has_bom = data.startswith(BOM)
    body = data[len(BOM) :] if has_bom else data
    out = []
    changed = 0
    for line in body.splitlines(keepends=True):
        f = _fields(line)
        if b"\t" in line and len(f) > C5_SEARCH:
            old = flags.get(_service_key(f))
            if old is not None and (f[C5_EPGCAP].strip(), f[C5_SEARCH].strip()) != old:
                f[C5_EPGCAP], f[C5_SEARCH] = old
                ending = line[len(line.rstrip(b"\r\n")) :]
                line = b"\t".join(f) + ending
                changed += 1
        out.append(line)
    return (BOM if has_bom else b"") + b"".join(out), changed
