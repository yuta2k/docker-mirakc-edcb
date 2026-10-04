from edcb_provision import config


def entries(plan):
    return {(e.file, e.section, e.key): e for e in plan.entries}


def test_defaults_only(tmp_path):
    plan = config.collect({}, str(tmp_path), None)
    e = entries(plan)
    assert not plan.warnings
    assert e[("EpgTimerSrv.ini", "SET", "CompatFlags")].value == "4095"
    assert e[("EpgTimerSrv.ini", "SET", "EnableTCPSrv")].value == "1"
    assert e[("EpgTimerSrv.ini", "SET", "HttpAccessControlList")].value == config.DEFAULT_HTTP_ACL
    assert e[("EpgTimerSrv.ini", "SET", "TCPAccessControlList")].value == config.DEFAULT_TCP_ACL
    assert e[("EpgDataCap_Bon.ini", "SET_TCP", "IP0")].anchor == "Count"
    assert all(not x.force for x in plan.entries)
    # no HttpPort without a certificate; no legacy switch unless booting
    assert ("EpgTimerSrv.ini", "SET", "HttpPort") not in e
    assert not any(x.file == config.WEBUI_INI for x in plan.entries)


def test_https_port_default_needs_certificate(tmp_path):
    (tmp_path / "ssl_cert.pem").write_text("x")
    e = entries(config.collect({}, str(tmp_path), None))
    assert e[("EpgTimerSrv.ini", "SET", "HttpPort")].value == "5510,5520,5511s,5521s"
    assert not e[("EpgTimerSrv.ini", "SET", "HttpPort")].force


def test_env_is_forced(tmp_path):
    env = {
        "EDCB_HTTP_ACL": "+0.0.0.0/0",
        "EDCB_HTTP_PORT": "5510,5520",
        "EDCB_HTTP_NUM_THREADS": "20",
        "EDCB_TCP_ENABLE": "False",
        "EDCB_TCP_ACL": "+192.168.0.0/16",
        "EDCB_COMPAT_FLAGS": "0",
        "EDCB_EMWUI_ALLOW_SETTING_LIST": "127.0.0.1,192.168.0.2",
    }
    plan = config.collect(env, str(tmp_path), None)
    e = entries(plan)
    assert not plan.warnings
    expect = {
        ("EpgTimerSrv.ini", "SET", "HttpAccessControlList"): "+0.0.0.0/0",
        ("EpgTimerSrv.ini", "SET", "HttpPort"): "5510,5520",
        ("EpgTimerSrv.ini", "SET", "HttpNumThreads"): "20",
        ("EpgTimerSrv.ini", "SET", "EnableTCPSrv"): "0",
        ("EpgTimerSrv.ini", "SET", "TCPAccessControlList"): "+192.168.0.0/16",
        ("EpgTimerSrv.ini", "SET", "CompatFlags"): "0",
        ("Setting/HttpPublic.ini", "SET", "ALLOW_SETTING_LIST"): "127.0.0.1,192.168.0.2",
    }
    for ident, value in expect.items():
        assert e[ident].value == value and e[ident].force, ident


def test_invalid_env_is_ignored_with_a_warning(tmp_path):
    env = {
        "EDCB_HTTP_ACL": "192.168.0.0/16",
        "EDCB_HTTP_NUM_THREADS": "100",
        "EDCB_TCP_ENABLE": "maybe",
        "EDCB_COMPAT_FLAGS": "x",
        "EDCB_REC_FOLDERS": " , ",
        "EDCB_CHSCAN": "always",
        "EDCB_TYPO": "1",
        "EDCB_BACKEND_VM_URL": "http://x",  # phase 3, not a typo
    }
    plan = config.collect(env, str(tmp_path), None)
    e = entries(plan)
    assert len(plan.warnings) == 7, plan.warnings
    assert not e[("EpgTimerSrv.ini", "SET", "HttpAccessControlList")].force
    assert not e[("EpgTimerSrv.ini", "SET", "EnableTCPSrv")].force
    assert not any(x.file == "Common.ini" for x in plan.entries)


def test_tcp_acl_mixing_families_warns(tmp_path):
    plan = config.collect({"EDCB_TCP_ACL": "+127.0.0.1,+::1"}, str(tmp_path), None)
    assert any("mixes IPv4 and IPv6" in w for w in plan.warnings)
    assert not config._acl_mixes_families(config.DEFAULT_TCP_ACL)


def test_rec_folders(tmp_path):
    plan = config.collect({"EDCB_REC_FOLDERS": "/recorded, /recorded2"}, str(tmp_path), None)
    e = entries(plan)
    assert e[("Common.ini", "SET", "RecFolderNum")].value == "2"
    assert e[("Common.ini", "SET", "RecFolderPath0")].value == "/recorded"
    assert e[("Common.ini", "SET", "RecFolderPath1")].value == "/recorded2"
    assert plan.trims[0].start == 2


def test_legacy_switch_on_boot(tmp_path):
    def legacy(env):
        plan = config.collect(env, str(tmp_path), None, boot=True)
        return entries(plan)[(config.WEBUI_INI, "LEGACY", "ALLOW_SETTING")]

    assert legacy({}).value == "0" and legacy({}).force
    assert legacy({"EDCB_LEGACY_ALLOW_SETTING": "true"}).value == "1"
    assert legacy({"EDCB_LEGACY_ALLOW_SETTING": "bogus"}).value == "0"


def test_overrides(tmp_path):
    ov = tmp_path / "ov"
    (ov / "Setting").mkdir(parents=True)
    (ov / "EpgTimerSrv.ini").write_text("[SET]\nHttpNumThreads=30\nCompatFlags=1\n")
    (ov / "Setting" / "HttpPublic.ini").write_text("[HLS]\nx=1\n")
    (ov / "notes.txt").write_text("hello")
    plan = config.collect({"EDCB_COMPAT_FLAGS": "2"}, str(tmp_path), str(ov))
    e = entries(plan)
    assert e[("EpgTimerSrv.ini", "SET", "HttpNumThreads")].value == "30"
    assert e[("EpgTimerSrv.ini", "SET", "HttpNumThreads")].source == "override EpgTimerSrv.ini"
    assert e[("EpgTimerSrv.ini", "SET", "CompatFlags")].value == "2"  # env wins
    assert e[("Setting/HttpPublic.ini", "HLS", "x")].force
    assert any("notes.txt" in w for w in plan.warnings)
    assert any("CompatFlags is ignored" in w for w in plan.warnings)
