"""Leftovers of removed backends and of kinds without tuners (edcbctl prune).

When a backend is removed from the environment, the start-up removes its
BonDriver files from the image, but the files in the volume stay: its ChSet4
files, its [BonDriver_*.so] sections and rows of the viewing list ([TVTEST])
in EpgTimerSrv.ini, and its records in .provision/. A kind whose tuners went
down to 0 keeps its section and viewing list row (its ChSet4 is removed by
the split, design.md 8.3).

The start-up only reports them; "edcbctl prune" removes them after a backup
(docs/v2/phases/5-mirakc.md, task 4). A BonDriver whose ChSet4 the user placed
or edited is left alone entirely. ChSet5.txt is never changed: several
backends may share services (edcbctl chscan --all --rebuild makes it again).
Reservations fixed to a tuner of a removed BonDriver are only counted.
"""

import contextlib
import os
import re
from dataclasses import dataclass, field

from . import backends, channels, ctrlcmd, fsutil, ini
from .backends import DEFAULT_NAME, KINDS, VIEW_SECTION
from .config import SRV_INI
from .state import State

# BonDriver_LinuxMirakc[_<NAME>][_T|_S].so; the name is tried empty first, so
# that _T and _S are kinds (backends.py does not allow T and S as names)
_BONDRIVER_RE = re.compile(r"BonDriver_LinuxMirakc(?:_([A-Z][A-Z0-9]*))??(?:_([TS]))?\.so", re.IGNORECASE)
_CHSET4_RE = re.compile(r"(BonDriver_LinuxMirakc[^()/]*)\(LinuxMirakc\)\.ChSet4\.txt", re.IGNORECASE)
_CACHE_RE = re.compile(r"backend-([A-Z][A-Z0-9]*)\.json")
_SCAN_RE = re.compile(r"scan-([A-Z][A-Z0-9]*)\.ChSet4\.txt")


def parse_bondriver(name):
    """(backend name, kind) of a BonDriver file name of ours, or None."""
    m = _BONDRIVER_RE.fullmatch(name.strip())
    if not m:
        return None
    return (m.group(1) or DEFAULT_NAME).upper(), (m.group(2) or "M").upper()


def bondriver_name(name, kind):
    return backends.Backend(name, "", "", 0).bondriver(kind)


@dataclass
class Plan:
    """What prune would do."""

    # BonDriver file name -> why it is a leftover
    bondrivers: dict = field(default_factory=dict)
    sections: list = field(default_factory=list)  # [BonDriver_*.so] sections, as written
    view_removed: list = field(default_factory=list)  # rows of [TVTEST] to remove
    view_kept: list = field(default_factory=list)  # the rows that stay, in order
    chset4: list = field(default_factory=list)  # generated ChSet4 files to delete
    forget: list = field(default_factory=list)  # records of ChSet4 files that are gone
    user_chset4: list = field(default_factory=list)  # ChSet4 files of the user of removed backends (left alone)
    state_files: list = field(default_factory=list)  # .provision/ files of removed backends
    channel_records: list = field(default_factory=list)  # names in the state's "channels"
    # Priority of each section to remove (reservations fixed to its tuners)
    priorities: dict = field(default_factory=dict)

    def empty(self):
        return not (
            self.sections
            or self.view_removed
            or self.chset4
            or self.forget
            or self.state_files
            or self.channel_records
        )

    def lines(self):
        """What would change, one line each."""
        out = []
        for bon, why in self.bondrivers.items():
            out.append(f"{bon}: {why}")
        for s in self.sections:
            out.append(f"  {SRV_INI}: remove section [{s}]")
        if self.view_removed:
            out.append(
                f"  {SRV_INI}: remove {', '.join(self.view_removed)} from [{VIEW_SECTION}] "
                f"(the BonDrivers used for viewing; {len(self.view_kept)} stay)"
            )
        for rel in self.chset4:
            out.append(f"  delete {rel}")
        for rel in self.state_files:
            out.append(f"  delete {rel}")
        for name in self.channel_records:
            out.append(f"  forget the channel scan of backend {name}")
        return out


def _srv(root):
    path = os.path.join(root, SRV_INI)
    return ini.IniFile.load(path) if os.path.isfile(path) else ini.IniFile()


def find(root, state, found, infos, keep=()):
    """Return the Plan for the backends found (with their Info by name).

    keep: names of backends whose settings were ignored (backends.ignored_names);
    they are not removed, so nothing of theirs is a leftover.
    """
    plan = Plan()
    by_name = {b.name: b for b in found}
    keep = set(keep)
    srv = _srv(root)

    # every BonDriver of ours that EDCB may still know about: (name, kind)
    candidates = set()
    for section in srv.section_names():
        parsed = parse_bondriver(section)
        if parsed:
            candidates.add(parsed)
    view = backends.view_bondrivers(srv)
    for row in view or []:
        parsed = parse_bondriver(row)
        if parsed:
            candidates.add(parsed)
    setting = os.path.join(root, "Setting")
    names = set(os.listdir(setting)) if os.path.isdir(setting) else set()
    names |= {os.path.basename(rel) for rel in state.data["files"] if rel.startswith("Setting" + os.sep)}
    for n in names:
        m = _CHSET4_RE.fullmatch(n)
        parsed = m and parse_bondriver(m.group(1) + ".so")
        if parsed:
            candidates.add(parsed)
    # backends removed with their records in .provision/: every kind
    removed = set()
    state_dir = os.path.join(root, fsutil.STATE_DIR)
    for n in sorted(os.listdir(state_dir)) if os.path.isdir(state_dir) else []:
        m = _CACHE_RE.fullmatch(n) or _SCAN_RE.fullmatch(n)
        if m and m.group(1) not in by_name and m.group(1) not in keep:
            removed.add(m.group(1))
            plan.state_files.append(os.path.join(fsutil.STATE_DIR, n))
    for name in state.section(channels.STATE_KEY):
        if name not in by_name and name not in keep:
            removed.add(name)
            plan.channel_records.append(name)
    # every kind of a removed backend, also those only some files mention
    removed |= {n for n, _ in candidates if n not in by_name and n not in keep}
    candidates |= {(n, k) for n in removed for k in KINDS}

    stale = {}  # BonDriver file name (lower) -> (file name, reason)
    for name, kind in sorted(candidates):
        if name in keep:
            continue
        bon = bondriver_name(name, kind)
        if name in by_name:
            counts, _ = backends.tuner_counts(by_name[name], infos[name])
            if counts is None or counts[kind] > 0:
                continue
            why = f"backend {name} has no tuners of kind {kind}"
        else:
            why = f"backend {name} is no longer set up"
        rel = backends.chset4_rel(bon)
        if os.path.lexists(os.path.join(root, rel)):
            if not state.is_ours(rel):
                # a kind without tuners is harmless: its Count is 0 or it is not used by EDCB;
                # a removed backend's BonDriver file is gone
                if name not in by_name:
                    plan.user_chset4.append(rel)
                continue
            plan.chset4.append(rel)
        elif state.recorded(rel) is not None:
            plan.forget.append(rel)
        stale[bon.lower()] = (bon, why)

    for section in srv.section_names():
        if section.strip().lower() in stale:
            plan.sections.append(section)
            v = (srv.get(section, "Priority") or "").strip()
            if v.isdigit():
                plan.priorities[section] = int(v)
    for row in view or []:
        (plan.view_removed if row.lower() in stale else plan.view_kept).append(row)

    # report only the BonDrivers that leave something to remove
    touched = {s.lower() for s in plan.sections} | {r.lower() for r in plan.view_removed}
    touched |= {_CHSET4_RE.fullmatch(os.path.basename(r)).group(1).lower() + ".so" for r in plan.chset4 + plan.forget}
    for key, (bon, why) in stale.items():
        if key in touched:
            plan.bondrivers[bon] = why
    return plan


def report_at_start(plan, *, warn):
    """The start-up message: nothing is removed (decided with the user)."""
    for rel in plan.user_chset4:
        warn(
            f"{rel} belongs to a backend that is no longer set up, but it was not made by the provisioning "
            "(or was edited) and is not removed; EDCB still lists its BonDriver, whose file is gone. "
            "Remove it yourself if it is not used"
        )
    if plan.empty():
        return
    what = f"leftovers of {', '.join(plan.bondrivers)}" if plan.bondrivers else "records of removed backends in .provision/"
    warn(f"{what} remain; nothing is deleted on start. Show them: edcbctl prune --diff; remove them: edcbctl prune")
    if plan.chset4:
        warn(
            f"EDCB still lists the BonDrivers of {', '.join(plan.chset4)} without their BonDriver files: "
            "a reservation given to them fails to record. Run edcbctl prune and restart"
        )


def _fixed_reservations(root, plan):
    """(number of enabled reservations fixed to a tuner of the removed sections, titles), or None."""
    if not plan.priorities:
        return 0, []
    try:
        items = ctrlcmd.reserves(root)
    except (OSError, ctrlcmd.CtrlCmdError):
        return None
    wanted = set(plan.priorities.values())
    fixed = [x for x in items if x["enabled"] and x["tuner_id"] and x["tuner_id"] >> 16 in wanted]
    return len(fixed), [x["title"] for x in fixed]


def apply(root, plan, state, backup, owner, *, log):
    """Remove what the plan lists."""
    if plan.sections or plan.view_removed:
        path = os.path.join(root, SRV_INI)
        srv = ini.IniFile.load(path)
        for s in plan.sections:
            srv.delete_section(s)
        if plan.view_removed:
            old = backends.view_bondrivers(srv) or []
            for i in range(len(old)):
                srv.delete(VIEW_SECTION, str(i))
            # Num=0 stays: without Num, the next start writes the default list again
            srv.set(VIEW_SECTION, "Num", str(len(plan.view_kept)))
            for i, row in enumerate(plan.view_kept):
                srv.set(VIEW_SECTION, str(i), row)
        backup.save(SRV_INI)
        fsutil.write_atomic(path, srv.to_bytes(), owner)
    for rel in plan.chset4:
        backup.save(rel)
        with contextlib.suppress(FileNotFoundError):
            os.remove(os.path.join(root, rel))
        state.forget(rel)
    for rel in plan.forget:
        state.forget(rel)
    for rel in plan.state_files:
        backup.save(rel)
        with contextlib.suppress(FileNotFoundError):
            os.remove(os.path.join(root, rel))
    records = state.section(channels.STATE_KEY)
    for name in plan.channel_records:
        records.pop(name, None)
    for line in plan.lines():
        log(line.strip())


def command(env, paths, *, diff=False, log, warn, out, fetch=None):
    """edcbctl prune. Return (exit status, whether files were changed)."""
    owner = fsutil.Owner.from_env(env)
    found, warnings = backends.parse_env(env)
    for w in warnings:
        warn(w)
    keep = backends.ignored_names(env, found)
    if keep:
        warn(
            f"backend {', '.join(sorted(keep))} is ignored because of its settings (see above); "
            "its files are left alone. Fix the variables to have them checked"
        )
    state = State(paths.root).load()
    for w in state.warnings:
        warn(w)
    live = (fetch or backends.fetch_all)(found, backends.TOTAL_TIMEOUT)
    infos = backends.resolve(paths.root, found, live, owner, dry_run=True, log=log, warn=warn)
    plan = find(paths.root, state, found, infos, keep)
    for rel in plan.user_chset4:
        warn(f"{rel} was not made by the provisioning (or was edited) and is left alone; remove it yourself if it is not used")
    if plan.empty():
        print("Nothing to prune.", file=out)
        return 0, False

    fixed = _fixed_reservations(paths.root, plan)
    if diff:
        print("Would prune (nothing is changed with --diff):", file=out)
        for line in plan.lines():
            print(line, file=out)
    if fixed is None:
        warn("cannot ask EpgTimerSrv for the reservations fixed to these tuners (is it running?)")
    elif fixed[0]:
        titles = ", ".join(fixed[1][:5]) + (", ..." if fixed[0] > 5 else "")
        warn(
            f"{fixed[0]} reservation(s) are fixed to tuners of these BonDrivers and are not changed: {titles}. "
            "Change their tuner in the WebUI"
        )
    if diff:
        return 0, False

    backup = fsutil.Backup(paths.root, owner)
    with channels.scan_lock(paths.root, owner) as locked:
        if not locked:
            warn("a channel scan is running; try again later")
            return 1, False
        # a scan may have finished since the plan was made: plan again on what it left
        state = State(paths.root).load()
        plan = find(paths.root, state, found, infos, keep)
        if plan.empty():
            print("Nothing to prune.", file=out)
            return 0, False
        try:
            apply(paths.root, plan, state, backup, owner, log=log)
            state.save(owner)
        except OSError as e:
            warn(f"pruning failed: {e}")
            return 1, True
        finally:
            backup.prune()
    if backup.dir:
        log(f"backup: {os.path.relpath(backup.dir, paths.root)}")
    return 0, True
