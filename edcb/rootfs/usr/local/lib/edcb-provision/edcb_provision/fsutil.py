"""File helpers: atomic writes that keep ownership, backups."""

import hashlib
import os
import shutil
import time
from dataclasses import dataclass

STATE_DIR = ".provision"


@dataclass
class Owner:
    """Owner for new files. None fields mean "leave as created"."""

    uid: int | None = None
    gid: int | None = None

    @classmethod
    def from_env(cls, env):
        # only root can give files away; as another user, files are ours anyway
        if os.geteuid() != 0:
            return cls()
        return cls(_int(env.get("PUID"), 1000), _int(env.get("PGID"), 1000))

    def apply(self, path):
        if self.uid is None and self.gid is None:
            return
        os.chown(path, -1 if self.uid is None else self.uid, -1 if self.gid is None else self.gid, follow_symlinks=False)


def _int(value, fallback):
    try:
        n = int(str(value).strip())
        return n if n >= 0 else fallback
    except (TypeError, ValueError):
        return fallback


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def makedirs(path, owner):
    """Create a directory and its missing parents, owned by owner."""
    missing = []
    p = os.path.abspath(path)
    while not os.path.isdir(p):
        missing.append(p)
        p = os.path.dirname(p)
    for d in reversed(missing):
        os.mkdir(d)
        owner.apply(d)


def write_atomic(path, data, owner):
    """Write data to path through a temporary file and rename.

    An existing file keeps its owner and mode. A new file gets owner and the
    mode from the umask.
    """
    makedirs(os.path.dirname(path) or ".", owner)
    try:
        st = os.stat(path)
    except FileNotFoundError:
        st = None
    tmp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.provision-tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    if st is not None:
        os.chmod(tmp, st.st_mode & 0o7777)
        if os.geteuid() == 0:
            os.chown(tmp, st.st_uid, st.st_gid)
    else:
        owner.apply(tmp)
    os.replace(tmp, path)


def copy_file(src, dst, owner):
    with open(src, "rb") as f:
        data = f.read()
    write_atomic(dst, data, owner)


class Backup:
    """Copies files into .provision/backup/<time>/ before they are changed.

    The directory is created on the first save, so a run without changes
    leaves no backup. Only the newest `keep` backups are kept.
    """

    def __init__(self, root, owner, keep=5):
        self.root = root
        self.owner = owner
        self.keep = keep
        self.base = os.path.join(root, STATE_DIR, "backup")
        self.dir = None

    def _ensure_dir(self):
        if self.dir is None:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            d = os.path.join(self.base, stamp)
            n = 1
            while os.path.exists(d):
                n += 1
                d = os.path.join(self.base, f"{stamp}-{n}")
            makedirs(d, self.owner)
            self.dir = d
        return self.dir

    def save(self, rel):
        src = os.path.join(self.root, rel)
        if not os.path.isfile(src):
            return
        dst = os.path.join(self._ensure_dir(), rel)
        makedirs(os.path.dirname(dst), self.owner)
        shutil.copy2(src, dst)
        self.owner.apply(dst)

    def prune(self):
        if not os.path.isdir(self.base):
            return
        names = sorted(n for n in os.listdir(self.base) if os.path.isdir(os.path.join(self.base, n)))
        for name in names[: max(0, len(names) - self.keep)]:
            shutil.rmtree(os.path.join(self.base, name))
