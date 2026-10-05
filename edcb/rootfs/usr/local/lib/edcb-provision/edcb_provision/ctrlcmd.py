"""A small client of EpgTimerSrv's control commands, for "edcbctl status".

On Linux, EpgTimerSrv listens on the UNIX socket <EDCB root>/EpgTimerSrvPipe
(Common/SendCtrlCmd.cpp, PipeServer.cpp). A request is the command and the
size of its data (both 32-bit little endian) followed by the data; the reply
is the result (1 = success), the size and the data.

Values are serialized as in Common/CtrlCmdUtil.cpp: integers little endian;
a string is its size in bytes (including the size field) and UTF-16LE text
ending with NUL; a struct starts with its size (including the size field);
a vector starts with its size and the number of items. The sizes let a
reader skip the fields it does not need.
"""

import datetime
import os
import socket
import struct
import time

from . import ini
from .config import SRV_INI

SOCKET_NAME = "EpgTimerSrvPipe"
CMD_SUCCESS = 1
CMD2_EPG_SRV_ENUM_RESERVE = 1011
CMD2_EPG_SRV_ENUM_TUNER_PROCESS = 1066
CMD2_EPG_SRV_EPG_CAP_NOW = 1053
# Common/ErrDef.h: busy (still loading the EPG data, ...)
CMD_ERR_BUSY = 208
TIMEOUT = 5

# REC_SETTING_DATA.recMode: 0-4 record; IsNoRec() is recMode / 5 % 2 != 0
DIV_RECMODE = 5


class CtrlCmdError(Exception):
    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result


def call(root, cmd, data=b"", timeout=TIMEOUT):
    """Send one command. Return the reply data; raise CtrlCmdError or OSError."""
    path = os.path.join(root, SOCKET_NAME)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(path)
        s.sendall(struct.pack("<II", cmd, len(data)) + data)
        head = _recv(s, 8)
        result, size = struct.unpack("<II", head)
        body = _recv(s, size)
    if result != CMD_SUCCESS:
        raise CtrlCmdError(f"command {cmd} failed with {result}", result)
    return body


def _recv(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise CtrlCmdError("the connection was closed early")
        buf += chunk
    return buf


class Reader:
    def __init__(self, data, pos=0, end=None):
        self.data = data
        self.pos = pos
        self.end = len(data) if end is None else end

    def _take(self, fmt):
        size = struct.calcsize(fmt)
        if self.pos + size > self.end:
            raise CtrlCmdError("truncated reply")
        (value,) = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return value

    def u8(self):
        return self._take("<B")

    def u16(self):
        return self._take("<H")

    def u32(self):
        return self._take("<I")

    def i32(self):
        return self._take("<i")

    def u64(self):
        return self._take("<Q")

    def _sized(self, header):
        """Return the end of a sized value that starts at pos."""
        start = self.pos
        size = self.u32()
        if size < header or start + size > self.end:
            raise CtrlCmdError("invalid size in reply")
        return start + size

    def wstring(self):
        end = self._sized(4)
        text = self.data[self.pos : end].decode("utf-16-le", "replace")
        self.pos = end
        return text.split("\0", 1)[0]

    def systemtime(self):
        if self.pos + 16 > self.end:
            raise CtrlCmdError("truncated reply")
        y, mo, _dow, d, h, mi, s, _ms = struct.unpack_from("<8H", self.data, self.pos)
        self.pos += 16
        try:
            return datetime.datetime(y, mo, d, h, mi, s)
        except ValueError:
            return None

    def struct(self):
        """Enter a struct: return a Reader limited to it and move past it."""
        start = self.pos
        end = self._sized(4)
        inner = Reader(self.data, start + 4, end)
        self.pos = end
        return inner

    def vector(self, item):
        end = self._sized(8)
        count = self.u32()
        inner = Reader(self.data, self.pos, end)
        items = [item(inner) for _ in range(count)]
        self.pos = end
        return items


def _reserve(r):
    s = r.struct()
    title = s.wstring()
    start = s.systemtime()
    duration = s.u32()
    station = s.wstring()
    onid, tsid, sid, eid = s.u16(), s.u16(), s.u16(), s.u16()
    s.wstring()  # comment
    reserve_id = s.u32()
    s.u8()  # unused
    s.u8()  # overlapMode
    s.wstring()  # unused
    s.systemtime()  # startTimeEpg
    rs = s.struct()  # REC_SETTING_DATA
    rec_mode = rs.u8()
    rs.u8()  # priority
    rs.u8()  # tuijyuuFlag
    rs.u32()  # serviceMode
    rs.u8()  # pittariFlag
    rs.wstring()  # batFilePath
    rs.vector(Reader.struct)  # recFolderList
    rs.u8()  # suspendMode
    rs.u8()  # rebootFlag
    rs.u8()  # useMargineFlag
    rs.i32()  # startMargine
    rs.i32()  # endMargine
    rs.u8()  # continueRecFlag
    rs.u8()  # partialRecFlag
    # 0: any tuner; otherwise the reservation is fixed to this tuner
    tuner_id = rs.u32()
    return {
        "id": reserve_id,
        "title": title,
        "start": start,
        "duration": duration,
        "station": station,
        "service": (onid, tsid, sid),
        "event": eid,
        "enabled": rec_mode // DIV_RECMODE % 2 == 0,
        "tuner_id": tuner_id,
    }


def _tuner_process(r):
    s = r.struct()
    tuner_id = s.u32()
    process_id = s.i32()
    s.u64()  # drop
    s.u64()  # scramble
    s.u32()  # signal level
    space, ch, onid, tsid = s.i32(), s.i32(), s.i32(), s.i32()
    rec, epg = s.u8(), s.u8()
    return {
        "tuner_id": tuner_id,
        "process_id": process_id,
        "space": space,
        "ch": ch,
        "onid": onid,
        "tsid": tsid,
        "recording": rec != 0,
        "epg_capture": epg != 0,
    }


def reserves(root):
    return Reader(call(root, CMD2_EPG_SRV_ENUM_RESERVE)).vector(_reserve)


def tuner_processes(root):
    """The tuners that are not idle (ReserveManager.cpp GetTunerProcessStatusAll)."""
    return Reader(call(root, CMD2_EPG_SRV_ENUM_TUNER_PROCESS)).vector(_tuner_process)


def request_epg_capture(root, *, wait=600, interval=5, log):
    """Ask EpgTimerSrv to capture EPG now, waiting until it is ready.

    Return True once EpgTimerSrv answered (started, or declined because it
    already captures or has no tuner for it), False if it never answered.
    """
    deadline = time.monotonic() + wait
    while True:
        try:
            call(root, CMD2_EPG_SRV_EPG_CAP_NOW)
            log("EPG capture requested (EpgTimerSrv starts it in about 10 s)")
            return True
        except CtrlCmdError as e:
            if e.result != CMD_ERR_BUSY:
                log(f"EpgTimerSrv did not start an EPG capture ({e}): it captures already, or no tuner has GetEpg=1")
                return True
        except OSError:
            pass  # not listening yet
        if time.monotonic() >= deadline:
            log(f"EpgTimerSrv did not accept an EPG capture within {wait} s")
            return False
        time.sleep(interval)


# ----- edcbctl status -----


def _fmt_time(t):
    return t.strftime("%Y-%m-%d %H:%M") if t else "?"


def _fmt_span(seconds):
    minutes = int(seconds) // 60
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _bondriver_names(root):
    """{Priority: BonDriver} from EpgTimerSrv.ini; tuner IDs are Priority << 16 | n."""
    path = os.path.join(root, SRV_INI)
    names = {}
    try:
        srv = ini.IniFile.load(path) if os.path.isfile(path) else ini.IniFile()
    except OSError:
        return names
    for section in srv.section_names():
        if section.lower().endswith(".so"):
            v = (srv.get(section, "Priority") or "0").strip()
            if v.isdigit():
                names.setdefault(int(v), section)
    return names


def summary(root, now=None):
    """Return (lines, recording?) or raise OSError / CtrlCmdError."""
    now = now or datetime.datetime.now()
    procs = tuner_processes(root)
    items = reserves(root)
    names = _bondriver_names(root)
    lines = []
    recording = any(p["recording"] for p in procs)
    lines.append(f"recording: {'yes' if recording else 'no'}")
    for p in procs:
        what = "recording" if p["recording"] else "EPG capture" if p["epg_capture"] else "in use"
        bon = names.get(p["tuner_id"] >> 16, f"priority {p['tuner_id'] >> 16}")
        lines.append(f"  {bon} #{p['tuner_id'] & 0xFFFF}: {what}")
    enabled = [x for x in items if x["enabled"] and x["start"]]
    running = [
        x for x in enabled if x["start"] <= now < x["start"] + datetime.timedelta(seconds=x["duration"])
    ]
    for x in sorted(running, key=lambda x: x["start"]):
        end = x["start"] + datetime.timedelta(seconds=x["duration"])
        lines.append(f"  reserved now: {_fmt_time(x['start'])} - {end:%H:%M} {x['title']} ({x['station']})")
    upcoming = sorted((x for x in enabled if x["start"] > now), key=lambda x: x["start"])
    if upcoming:
        x = upcoming[0]
        lines.append(
            f"next reservation: {_fmt_time(x['start'])} (in {_fmt_span((x['start'] - now).total_seconds())}) "
            f"{x['title']} ({x['station']})"
        )
    else:
        lines.append("next reservation: none")
    lines.append(f"reservations: {len(enabled)} enabled, {len(items) - len(enabled)} disabled")
    return lines, recording or bool(running)
