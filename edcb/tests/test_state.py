import json
import os

from edcb_provision import fsutil
from edcb_provision.state import State


def test_round_trip_and_ownership(tmp_path):
    s = State(str(tmp_path)).load()
    (tmp_path / "gen.txt").write_bytes(b"abc")
    s.record("gen.txt", fsutil.sha256_bytes(b"abc"))
    s.save(fsutil.Owner())
    s2 = State(str(tmp_path)).load()
    assert s2.is_ours("gen.txt")
    (tmp_path / "gen.txt").write_bytes(b"edited")
    assert not s2.is_ours("gen.txt")
    assert not s2.is_ours("unknown.txt")
    s2.forget("gen.txt")
    assert s2.recorded("gen.txt") is None


def test_missing_recorded_file_counts_as_ours(tmp_path):
    s = State(str(tmp_path))
    s.record("gone.txt", "x")
    assert s.is_ours("gone.txt")


def test_broken_state_is_ignored(tmp_path):
    (tmp_path / ".provision").mkdir()
    (tmp_path / ".provision" / "state.json").write_text("{broken")
    s = State(str(tmp_path)).load()
    assert s.warnings and s.data["files"] == {}
    (tmp_path / ".provision" / "state.json").write_text(json.dumps({"version": 99}))
    assert State(str(tmp_path)).load().warnings


def test_save_skips_identical_content(tmp_path):
    s = State(str(tmp_path))
    s.save(fsutil.Owner())
    p = tmp_path / ".provision" / "state.json"
    before = p.stat().st_mtime_ns
    s.save(fsutil.Owner())
    assert p.stat().st_mtime_ns == before


def test_write_atomic_keeps_mode(tmp_path):
    p = tmp_path / "a.ini"
    p.write_text("x")
    p.chmod(0o640)
    fsutil.write_atomic(str(p), b"y", fsutil.Owner())
    assert p.read_text() == "y" and (p.stat().st_mode & 0o777) == 0o640
    assert not list(tmp_path.glob(".*tmp*"))


def test_backup_prune(tmp_path):
    (tmp_path / "a.ini").write_text("x")
    for i in range(7):
        (tmp_path / ".provision" / "backup" / f"2026010{i}-000000").mkdir(parents=True, exist_ok=True)
    b = fsutil.Backup(str(tmp_path), fsutil.Owner())
    b.save("a.ini")
    assert (tmp_path / ".provision" / "backup").exists()
    b.prune()
    names = sorted(p.name for p in (tmp_path / ".provision" / "backup").iterdir())
    assert len(names) == 5
    assert names[-1] == os.path.basename(b.dir)
    assert (tmp_path / ".provision" / "backup" / names[-1] / "a.ini").read_text() == "x"
