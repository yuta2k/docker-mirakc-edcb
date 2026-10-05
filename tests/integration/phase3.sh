# shellcheck shell=bash
# Phase 3: BonDriver patches, several backends, tuner counts.
# Sourced by run.sh; uses the helpers in lib.sh.
# The backends are edcb/tests/fake_mirakurun.py, run from the image under test
# (it has python3) on a test network, so that host names are used.
# shellcheck disable=SC2154  # IMG, TMP, REPO, PREFIX, SKIP_BUILD etc. are set by run.sh
# EDCB_CHSCAN=never: without it, the first start would scan the fake servers
# (channel scans are phase 4).

NET=${PREFIX}-net
FA=$(cname fake-a); FB=$(cname fake-b); FB2=$(cname fake-b2); HOLD=$(cname ip-hold)
C31=$(cname 31); C35=$(cname 35); C38=$(cname 38); C39=$(cname 39)

# fake <container> <alias> <scenario> [fake_mirakurun.py options...]
fake() {
  local name=$1 alias=$2 scenario=$3; shift 3
  track "$name"
  docker run -d --name "$name" --network "$NET" --network-alias "$alias" \
    -v "$REPO/edcb/tests:/tests:ro" --entrypoint python3 "$IMG" \
    /tests/fake_mirakurun.py --port 40772 --scenario "$scenario" "$@" >/dev/null
}

# access <container>: the access log of a fake server
access() { docker logs "$1" 2>/dev/null | grep '^ACCESS'; }
# naccess <container> <pattern>: number of requests matching a pattern
naccess() { access "$1" | grep -c -- "$2"; }

# bon <container> <timeout> <EpgDataCap_Bon arguments...>: run EpgDataCap_Bon as PUID:PGID
bon() {
  local c=$1 t=$2; shift 2
  docker exec "$c" timeout "$t" setpriv --reuid=1000 --regid=1000 --clear-groups EpgDataCap_Bon "$@"
}

# lib_files <container>: the BonDriver files EDCB loads
lib_files() { docker exec "$1" sh -c 'cd /usr/local/lib/edcb && ls -1 BonDriver_LinuxMirakc*' | sort; }

net_create "$NET"
fake "$FA" fake-a dual
# fake-b closes the first stream after 100 kB (T34)
fake "$FB" fake-b split --drop-after 100000
sleep 2

# ---------------------------------------------------------------- T30 image
section "T30 BonDriver patches and the template in the image"
ok=1
if [ "$SKIP_BUILD" = 1 ]; then
  echo "(build skipped; the patch log is not available)"
else
  grep -q "Applied 3 patch(es) on top of" "$TMP/build.log" || { echo "patch log missing"; ok=0; }
  grep -A4 "Applied 3 patch(es) on top of" "$TMP/build.log" | sed 's/^/  /'
fi
docker run --rm --entrypoint sh "$IMG" -c \
  'ls -l /usr/local/lib/edcb-bondriver; echo "--- /usr/local/lib/edcb"; ls /usr/local/lib/edcb | grep -i bondriver || echo "(no BonDriver before the start)"' |
  tee "$TMP/t30"
grep -q "BonDriver_LinuxMirakc.so" "$TMP/t30" || ok=0
grep -q "(no BonDriver before the start)" "$TMP/t30" || ok=0
if [ $ok = 1 ]; then result T30 PASS; else result T30 FAIL; fi

# ---------------------------------------------------------------- T31 two backends
section "T31 two backends by host name: 6 BonDrivers with their own ini, tuner counts"
D31=$TMP/d31; mkdir "$D31"
run "$C31" "$D31" --network "$NET" -e EDCB_CHSCAN=never \
  -e EDCB_BACKEND_DEFAULT_URL=http://fake-a:40772 -e EDCB_BACKEND_VM_URL=http://fake-b:40772
wait_log "$C31" "starting EpgTimerSrv" 90 || echo "!! no start message"
sleep 3
docker logs "$C31" 2>&1 | grep -E "^provision: (WARNING: )?(backend|create /usr|.*\[BonDriver)"
ok=1
lib_files "$C31" | tee "$TMP/t31"
want=$(for n in "" _T _S _VM _VM_T _VM_S; do printf 'BonDriver_LinuxMirakc%s.so\nBonDriver_LinuxMirakc%s.so.ini\n' "$n" "$n"; done | sort)
[ "$(cat "$TMP/t31")" = "$want" ] || { echo "unexpected file list"; ok=0; }
docker exec "$C31" sh -c 'cd /usr/local/lib/edcb && for f in BonDriver_LinuxMirakc*.so; do [ -L "$f" ] && echo "symlink: $f"; done; true' | grep . && ok=0
for f in BonDriver_LinuxMirakc_S BonDriver_LinuxMirakc_VM_T; do
  echo "--- $f.so.ini"; docker exec "$C31" cat "/usr/local/lib/edcb/$f.so.ini"
done
docker exec "$C31" grep -qx 'SERVER_HOST="fake-a"' /usr/local/lib/edcb/BonDriver_LinuxMirakc_S.so.ini || ok=0
docker exec "$C31" grep -qx 'SERVER_HOST="fake-b"' /usr/local/lib/edcb/BonDriver_LinuxMirakc_VM_T.so.ini || ok=0
echo "--- EpgTimerSrv.ini (BonDriver sections)"
grep -A4 '^\[BonDriver' "$D31/EpgTimerSrv.ini"
# fake-a (dual): M=2; fake-b (split): T=3, S=2
py_count() { python3 - "$D31/EpgTimerSrv.ini" "$1" <<'EOF'
import sys
section = None
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line.startswith("["):
        section = line[1:-1]
    elif section == sys.argv[2] and line.startswith("Count="):
        print(line[6:]); break
EOF
}
for kv in BonDriver_LinuxMirakc.so=2 BonDriver_LinuxMirakc_VM_T.so=3 BonDriver_LinuxMirakc_VM_S.so=2; do
  [ "$(py_count "${kv%=*}")" = "${kv#*=}" ] || { echo "Count of ${kv%=*} is not ${kv#*=}"; ok=0; }
done
grep -q '^\[BonDriver_LinuxMirakc_T.so\]' "$D31/EpgTimerSrv.ini" && { echo "section without tuners was written"; ok=0; }
docker exec "$C31" edcbctl backends
if [ $ok = 1 ]; then result T31 PASS; else result T31 FAIL; fi

# ---------------------------------------------------------------- T32 / T33 host names, separate ini
section "T32 EpgDataCap_Bon -d BonDriver_LinuxMirakc.so reaches fake-a by host name"
a0=$(naccess "$FA" "GET /api/channels "); b0=$(naccess "$FB" "GET /api/channels ")
bon "$C31" 5 -d BonDriver_LinuxMirakc.so > "$TMP/t32" 2>&1
a1=$(naccess "$FA" "GET /api/channels "); b1=$(naccess "$FB" "GET /api/channels ")
echo "/api/channels: fake-a $a0 -> $a1, fake-b $b0 -> $b1"
grep -i "error\|cannot" "$TMP/t32" | head -5
if [ "$a1" -gt "$a0" ] && [ "$b1" = "$b0" ]; then result T32 PASS; else result T32 FAIL; fi

section "T33 BonDriver_LinuxMirakc_VM_T.so reaches fake-b (each copy reads its own ini)"
bon "$C31" 5 -d BonDriver_LinuxMirakc_VM_T.so > "$TMP/t33" 2>&1
a2=$(naccess "$FA" "GET /api/channels "); b2=$(naccess "$FB" "GET /api/channels ")
echo "/api/channels: fake-a $a1 -> $a2, fake-b $b1 -> $b2"
if [ "$b2" -gt "$b1" ] && [ "$a2" = "$a1" ]; then result T33 PASS; else result T33 FAIL; fi

# ---------------------------------------------------------------- T34 reconnect
section "T34 reconnect after the server closes the stream, and after the server is replaced"
ok=1
bon "$C31" 30 -d BonDriver_LinuxMirakc_VM.so -chscan > "$TMP/t34" 2>&1 &
BON_PID=$!
sleep 6
access "$FB" | grep stream
n=$(naccess "$FB" "GET /api/channels/GR/27/stream")
echo "requests for GR/27 to fake-b: $n (the first was closed after 100 kB)"
[ "$n" -ge 2 ] || ok=0
# replace fake-b: same alias, new container with a new address. Docker hands
# the freed address to the next container, so another one takes it first.
ip_old=$(docker inspect -f "{{(index .NetworkSettings.Networks \"$NET\").IPAddress}}" "$FB")
docker rm -f "$FB" >/dev/null
track "$HOLD"
docker run -d --name "$HOLD" --network "$NET" --entrypoint sleep "$IMG" infinity >/dev/null
fake "$FB2" fake-b split
ip_new=$(docker inspect -f "{{(index .NetworkSettings.Networks \"$NET\").IPAddress}}" "$FB2")
echo "fake-b: $ip_old -> $ip_new"
[ "$ip_old" != "$ip_new" ] || { echo "the address did not change"; ok=0; }
for _ in $(seq 20); do access "$FB2" | grep -q stream && break; sleep 1; done
access "$FB2" | grep stream || { echo "no stream request reached the new fake-b"; ok=0; }
wait "$BON_PID" 2>/dev/null
docker rm -f "$HOLD" >/dev/null
echo "--- EpgDataCap_Bon / BonDriver output"
grep -E "reconnect|stream closed" "$TMP/t34" | head -10
grep -q "reconnected after" "$TMP/t34" || { echo "no reconnect message"; ok=0; }
if [ $ok = 1 ]; then result T34 "PASS (address $ip_old -> $ip_new)"; else result T34 FAIL; fi

# ---------------------------------------------------------------- T36 saved information
section "T36 restart with fake-b down: the saved information is used"
docker stop "$FB2" >/dev/null
since=$(date -u +%Y-%m-%dT%H:%M:%SZ); sleep 1
docker restart -t 120 "$C31" >/dev/null
wait_log "$C31" "starting EpgTimerSrv as" 90 "$since"; sleep 2
docker logs --since "$since" "$C31" 2>&1 | grep -E "^provision: (WARNING: )?backend"
ok=1
docker logs --since "$since" "$C31" 2>&1 | grep -q "backend VM (http://fake-b:40772) is unreachable .*using the information from" || ok=0
[ "$(lib_files "$C31")" = "$want" ] || { echo "BonDriver files changed"; ok=0; }
docker exec "$C31" edcbctl backends > "$TMP/t36"; echo "(edcbctl backends exit $?)"; cat "$TMP/t36"
grep -q "^VM: .*UNREACHABLE.*showing the information from" "$TMP/t36" || ok=0
if [ $ok = 1 ]; then result T36 PASS; else result T36 FAIL; fi
docker rm -f "$C31" >/dev/null

# ---------------------------------------------------------------- T35 unreachable, invalid names
section "T35 one backend unreachable (192.0.2.1), invalid backend names"
D35=$TMP/d35; mkdir "$D35"
t0=$(date +%s)
run "$C35" "$D35" --network "$NET" -e EDCB_CHSCAN=never \
  -e EDCB_BACKEND_DEFAULT_URL=http://fake-a:40772 -e EDCB_BACKEND_FAR_URL=http://192.0.2.1:40772 \
  -e EDCB_BACKEND_T_URL=http://fake-a:40772 -e EDCB_BACKEND_MY_VM_URL=http://fake-a:40772 \
  -e EDCB_BACKEND_vm_URL=http://fake-a:40772
wait_log "$C35" "starting EpgTimerSrv" 120 || echo "!! no start message"
t1=$(date +%s)
docker logs "$C35" 2>&1 | grep -E "^provision: (WARNING: )?(backend|.*invalid backend name)"
ok=1
echo "from docker run to the start of EpgTimerSrv: $((t1 - t0)) s"
[ $((t1 - t0)) -le 45 ] || ok=0
docker exec "$C35" pgrep -x EpgTimerSrv >/dev/null || { echo "EpgTimerSrv not running"; ok=0; }
[ "$(docker logs "$C35" 2>&1 | grep -c "invalid backend name")" = 3 ] || { echo "expected 3 invalid name warnings"; ok=0; }
docker logs "$C35" 2>&1 | grep -q "backend FAR (http://192.0.2.1:40772) is unreachable" || ok=0
grep -A1 '^\[BonDriver_LinuxMirakc.so\]' "$D35/EpgTimerSrv.ini" | grep -qx "Count=2" || { echo "the reachable backend is not set up"; ok=0; }
lib_files "$C35" | tr '\n' ' '; echo
[ "$(lib_files "$C35" | grep -c '\.so$')" = 6 ] || ok=0
if [ $ok = 1 ]; then result T35 PASS; else result T35 FAIL; fi
docker rm -f "$C35" >/dev/null

# ---------------------------------------------------------------- T38 v1 configuration
section "T38 MIRAKC_ADDRESS / MIRAKC_PORT only, with an existing ChSet4"
D38=$TMP/d38; mkdir -p "$D38/Setting"
printf '\xef\xbb\xbfGR27\tGR Service A\tGR\t0\t0\t32736\t32736\t1024\t1\t0\t1\t1\n' \
  > "$D38/Setting/BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt"
chown -R 1000:1000 "$D38"
run "$C38" "$D38" --network "$NET" -e MIRAKC_ADDRESS=fake-a -e MIRAKC_PORT=40772
wait_log "$C38" "starting EpgTimerSrv" 90 || echo "!! no start message"
sleep 3
docker logs "$C38" 2>&1 | grep -E "^provision: (WARNING: )?backend"
ok=1
docker exec "$C38" grep -E "^SERVER_(HOST|PORT)" /usr/local/lib/edcb/BonDriver_LinuxMirakc.so.ini
docker exec "$C38" grep -qx 'SERVER_HOST="fake-a"' /usr/local/lib/edcb/BonDriver_LinuxMirakc.so.ini || ok=0
# EDCB lists the BonDriver (it has a ChSet4) with the tuner count
docker exec "$C38" python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:5510/legacy/setting_bon.html').read().decode())" \
  > "$TMP/t38.html" 2>&1
grep -o 'BonDriver_LinuxMirakc[^<"]*' "$TMP/t38.html" | sort -u
grep -q "BonDriver_LinuxMirakc.so" "$TMP/t38.html" || { echo "EDCB does not list the BonDriver"; ok=0; }
# tune the service of the ChSet4: space 0 / ch 0 is GR 27 at fake-a
s0=$(naccess "$FA" "GET /api/channels/GR/27/stream")
bon "$C38" 6 -d BonDriver_LinuxMirakc.so -nid 32736 -tsid 32736 -sid 1024 > "$TMP/t38" 2>&1
s1=$(naccess "$FA" "GET /api/channels/GR/27/stream")
echo "stream requests for GR/27: $s0 -> $s1"
[ "$s1" -gt "$s0" ] || ok=0
if [ $ok = 1 ]; then result T38 PASS; else result T38 FAIL; fi
docker rm -f "$C38" >/dev/null

# ---------------------------------------------------------------- T39 explicit TUNERS
section "T39 EDCB_BACKEND_DEFAULT_TUNERS overwrites Count on every start"
D39=$TMP/d39; mkdir "$D39"
printf '[BonDriver_LinuxMirakc.so]\nCount=5\nPriority=0\n' > "$D39/EpgTimerSrv.ini"
chown -R 1000:1000 "$D39"
run "$C39" "$D39" --network "$NET" -e EDCB_CHSCAN=never -e EDCB_BACKEND_DEFAULT_URL=http://fake-a:40772 -e EDCB_BACKEND_DEFAULT_TUNERS=M:1,T:1
wait_log "$C39" "starting EpgTimerSrv" 90 || echo "!! no start message"
sleep 2
docker logs "$C39" 2>&1 | grep -E "^provision: .*BonDriver_LinuxMirakc"
grep -A4 '^\[BonDriver' "$D39/EpgTimerSrv.ini"
ok=1
grep -A1 '^\[BonDriver_LinuxMirakc.so\]' "$D39/EpgTimerSrv.ini" | grep -qx "Count=1" || ok=0
grep -A1 '^\[BonDriver_LinuxMirakc_T.so\]' "$D39/EpgTimerSrv.ini" | grep -qx "Count=1" || ok=0
# a change in the WebUI is reverted on the next start
sed -i '0,/^Count=1$/s//Count=4/' "$D39/EpgTimerSrv.ini"
since=$(date -u +%Y-%m-%dT%H:%M:%SZ); sleep 1
docker restart -t 120 "$C39" >/dev/null
wait_log "$C39" "starting EpgTimerSrv as" 90 "$since"; sleep 2
docker logs --since "$since" "$C39" 2>&1 | grep -E "^provision: .*Count"
grep -A1 '^\[BonDriver_LinuxMirakc.so\]' "$D39/EpgTimerSrv.ini" | grep -qx "Count=1" || ok=0
if [ $ok = 1 ]; then result T39 PASS; else result T39 FAIL; fi
docker rm -f "$C39" >/dev/null
