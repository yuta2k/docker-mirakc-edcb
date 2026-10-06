"""Collect the ini keys to write from environment variables and override files.

See docs/v2/design.md, chapters 3 and 4. Every entry is either forced (written
on every start because the user asked for it) or a default (written only when
the key is absent). A key that exists is never replaced by a default, even
when its value is "0" or empty: that is how the WebUI stores "off".
"""

import os
import re
from dataclasses import dataclass, field

from . import ini

SRV_INI = "EpgTimerSrv.ini"
COMMON_INI = "Common.ini"
APP_INI = "EpgDataCap_Bon.ini"
EMWUI_INI = "Setting/HttpPublic.ini"
# Owned by the provisioning. Read by the patched legacy/util.lua on every request
# (edcb.GetPrivateProfile resolves the path relative to /var/local/edcb).
WEBUI_INI = ".provision/webui.ini"
LEGACY_SECTION = "LEGACY"
LEGACY_KEY = "ALLOW_SETTING"

# Private address ranges. The HTTP server (CivetWeb) matches IPv4 rules only
# against IPv4 clients, and sees IPv4 clients of a dual-stack port ("+5510")
# as IPv4-mapped IPv6 addresses, so both forms are listed.
DEFAULT_HTTP_ACL = ",".join(
    [
        "+127.0.0.1",
        "+10.0.0.0/8",
        "+172.16.0.0/12",
        "+192.168.0.0/16",
        "+::1",
        "+::ffff:127.0.0.1",
        "+::ffff:10.0.0.0/104",
        "+::ffff:172.16.0.0/108",
        "+::ffff:192.168.0.0/112",
        "+fc00::/7",
        "+fe80::/10",
    ]
)
# The TCP server (Common/TCPServer.cpp, TestAcl) parses every rule with the
# address family of the client and denies the connection when a rule does not
# parse, so a list that mixes IPv4 and IPv6 rules denies everyone. IPv4 only.
DEFAULT_TCP_ACL = "+127.0.0.1,+10.0.0.0/8,+172.16.0.0/12,+192.168.0.0/16"
# HttpPort recommended by EMWUI when HTTPS is available (ssl_cert.pem exists)
DEFAULT_HTTPS_PORTS = "5510,5520,5511s,5521s"

KNOWN_ENV = {
    "PUID",
    "PGID",
    "UMASK",
    "TZ",
    "EDCB_HTTP_ACL",
    "EDCB_HTTP_PORT",
    "EDCB_HTTP_NUM_THREADS",
    "EDCB_TCP_ENABLE",
    "EDCB_TCP_ACL",
    "EDCB_COMPAT_FLAGS",
    "EDCB_REC_FOLDERS",
    "EDCB_LEGACY_ALLOW_SETTING",
    "EDCB_EMWUI_ALLOW_SETTING_LIST",
    "EDCB_CHSCAN",
    "EDCB_LOG_STDOUT",
}
# handled elsewhere or reserved for later phases
_IGNORED_ENV_PREFIXES = ("EDCB_BACKEND_", "EDCB_PROVISION_")

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def parse_bool(value):
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return None


@dataclass
class Entry:
    file: str  # path relative to the EDCB root, e.g. "EpgTimerSrv.ini"
    section: str
    key: str
    value: str | None  # None: delete the key
    force: bool
    source: str  # shown in the change log, e.g. "env EDCB_HTTP_ACL"
    # for a default: write it only when this key (in the same section) is absent
    anchor: str | None = None

    @property
    def ident(self):
        return (self.file, self.section.casefold(), self.key.casefold())


@dataclass
class Trim:
    """Delete <prefix><N> keys for N >= start (the rest of a shortened list)."""

    file: str
    section: str
    prefix: str
    start: int
    source: str


@dataclass
class Plan:
    entries: list = field(default_factory=list)
    trims: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def files(self):
        names = []
        for item in [*self.entries, *self.trims]:
            if item.file not in names:
                names.append(item.file)
        return names


def _acl_ok(value):
    rules = value.split(",")
    return all(len(r) > 1 and r[0] in "+-" for r in rules)


def _acl_mixes_families(value):
    rules = [r[1:].split("/")[0] for r in value.split(",") if r]
    has_v6 = any(":" in r for r in rules)
    has_v4 = any(":" not in r for r in rules)
    return has_v4 and has_v6


def collect(env, root, overrides_dir, *, boot=False, extra=()):
    """Build the plan.

    env: mapping of environment variables.
    root: the EDCB root (/var/local/edcb); used for conditional defaults.
    overrides_dir: directory with the override ini files (may not exist).
    boot: True when run by the entrypoint. Resets the legacy WebUI permission
        to its start-up state; "edcbctl provision" leaves it alone.
    extra: entries computed elsewhere (tuner counts of the backends). Forced
        ones rank with the environment variables, the others with the defaults.
    """
    plan = Plan()
    warn = plan.warnings.append
    env_entries = []

    def from_env(name, file, section, key, value):
        env_entries.append(Entry(file, section, key, value, True, f"env {name}"))

    def get(name):
        value = env.get(name)
        if value is None or value.strip() == "":
            return None
        return value.strip()

    for name in sorted(env):
        if name.startswith("EDCB_") and name not in KNOWN_ENV and not name.startswith(_IGNORED_ENV_PREFIXES):
            warn(f"unknown variable {name} is ignored")

    # --- EpgTimerSrv.ini ---
    v = get("EDCB_HTTP_ACL")
    if v is not None:
        if _acl_ok(v):
            from_env("EDCB_HTTP_ACL", SRV_INI, "SET", "HttpAccessControlList", v)
        else:
            warn(f"EDCB_HTTP_ACL is ignored: every rule must start with + or - (got {v!r})")

    v = get("EDCB_HTTP_PORT")
    if v is not None:
        from_env("EDCB_HTTP_PORT", SRV_INI, "SET", "HttpPort", v)

    v = get("EDCB_HTTP_NUM_THREADS")
    if v is not None:
        if v.isdigit() and 1 <= int(v) <= 50:
            from_env("EDCB_HTTP_NUM_THREADS", SRV_INI, "SET", "HttpNumThreads", str(int(v)))
        else:
            warn(f"EDCB_HTTP_NUM_THREADS is ignored: must be 1 to 50 (got {v!r})")

    v = get("EDCB_TCP_ENABLE")
    if v is not None:
        b = parse_bool(v)
        if b is None:
            warn(f"EDCB_TCP_ENABLE is ignored: must be true or false (got {v!r})")
        else:
            from_env("EDCB_TCP_ENABLE", SRV_INI, "SET", "EnableTCPSrv", "1" if b else "0")

    v = get("EDCB_TCP_ACL")
    if v is not None:
        if not _acl_ok(v):
            warn(f"EDCB_TCP_ACL is ignored: every rule must start with + or - (got {v!r})")
        else:
            if _acl_mixes_families(v):
                warn(
                    "EDCB_TCP_ACL mixes IPv4 and IPv6 rules; EDCB's TCP server denies every "
                    "connection with such a list"
                )
            from_env("EDCB_TCP_ACL", SRV_INI, "SET", "TCPAccessControlList", v)

    v = get("EDCB_COMPAT_FLAGS")
    if v is not None:
        if re.fullmatch(r"-?\d+", v):
            from_env("EDCB_COMPAT_FLAGS", SRV_INI, "SET", "CompatFlags", v)
        else:
            warn(f"EDCB_COMPAT_FLAGS is ignored: must be an integer (got {v!r})")

    # --- Common.ini ---
    v = get("EDCB_REC_FOLDERS")
    if v is not None:
        folders = [f.strip() for f in v.split(",") if f.strip()]
        if folders:
            name = "EDCB_REC_FOLDERS"
            from_env(name, COMMON_INI, "SET", "RecFolderNum", str(len(folders)))
            for i, folder in enumerate(folders):
                from_env(name, COMMON_INI, "SET", f"RecFolderPath{i}", folder)
            plan.trims.append(Trim(COMMON_INI, "SET", "RecFolderPath", len(folders), f"env {name}"))
        else:
            warn("EDCB_REC_FOLDERS is ignored: no folder given")

    # --- Setting/HttpPublic.ini (EMWUI) ---
    v = get("EDCB_EMWUI_ALLOW_SETTING_LIST")
    if v is not None:
        from_env("EDCB_EMWUI_ALLOW_SETTING_LIST", EMWUI_INI, "SET", "ALLOW_SETTING_LIST", v)

    # --- legacy WebUI permission (reset on every start) ---
    if boot:
        v = get("EDCB_LEGACY_ALLOW_SETTING")
        allow = False
        source = "start-up state"
        if v is not None:
            b = parse_bool(v)
            if b is None:
                warn(f"EDCB_LEGACY_ALLOW_SETTING is ignored: must be true or false (got {v!r})")
            else:
                allow = b
                source = "env EDCB_LEGACY_ALLOW_SETTING"
        env_entries.append(Entry(WEBUI_INI, LEGACY_SECTION, LEGACY_KEY, "1" if allow else "0", True, source))

    # --- variables used later ---
    v = get("EDCB_CHSCAN")
    if v is not None and v.lower() not in ("first", "never"):
        warn(f"EDCB_CHSCAN must be first or never (got {v!r})")

    # --- override files ---
    override_entries = _collect_overrides(overrides_dir, warn)

    # --- defaults (written only when the key is absent) ---
    def default(file, section, key, value, anchor=None):
        return Entry(file, section, key, value, False, "default", anchor)

    defaults = [
        default(SRV_INI, "SET", "EnableHttpSrv", "1"),
        default(SRV_INI, "SET", "HttpAccessControlList", DEFAULT_HTTP_ACL),
        default(SRV_INI, "SET", "HttpNumThreads", "50"),
        default(SRV_INI, "SET", "EnableTCPSrv", "1"),
        default(SRV_INI, "SET", "TCPAccessControlList", DEFAULT_TCP_ACL),
        default(SRV_INI, "SET", "CompatFlags", "4095"),
        default(SRV_INI, "SET", "SaveDebugLog", "1"),
        default(APP_INI, "SET", "SaveLogo", "1"),
        default(APP_INI, "SET", "SaveLogoTypeFlags", "32"),
        # one TCP output to SrvPipe (IP 1 = 0.0.0.1, port 0); EMWUI uses it to
        # watch live TV. The three keys form one list, so they are written only
        # when Count is absent: "Count=0" means the user turned it off.
        default(APP_INI, "SET_TCP", "Count", "1"),
        default(APP_INI, "SET_TCP", "IP0", "1", anchor="Count"),
        default(APP_INI, "SET_TCP", "Port0", "0", anchor="Count"),
    ]
    if os.path.exists(os.path.join(root, "ssl_cert.pem")):
        defaults.append(default(SRV_INI, "SET", "HttpPort", DEFAULT_HTTPS_PORTS))

    env_entries += [e for e in extra if e.force]
    defaults += [e for e in extra if not e.force]

    # --- merge: env > override > default ---
    by_ident = {}
    for e in env_entries:
        by_ident[e.ident] = e
    for e in override_entries:
        if e.ident in by_ident:
            warn(
                f"{e.source}: [{e.section}] {e.key} is ignored because "
                f"{by_ident[e.ident].source} sets the same key"
            )
            continue
        by_ident[e.ident] = e
    for e in defaults:
        by_ident.setdefault(e.ident, e)
    plan.entries = list(by_ident.values())
    return plan


def _collect_overrides(overrides_dir, warn):
    entries = []
    if not overrides_dir or not os.path.isdir(overrides_dir):
        return entries
    for dirpath, dirnames, filenames in os.walk(overrides_dir):
        # hidden files and folders (the .gitkeep of the repository, editor files) are skipped silently
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, overrides_dir)
            if not name.lower().endswith(".ini"):
                warn(f"override {rel} is ignored: only .ini files are applied")
                continue
            try:
                with open(path, "rb") as f:
                    values = ini.parse_values(f.read())
            except OSError as e:
                warn(f"override {rel} is ignored: {e}")
                continue
            for (section, key), value in values.items():
                entries.append(Entry(rel, section, key, value, True, f"override {rel}"))
    return entries
