# shellcheck shell=bash
# Shared helpers for the integration tests. Sourced by run.sh; the phase*.sh
# files use these helpers and the variables that run.sh sets (IMG, TMP, PREFIX,
# REPO, HERE and the port variables).

# Results ------------------------------------------------------------------

N_PASS=0
N_FAIL=0
N_SKIP=0
RESULTS=()

# result <id> "<PASS|FAIL|SKIP>[ detail]"
result() {
  local line="RESULT $1: $2"
  echo "$line"
  RESULTS+=("$line")
  case ${2%% *} in
    PASS) N_PASS=$((N_PASS + 1)) ;;
    SKIP) N_SKIP=$((N_SKIP + 1)) ;;
    *) N_FAIL=$((N_FAIL + 1)) ;;
  esac
}

section() { echo; echo "=================== $* ($(date '+%F %T'))"; }

# abort <message>: stop the whole run (the EXIT trap cleans up and prints the summary)
abort() { echo "ABORT: $*"; exit 1; }

# Containers ---------------------------------------------------------------

# Names of the containers this run created; only these are removed on exit.
TRACKED=()

# cname <suffix>: the container name for a case
cname() { echo "${PREFIX}-$1"; }

track() { TRACKED+=("$1"); }

# Networks this run created; removed on exit after the containers.
TRACKED_NETS=()

# net_create <name>: create a bridge network for test containers
net_create() {
  TRACKED_NETS+=("$1")
  docker network create "$1" >/dev/null
}

# run <name> <dir> [docker run options...]: start a detached test container
# with <dir> as /var/local/edcb and a short health interval
run() {
  local name=$1 dir=$2; shift 2
  track "$name"
  docker run -d --name "$name" --health-interval=5s --health-start-period=60s \
    -v "$dir:/var/local/edcb" "$@" "$IMG" >/dev/null
}

# wait_log <name> <pattern> <timeout> [since]: wait for a log line. After a
# restart, pass the time before the restart as <since>; otherwise the line
# from the previous start matches at once.
wait_log() {
  local i
  for i in $(seq "$3"); do
    docker logs ${4:+--since "$4"} "$1" 2>&1 | grep -q -- "$2" && return 0
    sleep 1
  done
  return 1
}

wait_health() { # name want timeout
  local i s
  for i in $(seq "$3"); do
    s=$(docker inspect -f '{{.State.Health.Status}}' "$1" 2>/dev/null)
    [ "$s" = "$2" ] && { echo "health=$s after ${i}s"; return 0; }
    sleep 1
  done
  echo "health=$s (timeout)"; docker inspect -f '{{json .State.Health}}' "$1"; return 1
}

procs() { docker exec "$1" ps -eo user,uid,gid,pid,pgid,stat,args; }

# shellcheck disable=SC2016  # $(pgrep ...) must expand inside the container
srv_status() { docker exec "$1" sh -c 'grep -E "^(Uid|Gid|Groups)" /proc/$(pgrep -x EpgTimerSrv)/status'; }

# sums <dir>: hashes of the ini files that provisioning manages
sums() { (cd "$1" && sha256sum ./*.ini Setting/*.ini .provision/webui.ini 2>/dev/null); }

# Run control --------------------------------------------------------------

cleanup() {
  local n
  for n in "${TRACKED[@]}"; do docker rm -f "$n" >/dev/null 2>&1; done
  for n in "${TRACKED_NETS[@]}"; do docker network rm "$n" >/dev/null 2>&1; done
  [ -n "${TMP:-}" ] && [ -d "$TMP" ] && rm -rf "$TMP"
}

summary() {
  local line
  section "summary"
  for line in "${RESULTS[@]}"; do echo "$line"; done
  echo "SUMMARY: pass=$N_PASS fail=$N_FAIL skip=$N_SKIP"
}
