from edcb_provision import apply, config

# EpgTimerSrv.ini / EpgDataCap_Bon.ini as the WebUI writes them: features
# turned off are "0", and a v1 setup has no TCP keys at all
SRV = """[SET]
EnableHttpSrv=2
HttpAccessControlList=+127.0.0.1,+::1,+::ffff:127.0.0.1,+192.168.0.0/24
EnableTCPSrv=0
SaveDebugLog=0
StartMargin=5
[BonDriver_LinuxMirakc.so]
Count=4
"""
APP = """[SET]
SaveLogo=0
SaveLogoTypeFlags=
[SET_TCP]
Count=0
"""


def run(root, env=None, **kw):
    plan = config.collect(env or {}, str(root), None, **kw)
    return plan, apply.compute(plan, str(root))


def changes(results):
    return {(c.file, c.section, c.key): c for r in results for c in r.changes}


def test_existing_keys_are_never_replaced_by_defaults(tmp_path):
    (tmp_path / "EpgTimerSrv.ini").write_text(SRV)
    (tmp_path / "EpgDataCap_Bon.ini").write_text(APP)
    plan, results = run(tmp_path)
    c = changes(results)
    for r in results:
        for ch in r.changes:
            assert ch.old is None, ch.describe()  # only additions
    assert ("EpgTimerSrv.ini", "SET", "EnableHttpSrv") not in c
    assert ("EpgTimerSrv.ini", "SET", "EnableTCPSrv") not in c
    assert ("EpgTimerSrv.ini", "SET", "SaveDebugLog") not in c
    assert ("EpgDataCap_Bon.ini", "SET", "SaveLogo") not in c
    assert ("EpgDataCap_Bon.ini", "SET", "SaveLogoTypeFlags") not in c
    # Count=0 exists, so the SrvPipe list is not added
    assert not any(k[1] == "SET_TCP" for k in c)
    assert c[("EpgTimerSrv.ini", "SET", "CompatFlags")].new == "4095"
    assert c[("EpgTimerSrv.ini", "SET", "TCPAccessControlList")].new == config.DEFAULT_TCP_ACL


def test_new_files_get_all_defaults(tmp_path):
    plan, results = run(tmp_path)
    by_file = {r.file: r for r in results}
    assert not by_file["EpgTimerSrv.ini"].existed
    text = by_file["EpgDataCap_Bon.ini"].new.to_text()
    assert text == "[SET]\nSaveLogo=1\nSaveLogoTypeFlags=32\n[SET_TCP]\nCount=1\nIP0=1\nPort0=0\n"


def test_forced_values_are_restored_and_unchanged_ones_are_quiet(tmp_path):
    (tmp_path / "EpgTimerSrv.ini").write_text(SRV)
    env = {"EDCB_HTTP_ACL": "+0.0.0.0/0", "EDCB_TCP_ENABLE": "true"}
    plan, results = run(tmp_path, env)
    c = changes(results)
    assert c[("EpgTimerSrv.ini", "SET", "HttpAccessControlList")].new == "+0.0.0.0/0"
    assert c[("EpgTimerSrv.ini", "SET", "EnableTCPSrv")].old == "0"
    assert c[("EpgTimerSrv.ini", "SET", "EnableTCPSrv")].new == "1"
    for r in results:
        (tmp_path / r.file).write_bytes(r.new.to_bytes())
    plan, results = run(tmp_path, env)
    assert results == []


def test_rec_folders_trim(tmp_path):
    (tmp_path / "Common.ini").write_text(
        "[SET]\nRecFolderPath0=/a\nRecFolderPath1=/b\nRecFolderPath2=/c\nRecFolderNum=3\nRecInfoDelFile=0\n"
    )
    plan, results = run(tmp_path, {"EDCB_REC_FOLDERS": "/x"})
    assert results[0].new.to_text() == "[SET]\nRecFolderPath0=/x\nRecFolderNum=1\nRecInfoDelFile=0\n"
    c = changes(results)
    assert c[("Common.ini", "SET", "RecFolderPath2")].new is None


def test_describe():
    ch = apply.Change("A.ini", "SET", "K", None, "1", "default")
    assert ch.describe() == 'A.ini [SET] K: (absent) -> "1" (default)'
