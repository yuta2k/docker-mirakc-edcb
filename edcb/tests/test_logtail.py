import io

from edcb_provision.logtail import Follower


def test_follow_new_lines_and_new_files(tmp_path):
    srv = tmp_path / "EpgTimerSrvDebugLog.txt"
    srv.write_bytes(b"old line\n")
    out = io.StringIO()
    f = Follower(str(tmp_path), out)
    f.scan(initial=True)
    f.poll()
    assert out.getvalue() == ""
    with open(srv, "ab") as fp:
        fp.write("新しい行\r\npartial".encode())
    (tmp_path / "EpgDataCap_Bon_DebugLog-0.txt").write_bytes(b"tuner\n")
    f.scan()
    f.poll()
    assert out.getvalue().splitlines() == ["[EpgTimerSrv] 新しい行", "[EpgDataCap_Bon-0] tuner"]
    with open(srv, "ab") as fp:
        fp.write(b" done\n")
    f.poll()
    assert out.getvalue().splitlines()[-1] == "[EpgTimerSrv] partial done"
    # truncated: start over
    srv.write_bytes(b"restart\n")
    f.poll()
    assert out.getvalue().splitlines()[-1] == "[EpgTimerSrv] restart"


def test_ready_file(tmp_path, monkeypatch):
    from edcb_provision import logtail

    ready = tmp_path / "ready"

    def sleep(_):
        assert ready.exists()  # created before the loop starts
        raise SystemExit

    monkeypatch.setattr(logtail.signal, "signal", lambda *a: None)
    monkeypatch.setattr(logtail.time, "sleep", sleep)
    try:
        logtail.main([str(ready)], root=str(tmp_path))
    except SystemExit:
        pass
    assert ready.exists()
