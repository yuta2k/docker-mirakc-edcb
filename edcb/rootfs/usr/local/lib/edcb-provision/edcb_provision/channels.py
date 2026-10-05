"""Channel scans and the ChSet4 file of each kind (docs/v2/design.md, chapter 8).

A scan runs "EpgDataCap_Bon -d <BonDriver> -chscan" once per backend. It uses
a copy of the backend's dual (M) BonDriver under a name of its own, so that
EDCB writes the result next to, not over, the ChSet4 files in use; the result
is then moved to .provision/scan-<NAME>.ChSet4.txt. From there one ChSet4 per
kind is made: M gets every row, T the rows of terrestrial spaces, S the rows
of satellite spaces. A kind without tuners gets no file, which hides its
BonDriver from EDCB (facts.md F3).

EDCB itself adds the services it finds to Setting/ChSet5.txt and resets
their EPG capture and search flags while doing so; the flags are put back
after every scan (facts.md F3).

Only files recorded in the state file with an unchanged hash are replaced
or deleted (design.md 5.3). A backend with a ChSet4 the user placed is
neither scanned nor split, unless the user hands it over explicitly
(edcbctl chscan --force).
"""

import contextlib
import fcntl
import os
import re
import shlex
import signal
import subprocess
import threading
import time

from . import backends, chset, fsutil
from .backends import KINDS
from .state import State

STATE_KEY = "channels"
CHSET5_REL = os.path.join("Setting", "ChSet5.txt")
LOCK_REL = os.path.join(fsutil.STATE_DIR, "chscan.lock")
EPGDATACAP = "EpgDataCap_Bon"

# EDCB waits up to ChChgTimeOut + ServiceChkTimeOut (9 + 8 s) per channel
SCAN_BASE_TIMEOUT = 120
SCAN_TIMEOUT_PER_CHANNEL = 30
# after SIGTERM (EpgDataCap_Bon cancels the scan), before SIGKILL
KILL_GRACE = 10

CHSCAN_MODES = ("first", "never")

# BonDriver_LinuxMirakc's message when the backend has no free tuner for a
# channel (mirakc answers 404, Mirakurun 503); EDCB's scan then skips the channel
TUNER_REFUSED = "Tuner unavailable"
# EDCB asks for EPG capture after a start that follows a scan (EpgTimerSrv
# reads new channel files only when it starts, facts.md U11)
EPGCAP_PENDING_REL = os.path.join(fsutil.STATE_DIR, "epgcap-pending")

# the status line EpgDataCap_Bon rewrites every second with "\r"
_STATUS_RE = re.compile(r"Sig:\S+ D:\d+ S:\d+ (sp:-?\d+ ch:-?\d+ )?((Rec|ChScan|EpgCap) )*\s*")


def scan_rel(name):
    return os.path.join(fsutil.STATE_DIR, f"scan-{name}.ChSet4.txt")


def chset4_files(backend):
    """{kind: ChSet4 path relative to the root} of a backend."""
    return {kind: backends.chset4_rel(backend.bondriver(kind)) for kind in KINDS}


def user_files(root, state, backend):
    """The ChSet4 files of a backend that belong to the user (design.md 5.3)."""
    return [
        rel
        for rel in chset4_files(backend).values()
        if os.path.lexists(os.path.join(root, rel)) and not state.is_ours(rel)
    ]


def chscan_mode(env):
    v = (env.get("EDCB_CHSCAN") or "").strip().lower()
    # an invalid value is reported by config.collect
    return v if v in CHSCAN_MODES else "first"


def scan_command(env):
    # EDCB_PROVISION_EPGDATACAP is for tests only
    return shlex.split(env.get("EDCB_PROVISION_EPGDATACAP") or EPGDATACAP)


@contextlib.contextmanager
def scan_lock(root, owner):
    """Hold the scan lock; yields False if another scan holds it."""
    path = os.path.join(root, LOCK_REL)
    fsutil.makedirs(os.path.dirname(path), owner)
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            owner.apply(path)
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _remove(path):
    with contextlib.suppress(FileNotFoundError):
        os.remove(path)


def _progress(raw):
    """A line of EpgDataCap_Bon's output without the status line, or None."""
    text = raw.decode("utf-8", "replace").replace("\r", "").strip()
    text = _STATUS_RE.sub("", text).strip()
    return text or None


# ----- scanning -----


class Scanner:
    """Runs the channel scan of one backend."""

    def __init__(self, root, lib, owner, command, *, log, warn):
        self.root = root
        self.lib = lib
        self.owner = owner
        self.command = command
        self.log = log
        self.warn = warn

    def _run(self, argv, timeout, prefix):
        """Run argv as PUID:PGID, pass its output on.

        Return (status, timed out, number of lines that report a busy backend).
        """
        kwargs = {}
        if self.owner.uid is not None:
            kwargs.update(user=self.owner.uid, group=self.owner.gid, extra_groups=[])
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self.root,
            start_new_session=True,
            **kwargs,
        )
        timed_out = threading.Event()

        def stop():
            timed_out.set()
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(KILL_GRACE)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)

        timer = threading.Timer(timeout, stop)
        timer.daemon = True
        timer.start()
        refused = 0
        try:
            for raw in proc.stdout:
                line = _progress(raw)
                if line:
                    self.log(f"{prefix}{line}")
                    if TUNER_REFUSED in line:
                        refused += 1
            status = proc.wait()
        finally:
            timer.cancel()
            proc.stdout.close()
        return status, timed_out.is_set(), refused

    def scan(self, backend, channels):
        """Scan one backend. Return (the scanned ChSet4 or None, channels missed).

        channels: /api/channels of the backend. A channel is reported as
        missed when it has no services in the result while the backend
        refused a tuner during the scan: EDCB skips such a channel.
        Setting/ChSet5.txt is changed by EDCB; the caller restores it.
        """
        n_channels = len(channels)
        name = f"{backends.BONDRIVER_BASE}-scan-{backend.name}.so"
        src = os.path.join(self.lib, backend.bondriver("M"))
        so = os.path.join(self.lib, name)
        out = os.path.join(self.root, backends.chset4_rel(name))
        try:
            with open(src, "rb") as f:
                so_data = f.read()
        except OSError as e:
            self.warn(f"backend {backend.name} is not scanned: cannot read {src}: {e}")
            return None, []
        timeout = SCAN_BASE_TIMEOUT + SCAN_TIMEOUT_PER_CHANNEL * n_channels
        argv = [*self.command, "-d", name, "-chscan"]
        self.log(f"backend {backend.name}: scanning {n_channels} channel(s) (at most {timeout} s): {' '.join(argv)}")
        started = time.monotonic()
        try:
            backends.write_lib_file(so, so_data, 0o755)
            backends.write_lib_file(so + ".ini", backend.bondriver_ini(), 0o644)
            _remove(out)
            status, timed_out, refused = self._run(argv, timeout, f"chscan {backend.name}: ")
            data = _read(out)
        except OSError as e:
            self.warn(f"backend {backend.name}: the scan failed: {e}")
            return None, []
        finally:
            for path in (so, so + ".ini", out):
                with contextlib.suppress(OSError):
                    _remove(path)
        elapsed = int(time.monotonic() - started)
        if timed_out:
            self.warn(f"backend {backend.name}: the scan took longer than {timeout} s and was stopped")
            return None, []
        if data is None:
            self.warn(f"backend {backend.name}: the scan did not finish (EpgDataCap_Bon exited with status {status})")
            return None, []
        rows = chset.count_rows(data)
        if rows == 0:
            self.warn(
                f"backend {backend.name}: the scan found no services (is the backend receiving? "
                "are tuners free?); nothing is changed"
            )
            return None, []
        self.log(f"backend {backend.name}: the scan found {rows} service(s) in {elapsed} s")
        missed = []
        if refused:
            found = chset.scanned_positions(data)
            missed = [c["channel"] for space, ch, c in chset.positions(channels) if (space, ch) not in found]
        return data, missed


class Channels:
    """Scans, the per-kind ChSet4 files and the state they leave."""

    def __init__(self, root, state, backup, owner, *, dry_run=False, log, warn):
        self.root = root
        self.state = state
        self.backup = backup
        self.owner = owner
        self.dry_run = dry_run
        self.log = log
        self.warn = warn
        self._chset5_saved = False

    @property
    def records(self):
        return self.state.section(STATE_KEY)

    def _path(self, rel):
        return os.path.join(self.root, rel)

    def _backup_chset5(self):
        # once per run: a second copy would replace the first in the same backup
        if not self._chset5_saved:
            self.backup.save(CHSET5_REL)
            self._chset5_saved = True

    def _put_chset5(self, data):
        path = self._path(CHSET5_REL)
        if data is None:
            _remove(path)
        else:
            fsutil.write_atomic(path, data, self.owner)

    def _restore_flags(self, before):
        """Put the flags of `before` (ChSet5 bytes) back into the current ChSet5."""
        if not before:
            return
        current = _read(self._path(CHSET5_REL))
        if current is None:
            return
        data, n = chset.restore_flags(current, chset.service_flags(before))
        if n:
            self._put_chset5(data)
            self.log(f"{CHSET5_REL}: kept the EPG and search flags of {n} service(s)")

    def _commit(self, backend, info, data):
        fsutil.write_atomic(self._path(scan_rel(backend.name)), data, self.owner)
        # the new services have no EPG yet; EDCB's default capture is at 23:00
        fsutil.write_atomic(self._path(EPGCAP_PENDING_REL), b"", self.owner)
        self.records[backend.name] = {
            "url": backend.url,
            "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "channels": chset.channels_hash(info.channels),
            "spaces": chset.spaces(info.channels),
        }

    def _scan_one(self, scanner, backend, infos, strict):
        """Scan a backend; return the ChSet4 or None (a failure, already reported)."""
        data, missed = scanner.scan(backend, infos[backend.name].channels)
        if data is None or not missed:
            return data
        what = (
            f"backend {backend.name}: the backend had no free tuner during the scan, and "
            f"{len(missed)} channel(s) have no services: {', '.join(missed)}"
        )
        if strict:
            self.warn(f"{what}; the result is not used. Try again when no recording or EPG capture runs (edcbctl status)")
            return None
        self.warn(f"{what}; the result is used, but may be incomplete. Scan again later: edcbctl chscan {backend.name}")
        return data

    def scan(self, scanner, targets, infos, *, rebuild=False, strict=False):
        """Scan the targets. Return the names scanned successfully.

        Without rebuild, every backend stands alone: a failed scan leaves
        ChSet5 as it was before it. With rebuild, ChSet5 is backed up and
        removed first, and put back when any scan fails.
        strict: a scan that missed channels for want of a free tuner fails
        (it would replace a complete scan); otherwise it is used with a warning.
        """
        path = self._path(CHSET5_REL)
        done = []
        if rebuild:
            before = _read(path)
            if before is not None:
                self._backup_chset5()
                self.log(f"{CHSET5_REL}: backed up and removed to be made again")
                _remove(path)
            results = {}
            for b in targets:
                data = self._scan_one(scanner, b, infos, strict)
                if data is None:
                    self.warn(f"rebuild stopped: the scan of backend {b.name} failed; {CHSET5_REL} is restored")
                    self._put_chset5(before)
                    return []
                results[b.name] = data
            self._restore_flags(before)
            for b in targets:
                self._commit(b, infos[b.name], results[b.name])
                done.append(b.name)
            return done
        for b in targets:
            before = _read(path)
            if before is not None:
                self._backup_chset5()
            data = self._scan_one(scanner, b, infos, strict)
            if data is None:
                if _read(path) != before:
                    self._put_chset5(before)
                continue
            self._restore_flags(before)
            self._commit(b, infos[b.name], data)
            done.append(b.name)
        return done

    def adopt(self, backend):
        """Hand the user's ChSet4 files of a backend over to the provisioning.

        They are backed up; afterwards they are replaced or deleted like
        generated ones (edcbctl chscan --force).
        """
        for rel in user_files(self.root, self.state, backend):
            self.backup.save(rel)
            self.state.record(rel, fsutil.sha256_file(self._path(rel)))
            self.log(f"{rel}: backed up; now managed by the provisioning")

    def split(self, backend, counts):
        """Make the ChSet4 of each kind from the saved scan. Return the number of changes.

        counts: tuners per kind, or None when unknown (files are then left as they are).
        """
        record = self.records.get(backend.name)
        if not record or counts is None:
            return 0
        scan = _read(self._path(scan_rel(backend.name)))
        if scan is None:
            self.warn(f"backend {backend.name}: {scan_rel(backend.name)} is missing; run: edcbctl chscan {backend.name}")
            return 0
        files, rows, warnings = chset.split(scan, record.get("spaces") or [])
        for w in warnings:
            self.warn(f"backend {backend.name}: {w}")
        changes = 0
        for kind, rel in chset4_files(backend).items():
            path = self._path(rel)
            n = counts[kind]
            want = files[kind] if n > 0 and rows[kind] > 0 else None
            if n > 0 and rows[kind] == 0:
                self.warn(
                    f"backend {backend.name} has {n} tuner(s) of kind {kind}, but the scan found no "
                    f"channels for them; {rel} is not made"
                )
            exists = os.path.lexists(path)
            if want is not None:
                digest = fsutil.sha256_bytes(want)
                if exists and os.path.isfile(path) and fsutil.sha256_file(path) == digest:
                    if not self.dry_run:
                        self.state.record(rel, digest)
                    continue
                if exists and not self.state.is_ours(rel):
                    self.warn(f"{rel} was not made by the provisioning or was edited; left unchanged")
                    continue
                self.log(f"{'update' if exists else 'create'} {rel} ({rows[kind]} service(s))")
                changes += 1
                if not self.dry_run:
                    if exists:
                        self.backup.save(rel)
                    fsutil.write_atomic(path, want, self.owner)
                    self.state.record(rel, digest)
            elif exists:
                if not self.state.is_ours(rel):
                    continue
                self.log(f"delete {rel} (no tuners of kind {kind})")
                changes += 1
                if not self.dry_run:
                    self.backup.save(rel)
                    os.remove(path)
                    self.state.forget(rel)
            elif not self.dry_run:
                self.state.forget(rel)
        return changes

    def drift(self, backend, info):
        """Why the saved scan may not match the backend any more, or None (design.md 8.4)."""
        record = self.records.get(backend.name)
        if not record:
            return None
        if record.get("url") != backend.url:
            return f"it was scanned at {record.get('url')}, but the backend is now {backend.url}"
        if info.source != "none" and chset.channels_hash(info.channels) != record.get("channels"):
            return f"the channel list of the backend changed since the scan on {record.get('scanned_at')}"
        return None


def boot(env, paths, found, infos, state, backup, owner, *, dry_run, log, warn):
    """The channel step of the provisioning (design.md 8.2 to 8.4). Return the number of changes."""
    ch = Channels(paths.root, state, backup, owner, dry_run=dry_run, log=log, warn=warn)
    mode = chscan_mode(env)
    first = not os.path.exists(os.path.join(paths.root, CHSET5_REL))

    to_scan = []
    unreachable = []
    for b in found:
        info = infos[b.name]
        users = user_files(paths.root, state, b)
        if mode == "first" and first and not users:
            # without ChSet5, every backend is scanned, also one scanned before
            if info.source == "live":
                to_scan.append(b)
            else:
                unreachable.append(b.name)
            continue
        reason = ch.drift(b, info)
        if reason:
            warn(
                f"backend {b.name}: {reason}. EDCB may tune to the wrong channels; "
                f"scan again with: edcbctl chscan {b.name}"
            )
        # with EDCB_CHSCAN=never, the user makes the channel files
        if mode != "never" and not users and not ch.records.get(b.name):
            warn(f"backend {b.name} has no channel scan and EDCB does not use it; scan it with: edcbctl chscan {b.name}")

    changes = 0
    if to_scan:
        names = ", ".join(b.name for b in to_scan)
        if dry_run:
            log(f"would scan the channels of backend {names} ({CHSET5_REL} does not exist)")
        else:
            with scan_lock(paths.root, owner) as locked:
                if not locked:
                    warn("another channel scan is running; the scan is skipped")
                else:
                    log(f"first start ({CHSET5_REL} does not exist): scanning the channels of backend {names}")
                    scanner = Scanner(paths.root, paths.lib, owner, scan_command(env), log=log, warn=warn)
                    done = ch.scan(scanner, to_scan, infos)
                    changes += len(done)
                    unreachable += [b.name for b in to_scan if b.name not in done]

    # a scan that creates ChSet5 ends the first start: the others are not tried again
    if unreachable and not dry_run:
        if os.path.exists(os.path.join(paths.root, CHSET5_REL)):
            for name in unreachable:
                warn(f"backend {name} is not scanned and EDCB does not use it; scan it with: edcbctl chscan {name}")
        else:
            warn(f"backend {', '.join(unreachable)} is not scanned; the scan is tried again on the next start")

    for b in found:
        counts, _ = backends.tuner_counts(b, infos[b.name])
        changes += ch.split(b, counts)
    return changes


def command(env, paths, names, *, all_backends=False, rebuild=False, force=False, log, warn, fetch=None):
    """edcbctl chscan (design.md 9). Return the exit status."""
    owner = fsutil.Owner.from_env(env)
    found, warnings = backends.parse_env(env)
    for w in warnings:
        warn(w)
    by_name = {b.name: b for b in found}
    if rebuild and names:
        warn("--rebuild scans every backend; give no backend names")
        return 2
    if all_backends or rebuild:
        targets = found
    else:
        unknown = [n for n in names if n not in by_name]
        if unknown or not names:
            if unknown:
                warn(f"unknown backend {', '.join(unknown)}")
            warn(f"give a backend name or --all; backends: {', '.join(by_name) or 'none'}")
            return 2
        targets = [by_name[n] for n in dict.fromkeys(names)]
    if not targets:
        warn("no backend is set up")
        return 1

    missing = [b.name for b in targets if not os.path.isfile(os.path.join(paths.lib, b.bondriver("M")))]
    if missing:
        warn(
            f"the BonDriver of backend {', '.join(missing)} is not installed; "
            "restart the container first: docker compose restart edcb"
        )
        return 1

    state = State(paths.root).load()
    for w in state.warnings:
        warn(w)
    blocked = {b.name: user_files(paths.root, state, b) for b in targets}
    blocked = {k: v for k, v in blocked.items() if v}
    if blocked and not force:
        for name, rels in blocked.items():
            warn(f"backend {name}: not made by the provisioning (or edited): {', '.join(rels)}")
        warn("these files would be replaced; give --force to back them up and replace them")
        return 1

    live = (fetch or backends.fetch_all)(targets, backends.TOTAL_TIMEOUT)
    unreachable = [b for b in targets if live[b.name].source != "live"]
    for b in unreachable:
        warn(f"backend {b.name} ({b.url}) is unreachable: {live[b.name].error}")
    if unreachable:
        return 1

    backup = fsutil.Backup(paths.root, owner)
    with scan_lock(paths.root, owner) as locked:
        if not locked:
            warn("another channel scan is running; try again later")
            return 1
        ch = Channels(paths.root, state, backup, owner, log=log, warn=warn)
        scanner = Scanner(paths.root, paths.lib, owner, scan_command(env), log=log, warn=warn)
        done = ch.scan(scanner, targets, live, rebuild=rebuild, strict=True)
        for b in targets:
            if b.name not in done:
                continue
            if b.name in blocked:
                ch.adopt(b)
            counts, _ = backends.tuner_counts(b, live[b.name])
            ch.split(b, counts)
            try:
                backends.save_cache(paths.root, b, live[b.name], owner)
            except OSError as e:
                warn(f"cannot save {backends.cache_rel(b.name)}: {e}")
        state.save(owner)
        backup.prune()
    if backup.dir:
        log(f"backup: {os.path.relpath(backup.dir, paths.root)}")
    failed = [b.name for b in targets if b.name not in done]
    if failed:
        warn(f"not scanned: {', '.join(failed)}")
        return 1
    return 0
