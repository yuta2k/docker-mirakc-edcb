#!/bin/bash
# Detect machine-specific information (home paths, host names, LAN
# addresses, ...) before it is committed.
#
# Usage: check-local-info.sh [--tracked | --staged | --message-file <path>]
#
#   --tracked              Check all tracked files in the working tree (default).
#   --staged               Check only the lines added in the staged diff.
#   --message-file <path>  Check a commit message file. Lines starting with
#                          "#" and everything below git's scissors line are
#                          ignored.
#
# Patterns are extended regular expressions from two sources:
#   - the built-in, generic patterns below;
#   - .local-info-patterns at the repository root (git-ignored), one ERE per
#     line, "#" comments and blank lines ignored. The forbidden strings of a
#     particular machine (host names, project names, LAN addresses) are
#     themselves machine-specific, so they live there and not here. In a
#     linked worktree, the file of the main worktree is used as a fallback.
#
# Prints "file:line: text" for each hit and exits 1 if there is any.
set -euo pipefail

builtin_patterns=(
  # home directories
  '/home/[^/[:space:]]+/'
  # scratch directories of coding agents
  '/tmp/claude-'
  # "this development environment": a phrase that refers to one machine
  'この開発環境'
)

# Files that must contain the patterns themselves.
excludes=(
  scripts/check-local-info.sh
)

usage() {
  echo "usage: $0 [--tracked | --staged | --message-file <path>]" >&2
  exit 2
}

mode=tracked
msgfile=
msgname=
case ${1:-} in
  '' | --tracked) mode=tracked ;;
  --staged) mode=staged ;;
  --message-file)
    [ $# -eq 2 ] || usage
    mode=message
    msgname=$2
    [ -f "$msgname" ] || { echo "ERROR: $msgname not found" >&2; exit 2; }
    # absolute, as the script changes to the repository root below
    msgfile=$(cd "$(dirname "$msgname")" && pwd)/$(basename "$msgname")
    ;;
  *) usage ;;
esac
[ $# -le 1 ] || [ "$mode" = message ] || usage

root=$(git rev-parse --show-toplevel)
cd "$root"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Collect the patterns. A blank line in a pattern file would match every
# line, so blank lines and comments are dropped.
patterns=$tmp/patterns
printf '%s\n' "${builtin_patterns[@]}" >"$patterns"
local_file=$root/.local-info-patterns
if [ ! -f "$local_file" ]; then
  common=$(cd "$(git rev-parse --git-common-dir)" && pwd)
  local_file=$(dirname "$common")/.local-info-patterns
fi
if [ -f "$local_file" ]; then
  n=$(sed -e 's/\r$//' -e '/^[[:space:]]*#/d' -e '/^[[:space:]]*$/d' "$local_file" | tee -a "$patterns" | wc -l)
  echo "check-local-info: ${#builtin_patterns[@]} built-in patterns + $n from .local-info-patterns" >&2
else
  echo "check-local-info: .local-info-patterns not found; only the ${#builtin_patterns[@]} built-in patterns are checked" >&2
fi

pathspec=(.)
for f in "${excludes[@]}"; do
  pathspec+=(":(exclude)$f")
done

status=0
case $mode in
  tracked)
    # -I skips binary files. git grep exits 1 for no match, >1 on errors.
    rc=0
    git grep -nIE -f "$patterns" -- "${pathspec[@]}" >"$tmp/hits" || rc=$?
    if [ "$rc" -eq 0 ]; then
      sed -e 's/^\([^:]*:[0-9]*\):/\1: /' "$tmp/hits"
      status=1
    elif [ "$rc" -ne 1 ]; then
      echo "ERROR: git grep failed" >&2
      exit 2
    fi
    ;;
  staged)
    # Split the added lines into their locations and their text, grep the
    # text, then map the hits back. Binary files have no "+" lines.
    git diff --cached --no-color --no-ext-diff -U0 --diff-filter=ACMR -- "${pathspec[@]}" |
      awk -v loc="$tmp/loc" -v txt="$tmp/txt" '
        /^\+\+\+ / { file = substr($0, 7); next }
        /^@@ / {
          split($3, a, ",")
          line = substr(a[1], 2) + 0
          next
        }
        /^\+/ {
          print file ":" line > loc
          print substr($0, 2) > txt
          line++
        }
      '
    if [ -f "$tmp/txt" ] && grep -nE -f "$patterns" "$tmp/txt" >"$tmp/hits"; then
      awk -v loc="$tmp/loc" '
        BEGIN { n = 0; while ((getline l < loc) > 0) where[++n] = l }
        {
          i = index($0, ":")
          print where[substr($0, 1, i - 1)] ": " substr($0, i + 1)
        }
      ' "$tmp/hits"
      status=1
    fi
    ;;
  message)
    # Blank out comment lines and everything below the scissors line, so
    # that the line numbers stay those of the file.
    awk '
      /^# -+ >8 -+$/ { cut = 1 }
      cut || /^#/ { print ""; next }
      { print }
    ' "$msgfile" >"$tmp/msg"
    if grep -nE -f "$patterns" "$tmp/msg" >"$tmp/hits"; then
      awk -v f="$msgname" '{ i = index($0, ":"); print f ":" substr($0, 1, i - 1) ": " substr($0, i + 1) }' "$tmp/hits"
      status=1
    fi
    ;;
esac

if [ "$status" -ne 0 ]; then
  echo "check-local-info: machine-specific information found (see above)" >&2
fi
exit "$status"
