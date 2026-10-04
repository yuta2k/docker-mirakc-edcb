#!/bin/sh
# Make the legacy WebUI read its "allow setting changes" switch from an ini file.
#
# Usage: patch-legacy-util.sh <path to HttpPublic/legacy/util.lua>
#
# Upstream util.lua has a constant "ALLOW_SETTING=false" line. It is replaced
# by an expression that reads [LEGACY] ALLOW_SETTING from .provision/webui.ini
# (relative to /var/local/edcb) on every request, so "edcbctl allow-setting"
# takes effect without restarting EpgTimerSrv. The build fails unless exactly
# one such line is found, so that a change in upstream is noticed.
set -eu

if [ $# -ne 1 ]; then
  echo "usage: $0 <util.lua>" >&2
  exit 1
fi
file=$1
# util.lua uses CRLF line endings; accept LF too
cr=$(printf '\r')
pattern="^ALLOW_SETTING=\(true\|false\)\($cr\?\)\$"

count=$(grep -c "$pattern" "$file" || true)
if [ "$count" -ne 1 ]; then
  echo "ERROR: expected exactly one 'ALLOW_SETTING=true|false' line in $file, found $count" >&2
  echo "ERROR: upstream changed legacy/util.lua; update edcb/build/patch-legacy-util.sh" >&2
  exit 1
fi

expr="ALLOW_SETTING=edcb.GetPrivateProfile('LEGACY','ALLOW_SETTING','0','.provision/webui.ini')=='1'"
# "#" as the delimiter: "|" would clash with the \| alternation
sed -i "s#$pattern#$expr --docker-mirakc-edcb: edcbctl allow-setting\\2#" "$file"

if ! grep -qF "$expr" "$file"; then
  echo "ERROR: failed to patch $file" >&2
  exit 1
fi
echo "Patched $file:"
grep -n "^ALLOW_SETTING=" "$file"
