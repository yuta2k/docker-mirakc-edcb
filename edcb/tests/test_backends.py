import io
import json
import os
import socket
import time

import pytest
from fake_mirakurun import SCENARIOS, FakeMirakurun

from edcb_provision import backends, ini, provision


class Capture(provision.Reporter):
    def __init__(self):
        super().__init__(io.StringIO(), io.StringIO())

    @property
    def lines(self):
        return self.out.getvalue().splitlines()

    @property
    def warning_lines(self):
        return self.err.getvalue().splitlines()


def run(paths, env, **kw):
    r = Capture()
    env = {"EDCB_PROVISION_FETCH_TIMEOUT": "10", **env}
    assert provision.run(env, paths, reporter=r, **kw) == 0
    return r


def closed_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


def read_ini(path):
    return ini.IniFile.load(path)


def lib_files(paths):
    return sorted(n for n in os.listdir(paths.lib) if not n.startswith("."))


# ----- variables -----


def names(env):
    found, warnings = backends.parse_env(env)
    return [b.name for b in found], warnings


def test_no_backend_means_the_bundled_mirakc():
    found, warnings = backends.parse_env({})
    assert [(b.name, b.url, b.host, b.port) for b in found] == [("DEFAULT", "http://mirakc:40772", "mirakc", 40772)]
    assert warnings == []


def test_backends_are_sorted_default_first():
    env = {
        "EDCB_BACKEND_VM_URL": "http://vm.example:40772",
        "EDCB_BACKEND_DEFAULT_URL": "http://mirakc:40772",
        "EDCB_BACKEND_A2_URL": "http://192.0.2.1",
    }
    found, warnings = backends.parse_env(env)
    assert [b.name for b in found] == ["DEFAULT", "A2", "VM"]
    assert found[1].port == 40772  # the default port
    assert warnings == []


def test_only_other_backends_means_no_default():
    assert names({"EDCB_BACKEND_VM_URL": "http://vm:40772"}) == (["VM"], [])


@pytest.mark.parametrize("name", ["T", "S", "MY_VM", "vm", "Vm", "1VM"])
def test_invalid_names_are_ignored_with_a_warning(name):
    found, warnings = names({f"EDCB_BACKEND_{name}_URL": "http://vm:40772", "EDCB_BACKEND_OK_URL": "http://ok:1"})
    assert found == ["OK"]
    assert len(warnings) == 1 and "invalid backend name" in warnings[0]


def test_unknown_field_is_warned():
    found, warnings = names({"EDCB_BACKEND_VM_URL": "http://vm:1", "EDCB_BACKEND_VM_PORT": "1"})
    assert found == ["VM"]
    assert any("EDCB_BACKEND_VM_PORT" in w for w in warnings)


def test_fields_without_url_are_warned():
    found, warnings = names({"EDCB_BACKEND_VM_TUNERS": "M:1", "EDCB_BACKEND_A_URL": "http://a:1"})
    assert found == ["A"]
    assert any("EDCB_BACKEND_VM_URL is not set" in w for w in warnings)
    # no URL anywhere: the bundled mirakc is still used
    found, warnings = names({"EDCB_BACKEND_VM_TUNERS": "M:1"})
    assert found == ["DEFAULT"]
    assert any("EDCB_BACKEND_VM_URL is not set" in w for w in warnings)


def test_default_without_url_is_the_bundled_mirakc():
    (b,), warnings = backends.parse_env({"EDCB_BACKEND_DEFAULT_TUNERS": "M:4"})
    assert (b.name, b.url, b.tuners) == ("DEFAULT", "http://mirakc:40772", {"M": 4, "T": 0, "S": 0})
    assert warnings == []


@pytest.mark.parametrize(
    "url",
    ["https://vm:40772", "vm:40772", "http://vm:40772/api", "http://[::1]:40772", "http://vm:99999", "http://bad_host:1"],
)
def test_invalid_urls_are_ignored(url):
    found, warnings = backends.parse_env({"EDCB_BACKEND_VM_URL": url})
    assert [b.name for b in found] == []
    assert len(warnings) == 1 and "backend VM is ignored" in warnings[0]


def test_mirakc_address_and_port_are_the_default_backend():
    found, _ = backends.parse_env({"MIRAKC_ADDRESS": "192.0.2.10", "MIRAKC_PORT": "40773"})
    assert [(b.name, b.url, b.source) for b in found] == [
        ("DEFAULT", "http://192.0.2.10:40773", "MIRAKC_ADDRESS / MIRAKC_PORT")
    ]
    # either one alone works, the other takes the v1 default
    assert backends.parse_env({"MIRAKC_ADDRESS": "tuner"})[0][0].url == "http://tuner:40772"
    assert backends.parse_env({"MIRAKC_PORT": "1234"})[0][0].url == "http://mirakc:1234"


def test_misspelled_mirkac_variables_still_work():
    found, _ = backends.parse_env({"MIRKAC_ADDRESS": "tuner", "MIRKAC_PORT": "1"})
    assert found[0].url == "http://tuner:1"


def test_default_url_wins_over_mirakc_address():
    found, warnings = backends.parse_env({"EDCB_BACKEND_DEFAULT_URL": "http://a:1", "MIRAKC_ADDRESS": "b"})
    assert found[0].url == "http://a:1"
    assert any("MIRAKC_ADDRESS" in w for w in warnings)


def test_tuners_priority_decode():
    env = {
        "EDCB_BACKEND_VM_URL": "http://vm:1",
        "EDCB_BACKEND_VM_TUNERS": "m:2, S:1",
        "EDCB_BACKEND_VM_PRIORITY": "5",
        "EDCB_BACKEND_VM_DECODE": "0",
    }
    (b,), warnings = backends.parse_env(env)
    assert (b.tuners, b.priority, b.decode) == ({"M": 2, "T": 0, "S": 1}, 5, 0)
    assert warnings == []
    assert b.bondriver_ini().decode().splitlines()[1:] == [
        "[GLOBAL]",
        'SERVER_HOST="vm"',
        "SERVER_PORT=1",
        'SERVER_TYPE="http"',
        "DECODE_B25=0",
        "PRIORITY=5",
        "SERVICE_SPLIT=0",
    ]


@pytest.mark.parametrize("value", ["M2", "X:1", "M:1,M:2", "M:-1", "M:100"])
def test_invalid_tuners_fall_back_to_auto(value):
    (b,), warnings = backends.parse_env({"EDCB_BACKEND_VM_URL": "http://vm:1", "EDCB_BACKEND_VM_TUNERS": value})
    assert b.tuners is None
    assert len(warnings) == 1


def test_bondriver_names():
    d = backends.Backend("DEFAULT", "", "", 0)
    vm = backends.Backend("VM", "", "", 0)
    assert [d.bondriver(k) for k in backends.KINDS] == [
        "BonDriver_LinuxMirakc.so",
        "BonDriver_LinuxMirakc_T.so",
        "BonDriver_LinuxMirakc_S.so",
    ]
    assert [vm.bondriver(k) for k in backends.KINDS] == [
        "BonDriver_LinuxMirakc_VM.so",
        "BonDriver_LinuxMirakc_VM_T.so",
        "BonDriver_LinuxMirakc_VM_S.so",
    ]


# ----- classification -----


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_classification_of_every_scenario(scenario):
    counts, others = backends.classify(SCENARIOS[scenario]["tuners"])
    assert counts == SCENARIOS[scenario]["expected"]
    assert others == (["tuner1"] if scenario == "sky" else [])


# ----- fetching -----


def test_fetch_from_the_fake_server(fake):
    s = fake("mixed")
    b = backends.Backend("VM", s.url, "127.0.0.1", s.port)
    info = backends.fetch_all([b], 10)["VM"]
    assert info.source == "live"
    assert [c["type"] for c in info.channels] == ["GR", "GR", "BS", "BS", "CS"]
    assert backends.classify(info.tuners)[0] == {"M": 2, "T": 1, "S": 2}
    assert s.requests == ["/api/tuners", "/api/channels"]


def test_fetch_by_host_name(fake):
    s = fake("dual")
    (b,), _ = backends.parse_env({"EDCB_BACKEND_VM_URL": f"http://localhost:{s.port}"})
    assert backends.fetch_all([b], 10)["VM"].source == "live"


def test_unreachable_backend_does_not_delay_the_others(fake):
    ok = fake("dual")
    slow = fake("dual", delay=30)
    found = [
        backends.Backend("OK", ok.url, "127.0.0.1", ok.port),
        backends.Backend("SLOW", slow.url, "127.0.0.1", slow.port),
        backends.Backend("DOWN", f"http://127.0.0.1:{closed_port()}", "127.0.0.1", 1),
    ]
    start = time.monotonic()
    infos = backends.fetch_all(found, 3)
    elapsed = time.monotonic() - start
    assert elapsed < 4
    assert infos["OK"].source == "live"
    assert infos["SLOW"].source == "none"
    assert infos["DOWN"].source == "none"


# ----- the whole provisioning -----


def two_backends(a, b, **extra):
    return {"EDCB_BACKEND_DEFAULT_URL": f"http://localhost:{a.port}", "EDCB_BACKEND_VM_URL": f"http://127.0.0.1:{b.port}", **extra}


def test_two_backends_make_six_bondrivers_with_their_own_ini(tree, fake):
    a = fake("dual")
    b = fake("split")
    r = run(tree, two_backends(a, b), boot=True)
    assert lib_files(tree) == sorted(
        n + ext
        for n in [
            "BonDriver_LinuxMirakc",
            "BonDriver_LinuxMirakc_T",
            "BonDriver_LinuxMirakc_S",
            "BonDriver_LinuxMirakc_VM",
            "BonDriver_LinuxMirakc_VM_T",
            "BonDriver_LinuxMirakc_VM_S",
        ]
        for ext in (".so", ".so.ini")
    )
    for name, port, host in [("BonDriver_LinuxMirakc_S", a.port, "localhost"), ("BonDriver_LinuxMirakc_VM", b.port, "127.0.0.1")]:
        conf = read_ini(os.path.join(tree.lib, name + ".so.ini"))
        assert (conf.get("GLOBAL", "SERVER_HOST"), conf.get("GLOBAL", "SERVER_PORT")) == (host, str(port))
    with open(os.path.join(tree.lib, "BonDriver_LinuxMirakc_VM_T.so"), "rb") as f:
        assert f.read() == b"\x7fELF fake BonDriver\n"
    assert os.stat(os.path.join(tree.lib, "BonDriver_LinuxMirakc.so")).st_mode & 0o777 == 0o755

    srv = read_ini(os.path.join(tree.root, "EpgTimerSrv.ini"))
    # dual: 2 x M; split: 3 x T and 2 x S. Kinds without tuners get no section.
    assert srv.keys("BonDriver_LinuxMirakc.so") == [("Count", "2"), ("GetEpg", "1"), ("EPGCount", "0"), ("Priority", "0")]
    assert srv.get("BonDriver_LinuxMirakc_VM_T.so", "Count") == "3"
    assert srv.get("BonDriver_LinuxMirakc_VM_T.so", "Priority") == "1"
    assert srv.get("BonDriver_LinuxMirakc_VM_S.so", "Count") == "2"
    assert srv.get("BonDriver_LinuxMirakc_VM_S.so", "Priority") == "2"
    for empty in ["BonDriver_LinuxMirakc_T.so", "BonDriver_LinuxMirakc_S.so", "BonDriver_LinuxMirakc_VM.so"]:
        assert not srv.has_section(empty)
    assert "provision: backend VM: http://127.0.0.1:%d (reachable), tuners M=0 T=3 S=2" % b.port in r.lines
    assert not r.warning_lines

    for name in ("DEFAULT", "VM"):
        with open(os.path.join(tree.root, ".provision", f"backend-{name}.json"), encoding="utf-8") as f:
            assert json.load(f)["channels"][0] == {"type": "GR", "channel": "27", "name": "GR27"}


def test_second_run_changes_nothing(tree, fake):
    env = two_backends(fake("dual"), fake("split"))
    run(tree, env, boot=True)
    r = run(tree, env, boot=True)
    assert r.lines[-1] == "provision: no changes"
    assert not r.warning_lines


def test_existing_section_is_only_warned_about(tree, fake):
    a = fake("dual")
    with open(os.path.join(tree.root, "EpgTimerSrv.ini"), "w") as f:
        f.write("[SET]\n[BonDriver_LinuxMirakc.so]\nCount=1\nGetEpg=0\nPriority=7\n")
    r = run(tree, {"EDCB_BACKEND_DEFAULT_URL": a.url}, boot=True)
    srv = read_ini(os.path.join(tree.root, "EpgTimerSrv.ini"))
    assert srv.keys("BonDriver_LinuxMirakc.so") == [("Count", "1"), ("GetEpg", "0"), ("Priority", "7")]
    assert any("[BonDriver_LinuxMirakc.so] Count is 1, but backend DEFAULT has 2" in w for w in r.warning_lines)


def test_new_sections_are_numbered_after_existing_priorities(tree, fake):
    b = fake("split")
    with open(os.path.join(tree.root, "EpgTimerSrv.ini"), "w") as f:
        f.write("[BonDriver_LinuxMirakc.so]\nCount=2\nPriority=0\n[BonDriver_Other.so]\nCount=1\nPriority=4\n")
    run(tree, {"EDCB_BACKEND_VM_URL": b.url}, boot=True)
    srv = read_ini(os.path.join(tree.root, "EpgTimerSrv.ini"))
    assert srv.get("BonDriver_LinuxMirakc_VM_T.so", "Priority") == "5"
    assert srv.get("BonDriver_LinuxMirakc_VM_S.so", "Priority") == "6"


def test_explicit_tuners_overwrite_count_on_every_start(tree, fake):
    a = fake("dual")
    env = {"EDCB_BACKEND_DEFAULT_URL": a.url, "EDCB_BACKEND_DEFAULT_TUNERS": "M:1,T:2"}
    with open(os.path.join(tree.root, "EpgTimerSrv.ini"), "w") as f:
        f.write("[BonDriver_LinuxMirakc.so]\nCount=4\nPriority=0\n")
    r = run(tree, env, boot=True)
    srv = read_ini(os.path.join(tree.root, "EpgTimerSrv.ini"))
    assert srv.get("BonDriver_LinuxMirakc.so", "Count") == "1"
    assert srv.keys("BonDriver_LinuxMirakc_T.so") == [("Count", "2"), ("GetEpg", "1"), ("EPGCount", "0"), ("Priority", "1")]
    assert not srv.has_section("BonDriver_LinuxMirakc_S.so")  # 0 and absent: not created
    assert any('[BonDriver_LinuxMirakc.so] Count: "4" -> "1" (env EDCB_BACKEND_DEFAULT_TUNERS)' in line for line in r.lines)
    # changed in the WebUI: back to the variable on the next start
    path = os.path.join(tree.root, "EpgTimerSrv.ini")
    with open(path) as f:
        text = f.read().replace("Count=1", "Count=3", 1)
    with open(path, "w") as f:
        f.write(text)
    run(tree, env, boot=True)
    assert read_ini(os.path.join(tree.root, "EpgTimerSrv.ini")).get("BonDriver_LinuxMirakc.so", "Count") == "1"


def test_unreachable_backend_uses_the_saved_information(tree, fake):
    a = fake("dual")
    b = fake("split")
    env = two_backends(a, b)
    run(tree, env, boot=True)
    b.stop()
    # the user lowered a count; the stored tuners are compared with it
    path = os.path.join(tree.root, "EpgTimerSrv.ini")
    with open(path) as f:
        text = f.read()
    with open(path, "w") as f:
        f.write(text.replace("[BonDriver_LinuxMirakc_VM_T.so]\nCount=3", "[BonDriver_LinuxMirakc_VM_T.so]\nCount=1"))
    r = run(tree, env, boot=True)
    assert any("backend VM" in w and "unreachable" in w and "using the information from" in w for w in r.warning_lines)
    assert any("[BonDriver_LinuxMirakc_VM_T.so] Count is 1, but backend VM has 3" in w for w in r.warning_lines)
    assert any(line.startswith("provision: backend VM: ") and "unreachable, saved" in line and "T=3 S=2" in line for line in r.lines)
    assert len(lib_files(tree)) == 12


def test_unreachable_backend_without_saved_information(tree, fake):
    a = fake("dual")
    env = {"EDCB_BACKEND_DEFAULT_URL": a.url, "EDCB_BACKEND_VM_URL": f"http://127.0.0.1:{closed_port()}"}
    start = time.monotonic()
    r = run(tree, env, boot=True)
    assert time.monotonic() - start < 10
    srv = read_ini(os.path.join(tree.root, "EpgTimerSrv.ini"))
    assert srv.get("BonDriver_LinuxMirakc.so", "Count") == "2"  # the reachable one is set up
    assert not any(s.startswith("bondriver_linuxmirakc_vm") for s in srv.sections())
    assert any("backend VM" in w and "nothing was saved before" in w for w in r.warning_lines)
    assert len(lib_files(tree)) == 12  # its BonDrivers exist anyway


def test_cache_of_another_url_is_ignored(tree, fake):
    a = fake("dual")
    run(tree, {"EDCB_BACKEND_DEFAULT_URL": a.url}, boot=True)
    r = run(tree, {"EDCB_BACKEND_DEFAULT_URL": f"http://127.0.0.1:{closed_port()}"}, boot=True)
    assert any("is ignored" in w and "backend-DEFAULT.json" in w for w in r.warning_lines)


def test_removed_backend_files_are_deleted(tree, fake):
    a = fake("dual")
    b = fake("split")
    run(tree, two_backends(a, b), boot=True)
    r = run(tree, {"EDCB_BACKEND_DEFAULT_URL": a.url}, boot=True)
    assert lib_files(tree) == sorted(
        n + ext for n in ["BonDriver_LinuxMirakc", "BonDriver_LinuxMirakc_T", "BonDriver_LinuxMirakc_S"] for ext in (".so", ".so.ini")
    )
    assert sum("(backend removed)" in line for line in r.lines) == 6


def test_files_of_the_user_are_left_alone(tree, fake):
    a = fake("dual")
    own = os.path.join(tree.lib, "BonDriver_LinuxMirakc_T.so.ini")
    with open(own, "w") as f:
        f.write("[GLOBAL]\nSERVER_HOST=mine\n")
    r = run(tree, {"EDCB_BACKEND_DEFAULT_URL": a.url}, boot=True)
    with open(own) as f:
        assert f.read() == "[GLOBAL]\nSERVER_HOST=mine\n"
    assert any(own in w and "not created by the provisioning" in w for w in r.warning_lines)
    # an edited generated file is not replaced or deleted either
    edited = os.path.join(tree.lib, "BonDriver_LinuxMirakc_S.so.ini")
    with open(edited, "a") as f:
        f.write("; edited\n")
    r = run(tree, {"EDCB_BACKEND_DEFAULT_URL": a.url}, boot=True)
    assert open(edited).read().endswith("; edited\n")
    assert any(edited in w for w in r.warning_lines)


def test_diff_writes_nothing(tree, fake):
    a = fake("dual")
    r = run(tree, {"EDCB_BACKEND_DEFAULT_URL": a.url}, diff=True)
    assert lib_files(tree) == []
    assert not os.path.exists(os.path.join(tree.root, ".provision", "backend-DEFAULT.json"))
    assert any(line.startswith("provision: create ") and line.endswith("BonDriver_LinuxMirakc.so") for line in r.lines)
    assert any("[BonDriver_LinuxMirakc.so] Count" in line for line in r.lines)


def test_a_failure_in_the_backend_stage_does_not_stop_the_rest(tree):
    def broken(found, timeout):
        raise RuntimeError("boom")

    r = Capture()
    assert provision.run({}, tree, reporter=r, fetch=broken, boot=True) == 0
    assert any("backends are not set up: RuntimeError: boom" in w for w in r.warning_lines)
    assert os.path.exists(os.path.join(tree.root, "EpgTimerSrv.ini"))


# ----- edcbctl backends -----


def test_report(tree, fake):
    a = fake("dual")
    b = fake("split")
    env = two_backends(a, b)
    run(tree, env, boot=True)
    os.makedirs(os.path.join(tree.root, "Setting"), exist_ok=True)
    open(os.path.join(tree.root, "Setting", "BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt"), "w").close()
    with open(os.path.join(tree.root, "EpgTimerSrv.ini")) as f:
        text = f.read()
    with open(os.path.join(tree.root, "EpgTimerSrv.ini"), "w") as f:
        f.write(text.replace("Count=2", "Count=1", 1))
    out = io.StringIO()
    assert backends.report(env, tree.root, out=out) == 0
    lines = out.getvalue().splitlines()
    assert lines[0] == f"DEFAULT: http://localhost:{a.port} (reachable)"
    assert lines[1].split() == ["kind", "BonDriver", "tuners", "Count", "ChSet4"]
    assert lines[2].split() == ["M", "BonDriver_LinuxMirakc.so", "2", "1", "*", "yes"]
    assert lines[3].split() == ["T", "BonDriver_LinuxMirakc_T.so", "0", "-", "no"]
    assert "  * Count differs from the tuners of the backend" in lines
    assert "  channels: 5 (GR 2, BS 2, CS 1)" in lines
    vm = lines.index(f"VM: http://127.0.0.1:{b.port} (reachable)")
    assert lines[vm + 3].split() == ["T", "BonDriver_LinuxMirakc_VM_T.so", "3", "3", "no"]

    b.stop()
    out = io.StringIO()
    assert backends.report(env, tree.root, out=out) == 1
    assert any(line.startswith("VM: ") and "UNREACHABLE" in line and "showing the information from" in line for line in out.getvalue().splitlines())


def test_edcbctl_backends(tree, fake, capsys):
    from edcb_provision import cli

    a = fake("mixed")
    env = {"EDCB_PROVISION_ROOT": tree.root, "EDCB_BACKEND_DEFAULT_URL": a.url}
    assert cli.main(["backends"], env) == 0
    assert capsys.readouterr().out.startswith(f"DEFAULT: {a.url} (reachable)\n")
