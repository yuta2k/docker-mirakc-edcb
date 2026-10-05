"""edcbctl: control commands run inside the container.

    docker compose exec edcb edcbctl <command>
"""

import argparse
import os
import sys

from . import backends, channels, ctrlcmd, fsutil, legacy, provision, prune


def _cmd_provision(args, env):
    paths = provision.Paths.from_env(env)
    rc = provision.run(env, paths, diff=args.diff, boot=args.boot)
    if rc == 0 and not args.diff and not args.boot:
        print("Restart the container to apply changed EDCB settings: docker compose restart edcb")
    return rc


def _cmd_allow_setting(args, env):
    root = provision.Paths.from_env(env).root
    if args.state != "status":
        legacy.set(root, args.state == "on", fsutil.Owner.from_env(env))
    current = legacy.get(root)
    if current is None:
        print("Legacy WebUI setting changes: not set (denied)")
    else:
        print(f"Legacy WebUI setting changes: {'allowed' if current else 'denied'}")
    patched = legacy.util_lua_is_patched(root)
    if patched is False:
        print(
            f"WARNING: {legacy.UTIL_LUA} does not read this switch (edited or from another image); "
            "it has no effect until the file is restored",
            file=sys.stderr,
        )
        return 1
    if args.state == "on":
        print("Reset to EDCB_LEGACY_ALLOW_SETTING (default: denied) on the next container start.")
    return 0


def _cmd_backends(args, env):
    root = provision.Paths.from_env(env).root
    return backends.report(env, root, out=sys.stdout)


RESTART_HINT = "Restart the container to have EDCB load the channel files: docker compose restart edcb"


def _print_status(root, out):
    """Print the recording state. Return True if recording, None if unknown."""
    try:
        lines, busy = ctrlcmd.summary(root)
    except (OSError, ctrlcmd.CtrlCmdError) as e:
        print(f"EpgTimerSrv: cannot ask ({e}); is it running?", file=out)
        return None
    for line in lines:
        print(line, file=out)
    return busy


def _cmd_chscan(args, env):
    paths = provision.Paths.from_env(env)
    r = provision.Reporter()
    rc = channels.command(
        env,
        paths,
        args.names,
        all_backends=args.all,
        rebuild=args.rebuild,
        force=args.force,
        log=r.log,
        warn=r.warn,
    )
    if rc == 0:
        # EpgTimerSrv reads the ChSet4 files and its tuner list only when it
        # starts; ReloadSetting rereads ChSet5 alone (facts.md U11)
        print(RESTART_HINT)
        print("EPG of the scanned channels is captured right after the restart.")
        if _print_status(paths.root, sys.stdout):
            print("WARNING: a restart now stops the recording in progress", file=sys.stderr)
    return rc


def _cmd_prune(args, env):
    paths = provision.Paths.from_env(env)
    r = provision.Reporter()
    rc, changed = prune.command(env, paths, diff=args.diff, log=r.log, warn=r.warn, out=sys.stdout)
    if rc == 0 and changed:
        # EpgTimerSrv reads the tuner list and the ChSet4 files only when it starts (facts.md U11)
        print("Restart the container to have EDCB drop the removed BonDrivers: docker compose restart edcb")
        if _print_status(paths.root, sys.stdout):
            print("WARNING: a restart now stops the recording in progress", file=sys.stderr)
    return rc


def _cmd_epgcap(args, env):
    """Used by the entrypoint after a scan: one EPG capture once EpgTimerSrv is ready."""
    root = provision.Paths.from_env(env).root
    marker = os.path.join(root, channels.EPGCAP_PENDING_REL)
    if not os.path.exists(marker):
        return 0
    r = provision.Reporter()
    if not ctrlcmd.request_epg_capture(root, log=r.log):
        return 1
    try:
        os.remove(marker)
    except FileNotFoundError:
        pass
    return 0


def _cmd_status(args, env):
    busy = _print_status(provision.Paths.from_env(env).root, sys.stdout)
    return 1 if busy is None else 0


def main(argv=None, env=None):
    env = dict(os.environ if env is None else env)
    parser = argparse.ArgumentParser(prog="edcbctl", description="Control commands for the EDCB container.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("provision", help="apply the environment variables and override files to the ini files")
    p.add_argument("--diff", action="store_true", help="only show what would change")
    # used by the entrypoint: also resets the start-up state of the legacy WebUI switch
    p.add_argument("--boot", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=_cmd_provision)

    p = sub.add_parser("allow-setting", help="allow or deny setting changes from the legacy WebUI (no restart needed)")
    p.add_argument("state", choices=["on", "off", "status"])
    p.set_defaults(func=_cmd_allow_setting)

    p = sub.add_parser("backends", help="show the backends, their tuners and the tuner counts EDCB uses")
    p.set_defaults(func=_cmd_backends)

    p = sub.add_parser("chscan", help="scan the channels of backends and make their channel files")
    p.add_argument("names", nargs="*", metavar="NAME", help="backends to scan (DEFAULT, ...)")
    p.add_argument("--all", action="store_true", help="scan every backend")
    p.add_argument("--rebuild", action="store_true", help="make ChSet5.txt again from the scans of every backend")
    p.add_argument("--force", action="store_true", help="back up and replace channel files the provisioning did not make")
    p.set_defaults(func=_cmd_chscan)

    p = sub.add_parser("status", help="show whether EDCB is recording and the next reservation")
    p.set_defaults(func=_cmd_status)

    p = sub.add_parser("prune", help="remove what removed backends and kinds without tuners left behind")
    p.add_argument("--diff", action="store_true", help="only show what would be removed")
    p.set_defaults(func=_cmd_prune)

    # used by the entrypoint after a channel scan
    p = sub.add_parser("epgcap-pending")
    p.set_defaults(func=_cmd_epgcap)

    args = parser.parse_args(argv)
    return args.func(args, env)
