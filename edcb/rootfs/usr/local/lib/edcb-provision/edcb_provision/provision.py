"""The provisioning run (docs/v2/design.md, 5.1)."""

import os
import sys
from dataclasses import dataclass

from . import apply, config, fsutil, httppublic, initfiles
from .state import State


@dataclass
class Paths:
    root: str = "/var/local/edcb"
    overrides: str = "/etc/edcb/overrides"
    share: str = "/usr/local/share/edcb"  # HttpPublic/ and Setting/ of the image
    edcb_ini: str = "/usr/local/src/EDCB/ini"  # EDCB's ini/ (sources of the initial files)

    @classmethod
    def from_env(cls, env):
        # EDCB_PROVISION_* are for tests only
        p = cls()
        p.root = env.get("EDCB_PROVISION_ROOT", p.root)
        p.overrides = env.get("EDCB_PROVISION_OVERRIDES", p.overrides)
        p.share = env.get("EDCB_PROVISION_SHARE", p.share)
        p.edcb_ini = env.get("EDCB_PROVISION_EDCB_INI", p.edcb_ini)
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


def run(env, paths, *, diff=False, boot=False, reporter=None):
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

    plan = config.collect(env, paths.root, paths.overrides, boot=boot)
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
