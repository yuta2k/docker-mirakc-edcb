# shellcheck shell=bash
# Phase 2: image build, start-up provisioning, privilege drop, health check.
# Sourced by run.sh; uses the helpers in lib.sh.
# shellcheck disable=SC2154  # IMG, TMP, REPO, HERE, PORT_* etc. are set by run.sh

C1=$(cname 1); C3=$(cname 3); C4=$(cname 4); C6=$(cname 6); C7=$(cname 7)
C8=$(cname 8); C9=$(cname 9); C11=$(cname 11); C15=$(cname 15)

# ---------------------------------------------------------------- T0 build
section "T0 docker build edcb/"
if [ "$SKIP_BUILD" = 1 ]; then
  result T0 "SKIP EDCBTEST_SKIP_BUILD=1 (using the existing $IMG)"
elif docker build -t "$IMG" "$REPO/edcb" > "$TMP/build.log" 2>&1; then
  result T0 "PASS build"
  grep -E "Patched|ALLOW_SETTING=|Applied|Fetched" "$TMP/build.log" | sed 's/^/  /'
else
  tail -50 "$TMP/build.log"; result T0 "FAIL build"; abort "the image could not be built"
fi
docker image inspect -f '{{json .Config.Healthcheck}} {{json .Config.ExposedPorts}} {{json .Config.Env}}' "$IMG"

section "T0b build must fail when legacy/util.lua has no ALLOW_SETTING line"
if [ "$SKIP_BUILD" = 1 ]; then
  result T0b "SKIP EDCBTEST_SKIP_BUILD=1"
else
  mkdir -p "$TMP/ctx" && tar -C "$REPO/edcb" --exclude=./ini --exclude=./overrides --exclude=./tests -cf - . | tar -C "$TMP/ctx" -xf -
  cp "$HERE/fixtures/9999-break-allow-setting.patch" "$TMP/ctx/patches/edcb/"
  if docker build -t "$IMG_SHOULDFAIL" "$TMP/ctx" > "$TMP/build-fail.log" 2>&1; then
    result T0b "FAIL build succeeded"; docker rmi "$IMG_SHOULDFAIL" >/dev/null 2>&1
  else
    grep -E "ERROR: expected|upstream changed|Applying:|patch-legacy-util" "$TMP/build-fail.log" | sed 's/^/  /' | head
    if grep -q "found 0" "$TMP/build-fail.log"; then
      result T0b "PASS build failed at the util.lua check"
    else
      tail -30 "$TMP/build-fail.log"; result T0b "FAIL build failed for another reason"
    fi
  fi
fi

# ---------------------------------------------------------------- T1 empty dir
section "T1 empty /var/local/edcb (mirakc not resolvable)"
D1=$TMP/d1; mkdir "$D1"
run "$C1" "$D1" -p "127.0.0.1:$PORT_HTTP:5510"
wait_log "$C1" "starting EpgTimerSrv" 60 || echo "!! no start message"
sleep 8
docker logs "$C1" 2>&1 | grep -v "^provision: .*HttpPublic/" | head -60
echo "--- files"; ls -lan "$D1" "$D1/Setting" "$D1/.provision"
echo "--- EpgTimerSrv.ini"; cat "$D1/EpgTimerSrv.ini"
echo "--- EpgDataCap_Bon.ini"; cat "$D1/EpgDataCap_Bon.ini"
echo "--- .provision/webui.ini"; cat "$D1/.provision/webui.ini"
echo "--- processes"; procs "$C1"; srv_status "$C1"
ok=1
for kv in EnableHttpSrv=1 HttpNumThreads=50 EnableTCPSrv=1 CompatFlags=4095 SaveDebugLog=1 \
  "HttpAccessControlList=+127.0.0.1,+10.0.0.0/8,+172.16.0.0/12,+192.168.0.0/16,+::1,+::ffff:127.0.0.1,+::ffff:10.0.0.0/104,+::ffff:172.16.0.0/108,+::ffff:192.168.0.0/112,+fc00::/7,+fe80::/10" \
  "TCPAccessControlList=+127.0.0.1,+10.0.0.0/8,+172.16.0.0/12,+192.168.0.0/16"; do
  grep -qxF "$kv" "$D1/EpgTimerSrv.ini" || { echo "missing $kv"; ok=0; }
done
grep -q "^HttpPort=" "$D1/EpgTimerSrv.ini" && { echo "HttpPort must not be written without ssl_cert.pem"; ok=0; }
for kv in SaveLogo=1 SaveLogoTypeFlags=32 Count=1 IP0=1 Port0=0; do
  grep -qxF "$kv" "$D1/EpgDataCap_Bon.ini" || { echo "missing $kv"; ok=0; }
done
if python3 -c "import sys; open(sys.argv[1],'rb').read().decode('utf-8')" "$D1/Setting/HttpPublic.ini"; then
  echo "Setting/HttpPublic.ini is UTF-8"
else
  echo "Setting/HttpPublic.ini is not UTF-8"; ok=0
fi
head -3 "$D1/Setting/HttpPublic.ini"
docker exec "$C1" pgrep -x EpgTimerSrv >/dev/null || { echo "EpgTimerSrv not running"; ok=0; }
for p in /legacy/ /E3/; do
  c=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT_HTTP$p"); echo "GET $p -> $c"; [ "$c" = 200 ] || ok=0
done
docker exec "$C1" python3 -c "import socket; socket.create_connection(('127.0.0.1',4510),3); print('TCP 4510 accepts connections')" || ok=0
docker logs "$C1" 2>&1 | grep -m3 '^\[EpgTimerSrv\]' || { echo "no debug log on stdout"; ok=0; }
docker logs "$C1" 2>&1 | grep -q "WARNING: backend DEFAULT (http://mirakc:40772) is unreachable" && echo "unresolvable mirakc: warned, kept starting"
wait_health "$C1" healthy 90 || ok=0
if [ $ok = 1 ]; then result T1 PASS; else result T1 FAIL; fi

# ---------------------------------------------------------------- T2 restart
section "T2 restart without changes"
sums "$D1" > "$TMP/s1"
since=$(date -u +%Y-%m-%dT%H:%M:%SZ); sleep 1
docker restart -t 120 "$C1" >/dev/null
wait_log "$C1" "starting EpgTimerSrv as" 60 "$since"; sleep 3
docker logs --since "$since" "$C1" 2>&1 | grep -E "^(provision|entrypoint):"
sums "$D1" > "$TMP/s2"
if diff "$TMP/s1" "$TMP/s2" && docker logs --since "$since" "$C1" 2>&1 | grep -qx "provision: no changes"; then
  result T2 PASS; else result T2 FAIL; fi

# ---------------------------------------------------------------- T5 allow-setting
section "T5 edcbctl allow-setting without restart (POST to /legacy/setting_app.html)"
p2_post() { # value for RecFileName
  local page ctok
  page=$(curl -s "http://127.0.0.1:$PORT_HTTP/legacy/setting_app.html")
  ctok=$(printf '%s' "$page" | grep -o 'name="ctok" value="[^"]*"' | head -1 | sed 's/.*value="//; s/"$//')
  curl -s -X POST --data "ctok=$ctok&saveDebugLog=1&recFileName=$1" "http://127.0.0.1:$PORT_HTTP/legacy/setting_app.html" |
    grep -o '<div id="result">[^<]*</div>'
}
ok=1
pid_before=$(docker exec "$C1" pgrep -x EpgTimerSrv)
docker exec "$C1" edcbctl allow-setting status
r=$(p2_post denied1.ts); echo "off: $r"; [[ $r == *許可されていません* ]] || ok=0
docker exec "$C1" edcbctl allow-setting on
r=$(p2_post allowed.ts); echo "on: $r"; [[ $r == *変更しました* ]] || ok=0
grep -n "RecFileName" "$D1/EpgDataCap_Bon.ini"; grep -qx "RecFileName=allowed.ts" "$D1/EpgDataCap_Bon.ini" || ok=0
docker exec "$C1" edcbctl allow-setting off
r=$(p2_post denied2.ts); echo "off again: $r"; [[ $r == *許可されていません* ]] || ok=0
grep -qx "RecFileName=allowed.ts" "$D1/EpgDataCap_Bon.ini" || ok=0
pid_after=$(docker exec "$C1" pgrep -x EpgTimerSrv)
echo "EpgTimerSrv pid before=$pid_before after=$pid_after"; [ "$pid_before" = "$pid_after" ] || ok=0
if [ $ok = 1 ]; then result T5 PASS; else result T5 FAIL; fi

section "T12 allowed state is reset by a restart"
docker exec "$C1" edcbctl allow-setting on
since=$(date -u +%Y-%m-%dT%H:%M:%SZ); sleep 1
docker restart -t 120 "$C1" >/dev/null; wait_log "$C1" "starting EpgTimerSrv as" 60 "$since"; sleep 3
docker logs --since "$since" "$C1" 2>&1 | grep "^provision:"
s=$(docker exec "$C1" edcbctl allow-setting status); echo "$s"
r=$(p2_post after-restart.ts); echo "POST: $r"
if [[ $s == *denied* && $r == *許可されていません* ]]; then result T12 PASS; else result T12 FAIL; fi

# ---------------------------------------------------------------- T10 stop
section "T10 docker stop"
procs "$C1"
start=$(date +%s%N)
docker stop -t 120 "$C1" >/dev/null
end=$(date +%s%N)
echo "docker stop took $(( (end - start) / 1000000 )) ms, exit code $(docker inspect -f '{{.State.ExitCode}}' "$C1")"
docker logs "$C1" 2>&1 | tail -8
tail -3 "$D1/EpgTimerSrvDebugLog.txt"
code=$(docker inspect -f '{{.State.ExitCode}}' "$C1")
if docker logs "$C1" 2>&1 | tail -3 | grep -q "entrypoint: stopped" && [ "$code" = 0 ]; then
  result T10 PASS; else result T10 FAIL; fi

# ---------------------------------------------------------------- T3 existing data
section "T3 copy of the existing real ini files"
if [ -z "$REAL_INI" ]; then
  result T3 "SKIP no real *.ini available (set EDCBTEST_REAL_INI)"
else
  echo "source: $REAL_INI (only read)"
  D3=$TMP/d3; mkdir "$D3"; cp -a "$REAL_INI"/*.ini "$D3/"; mkdir "$TMP/orig3"; cp -a "$REAL_INI"/*.ini "$TMP/orig3/"
  ls -lan "$D3"
  echo "--- edcbctl provision --diff (one-off container, nothing may change)"
  sums "$D3" > "$TMP/s3a"; find "$D3" | sort > "$TMP/f3a"
  docker run --rm --entrypoint edcbctl -v "$D3:/var/local/edcb" "$IMG" provision --diff 2>&1 | grep -v "HttpPublic/"
  sums "$D3" > "$TMP/s3b"; find "$D3" | sort > "$TMP/f3b"
  ok=1
  if diff "$TMP/s3a" "$TMP/s3b" && diff "$TMP/f3a" "$TMP/f3b"; then echo "--diff wrote nothing"; else echo "--diff changed files"; ok=0; fi
  echo "--- start"
  run "$C3" "$D3" -e PUID=1000 -e PGID=1000
  wait_log "$C3" "starting EpgTimerSrv" 60; sleep 5
  docker logs "$C3" 2>&1 | grep -E "^(provision|entrypoint)" | grep -v "HttpPublic/"
  for f in "$TMP"/orig3/*.ini; do
    b=$(basename "$f"); echo "--- diff $b"
    diff "$f" "$D3/$b" | tee "$TMP/d.$b"
    if grep -q '^<' "$TMP/d.$b"; then echo "!! existing line changed in $b"; ok=0; fi
  done
  ls "$D3/.provision/backup/"*/ 2>/dev/null && echo "backup created"
  docker exec "$C3" pgrep -x EpgTimerSrv >/dev/null || ok=0
  if [ $ok = 1 ]; then result T3 "PASS only additions"; else result T3 FAIL; fi
  docker rm -f "$C3" >/dev/null
fi

# ---------------------------------------------------------------- T4 WebUI-like edits, env, overrides
section "T4 WebUI-like edits survive, env keys are restored, overrides apply"
D4=$TMP/d4; O4=$TMP/o4; S4=$TMP/seed4; mkdir -p "$D4" "$O4/Setting" "$S4"
printf '[EPGCAP]\nEpgCapTimeOut=20\n' > "$O4/BonCtrl.ini"
printf '[SET]\nSHOW_DEBUG_LOG=1\n' > "$O4/Setting/HttpPublic.ini"
printf 'not an ini\n' > "$O4/readme.txt"
# an existing BonCtrl.ini with comments: the initial file the image creates
# (a one-off provisioning into a scratch directory), so the case does not
# depend on the host's ini files
seed_ok=1
docker run --rm --entrypoint edcbctl -v "$S4:/var/local/edcb" "$IMG" provision > "$TMP/seed4.log" 2>&1
if [ -f "$S4/BonCtrl.ini" ]; then
  cp "$S4/BonCtrl.ini" "$D4/BonCtrl.ini"; cp "$D4/BonCtrl.ini" "$TMP/bonctrl4.orig"
else
  echo "!! the one-off provisioning did not create BonCtrl.ini"; tail -20 "$TMP/seed4.log"; seed_ok=0
fi
# shellcheck disable=SC2054  # the commas belong to the value
T4ENV=(-e EDCB_HTTP_NUM_THREADS=30 -e EDCB_REC_FOLDERS=/recorded,/recorded2 -v "$O4:/etc/edcb/overrides:ro")
run "$C4" "$D4" "${T4ENV[@]}"
wait_log "$C4" "starting EpgTimerSrv" 60; sleep 3
docker stop -t 120 "$C4" >/dev/null
echo "--- edit like the WebUI / by hand"
sed -i -e 's/^HttpNumThreads=30/HttpNumThreads=5/' -e 's/^SaveDebugLog=1/SaveDebugLog=0/' -e 's/^EnableTCPSrv=1/EnableTCPSrv=0/' "$D4/EpgTimerSrv.ini"
printf 'StartMargin=10\n' >> "$D4/EpgTimerSrv.ini"
sed -i -e 's/^SaveLogo=1/SaveLogo=0/' -e 's/^Count=1/Count=0/' -e '/^IP0=/d' -e '/^Port0=/d' "$D4/EpgDataCap_Bon.ini"
sed -i -e 's/^RecFolderPath0=.*/RecFolderPath0=\/changed/' "$D4/Common.ini"
cp "$D4/EpgTimerSrv.ini" "$TMP/srv4.edited"; cp "$D4/EpgDataCap_Bon.ini" "$TMP/app4.edited"; cp "$D4/BonCtrl.ini" "$TMP/bonctrl4"
since=$(date -u +%Y-%m-%dT%H:%M:%SZ); sleep 1
docker start "$C4" >/dev/null; wait_log "$C4" "starting EpgTimerSrv as" 60 "$since"; sleep 3
docker logs --since "$since" "$C4" 2>&1 | grep -E "^(provision|entrypoint)"
ok=$seed_ok
echo "--- EpgTimerSrv.ini diff (edited -> after restart)"; diff "$TMP/srv4.edited" "$D4/EpgTimerSrv.ini"
if [ "$(diff "$TMP/srv4.edited" "$D4/EpgTimerSrv.ini" | grep -c '^[<>]')" = 2 ] && grep -qx HttpNumThreads=30 "$D4/EpgTimerSrv.ini"; then :; else ok=0; fi
echo "--- EpgDataCap_Bon.ini diff"; diff "$TMP/app4.edited" "$D4/EpgDataCap_Bon.ini" || ok=0
echo "--- Common.ini"; cat "$D4/Common.ini"; grep -qx "RecFolderPath0=/recorded" "$D4/Common.ini" || ok=0
echo "--- BonCtrl.ini: original -> after (override; only EpgCapTimeOut may change)"
diff "$TMP/bonctrl4.orig" "$D4/BonCtrl.ini"
if [ "$(diff "$TMP/bonctrl4.orig" "$D4/BonCtrl.ini" | grep -c '^[<>]')" = 2 ] && grep -qx EpgCapTimeOut=20 "$D4/BonCtrl.ini"; then :; else ok=0; fi
echo "--- Setting/HttpPublic.ini head"; head -5 "$D4/Setting/HttpPublic.ini"; grep -qx SHOW_DEBUG_LOG=1 "$D4/Setting/HttpPublic.ini" || ok=0
docker logs "$C4" 2>&1 | grep -q "override readme.txt is ignored" || ok=0
echo "--- backups"
# shellcheck disable=SC2012  # listing for the log only
ls -R "$D4/.provision/backup" | head -20
if [ "$ok" = 1 ]; then result T4 PASS; else result T4 FAIL; fi
docker rm -f "$C4" >/dev/null

# ---------------------------------------------------------------- T6 groups
section "T6 group_add and /dev/dri render group survive the privilege drop"
D6=$TMP/d6; mkdir "$D6"
# The /dev/dri part needs a render node on the host (GitHub-hosted runners have none)
DRI=(); have_render=0
if compgen -G '/dev/dri/renderD*' >/dev/null; then DRI=(--device /dev/dri); have_render=1; fi
run "$C6" "$D6" --group-add 1500 --group-add video "${DRI[@]}"
wait_log "$C6" "starting EpgTimerSrv" 60; sleep 3
docker logs "$C6" 2>&1 | grep "starting EpgTimerSrv"
docker exec "$C6" sh -c 'id; ls -ln /dev/dri 2>/dev/null; getent group video'
srv_status "$C6"
groups=$(srv_status "$C6" | sed -n 's/^Groups:\s*//p')
render=$(docker exec "$C6" sh -c 'stat -c %g /dev/dri/renderD* 2>/dev/null | head -1')
video=$(docker exec "$C6" getent group video | cut -d: -f3)
ok=1
for g in 1500 "$video" ${render:+"$render"}; do echo " $groups " | grep -q " $g " || { echo "missing group $g"; ok=0; }; done
echo " $groups " | grep -q " 0 " && { echo "root group must not be kept"; ok=0; }
if [ $have_render = 1 ]; then
  render_note="render gid ${render:-none}"
else
  render_note="render group SKIP: no /dev/dri/renderD* on the host"
fi
if [ $ok = 1 ]; then result T6 "PASS groups: $groups ($render_note)"; else result T6 FAIL; fi
docker rm -f "$C6" >/dev/null

# ---------------------------------------------------------------- T7 PUID/PGID
section "T7 PUID=1234 PGID=1234"
D7=$TMP/d7; mkdir "$D7"
run "$C7" "$D7" -e PUID=1234 -e PGID=1234 -e UMASK=002
wait_log "$C7" "starting EpgTimerSrv" 60; sleep 5
procs "$C7"; srv_status "$C7"
find "$D7" -printf '%U:%G %m %P\n' | grep -v '^1234:1234 ' | head -20 > "$TMP/notowned"
find "$D7" -maxdepth 1 -printf '%U:%G %m %P\n'
ok=1
if srv_status "$C7" | grep -qE '^Uid:\s+1234\s' && srv_status "$C7" | grep -qE '^Gid:\s+1234\s'; then :; else ok=0; fi
if [ -s "$TMP/notowned" ]; then echo "not owned by 1234:"; cat "$TMP/notowned"; ok=0; fi
ls -ln "$D7/EpgTimerSrvDebugLog.txt" || ok=0
if [ $ok = 1 ]; then result T7 PASS; else result T7 FAIL; fi
docker rm -f "$C7" >/dev/null

# ---------------------------------------------------------------- T8 user:
section "T8 --user 1000:1000 must exit with a migration message"
D8=$TMP/d8; mkdir "$D8"
track "$C8"
docker run -d --name "$C8" --user 1000:1000 -v "$D8:/var/local/edcb" "$IMG" >/dev/null
sleep 5
docker logs "$C8" 2>&1
st=$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$C8"); echo "state: $st"
if [ "$st" = "exited 1" ] && docker logs "$C8" 2>&1 | grep -q PUID; then result T8 PASS; else result T8 FAIL; fi
docker rm -f "$C8" >/dev/null

# ---------------------------------------------------------------- T9 unreachable backend
section "T9 backend resolvable but unreachable (192.0.2.1)"
D9=$TMP/d9; mkdir "$D9"
run "$C9" "$D9" -e MIRAKC_ADDRESS=192.0.2.1 -e MIRAKC_PORT=40772
wait_log "$C9" "starting EpgTimerSrv" 60; sleep 5
docker logs "$C9" 2>&1 | grep -E "^(entrypoint|provision: (WARNING: )?backend)"
docker exec "$C9" grep -E "^SERVER_(HOST|PORT)" /usr/local/lib/edcb/BonDriver_LinuxMirakc.so.ini
if docker exec "$C9" pgrep -x EpgTimerSrv >/dev/null; then result T9 PASS; else result T9 FAIL; fi
docker rm -f "$C9" >/dev/null

# ---------------------------------------------------------------- T11 health with HTTP off
section "T11 EnableHttpSrv=0 stays healthy"
D11=$TMP/d11; O11=$TMP/o11; mkdir -p "$D11" "$O11"
printf '[SET]\nEnableHttpSrv=0\n' > "$O11/EpgTimerSrv.ini"
run "$C11" "$D11" -v "$O11:/etc/edcb/overrides:ro"
grep -n EnableHttpSrv "$D11/EpgTimerSrv.ini" 2>/dev/null
if wait_health "$C11" healthy 90; then result T11 PASS; else result T11 FAIL; fi
docker exec "$C11" grep EnableHttpSrv /var/local/edcb/EpgTimerSrv.ini
docker inspect -f '{{range .State.Health.Log}}{{.Output}}{{end}}' "$C11" | tail -2
echo "--- negative check: the health check fails without EpgTimerSrv (one-off container)"
docker run --rm --entrypoint env "$IMG" PYTHONPATH=/usr/local/lib/edcb-provision python3 -m edcb_provision.healthcheck; echo "rc=$? (expected 1)"
docker rm -f "$C11" >/dev/null

# ---------------------------------------------------------------- T15 HTTPS
section "T15 ssl_cert.pem present on first start -> HttpPort default and HTTPS"
D15=$TMP/d15; mkdir "$D15"
openssl req -new -newkey rsa:2048 -nodes -keyout "$TMP/k.pem" -out "$TMP/c.pem" -x509 -days 1 -sha256 \
  -subj /CN=edcbtest -addext "subjectAltName = IP:127.0.0.1" 2>/dev/null
cat "$TMP/c.pem" "$TMP/k.pem" > "$D15/ssl_cert.pem"
run "$C15" "$D15" -p "127.0.0.1:$PORT_HTTPS:5511" -p "127.0.0.1:$PORT_HTTP2:5510"
wait_log "$C15" "starting EpgTimerSrv" 60; sleep 5
grep -n "HttpPort" "$D15/EpgTimerSrv.ini"
c1=$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:$PORT_HTTPS/E3/"); echo "https /E3/ -> $c1"
c2=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT_HTTP2/legacy/"); echo "http /legacy/ -> $c2"
curl -skI "https://127.0.0.1:$PORT_HTTPS/E3/" | grep -iE "^(HTTP|cross-origin)" | tr -d '\r'
wait_health "$C15" healthy 90; h=$?
if grep -qx "HttpPort=5510,5520,5511s,5521s" "$D15/EpgTimerSrv.ini" && [ "$c1" = 200 ] && [ "$c2" = 200 ] && [ $h = 0 ]; then
  result T15 PASS; else result T15 FAIL; fi
docker rm -f "$C15" >/dev/null
