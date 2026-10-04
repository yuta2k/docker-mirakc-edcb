"""edcbctl: control commands run inside the container.

    docker compose exec edcb edcbctl <command>
"""

import argparse
import os
import sys

from . import backends, fsutil, legacy, provision


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

    args = parser.parse_args(argv)
    return args.func(args, env)
