import os
import subprocess

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "patch-legacy-util.sh")


def run(path):
    return subprocess.run(["sh", SCRIPT, str(path)], capture_output=True, text=True)


def test_patches_the_line_and_keeps_crlf(tmp_path):
    p = tmp_path / "util.lua"
    p.write_bytes(b"SHOW_DEBUG_LOG=false\r\n\r\n--comment\r\nALLOW_SETTING=false\r\n\r\n--ALLOW_SETTING=mg.request_info.remote_addr=='127.0.0.1'\r\n")
    r = run(p)
    assert r.returncode == 0, r.stderr
    lines = p.read_bytes().split(b"\r\n")
    assert lines[3] == (
        b"ALLOW_SETTING=edcb.GetPrivateProfile('LEGACY','ALLOW_SETTING','0','.provision/webui.ini')=='1'"
        b" --docker-mirakc-edcb: edcbctl allow-setting"
    )
    assert lines[5].startswith(b"--ALLOW_SETTING=")
    assert b"\n" not in p.read_bytes().replace(b"\r\n", b"")


def test_fails_without_the_line(tmp_path):
    p = tmp_path / "util.lua"
    p.write_bytes(b"ALLOW_SETTING=mg.request_info.remote_addr=='127.0.0.1'\r\n")
    r = run(p)
    assert r.returncode != 0 and "found 0" in r.stderr


def test_fails_with_two_lines(tmp_path):
    p = tmp_path / "util.lua"
    p.write_bytes(b"ALLOW_SETTING=false\nALLOW_SETTING=true\n")
    assert run(p).returncode != 0
