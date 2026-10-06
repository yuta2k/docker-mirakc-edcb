#!/bin/bash
# Run every check that does not need the Docker daemon. Used as is by
# developers and by CI (.github/workflows/build.yml, job "check").
#
# Usage: check.sh [check...]
#
#   Checks, in the order they run: pytest shellcheck actionlint compose
#   links local-info. Without arguments, all of them run.
#
# Tools are looked up in .tools/bin (see scripts/install-tools.sh), then in
# PATH. A missing tool makes its check SKIP, except when CI is set: then it
# is a FAIL, so that a check that did not run never looks like a pass.
#
# Exits 1 if any check failed.
set -u

# Python for the unit tests: the python3 of the edcb image (Ubuntu 26.04).
# Only uv can pick the version; without uv the python3 in PATH is used, and
# a different version is a FAIL when CI is set.
PYTHON_VERSION=3.14

all_checks=(pytest shellcheck actionlint compose links local-info)

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root" || exit 1

if [ $# -eq 0 ]; then
  checks=("${all_checks[@]}")
else
  checks=()
  for c in "$@"; do
    case " ${all_checks[*]} " in
      *" $c "*) checks+=("$c") ;;
      *)
        echo "ERROR: unknown check '$c' (available: ${all_checks[*]})" >&2
        exit 2
        ;;
    esac
  done
fi

# find_tool <name>: print the path of a tool, .tools/bin first
find_tool() {
  if [ -x "$root/.tools/bin/$1" ]; then
    echo "$root/.tools/bin/$1"
  else
    command -v "$1"
  fi
}

results=()
failed=0

# record <check> <PASS|FAIL|SKIP> [note]
record() {
  local line
  line=$(printf '%-11s %s' "$1" "$2")
  [ -n "${3:-}" ] && line="$line ($3)"
  results+=("$line")
  echo "==> $line"
  [ "$2" = FAIL ] && failed=1
}

# missing <check> <hint>: a tool is not available
missing() {
  if [ -n "${CI:-}" ]; then
    record "$1" FAIL "$2"
  else
    record "$1" SKIP "$2"
  fi
}

# run <check> <command...>: run a command and record its result
run() {
  local name=$1
  shift
  if "$@"; then
    record "$name" PASS
  else
    record "$name" FAIL
  fi
}

check_pytest() {
  # leave no __pycache__ or .pytest_cache behind in the working tree
  export PYTHONDONTWRITEBYTECODE=1
  local args=(-p no:cacheprovider edcb/tests)
  if command -v uv >/dev/null; then
    run pytest uv run --no-project --python "$PYTHON_VERSION" --with pytest pytest "${args[@]}"
    return
  fi
  local version
  version=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
  if [ "$version" != "$PYTHON_VERSION" ]; then
    if [ -n "${CI:-}" ]; then
      record pytest FAIL "uv not found and python3 is ${version:-missing}, not $PYTHON_VERSION"
      return
    fi
    echo "WARNING: uv not found; testing with python3 ${version:-?} instead of $PYTHON_VERSION" >&2
  fi
  if command -v pipx >/dev/null; then
    run pytest pipx run pytest "${args[@]}"
  elif python3 -c 'import pytest' 2>/dev/null; then
    run pytest python3 -m pytest "${args[@]}"
  else
    missing pytest "none of uv, pipx or python3 with pytest found"
  fi
}

# Shell scripts are found by their shebang, not their extension. Untracked
# files that are not ignored are included, so a new script is checked
# before it is added.
shell_scripts() {
  git ls-files -z --cached --others --exclude-standard |
    while IFS= read -r -d '' f; do
      [ -f "$f" ] || continue
      # a shebang, or the directive of a sourced file (tests/integration/lib.sh, phase*.sh)
      head -n 1 "$f" | grep -Eq '^(#![[:space:]]*/[^[:space:]]*/(env[[:space:]]+)?(sh|bash|dash|ksh)([[:space:]]|$)|#[[:space:]]*shellcheck[[:space:]]+shell=)' &&
        printf '%s\0' "$f"
    done | sort -zu
}

check_shellcheck() {
  local tool
  if ! tool=$(find_tool shellcheck); then
    missing shellcheck "not installed; run scripts/install-tools.sh"
    return
  fi
  local files=()
  while IFS= read -r -d '' f; do
    files+=("$f")
  done < <(shell_scripts)
  if [ ${#files[@]} -eq 0 ]; then
    record shellcheck FAIL "no shell scripts found"
    return
  fi
  printf 'shellcheck: %s\n' "${files[@]}"
  run shellcheck "$tool" -x "${files[@]}"
}

check_actionlint() {
  local tool
  if ! tool=$(find_tool actionlint); then
    missing actionlint "not installed; run scripts/install-tools.sh"
    return
  fi
  # actionlint finds .github/workflows itself; it also runs shellcheck on
  # run: steps if shellcheck is in PATH
  run actionlint env PATH="$root/.tools/bin:$PATH" "$tool"
}

# called through "run compose compose_config"
# shellcheck disable=SC2329
compose_config() {
  local tmp rc=0
  tmp=$(mktemp -d) || return 1
  # Copy the files to an empty directory, so that a local .env,
  # compose.override.yml or edcb.env does not affect the result. compose.yml
  # only refers to optional or not-yet-existing files (env_file is
  # required: false; bind mounts and build contexts are not checked by
  # "config"). The COMPOSE_* variables of the caller are not passed either.
  cp compose.yml compose.override-sample.yml "$tmp/" || rc=1
  if [ "$rc" -eq 0 ]; then
    (
      cd "$tmp" || exit 1
      for v in $(compgen -e); do
        case $v in COMPOSE_* | EDCB_*) unset "$v" ;; esac
      done
      echo "docker compose -f compose.yml config -q" &&
        docker compose -f compose.yml config -q &&
        echo "docker compose -f compose.yml -f compose.override-sample.yml config -q" &&
        docker compose -f compose.yml -f compose.override-sample.yml config -q
    ) || rc=1
  fi
  rm -rf "$tmp"
  return "$rc"
}

check_compose() {
  if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
    missing compose "docker compose not available"
    return
  fi
  run compose compose_config
}

check_links() {
  run links python3 scripts/check-links.py
}

check_local_info() {
  run local-info scripts/check-local-info.sh --tracked
}

for c in "${checks[@]}"; do
  echo "==> running $c"
  case $c in
    pytest) check_pytest ;;
    shellcheck) check_shellcheck ;;
    actionlint) check_actionlint ;;
    compose) check_compose ;;
    links) check_links ;;
    local-info) check_local_info ;;
  esac
  echo
done

echo "Summary:"
printf '  %s\n' "${results[@]}"
exit "$failed"
