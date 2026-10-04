#!/bin/sh
# Entrypoint of the EDCB container (docs/v2/design.md, chapter 5).
#
# Starts as root, prepares /var/local/edcb, then runs EpgTimerSrv as
# PUID:PGID. A failure of any preparation step is reported and EpgTimerSrv is
# started anyway; only a start as non-root stops here.
set -u

EDCB_ROOT=/var/local/edcb
PROVISION_LIB=/usr/local/lib/edcb-provision

# PID 1 ignores signals without a handler; leave promptly if stopped while preparing
trap 'exit 143' HUP INT QUIT TERM

log() { echo "entrypoint: $*"; }
warn() { echo "entrypoint: WARNING: $*" >&2; }

is_true() {
  case $(printf '%s' "$1" | tr '[:upper:]' '[:lower:]') in
    1 | true | yes | on) return 0 ;;
    *) return 1 ;;
  esac
}

is_uint() {
  case $1 in
    '' | *[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

if [ "$(id -u)" != 0 ]; then
  cat >&2 <<'EOF'
entrypoint: ERROR: this container must start as root; it switches to PUID/PGID by itself.
entrypoint: ERROR: remove "user:" from compose.override.yml (or "--user" from docker run)
entrypoint: ERROR: and set the user with environment variables instead, for example:
entrypoint: ERROR:     environment:
entrypoint: ERROR:       - PUID=1000
entrypoint: ERROR:       - PGID=1000
EOF
  exit 1
fi

PUID=${PUID:-1000}
PGID=${PGID:-1000}
if ! is_uint "$PUID"; then warn "PUID must be a number (got '$PUID'); using 1000"; PUID=1000; fi
if ! is_uint "$PGID"; then warn "PGID must be a number (got '$PGID'); using 1000"; PGID=1000; fi
if [ "$PUID" = 0 ]; then warn "PUID=0: EpgTimerSrv runs as root"; fi
export PUID PGID

if [ -n "${UMASK:-}" ]; then
  umask "$UMASK" || warn "invalid UMASK '$UMASK' is ignored"
fi

# Supplementary groups for EpgTimerSrv: the groups given to the container
# (compose "group_add"), without root, plus the owner group of the render
# nodes for hardware transcoding (the GID differs from host to host).
groups=
for g in $(id -G); do
  [ "$g" = 0 ] || groups="$groups $g"
done
for dev in /dev/dri/renderD*; do
  [ -e "$dev" ] || continue
  g=$(stat -c %g "$dev")
  [ "$g" = 0 ] || groups="$groups $g"
done
# shellcheck disable=SC2086 # split the list on purpose
groups=$(printf '%s\n' $groups | sort -un | paste -sd, -)
if [ -n "$groups" ]; then
  set -- --groups="$groups"
else
  set -- --clear-groups
fi
as_user() {
  setpriv --reuid="$PUID" --regid="$PGID" "$@"
}

# === BonDriver_LinuxMirakc (unchanged from v1 until phase 3) ===
# BonDriver_LinuxMirakc cannot resolve host names, so the address is resolved here.

# typo correction for under v1.0.4 compose.yml
if [ -z "${MIRAKC_ADDRESS:-}" ] && [ -n "${MIRKAC_ADDRESS:-}" ]; then MIRAKC_ADDRESS=$MIRKAC_ADDRESS; fi
if [ -z "${MIRAKC_PORT:-}" ] && [ -n "${MIRKAC_PORT:-}" ]; then MIRAKC_PORT=$MIRKAC_PORT; fi
MIRAKC_ADDRESS=${MIRAKC_ADDRESS:-mirakc}
MIRAKC_PORT=${MIRAKC_PORT:-40772}

BONDRIVER_INI=/var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini
MIRAKC_IP_ADDRESS=$(getent ahosts "$MIRAKC_ADDRESS" | sed -n 's/ *STREAM.*//p' | head -n 1)
if [ -z "$MIRAKC_IP_ADDRESS" ]; then
  warn "cannot resolve '$MIRAKC_ADDRESS' (MIRAKC_ADDRESS); tuners are unavailable until it resolves and the container restarts"
else
  sed -i -e "s/^SERVER_HOST=.*/SERVER_HOST=\"$MIRAKC_IP_ADDRESS\"/" \
    -e "s/^SERVER_PORT=.*/SERVER_PORT=\"$MIRAKC_PORT\"/" "$BONDRIVER_INI" ||
    warn "cannot write $BONDRIVER_INI"
  log "mirakc: $MIRAKC_ADDRESS ($MIRAKC_IP_ADDRESS):$MIRAKC_PORT"
fi

# === 1. leftovers of SrvPipe from the previous run ===
rm -f "$EDCB_ROOT"/*.fifo

# === ownership of /var/local/edcb ===
# Decided before the provisioning creates files: on the first start (no
# Setting/ yet, or an empty one) the folder is given to PUID:PGID. Otherwise
# ownership is only checked; existing data is never chowned.
mkdir -p "$EDCB_ROOT"
if [ -z "$(ls -A "$EDCB_ROOT/Setting" 2>/dev/null)" ]; then
  log "first start: giving $EDCB_ROOT to $PUID:$PGID"
  chown -R "$PUID:$PGID" "$EDCB_ROOT" || warn "cannot change the owner of $EDCB_ROOT"
else
  not_writable=
  for f in "$EDCB_ROOT" "$EDCB_ROOT/Setting" "$EDCB_ROOT"/*.ini; do
    [ -e "$f" ] || continue
    as_user "$@" test -w "$f" || not_writable="$not_writable $f"
  done
  if [ -n "$not_writable" ]; then
    warn "not writable by PUID=$PUID PGID=$PGID:$not_writable"
    warn "set PUID/PGID to the owner of ./edcb/ini, or change the owner on the host"
  fi
fi

# === 2-3. initial files and provisioning ===
edcbctl provision --boot || warn "provisioning failed; starting EpgTimerSrv with the current settings"

# === 5. debug logs to standard output ===
LOGTAIL_PID=
if is_true "${EDCB_LOG_STDOUT:-true}"; then
  ready=/tmp/edcb-logtail.ready
  rm -f "$ready"
  PYTHONPATH=$PROVISION_LIB python3 -m edcb_provision.logtail "$ready" &
  LOGTAIL_PID=$!
  # wait until it has measured the existing logs; otherwise EpgTimerSrv's
  # first lines could be taken for old ones and skipped
  i=0
  while [ ! -e "$ready" ] && [ $i -lt 100 ] && kill -0 "$LOGTAIL_PID" 2>/dev/null; do
    sleep 0.1
    i=$((i + 1))
  done
fi

# === 6. EpgTimerSrv as PUID:PGID ===
stopping=
# shellcheck disable=SC2329 # invoked by trap
terminate_edcb() {
  # terminate EpgTimerSrv and all child processes such as EpgDataCap_Bon
  stopping=1
  [ -n "${PGID_SRV:-}" ] || return # still starting; handled right after the start
  log "stopping EpgTimerSrv"
  kill -TERM -"$PGID_SRV" 2>/dev/null || kill -TERM "$SRV_PID" 2>/dev/null
  pidwait -g "$PGID_SRV" >/dev/null 2>&1
}

# see: https://docs.docker.jp/engine/reference/builder.html#exec-entrypoint
trap terminate_edcb HUP INT QUIT TERM

log "starting EpgTimerSrv as $PUID:$PGID (groups: ${groups:-none})"
setsid setpriv --reuid="$PUID" --regid="$PGID" "$@" EpgTimerSrv &
SRV_PID=$!
# setsid makes EpgTimerSrv the leader of a new process group whose ID is its
# PID. Wait until that has happened: before it, the process is still in the
# entrypoint's group, and signalling that group would hit everything.
i=0
while [ "$(ps -o pgid= -p "$SRV_PID" | tr -d ' ')" != "$SRV_PID" ] && kill -0 "$SRV_PID" 2>/dev/null && [ $i -lt 50 ]; do
  sleep 0.1
  i=$((i + 1))
done
PGID_SRV=$SRV_PID
# a stop signal that arrived while starting
if [ -n "$stopping" ]; then terminate_edcb; fi

# wait for terminate_edcb() or an unexpected exit of EpgTimerSrv
wait "$SRV_PID"
status=$?
if [ -z "$stopping" ]; then
  warn "EpgTimerSrv exited unexpectedly (status $status)"
  # stop the children left in its process group
  kill -TERM -"$PGID_SRV" 2>/dev/null
  pidwait -g "$PGID_SRV" >/dev/null 2>&1
fi
if [ -n "$LOGTAIL_PID" ]; then
  kill -TERM "$LOGTAIL_PID" 2>/dev/null
  wait "$LOGTAIL_PID" 2>/dev/null
fi
log "stopped"
[ -n "$stopping" ] && exit 0
exit "$status"
