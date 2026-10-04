"""Switch whether the legacy WebUI may change settings, without a restart.

At build time, the "ALLOW_SETTING=false" line of HttpPublic/legacy/util.lua is
replaced by an expression that reads [LEGACY] ALLOW_SETTING from
.provision/webui.ini (see edcb/build/patch-legacy-util.sh). Every legacy
setting page runs util.lua on each request, so a change of the key takes
effect on the next request.
"""

import os

from . import config, fsutil, ini

UTIL_LUA = "HttpPublic/legacy/util.lua"
MARKER = config.WEBUI_INI


def _path(root):
    return os.path.join(root, config.WEBUI_INI)


def get(root):
    """Return True/False, or None if the switch was never written."""
    try:
        value = ini.IniFile.load(_path(root)).get(config.LEGACY_SECTION, config.LEGACY_KEY)
    except FileNotFoundError:
        return None
    if value is None:
        return None
    return value == "1"


def set(root, allow, owner):
    path = _path(root)
    try:
        f = ini.IniFile.load(path)
    except FileNotFoundError:
        f = ini.IniFile()
    f.set(config.LEGACY_SECTION, config.LEGACY_KEY, "1" if allow else "0")
    fsutil.write_atomic(path, f.to_bytes(), owner)


def util_lua_is_patched(root):
    """None if util.lua is missing, else whether it reads the switch."""
    try:
        with open(os.path.join(root, UTIL_LUA), "rb") as f:
            return MARKER.encode() in f.read()
    except FileNotFoundError:
        return None
