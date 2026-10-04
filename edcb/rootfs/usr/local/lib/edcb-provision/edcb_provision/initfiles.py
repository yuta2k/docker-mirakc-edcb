"""Create the initial files that EDCB expects, only when they are missing.

This replaces "make setup_ini" (Document/Unix/Makefile), which also copies
HttpPublic; HttpPublic is handled by httppublic.py instead. EpgTimerSrv.ini is
not created here: the defaults of the plan create it.
"""

import os

from . import fsutil


def _crlf_to_lf(data):
    return data.replace(b"\r", b"")


def _from_cp932(data):
    return _crlf_to_lf(data.decode("cp932").encode("utf-8"))


def _to_utf8(data):
    # EMWUI ships Setting/HttpPublic.ini in CP932 (Windows); EDCB on Linux and
    # the provisioning read ini files as UTF-8
    try:
        data.decode("utf-8")
        return data
    except UnicodeDecodeError:
        return data.decode("cp932").encode("utf-8")


def _bonctrl(data):
    # sed 's/\.dll$/.so/'
    lines = _from_cp932(data).split(b"\n")
    return b"\n".join(line[:-4] + b".so" if line.endswith(b".dll") else line for line in lines)


# (file under the EDCB root, file under EDCB's ini/, conversion)
_FROM_EDCB = [
    ("Bitrate.ini", "Bitrate.ini", _from_cp932),
    ("BonCtrl.ini", "BonCtrl.ini", _bonctrl),
    ("ContentTypeText.txt", "ContentTypeText.txt", _crlf_to_lf),
]
# EMWUI's per-user settings (<share>/Setting/: HttpPublic.ini, XCODE_OPTIONS.lua),
# copied once and then owned by the user; ini files are converted to UTF-8
_SETTING = "Setting"


def ensure(root, edcb_ini_dir, share_dir, owner, *, dry_run, log, warn):
    """Create the missing files. Return the number of files (to be) created."""
    created = 0
    jobs = [(dst, os.path.join(edcb_ini_dir, src), conv) for dst, src, conv in _FROM_EDCB]
    setting_src = os.path.join(share_dir, _SETTING)
    for dirpath, dirnames, filenames in os.walk(setting_src):
        dirnames.sort()
        for name in sorted(filenames):
            src = os.path.join(dirpath, name)
            jobs.append((os.path.relpath(src, share_dir), src, _to_utf8 if name.lower().endswith(".ini") else None))
    for rel, src, conv in jobs:
        dst = os.path.join(root, rel)
        if os.path.lexists(dst):
            continue
        try:
            with open(src, "rb") as f:
                data = f.read()
            if conv:
                data = conv(data)
        except (OSError, UnicodeDecodeError) as e:
            warn(f"cannot create {rel}: {e}")
            continue
        log(f"create {rel}")
        created += 1
        if not dry_run:
            fsutil.write_atomic(dst, data, owner)
    return created
