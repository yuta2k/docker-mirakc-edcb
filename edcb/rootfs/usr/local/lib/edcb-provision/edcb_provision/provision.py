"""The provisioning run (docs/v2/design.md, 5.1)."""

import os
import sys
from dataclasses import dataclass

from . import apply, backends, channels, config, fsutil, httppublic, initfiles, prune
from .state import State


@dataclass
class Paths:
    root: str = "/var/local/edcb"
    overrides: str = "/etc/edcb/overrides"
    share: str = "/usr/local/share/edcb"  # HttpPublic/ and Setting/ of the image
    edcb_ini: str = "/usr/local/src/EDCB/ini"  # EDCB's ini/ (sources of the initial files)
    lib: str = "/usr/local/lib/edcb"  # where EDCB loads BonDrivers from
    bondriver: str = "/usr/local/lib/edcb-bondriver/BonDriver_LinuxMirakc.so"  # copied into lib

    @classmethod
    def from_env(cls, env):
        # EDCB_PROVISION_* are for tests only
        p = cls()
        p.root = env.get("EDCB_PROVISION_ROOT", p.root)
        p.overrides = env.get("EDCB_PROVISION_OVERRIDES", p.overrides)
        p.share = env.get("EDCB_PROVISION_SHARE", p.share)
        p.edcb_ini = env.get("EDCB_PROVISION_EDCB_INI", p.edcb_ini)
        p.lib = env.get("EDCB_PROVISION_LIB", p.lib)
        p.bondriver = env.get("EDCB_PROVISION_BONDRIVER", p.bondriver)
        return p


PREFIX = "provision:"


class Reporter:
    def __init__(self, out=None, err=None):
        self.out = out
        self.err = err
        self.warnings = 0

    def log(self, msg):
        print(f"{PREFIX} {msg}", file=self.out or sys.stdout, flush=True)

    def warn(self, msg):
        self.warnings += 1
        print(f"{PREFIX} WARNING: {msg}", file=self.err or sys.stderr, flush=True)


def _fetch_timeout(env):
    # EDCB_PROVISION_FETCH_TIMEOUT is for tests only
    try:
        return max(1.0, float(env.get("EDCB_PROVISION_FETCH_TIMEOUT", backends.TOTAL_TIMEOUT)))
    except ValueError:
        return backends.TOTAL_TIMEOUT


def setup_backends(env, paths, owner, *, diff, r, fetch=None):
    """Fetch the backends, install their BonDrivers and return the tuner count entries.

    Never raises: a backend problem must not keep EpgTimerSrv from starting.
    Returns (backends, their Info by name, entries, number of changes); after
    an unexpected error, the Info is None (the backends are unknown).
    """
    try:
        found, warnings = backends.parse_env(env)
        for w in warnings:
            r.warn(w)
        live = (fetch or backends.fetch_all)(found, _fetch_timeout(env))
        infos = backends.resolve(paths.root, found, live, owner, dry_run=diff, log=r.log, warn=r.warn)
        for b in found:
            r.log(backends.describe(b, infos[b.name]))
        changes = backends.install_bondrivers(
            found, paths.lib, paths.bondriver, dry_run=diff, log=r.log, warn=r.warn
        )
        return found, infos, backends.tuner_entries(paths.root, found, infos, warn=r.warn), changes
    except Exception as e:  # noqa: BLE001 - see the docstring
        r.warn(f"backends are not set up: {type(e).__name__}: {e}")
        return [], None, [], 0


def setup_channels(env, paths, found, infos, state, backup, owner, *, diff, r):
    """Scan on the first start, split the scans into ChSet4 files (design.md 8).

    Never raises, like setup_backends. Returns the number of changes.
    """
    try:
        return channels.boot(
            env, paths, found, infos, state, backup, owner, dry_run=diff, log=r.log, warn=r.warn
        )
    except Exception as e:  # noqa: BLE001 - see the docstring
        r.warn(f"channel files are not set up: {type(e).__name__}: {e}")
        return 0


def report_leftovers(env, paths, found, infos, state, *, r):
    """Warn about leftovers of removed backends; never removes them (edcbctl prune does)."""
    if infos is None:
        # the backends are unknown: every one would look removed
        return
    try:
        keep = backends.ignored_names(env, found)
        prune.report_at_start(prune.find(paths.root, state, found, infos, keep), warn=r.warn)
    except Exception as e:  # noqa: BLE001 - like setup_backends
        r.warn(f"cannot look for leftovers of removed backends: {type(e).__name__}: {e}")


def run(env, paths, *, diff=False, boot=False, reporter=None, fetch=None):
    r = reporter or Reporter()
    owner = fsutil.Owner.from_env(env)
    if not os.path.isdir(paths.root):
        r.warn(f"{paths.root} does not exist; nothing to do")
        return 1
    state = State(paths.root).load()
    for w in state.warnings:
        r.warn(w)
    backup = fsutil.Backup(paths.root, owner)
    if diff:
        r.log("dry run (--diff): nothing is written")

    count = initfiles.ensure(
        paths.root, paths.edcb_ini, paths.share, owner, dry_run=diff, log=r.log, warn=r.warn
    )
    count += httppublic.sync(
        paths.root,
        os.path.join(paths.share, "HttpPublic"),
        state,
        backup,
        owner,
        dry_run=diff,
        log=r.log,
        warn=r.warn,
    )

    found, infos, entries, changes = setup_backends(env, paths, owner, diff=diff, r=r, fetch=fetch)
    count += changes
    count += setup_channels(env, paths, found, infos or {}, state, backup, owner, diff=diff, r=r)
    report_leftovers(env, paths, found, infos, state, r=r)

    plan = config.collect(env, paths.root, paths.overrides, boot=boot, extra=entries)
    results = apply.compute(plan, paths.root)
    for w in plan.warnings:
        r.warn(w)
    for res in results:
        if not res.existed:
            r.log(f"create {res.file}")
        for c in res.changes:
            r.log(c.describe())
        count += len(res.changes)

    if not diff:
        apply.write(results, paths.root, backup, owner)
        state.save(owner)
        backup.prune()
        if backup.dir:
            r.log(f"backup: {os.path.relpath(backup.dir, paths.root)}")
    if count == 0:
        r.log("no changes")
    return 0
