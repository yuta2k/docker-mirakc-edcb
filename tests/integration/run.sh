#!/bin/bash
# Integration tests for the edcb image. Run as root: sudo tests/integration/run.sh
#
# Touches only: containers named ${EDCBTEST_PREFIX}-* that this run creates,
# the image tags $EDCBTEST_IMAGE, $EDCBTEST_IMAGE-shouldfail, $EDCBTEST_IMAGE-hwaccel[-qsvencc]
# and $EDCBTEST_MIRAKC_IMAGE, a mktemp -d
# directory, and host ports on 127.0.0.1 (EDCBTEST_PORT_BASE and the next two).
# Phase 6 also creates Compose projects, networks and volumes named ${EDCBTEST_PREFIX}-*.
# EDCBTEST_REAL_INI (default edcb/ini) is only read.
#
# Every phase*.sh next to this file is sourced in version order (phase2.sh,
# phase3.sh, ..., phase10.sh).
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)

if [ "$(id -u)" != 0 ]; then
  echo "This script must run as root (the cleanup removes files owned by other users)." >&2
  echo "Run: sudo tests/integration/run.sh" >&2
  exit 2
fi

# shellcheck source=tests/integration/lib.sh
. "$HERE/lib.sh"

# Configuration (the variables are used by the phase*.sh files)
# shellcheck disable=SC2034
load_config() {
  IMG=${EDCBTEST_IMAGE:-edcb:integration-test}
  IMG_SHOULDFAIL=${IMG}-shouldfail
  MIRAKC_IMG=${EDCBTEST_MIRAKC_IMAGE:-mirakc:integration-test}
  SKIP_BUILD=${EDCBTEST_SKIP_BUILD:-0}
  PREFIX=${EDCBTEST_PREFIX:-edcbtest}
  PORT_BASE=${EDCBTEST_PORT_BASE:-15510}
  LOG_DIR_DEFAULT=$HERE/logs
  LOG=${EDCBTEST_LOG:-$LOG_DIR_DEFAULT/run-$(date +%Y%m%d-%H%M%S).log}

  # Host ports, all published on 127.0.0.1
  PORT_HTTP=$PORT_BASE                # T1: container 5510 (HTTP)
  PORT_HTTPS=$((PORT_BASE + 1))       # T15: container 5511 (HTTPS)
  PORT_HTTP2=$((PORT_BASE + 2))       # T15: container 5510 (HTTP)

  # Real ini files for T3 (only read)
  if [ -n "${EDCBTEST_REAL_INI:-}" ]; then
    REAL_INI=$EDCBTEST_REAL_INI
  else
    REAL_INI=$REPO/edcb/ini
  fi
  if ! compgen -G "$REAL_INI/*.ini" >/dev/null; then
    REAL_INI=
  fi
}
load_config

case $PORT_BASE in
  ''|*[!0-9]*) echo "EDCBTEST_PORT_BASE must be a number: $PORT_BASE" >&2; exit 2 ;;
esac
if [ "$PORT_BASE" -lt 1024 ] || [ "$PORT_BASE" -gt 65533 ]; then
  echo "EDCBTEST_PORT_BASE must be between 1024 and 65533: $PORT_BASE" >&2; exit 2
fi

missing=
for cmd in docker curl openssl python3 sha256sum tar find; do
  command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"
done
if [ -n "$missing" ]; then
  echo "missing commands:$missing" >&2; exit 2
fi
if ! docker version >/dev/null 2>&1; then
  echo "cannot talk to the Docker daemon" >&2; exit 2
fi
if [ "$SKIP_BUILD" = 1 ] && ! docker image inspect "$IMG" >/dev/null 2>&1; then
  echo "EDCBTEST_SKIP_BUILD=1 but the image $IMG does not exist; build it first or unset EDCBTEST_SKIP_BUILD" >&2
  exit 2
fi
# Refuse to run over leftovers instead of removing containers this run did not create
mapfile -t stale < <(docker ps -a --filter "name=^/?${PREFIX}-" --format '{{.Names}}')
if [ "${#stale[@]}" -gt 0 ]; then
  echo "containers named ${PREFIX}-* already exist:" >&2
  printf '  %s\n' "${stale[@]}" >&2
  echo "remove them (docker rm -f ...) or set EDCBTEST_PREFIX to another value" >&2
  exit 2
fi
mapfile -t stale < <(docker volume ls --filter "name=^${PREFIX}-" --format '{{.Name}}')
if [ "${#stale[@]}" -gt 0 ]; then
  echo "volumes named ${PREFIX}-* already exist:" >&2
  printf '  %s\n' "${stale[@]}" >&2
  echo "remove them (docker volume rm ...) or set EDCBTEST_PREFIX to another value" >&2
  exit 2
fi
mapfile -t stale < <(docker network ls --filter "name=^${PREFIX}-" --format '{{.Name}}')
if [ "${#stale[@]}" -gt 0 ]; then
  echo "networks named ${PREFIX}-* already exist:" >&2
  printf '  %s\n' "${stale[@]}" >&2
  echo "remove them (docker network rm ...) or set EDCBTEST_PREFIX to another value" >&2
  exit 2
fi

# Owner for the log: the user who ran sudo, otherwise the owner of the repository
if [ -n "${SUDO_UID:-}" ] && [ -n "${SUDO_GID:-}" ]; then
  LOG_OWNER=$SUDO_UID:$SUDO_GID
else
  LOG_OWNER=$(stat -c '%u:%g' "$REPO")
fi
LOG_DIR=$(dirname "$LOG")
mkdir -p "$LOG_DIR" || exit 2
: >> "$LOG" || exit 2

TMP=$(mktemp -d "${TMPDIR:-/tmp}/${PREFIX}.XXXXXX") || exit 2

on_exit() {
  local rc=$?
  cleanup
  summary
  echo "integration tests end $(date '+%F %T'), log: $LOG"
  [ "$N_FAIL" -gt 0 ] && rc=1
  chown "$LOG_OWNER" "$LOG" 2>/dev/null
  [ "$LOG_DIR" = "$LOG_DIR_DEFAULT" ] && chown "$LOG_OWNER" "$LOG_DIR" 2>/dev/null
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' INT TERM

exec > >(tee -a "$LOG") 2>&1

rev=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)
changed=$(git -C "$REPO" status --short 2>/dev/null | wc -l)
echo "integration tests start $(date '+%F %T'), git $rev $changed changed files"
echo "image=$IMG mirakc image=$MIRAKC_IMG skip_build=$SKIP_BUILD prefix=$PREFIX ports=127.0.0.1:$PORT_HTTP-$PORT_HTTP2 tmp=$TMP"
echo "real ini: ${REAL_INI:-none}"
docker version --format 'docker {{.Server.Version}}'

mapfile -t PHASES < <(find "$HERE" -maxdepth 1 -name 'phase*.sh' | sort -V)
for phase in "${PHASES[@]}"; do
  echo; echo "################### $(basename "$phase")"
  # shellcheck source=/dev/null
  . "$phase"
done
