import os

from edcb_provision import fsutil, httppublic
from edcb_provision.state import State


def sync(root, src, state, dry_run=False):
    logs, warns = [], []
    backup = fsutil.Backup(str(root), fsutil.Owner())
    n = httppublic.sync(str(root), str(src), state, backup, fsutil.Owner(), dry_run=dry_run, log=logs.append, warn=warns.append)
    return n, logs, warns, backup


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_install_update_and_remove(tmp_path):
    src, root = tmp_path / "img", tmp_path / "root"
    root.mkdir()
    write(src / "legacy" / "util.lua", b"v1")
    write(src / "E3" / "old.js", b"old")
    state = State(str(root))
    n, logs, warns, _ = sync(root, src, state)
    assert n == 2 and (root / "HttpPublic" / "E3" / "old.js").read_bytes() == b"old"

    # runtime files and the user's edits under HttpPublic
    write(root / "HttpPublic" / "video" / "thumbs" / "a.jpg", b"thumb")
    write(root / "HttpPublic" / "EMWUI" / "x.html", b"v1 emwui")

    # unchanged image: nothing happens, a deleted file is restored
    (root / "HttpPublic" / "legacy" / "util.lua").write_bytes(b"user edit")
    os.remove(root / "HttpPublic" / "E3" / "old.js")
    n, logs, warns, _ = sync(root, src, state)
    assert n == 1
    assert (root / "HttpPublic" / "legacy" / "util.lua").read_bytes() == b"user edit"
    assert (root / "HttpPublic" / "E3" / "old.js").exists()

    # new image: changed files are backed up and replaced, dropped ones removed
    write(src / "legacy" / "util.lua", b"v2")
    os.remove(src / "E3" / "old.js")
    write(src / "E3" / "new.js", b"new")
    n, logs, warns, backup = sync(root, src, state)
    assert logs == ["HttpPublic: updated (1 added, 1 replaced, 1 removed)"]
    assert (root / "HttpPublic" / "legacy" / "util.lua").read_bytes() == b"v2"
    assert not (root / "HttpPublic" / "E3" / "old.js").exists()
    assert (root / "HttpPublic" / "video" / "thumbs" / "a.jpg").exists()
    assert (root / "HttpPublic" / "EMWUI" / "x.html").exists()
    assert open(os.path.join(backup.dir, "HttpPublic", "legacy", "util.lua"), "rb").read() == b"user edit"


def test_first_run_over_v1_volume_replaces_different_files(tmp_path):
    src, root = tmp_path / "img", tmp_path / "root"
    write(src / "legacy" / "util.lua", b"patched")
    write(src / "index.html", b"same")
    write(root / "HttpPublic" / "legacy" / "util.lua", b"ALLOW_SETTING=true")
    write(root / "HttpPublic" / "index.html", b"same")
    n, logs, warns, backup = sync(root, src, State(str(root)))
    assert n == 1 and logs == ["HttpPublic: updated (0 added, 1 replaced, 0 removed)"]
    assert (root / "HttpPublic" / "legacy" / "util.lua").read_bytes() == b"patched"


def test_edited_file_dropped_from_image_is_kept(tmp_path):
    src, root = tmp_path / "img", tmp_path / "root"
    write(src / "a.lua", b"a")
    state = State(str(root))
    root.mkdir()
    sync(root, src, state)
    (root / "HttpPublic" / "a.lua").write_bytes(b"edited")
    os.remove(src / "a.lua")
    write(src / "b.lua", b"b")
    n, logs, warns, _ = sync(root, src, state)
    assert (root / "HttpPublic" / "a.lua").read_bytes() == b"edited"
    assert warns and "was edited" in warns[0]


def test_dry_run(tmp_path):
    src, root = tmp_path / "img", tmp_path / "root"
    root.mkdir()
    write(src / "a.lua", b"a")
    state = State(str(root))
    n, logs, warns, _ = sync(root, src, state, dry_run=True)
    assert n == 1 and logs == ["HttpPublic: would update (1 added, 0 replaced, 0 removed)"]
    assert not (root / "HttpPublic").exists()
    assert state.section("httppublic") == {}
