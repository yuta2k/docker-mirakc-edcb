"""edcbctl status against a fake EpgTimerSrv control socket.

The replies are built like Common/CtrlCmdUtil.cpp writes them (WriteVALUE).
"""

import datetime
import os
import socket
import struct
import threading

import pytest

from edcb_provision import cli, ctrlcmd


def u8(v):
    return struct.pack("<B", v)


def u16(v):
    return struct.pack("<H", v)


def u32(v):
    return struct.pack("<I", v)


def i32(v):
    return struct.pack("<i", v)


def u64(v):
    return struct.pack("<Q", v)


def wstring(s):
    body = (s + "\0").encode("utf-16-le")
    return u32(4 + len(body)) + body


def systemtime(t):
    return struct.pack("<8H", t.year, t.month, (t.weekday() + 1) % 7, t.day, t.hour, t.minute, t.second, 0)


def sized(body):
    return u32(4 + len(body)) + body


def vector(items):
    body = b"".join(items)
    return u32(8 + len(body)) + u32(len(items)) + body


def rec_setting(rec_mode):
    # recMode, priority, tuijyuuFlag, serviceMode, pittariFlag, batFilePath, ... (only recMode is read)
    return sized(u8(rec_mode) + u8(2) + u8(1) + u32(0) + u8(0) + wstring("") + vector([]) + u8(0) + u8(0))


def reserve(reserve_id, title, start, minutes, station="Station", rec_mode=1, ver=5):
    body = (
        wstring(title)
        + systemtime(start)
        + u32(minutes * 60)
        + wstring(station)
        + u16(32736)
        + u16(32736)
        + u16(1024)
        + u16(0xFFFF)
        + wstring("comment")
        + u32(reserve_id)
        + u8(0)
        + u8(0)
        + wstring("")
        + systemtime(start)
        + rec_setting(rec_mode)
        + u32(0)
    )
    if ver >= 5:
        body += vector([wstring("file.ts")]) + u32(0)
    return sized(body)


def tuner(tuner_id, rec=0, epg=0):
    return sized(
        u32(tuner_id) + i32(1234) + u64(0) + u64(0) + u32(0) + i32(0) + i32(1) + i32(32736) + i32(32736) + u8(rec) + u8(epg) + u16(0)
    )


class FakeSrv:
    """Answers the control commands on <root>/EpgTimerSrvPipe."""

    def __init__(self, root, replies):
        self.replies = replies
        self.requests = []
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(os.path.join(root, ctrlcmd.SOCKET_NAME))
        self.sock.listen(4)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                cmd, size = struct.unpack("<II", conn.recv(8))
                self.requests.append(cmd)
                result, data = self.replies.get(cmd, (203, b""))
                conn.sendall(struct.pack("<II", result, len(data)) + data)

    def close(self):
        self.sock.close()


@pytest.fixture
def root(tmp_path):
    # AF_UNIX paths are limited to about 100 bytes
    d = tmp_path / "r"
    d.mkdir()
    if len(str(d)) > 80:
        pytest.skip("temporary path too long for a UNIX socket")
    return str(d)


NOW = datetime.datetime(2026, 10, 5, 20, 0, 0)


def test_summary_idle_with_next_reservation(root):
    srv = FakeSrv(
        root,
        {
            ctrlcmd.CMD2_EPG_SRV_ENUM_TUNER_PROCESS: (1, vector([])),
            ctrlcmd.CMD2_EPG_SRV_ENUM_RESERVE: (
                1,
                vector(
                    [
                        reserve(3, "Later", NOW + datetime.timedelta(days=2), 30),
                        reserve(2, "Next", NOW + datetime.timedelta(hours=1, minutes=5), 30, "ＮＨＫ"),
                        reserve(4, "Disabled", NOW + datetime.timedelta(minutes=10), 30, rec_mode=5),
                        reserve(5, "Past", NOW - datetime.timedelta(hours=2), 30),
                    ]
                ),
            ),
        },
    )
    try:
        lines, busy = ctrlcmd.summary(root, now=NOW)
    finally:
        srv.close()
    assert busy is False
    assert lines == [
        "recording: no",
        "next reservation: 2026-10-05 21:05 (in 1h 5m) Next (ＮＨＫ)",
        "reservations: 3 enabled, 1 disabled",
    ]


def test_summary_recording(root):
    with open(os.path.join(root, "EpgTimerSrv.ini"), "w") as f:
        f.write("[BonDriver_LinuxMirakc.so]\nCount=2\nPriority=0\n[BonDriver_LinuxMirakc_T.so]\nCount=1\nPriority=1\n")
    srv = FakeSrv(
        root,
        {
            ctrlcmd.CMD2_EPG_SRV_ENUM_TUNER_PROCESS: (1, vector([tuner(0x00000002, rec=1), tuner(0x00010001, epg=1)])),
            # an older EpgTimerSrv (CMD_VER < 5) writes no file name list; the size skips it either way
            ctrlcmd.CMD2_EPG_SRV_ENUM_RESERVE: (1, vector([reserve(7, "Now", NOW - datetime.timedelta(minutes=10), 30, ver=0)])),
        },
    )
    try:
        lines, busy = ctrlcmd.summary(root, now=NOW)
    finally:
        srv.close()
    assert busy is True
    assert lines == [
        "recording: yes",
        "  BonDriver_LinuxMirakc.so #2: recording",
        "  BonDriver_LinuxMirakc_T.so #1: EPG capture",
        "  reserved now: 2026-10-05 19:50 - 20:20 Now (Station)",
        "next reservation: none",
        "reservations: 1 enabled, 0 disabled",
    ]


def test_failed_command_and_truncated_reply(root):
    srv = FakeSrv(
        root,
        {
            ctrlcmd.CMD2_EPG_SRV_ENUM_TUNER_PROCESS: (1, vector([tuner(1)])[:-3]),
        },
    )
    try:
        with pytest.raises(ctrlcmd.CtrlCmdError):
            ctrlcmd.tuner_processes(root)
        with pytest.raises(ctrlcmd.CtrlCmdError):
            ctrlcmd.reserves(root)  # not answered: 203
    finally:
        srv.close()


def test_status_command_without_epgtimersrv(root, capsys):
    assert cli.main(["status"], env={"EDCB_PROVISION_ROOT": root}) == 1
    assert "cannot ask" in capsys.readouterr().out
