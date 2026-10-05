import io
import os
import sys

import pytest
from fake_mirakurun import SCENARIOS, FakeMirakurun

from edcb_provision import chset, channels, provision
from edcb_provision.state import State

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE_SCAN = f"{sys.executable} {os.path.join(HERE, 'fake_epgdatacap.py')}"
CHSET5 = os.path.join("Setting", "ChSet5.txt")


class Capture(provision.Reporter):
    def __init__(self):
        super().__init__(io.StringIO(), io.StringIO())

    @property
    def lines(self):
        return self.out.getvalue().splitlines()

    @property
    def warning_lines(self):
        return self.err.getvalue().splitlines()


@pytest.fixture
def fake():
    servers = []

    def start(scenario="dual", **kw):
        s = FakeMirakurun(scenario, **kw).start()
        servers.append(s)
        return s

    yield start
    for s in servers:
        s.stop()


@pytest.fixture
def scan_env(tree, tmp_path):
    """Environment that makes the provisioning use the fake EpgDataCap_Bon."""
    log = tmp_path / "chscan.log"
    return {
        "EDCB_PROVISION_FETCH_TIMEOUT": "10",
        "EDCB_PROVISION_EPGDATACAP": FAKE_SCAN,
        "FAKE_EDCB_ROOT": tree.root,
        "FAKE_EDCB_LIB": tree.lib,
        "FAKE_CHSCAN_LOG": str(log),
    }


def scans(env):
    """The BonDrivers the fake EpgDataCap_Bon was run with."""
    try:
        with open(env["FAKE_CHSCAN_LOG"], encoding="utf-8") as f:
            return [line.split()[1] for line in f]
    except FileNotFoundError:
        return []


def boot(paths, env):
    r = Capture()
    assert provision.run(env, paths, reporter=r, boot=True) == 0
    return r


def chscan(paths, env, names=(), **kw):
    r = Capture()
    rc = channels.command(env, paths, list(names), log=r.log, warn=r.warn, **kw)
    return rc, r


def read(paths, rel):
    with open(os.path.join(paths.root, rel), "rb") as f:
        return f.read()


def exists(paths, rel):
    return os.path.exists(os.path.join(paths.root, rel))


def setting_files(paths):
    d = os.path.join(paths.root, "Setting")
    return sorted(n for n in os.listdir(d) if n.endswith(".txt")) if os.path.isdir(d) else []


def snapshot(paths):
    return {n: read(paths, os.path.join("Setting", n)) for n in setting_files(paths)}


def spaces_of(paths, rel):
    return [int(line.split(b"\t")[3]) for line in chset.split_lines(read(paths, rel))[1]]


@pytest.fixture(autouse=True)
def fake_env(monkeypatch, scan_env):
    # the fake EpgDataCap_Bon reads these from its own environment
    for k, v in scan_env.items():
        if k.startswith("FAKE_"):
            monkeypatch.setenv(k, v)


# ----- first start -----


def test_first_start_scans_and_splits_by_kind(tree, fake, scan_env):
    a = fake("mixed")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": a.url}
    r = boot(tree, env)
    assert scans(env) == ["BonDriver_LinuxMirakc-scan-DEFAULT.so"]
    # mixed: M=2, T=1, S=2 tuners; spaces GR=0, BS=1, CS=2
    assert setting_files(tree) == [
        "BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt",
        "BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt",
        "BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt",
        "ChSet5.txt",
    ]
    assert spaces_of(tree, "Setting/BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt") == [0, 0, 1, 1, 2]
    assert spaces_of(tree, "Setting/BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt") == [0, 0]
    assert spaces_of(tree, "Setting/BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt") == [1, 1, 2]
    assert read(tree, channels.scan_rel("DEFAULT")) == read(tree, "Setting/BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt")
    # the temporary BonDriver and its ChSet4 are gone
    assert not [n for n in os.listdir(tree.lib) if "-scan-" in n]
    assert "provision: chscan DEFAULT: Completed" in r.lines
    assert any('chscan DEFAULT: "GR27" 1/5' in line for line in r.lines)
    assert not any("Sig:" in line for line in r.lines)
    assert not r.warning_lines


def test_kind_without_tuners_gets_no_file(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("split").url}
    boot(tree, env)
    # split: T=3, S=2, no dual tuners: no M file, though M was used to scan
    assert setting_files(tree) == [
        "BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt",
        "BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt",
        "ChSet5.txt",
    ]


def test_interleaved_types_get_the_spaces_of_the_bondriver(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("interleaved").url}
    boot(tree, env)
    # GR27, BS x2, GR26, CS2: spaces 0, 1, 2, 3
    assert spaces_of(tree, "Setting/BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt") == [0, 2]
    assert spaces_of(tree, "Setting/BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt") == [1, 1, 3]


def test_two_backends_are_both_scanned(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url, "EDCB_BACKEND_VM_URL": fake("split").url}
    boot(tree, env)
    assert scans(env) == ["BonDriver_LinuxMirakc-scan-DEFAULT.so", "BonDriver_LinuxMirakc-scan-VM.so"]
    assert setting_files(tree) == [
        "BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt",
        "BonDriver_LinuxMirakc_VM_S(LinuxMirakc).ChSet4.txt",
        "BonDriver_LinuxMirakc_VM_T(LinuxMirakc).ChSet4.txt",
        "ChSet5.txt",
    ]


def test_second_start_does_not_scan_or_change_anything(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("mixed").url}
    boot(tree, env)
    before = snapshot(tree)
    r = boot(tree, env)
    assert scans(env) == ["BonDriver_LinuxMirakc-scan-DEFAULT.so"]
    assert snapshot(tree) == before
    assert r.lines[-1] == "provision: no changes"
    assert not r.warning_lines


def test_existing_chset5_means_no_scan(tree, fake, scan_env):
    os.makedirs(os.path.join(tree.root, "Setting"))
    with open(os.path.join(tree.root, CHSET5), "wb") as f:
        f.write(chset.BOM)
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    r = boot(tree, env)
    assert scans(env) == []
    assert setting_files(tree) == ["ChSet5.txt"]
    assert any("backend DEFAULT has no channel scan" in w and "edcbctl chscan DEFAULT" in w for w in r.warning_lines)


@pytest.mark.parametrize("chset5", [False, True])
def test_never_means_no_scan(tree, fake, scan_env, chset5):
    if chset5:
        os.makedirs(os.path.join(tree.root, "Setting"))
        with open(os.path.join(tree.root, CHSET5), "wb") as f:
            f.write(chset.BOM)
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url, "EDCB_CHSCAN": "never"}
    r = boot(tree, env)
    assert scans(env) == []
    assert setting_files(tree) == (["ChSet5.txt"] if chset5 else [])
    assert not r.warning_lines


def test_existing_user_data_is_left_unchanged(tree, fake, scan_env):
    """A v1 user: ChSet4 and ChSet5 made by hand, nothing recorded."""
    setting = os.path.join(tree.root, "Setting")
    os.makedirs(setting)
    files = {
        "BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt": chset.BOM + b"a\tb\tc\t0\t0\t1\t2\t3\t1\t0\t1\t0\n",
        "BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt": chset.BOM + b"a\tb\tc\t0\t0\t1\t2\t3\t1\t0\t1\t0\n",
        "ChSet5.txt": chset.BOM + b"b\tc\t1\t2\t3\t1\t0\t0\t0\n",
    }
    for name, data in files.items():
        with open(os.path.join(setting, name), "wb") as f:
            f.write(data)
    env = {**scan_env, "MIRAKC_ADDRESS": "127.0.0.1", "MIRAKC_PORT": str(fake("mixed").port)}
    boot(tree, env)
    boot(tree, env)
    assert scans(env) == []
    assert snapshot(tree) == files


def test_user_chset4_without_chset5_is_not_scanned(tree, fake, scan_env):
    setting = os.path.join(tree.root, "Setting")
    os.makedirs(setting)
    mine = chset.BOM + b"mine\tb\tc\t0\t0\t1\t2\t3\t1\t0\t1\t0\n"
    with open(os.path.join(setting, "BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt"), "wb") as f:
        f.write(mine)
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url, "EDCB_BACKEND_VM_URL": fake("split").url}
    boot(tree, env)
    # DEFAULT has a file of the user: not scanned; VM is
    assert scans(env) == ["BonDriver_LinuxMirakc-scan-VM.so"]
    assert read(tree, "Setting/BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt") == mine


@pytest.mark.parametrize("mode", ["empty", "fail"])
def test_failed_scan_changes_nothing(tree, fake, scan_env, monkeypatch, mode):
    monkeypatch.setenv("FAKE_CHSCAN", mode)
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    r = boot(tree, env)
    assert scans(env) == ["BonDriver_LinuxMirakc-scan-DEFAULT.so"]
    # no ChSet5 either: the next start tries again
    assert setting_files(tree) == []
    assert not exists(tree, channels.scan_rel("DEFAULT"))
    assert any("backend DEFAULT: the scan" in w for w in r.warning_lines)
    monkeypatch.setenv("FAKE_CHSCAN", "ok")
    boot(tree, env)
    assert "BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt" in setting_files(tree)


def test_scan_that_hangs_is_stopped(tree, fake, scan_env, monkeypatch):
    monkeypatch.setenv("FAKE_CHSCAN", "hang")
    monkeypatch.setattr(channels, "SCAN_BASE_TIMEOUT", 1)
    monkeypatch.setattr(channels, "SCAN_TIMEOUT_PER_CHANNEL", 0)
    monkeypatch.setattr(channels, "KILL_GRACE", 1)
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    r = boot(tree, env)
    assert any("took longer than 1 s" in w for w in r.warning_lines)
    assert setting_files(tree) == []


def test_unreachable_backend_is_not_scanned(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url, "EDCB_BACKEND_GONE_URL": "http://127.0.0.1:9"}
    r = boot(tree, env)
    assert scans(env) == ["BonDriver_LinuxMirakc-scan-DEFAULT.so"]
    # DEFAULT made ChSet5: GONE is not tried again on the next start
    assert any("backend GONE is not scanned" in w and "edcbctl chscan GONE" in w for w in r.warning_lines)


def test_no_backend_scanned_is_tried_again(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": "http://127.0.0.1:9"}
    r = boot(tree, env)
    assert any("backend DEFAULT is not scanned; the scan is tried again on the next start" in w for w in r.warning_lines)
    assert not exists(tree, CHSET5)


def test_diff_does_not_scan(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    r = Capture()
    assert provision.run(env, tree, reporter=r, diff=True) == 0
    assert scans(env) == []
    assert any("would scan the channels of backend DEFAULT" in line for line in r.lines)


# ----- after the scan -----


def test_changed_channels_are_warned_about_and_nothing_changes(tree, fake, scan_env):
    a = fake("dual")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": a.url}
    boot(tree, env)
    before = snapshot(tree)
    a.data = {**a.data, "channels": SCENARIOS["sky"]["channels"]}
    r = boot(tree, env)
    assert any("backend DEFAULT: the channel list of the backend changed" in w for w in r.warning_lines)
    assert snapshot(tree) == before
    assert scans(env) == ["BonDriver_LinuxMirakc-scan-DEFAULT.so"]


def test_changed_url_is_warned_about(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    boot(tree, env)
    r = boot(tree, {**env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url})
    assert any("it was scanned at" in w for w in r.warning_lines)


def test_tuner_count_zero_removes_generated_file(tree, fake, scan_env):
    a = fake("mixed")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": a.url}
    boot(tree, env)
    assert "BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt" in setting_files(tree)
    r = boot(tree, {**env, "EDCB_BACKEND_DEFAULT_TUNERS": "M:2,S:2"})
    assert "BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt" not in setting_files(tree)
    assert any("delete Setting/BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt" in line for line in r.lines)
    # back to auto: made again from the saved scan, without scanning
    boot(tree, env)
    assert "BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt" in setting_files(tree)
    assert scans(env) == ["BonDriver_LinuxMirakc-scan-DEFAULT.so"]


def test_edited_generated_file_is_left_alone(tree, fake, scan_env):
    a = fake("mixed")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": a.url}
    boot(tree, env)
    rel = "Setting/BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt"
    edited = read(tree, rel) + "x\ty\tz\t0\t9\t1\t2\t3\t1\t0\t1\t0\n".encode()
    with open(os.path.join(tree.root, rel), "wb") as f:
        f.write(edited)
    r = boot(tree, {**env, "EDCB_BACKEND_DEFAULT_TUNERS": "M:2,S:2"})
    assert read(tree, rel) == edited
    assert not any(rel in w for w in r.warning_lines)  # nothing would have been written to it


# ----- edcbctl chscan -----


def test_chscan_one_backend(tree, fake, scan_env):
    a, b = fake("dual"), fake("split")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": a.url, "EDCB_BACKEND_VM_URL": b.url}
    boot(tree, env)
    before = snapshot(tree)
    b.data = {**b.data, "channels": SCENARIOS["interleaved"]["channels"]}
    rc, r = chscan(tree, env, ["VM"])
    assert rc == 0, r.warning_lines
    assert scans(env)[-1] == "BonDriver_LinuxMirakc-scan-VM.so" and len(scans(env)) == 3
    after = snapshot(tree)
    assert after["BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt"] == before["BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt"]
    assert spaces_of(tree, "Setting/BonDriver_LinuxMirakc_VM_T(LinuxMirakc).ChSet4.txt") == [0, 2]
    # no drift any more
    r = boot(tree, env)
    assert not r.warning_lines


def test_chscan_keeps_flags(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    boot(tree, env)
    data = read(tree, CHSET5).replace(b"\t1\t1\n", b"\t0\t0\n", 1)
    with open(os.path.join(tree.root, CHSET5), "wb") as f:
        f.write(data)
    rc, r = chscan(tree, env, ["DEFAULT"])
    assert rc == 0
    assert read(tree, CHSET5) == data
    assert any("kept the EPG and search flags of 1 service" in line for line in r.lines)


def test_chscan_rebuild_makes_chset5_again_with_flags(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url, "EDCB_BACKEND_VM_URL": fake("split").url}
    boot(tree, env)
    # a service that no longer exists, and one with flags turned off
    data = read(tree, CHSET5).replace(b"\t1\t1\n", b"\t0\t0\n", 1) + b"old\tnet\t9\t9\t9\t1\t0\t1\t1\n"
    with open(os.path.join(tree.root, CHSET5), "wb") as f:
        f.write(data)
    rc, r = chscan(tree, env, all_backends=True, rebuild=True)
    assert rc == 0, r.warning_lines
    assert scans(env)[2:] == ["BonDriver_LinuxMirakc-scan-DEFAULT.so", "BonDriver_LinuxMirakc-scan-VM.so"]
    new = read(tree, CHSET5)
    assert b"old\t" not in new
    assert new == data.replace(b"old\tnet\t9\t9\t9\t1\t0\t1\t1\n", b"")
    backups = os.path.join(tree.root, ".provision", "backup")
    latest = sorted(os.listdir(backups))[-1]
    with open(os.path.join(backups, latest, CHSET5), "rb") as f:
        assert f.read() == data


def test_chscan_rebuild_restores_chset5_when_a_scan_fails(tree, fake, scan_env, monkeypatch):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    boot(tree, env)
    before = snapshot(tree)
    monkeypatch.setenv("FAKE_CHSCAN", "empty")
    rc, r = chscan(tree, env, rebuild=True)
    assert rc == 1
    assert snapshot(tree) == before
    assert any("rebuild stopped" in w for w in r.warning_lines)


def test_chscan_refuses_user_files_without_force(tree, fake, scan_env):
    setting = os.path.join(tree.root, "Setting")
    os.makedirs(setting)
    mine = chset.BOM + b"mine\tb\tc\t0\t0\t1\t2\t3\t1\t0\t1\t0\n"
    rel = "Setting/BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt"
    with open(os.path.join(tree.root, rel), "wb") as f:
        f.write(mine)
    with open(os.path.join(tree.root, CHSET5), "wb") as f:
        f.write(chset.BOM)
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("split").url}
    boot(tree, env)
    rc, r = chscan(tree, env, ["DEFAULT"])
    assert rc == 1 and scans(env) == []
    assert any("--force" in w for w in r.warning_lines)
    assert read(tree, rel) == mine

    rc, r = chscan(tree, env, ["DEFAULT"], force=True)
    assert rc == 0, r.warning_lines
    # split has no dual tuners: the user's M file is backed up and removed
    assert setting_files(tree) == [
        "BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt",
        "BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt",
        "ChSet5.txt",
    ]
    backups = os.path.join(tree.root, ".provision", "backup")
    (stamp,) = os.listdir(backups)
    with open(os.path.join(backups, stamp, rel), "rb") as f:
        assert f.read() == mine


def test_chscan_errors(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url, "EDCB_BACKEND_GONE_URL": "http://127.0.0.1:9"}
    boot(tree, env)
    assert chscan(tree, env)[0] == 2  # no name
    assert chscan(tree, env, ["NOPE"])[0] == 2
    assert chscan(tree, env, ["DEFAULT"], rebuild=True)[0] == 2
    rc, r = chscan(tree, env, ["GONE"])
    assert rc == 1 and any("backend GONE" in w and "unreachable" in w for w in r.warning_lines)
    # --rebuild needs every backend
    rc, r = chscan(tree, env, rebuild=True)
    assert rc == 1
    assert scans(env) == ["BonDriver_LinuxMirakc-scan-DEFAULT.so"]


def test_chscan_is_locked_against_another_scan(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    boot(tree, env)
    owner = provision.fsutil.Owner()
    with channels.scan_lock(tree.root, owner) as locked:
        assert locked
        rc, r = chscan(tree, env, ["DEFAULT"])
    assert rc == 1 and any("another channel scan" in w for w in r.warning_lines)


def test_state_records_the_scan(tree, fake, scan_env):
    a = fake("interleaved")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": a.url}
    boot(tree, env)
    record = State(tree.root).load().section(channels.STATE_KEY)["DEFAULT"]
    assert record["url"] == a.url
    assert record["spaces"] == ["GR", "BS", "GR", "CS"]
    assert record["channels"] == chset.channels_hash(SCENARIOS["interleaved"]["channels"])


def test_backends_report_shows_the_scan(tree, fake, scan_env):
    from edcb_provision import backends

    a = fake("dual")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": a.url}
    out = io.StringIO()
    backends.report(env, tree.root, out=out)
    assert "channel scan: none (edcbctl chscan DEFAULT)" in out.getvalue()
    boot(tree, env)
    out = io.StringIO()
    backends.report(env, tree.root, out=out)
    assert "the channels are unchanged" in out.getvalue()
    (m_row,) = [line for line in out.getvalue().splitlines() if " BonDriver_LinuxMirakc.so " in line]
    assert m_row.split()[-1] == "yes"
    a.data = {**a.data, "channels": SCENARIOS["sky"]["channels"]}
    out = io.StringIO()
    backends.report(env, tree.root, out=out)
    assert "CHANGED: the channel list of the backend changed" in out.getvalue()


# ----- channels skipped for want of a free tuner -----


def test_first_start_uses_a_scan_with_skipped_channels(tree, fake, scan_env, monkeypatch):
    monkeypatch.setenv("FAKE_CHSCAN", "busy")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    r = boot(tree, env)
    # dual: GR27, GR26, ... GR26 (space 0, ch 1) was skipped
    assert any("no free tuner" in w and "1 channel(s) have no services: 26" in w and "edcbctl chscan DEFAULT" in w for w in r.warning_lines)
    assert spaces_of(tree, "Setting/BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt") == [0, 1, 1, 2]


def test_chscan_does_not_use_a_scan_with_skipped_channels(tree, fake, scan_env, monkeypatch):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    boot(tree, env)
    before = snapshot(tree)
    monkeypatch.setenv("FAKE_CHSCAN", "busy")
    rc, r = chscan(tree, env, ["DEFAULT"])
    assert rc == 1
    assert any("the result is not used" in w for w in r.warning_lines)
    assert snapshot(tree) == before


def test_refused_tuner_that_the_retry_got_is_not_reported(tree, fake, scan_env, monkeypatch):
    # EDCB retries SetChannel once; when that works, every channel has services
    monkeypatch.setenv("FAKE_CHSCAN", "retried")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    r = boot(tree, env)
    assert any("Tuner unavailable" in line for line in r.lines)
    assert not any("no free tuner" in w for w in r.warning_lines)
    assert spaces_of(tree, "Setting/BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt") == [0, 0, 1, 1, 2]


# ----- EPG capture after a scan -----


def test_scan_requests_an_epg_capture_after_the_next_start(tree, fake, scan_env):
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": fake("dual").url}
    boot(tree, env)
    assert exists(tree, channels.EPGCAP_PENDING_REL)
    os.remove(os.path.join(tree.root, channels.EPGCAP_PENDING_REL))
    boot(tree, env)  # no scan: nothing to capture
    assert not exists(tree, channels.EPGCAP_PENDING_REL)
    assert chscan(tree, env, ["DEFAULT"])[0] == 0
    assert exists(tree, channels.EPGCAP_PENDING_REL)
