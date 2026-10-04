#!/bin/sh
# Smoke test for a built edcb image.
#
# Usage: smoke-test.sh <image>
#
# Runs "EpgTimerSrv -h" and "EpgDataCap_Bon -h". Both print "Ver.<version>"
# and exit with status 2 (upstream behavior for -h), so status 2 with that
# output counts as success.
set -u

image=$1
status=0

for bin in EpgTimerSrv EpgDataCap_Bon; do
  out=$(docker run --rm --entrypoint "$bin" "$image" -h 2>&1)
  rc=$?
  printf '%s -h (exit %s):\n%s\n' "$bin" "$rc" "$out"
  if [ "$rc" -ne 2 ] || ! printf '%s\n' "$out" | grep -q '^Ver\.'; then
    echo "::error::$bin -h failed (exit $rc)"
    status=1
  fi
done

echo "Upstream labels:"
docker image inspect --format '{{range $k, $v := .Config.Labels}}{{println $k "=" $v}}{{end}}' "$image" |
  grep 'docker-mirakc-edcb' || status=1

exit $status
