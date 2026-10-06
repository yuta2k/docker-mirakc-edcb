import datetime
import hashlib
import io
import os

import pytest
from test_channels import CHSET5, Capture, boot, read
from test_channels import fake, fake_env, scan_env  # noqa: F401 - fixtures (fake_env is autouse)
from test_ctrlcmd import FakeSrv, reserve, vector

from edcb_provision import ctrlcmd, ini, prune
from edcb_provision.state import State

VM_FILES = [
    "Setting/BonDriver_LinuxMirakc_VM_T(LinuxMirakc).ChSet4.txt",
    "Setting/BonDriver_LinuxMirakc_VM_S(LinuxMirakc).ChSet4.txt",
]
VM_STATE = [".provision/backend-VM.json", ".provision/scan-VM.ChSet4.txt"]


def run_prune(paths, env, diff=False):
    r = Capture()
    out = io.StringIO()
    rc, changed = prune.command(env, paths, diff=diff, log=r.log, warn=r.warn, out=out)
    return rc, changed, r, out.getvalue()


def srv(paths):
    return ini.IniFile.load(os.path.join(paths.root, "EpgTimerSrv.ini"))


def tree_hashes(root):
    result = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                result[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return result


def exists(paths, rel):
    return os.path.exists(os.path.join(paths.root, rel))


@pytest.fixture
def two_backends(tree, fake, scan_env):
    """DEFAULT (mixed) and VM (split) scanned; returns the environment with DEFAULT only."""
    a, b = fake("mixed"), fake("split")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": a.url}
    boot(tree, {**env, "EDCB_BACKEND_VM_URL": b.url})
    assert [rel for rel in VM_FILES + VM_STATE if not exists(tree, rel)] == []
    return env


def test_removed_backend_is_reported_but_kept_on_start(tree, two_backends):
    before = srv(tree)
    r = boot(tree, two_backends)
    for rel in VM_FILES + VM_STATE:
        assert exists(tree, rel), rel
    after = srv(tree)
    assert after.has_section("BonDriver_LinuxMirakc_VM_T.so")
    assert after.keys("TVTEST") == before.keys("TVTEST")
    text = "\n".join(r.warning_lines)
    assert "edcbctl prune --diff" in text
    assert "BonDriver_LinuxMirakc_VM_T.so" in text
    # the generated ChSet4 files make EDCB list BonDrivers whose files are gone
    assert "fails to record" in text


def test_prune_diff_changes_nothing(tree, two_backends):
    boot(tree, two_backends)
    before = tree_hashes(tree.root)
    rc, changed, r, out = run_prune(tree, two_backends, diff=True)
    assert (rc, changed) == (0, False)
    assert tree_hashes(tree.root) == before
    assert "remove section [BonDriver_LinuxMirakc_VM_T.so]" in out
    assert "delete Setting/BonDriver_LinuxMirakc_VM_S(LinuxMirakc).ChSet4.txt" in out
    assert "forget the channel scan of backend VM" in out


def test_prune_removes_the_leftovers_of_a_removed_backend(tree, two_backends):
    boot(tree, two_backends)
    chset5 = read(tree, CHSET5)
    view_before = [v for _, v in srv(tree).keys("TVTEST")]
    rc, changed, r, out = run_prune(tree, two_backends)
    assert (rc, changed) == (0, True)
    for rel in VM_FILES + VM_STATE:
        assert not exists(tree, rel), rel
    s = srv(tree)
    assert not s.has_section("BonDriver_LinuxMirakc_VM_T.so")
    assert not s.has_section("BonDriver_LinuxMirakc_VM_S.so")
    assert s.has_section("BonDriver_LinuxMirakc_T.so")
    # the viewing list keeps its order without the removed rows, numbered from 0
    kept = [v for v in view_before[1:] if "_VM_" not in v]
    assert s.get("TVTEST", "Num") == str(len(kept))
    assert [s.get("TVTEST", str(i)) for i in range(len(kept))] == kept
    assert s.get("TVTEST", str(len(kept))) is None
    # ChSet5 is shared by the backends and stays
    assert read(tree, CHSET5) == chset5
    st = State(tree.root).load()
    assert "VM" not in st.section("channels")
    assert not any("_VM_" in rel for rel in st.data["files"])
    # everything removed is in the backup
    backups = os.path.join(tree.root, ".provision", "backup")
    newest = os.path.join(backups, sorted(os.listdir(backups))[-1])
    for rel in ["EpgTimerSrv.ini", *VM_FILES, *VM_STATE]:
        assert os.path.isfile(os.path.join(newest, rel)), rel
    # a start afterwards has nothing to report, and prune nothing to do
    r = boot(tree, two_backends)
    assert not any("prune" in w for w in r.warning_lines), r.warning_lines
    rc, changed, _, out = run_prune(tree, two_backends)
    assert (rc, changed, out.strip()) == (0, False, "Nothing to prune.")


def test_user_chset4_of_a_removed_backend_is_left_alone(tree, two_backends):
    rel = VM_FILES[0]
    with open(os.path.join(tree.root, rel), "ab") as f:
        f.write(b"edited\n")
    r = boot(tree, two_backends)
    assert any(rel in w and "not removed" in w for w in r.warning_lines)
    rc, _, r, _ = run_prune(tree, two_backends)
    assert rc == 0
    assert exists(tree, rel)
    s = srv(tree)
    # its BonDriver keeps its section; the other kind is pruned
    assert s.has_section("BonDriver_LinuxMirakc_VM_T.so")
    assert not s.has_section("BonDriver_LinuxMirakc_VM_S.so")
    assert any(rel in w for w in r.warning_lines)


def test_prune_a_kind_without_tuners(tree, fake, scan_env):
    a = fake("mixed")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": a.url}
    boot(tree, env)
    assert srv(tree).has_section("BonDriver_LinuxMirakc_T.so")
    env = {**env, "EDCB_BACKEND_DEFAULT_TUNERS": "M:2,T:0,S:2"}
    r = boot(tree, env)
    # the split removed the ChSet4; the section (Count=0) and the viewing row stay until prune
    assert not exists(tree, "Setting/BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt")
    assert srv(tree).get("BonDriver_LinuxMirakc_T.so", "Count") == "0"
    assert any("edcbctl prune" in w for w in r.warning_lines)
    rc, changed, r, _ = run_prune(tree, env)
    assert (rc, changed) == (0, True)
    s = srv(tree)
    assert not s.has_section("BonDriver_LinuxMirakc_T.so")
    assert "BonDriver_LinuxMirakc_T.so" not in [v for _, v in s.keys("TVTEST")]
    assert s.has_section("BonDriver_LinuxMirakc_S.so")
    # no section is written again for a kind without tuners
    r = boot(tree, env)
    assert not srv(tree).has_section("BonDriver_LinuxMirakc_T.so")
    assert not any("prune" in w for w in r.warning_lines)


def test_unknown_tuner_counts_are_not_pruned(tree, fake, scan_env):
    a = fake("mixed")
    env = {**scan_env, "EDCB_BACKEND_DEFAULT_URL": a.url}
    boot(tree, env)
    os.remove(os.path.join(tree.root, ".provision", "backend-DEFAULT.json"))
    a.stop()
    rc, changed, _, out = run_prune(tree, env)
    assert (rc, changed) == (0, False)
    assert out.strip() == "Nothing to prune."


def test_bondriver_names():
    assert prune.parse_bondriver("BonDriver_LinuxMirakc.so") == ("DEFAULT", "M")
    assert prune.parse_bondriver("BonDriver_LinuxMirakc_T.so") == ("DEFAULT", "T")
    assert prune.parse_bondriver("bondriver_linuxmirakc_vm_s.so") == ("VM", "S")
    assert prune.parse_bondriver("BonDriver_LinuxMirakc_TV.so") == ("TV", "M")
    assert prune.parse_bondriver("BonDriver_LinuxMirakc_TV_T.so") == ("TV", "T")
    assert prune.parse_bondriver("BonDriver_LinuxMirakc-scan-VM.so") is None
    assert prune.parse_bondriver("BonDriver_Proxy.so") is None


def test_fixed_reservations_are_counted(tmp_path):
    root = tmp_path / "r"
    if len(str(root)) > 80:
        pytest.skip("temporary path too long for a UNIX socket")
    plan = prune.Plan(sections=["BonDriver_LinuxMirakc_VM_T.so"], priorities={"BonDriver_LinuxMirakc_VM_T.so": 3})
    root.mkdir()
    now = datetime.datetime(2026, 10, 6, 20, 0)
    s = FakeSrv(
        str(root),
        {
            ctrlcmd.CMD2_EPG_SRV_ENUM_RESERVE: (
                1,
                vector(
                    [
                        reserve(1, "Fixed", now, 30, tuner_id=3 << 16 | 1),
                        reserve(2, "Other tuner", now, 30, tuner_id=1 << 16 | 1),
                        reserve(3, "Any tuner", now, 30),
                        reserve(4, "Fixed but disabled", now, 30, rec_mode=5, tuner_id=3 << 16 | 2),
                    ]
                ),
            )
        },
    )
    try:
        assert prune._fixed_reservations(str(root), plan) == (1, ["Fixed"])
    finally:
        s.close()
    # EpgTimerSrv is not running
    assert prune._fixed_reservations(str(tmp_path), plan) is None


def test_backend_with_bad_settings_is_not_treated_as_removed(tree, two_backends):
    # an underscore in the host name makes parse_env ignore backend VM
    env = {**two_backends, "EDCB_BACKEND_VM_URL": "http://tuner_pc:40772"}
    r = boot(tree, env)
    assert any("backend VM is ignored" in w for w in r.warning_lines)
    assert not any("prune" in w for w in r.warning_lines), r.warning_lines
    before = tree_hashes(tree.root)
    rc, changed, r, out = run_prune(tree, env)
    assert (rc, changed, out.strip()) == (0, False, "Nothing to prune.")
    assert any("VM is ignored because of its settings" in w for w in r.warning_lines)
    for rel in VM_FILES + VM_STATE:
        assert exists(tree, rel), rel
    assert srv(tree).has_section("BonDriver_LinuxMirakc_VM_T.so")
    assert tree_hashes(tree.root) == before


def test_no_leftover_report_when_the_backends_fail(tree, two_backends, monkeypatch):
    from edcb_provision import backends

    def broken(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(backends, "install_bondrivers", broken)
    r = boot(tree, {**two_backends, "EDCB_BACKEND_VM_URL": "http://127.0.0.1:1"})
    assert any("backends are not set up" in w for w in r.warning_lines)
    assert not any("prune" in w or "leftovers" in w for w in r.warning_lines), r.warning_lines


def test_prune_keeps_records_written_while_it_waited(tree, two_backends):
    from edcb_provision import backends

    boot(tree, two_backends)
    rel = "Setting/BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt"

    def fetch(found, timeout):
        # a scan finishes and saves the state while prune asks the backends
        result = backends.fetch_all(found, timeout)
        st = State(tree.root).load()
        st.section("channels")["DEFAULT"]["scanned_at"] = "while prune waited"
        st.save(prune.fsutil.Owner(None, None))
        return result

    r = Capture()
    rc, changed = prune.command(two_backends, tree, log=r.log, warn=r.warn, out=io.StringIO(), fetch=fetch)
    assert (rc, changed) == (0, True)
    st = State(tree.root).load()
    assert st.section("channels")["DEFAULT"]["scanned_at"] == "while prune waited"
    assert st.recorded(rel) is not None
    assert "VM" not in st.section("channels")
