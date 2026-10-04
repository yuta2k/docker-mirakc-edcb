import io
import os

from edcb_provision import config, provision


class Capture(provision.Reporter):
    def __init__(self):
        super().__init__(io.StringIO(), io.StringIO())

    @property
    def lines(self):
        return self.out.getvalue().splitlines()


def run(paths, env=None, **kw):
    r = Capture()
    rc = provision.run(env or {}, paths, reporter=r, **kw)
    assert rc == 0
    return r


def snapshot(root):
    result = {}
    for dirpath, dirnames, filenames in os.walk(root):
        if ".provision" in dirpath.split(os.sep):
            continue
        for name in filenames:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                result[os.path.relpath(path, root)] = f.read()
    return result


def test_empty_root_gets_initial_files_and_defaults(tree):
    r = run(tree, boot=True)
    root = tree.root
    files = snapshot(root)
    assert files["Bitrate.ini"] == "[BITRATE]\n;地上波\nFFFFFFFFFFFF=16860\n".encode()
    assert files["BonCtrl.ini"] == b"[SET]\nFFFFFFFF=B25Decoder.so\n"
    assert files["ContentTypeText.txt"] == b".ts\tvideo/MP2T\n"
    assert files["Setting/XCODE_OPTIONS.lua"] == b"XCODE_OPTIONS={}\n"
    assert files["Setting/HttpPublic.ini"] == "[SET]\n;既定値\n".encode()  # CP932 -> UTF-8
    assert b"ALLOW_SETTING=edcb.GetPrivateProfile" in files["HttpPublic/legacy/util.lua"]
    srv = files["EpgTimerSrv.ini"].decode()
    assert srv.startswith("[SET]\nEnableHttpSrv=1\n")
    assert "CompatFlags=4095\n" in srv and "SaveDebugLog=1\n" in srv
    with open(os.path.join(root, config.WEBUI_INI), "rb") as f:
        assert f.read() == b"[LEGACY]\nALLOW_SETTING=0\n"
    assert any("create EpgTimerSrv.ini" in line for line in r.lines)
    assert not r.err.getvalue()


def test_second_run_changes_nothing(tree):
    run(tree, boot=True)
    before = snapshot(tree.root)
    r = run(tree, boot=True)
    assert r.lines == ["provision: no changes"]
    assert snapshot(tree.root) == before
    assert not os.path.exists(os.path.join(tree.root, ".provision", "backup"))


def test_diff_writes_nothing(tree):
    (open(os.path.join(tree.root, "EpgTimerSrv.ini"), "w")).write("[SET]\nCompatFlags=0\n")
    before = snapshot(tree.root)
    r = run(tree, {"EDCB_COMPAT_FLAGS": "4095"}, diff=True, boot=True)
    assert snapshot(tree.root) == before
    assert not os.path.exists(os.path.join(tree.root, ".provision"))
    out = "\n".join(r.lines)
    assert 'EpgTimerSrv.ini [SET] CompatFlags: "0" -> "4095" (env EDCB_COMPAT_FLAGS)' in out
    assert "create Bitrate.ini" in out
    assert "HttpPublic: would update (2 added" in out


def test_webui_edits_survive_and_env_keys_are_restored(tree):
    env = {"EDCB_HTTP_NUM_THREADS": "40"}
    run(tree, env, boot=True)
    srv = os.path.join(tree.root, "EpgTimerSrv.ini")
    with open(srv) as f:
        text = f.read()
    # what the WebUI would do: change and turn off options; a manual edit of a forced key
    text = text.replace("SaveDebugLog=1", "SaveDebugLog=0").replace("HttpNumThreads=40", "HttpNumThreads=5")
    text = text.replace("EnableTCPSrv=1", "EnableTCPSrv=0") + "StartMargin=10\n"
    with open(srv, "w") as f:
        f.write(text)
    r = run(tree, env, boot=True)
    with open(srv) as f:
        after = f.read()
    assert after == text.replace("HttpNumThreads=5", "HttpNumThreads=40")
    assert any("backup:" in line for line in r.lines)
    backups = os.listdir(os.path.join(tree.root, ".provision", "backup"))
    with open(os.path.join(tree.root, ".provision", "backup", backups[0], "EpgTimerSrv.ini")) as f:
        assert f.read() == text


def test_override_files_keep_comments_and_order(tree):
    os.makedirs(os.path.join(tree.overrides, "Setting"))
    with open(os.path.join(tree.overrides, "BonCtrl.ini"), "w") as f:
        f.write("[EPGCAP]\nEpgCapTimeOut=20\n")
    with open(os.path.join(tree.overrides, "Setting", "HttpPublic.ini"), "w") as f:
        f.write("[SET]\nALLOW_SETTING=0\n")
    bonctrl = os.path.join(tree.root, "BonCtrl.ini")
    original = ";comment\n[SET]\nFFFFFFFF=B25Decoder.so\n\n;about EPGCAP\n[EPGCAP]\nEpgCapTimeOut=10\nEpgCapSaveTimeOut=0\n"
    with open(bonctrl, "w") as f:
        f.write(original)
    run(tree)
    with open(bonctrl) as f:
        assert f.read() == original.replace("EpgCapTimeOut=10", "EpgCapTimeOut=20")
    with open(os.path.join(tree.root, "Setting", "HttpPublic.ini")) as f:
        # a section without keys gets the key right after its header
        assert f.read() == "[SET]\nALLOW_SETTING=0\n;既定値\n"


def test_legacy_switch_is_left_alone_without_boot(tree):
    run(tree, boot=True)
    from edcb_provision import fsutil, legacy

    legacy.set(tree.root, True, fsutil.Owner())
    run(tree)
    assert legacy.get(tree.root) is True
    run(tree, boot=True)
    assert legacy.get(tree.root) is False
    run(tree, {"EDCB_LEGACY_ALLOW_SETTING": "true"}, boot=True)
    assert legacy.get(tree.root) is True


def test_missing_root(tmp_path):
    paths = provision.Paths(str(tmp_path / "nope"), "", "", "")
    r = Capture()
    assert provision.run({}, paths, reporter=r) == 1
