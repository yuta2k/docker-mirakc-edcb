# shellcheck shell=bash
# Phase 4: channel scans, ChSet4 files per kind, edcbctl chscan / status.
# Sourced by run.sh after phase3.sh; uses its test network ($NET) and fake().
# The fake servers send null packets only, in which EpgDataCap_Bon finds no
# services, so most cases scan with edcb/tests/fake_epgdatacap.py, which
# writes what a scan would. T47 runs the real EpgDataCap_Bon.
# shellcheck disable=SC2154  # IMG, TMP, REPO, NET, REAL_INI etc. are set by run.sh / phase3.sh

P4A=$(cname p4-a); P4B=$(cname p4-b); P4B2=$(cname p4-b2)
C40=$(cname 40); C45=$(cname 45); C46=$(cname 46); C47=$(cname 47); C48=$(cname 48); C49=$(cname 49)

# run options that make the provisioning scan with the fake EpgDataCap_Bon
FAKESCAN=(-v "$REPO/edcb/tests:/tests:ro"
  -e "EDCB_PROVISION_EPGDATACAP=python3 /tests/fake_epgdatacap.py"
  -e FAKE_CHSCAN_LOG=/var/local/edcb/chscan.log)

# cs4 <dir> <suffix>: the ChSet4 of BonDriver_LinuxMirakc<suffix>.so
cs4() { printf '%s/Setting/BonDriver_LinuxMirakc%s(LinuxMirakc).ChSet4.txt' "$1" "$2"; }
# nscan <dir>: how many scans the fake EpgDataCap_Bon ran
nscan() { if [ -f "$1/chscan.log" ]; then wc -l < "$1/chscan.log"; else echo 0; fi; }
# chsums <dir>: hashes of the channel files
chsums() { (cd "$1/Setting" 2>/dev/null && sha256sum ./*.ChSet4.txt ChSet5.txt 2>/dev/null); }
# chfiles <dir>: names of the channel files
chfiles() { (cd "$1/Setting" 2>/dev/null && ls -1 ./*.ChSet4.txt ChSet5.txt 2>/dev/null) | sed 's|^\./||'; }
# spaces <ChSet4>: the space column, one line
spaces() {
  python3 -c 'import sys; print(" ".join(l.split("\t")[3] for l in open(sys.argv[1], encoding="utf-8-sig") if "\t" in l))' "$1"
}
# service_args <ChSet4> <row>: "-nid X -tsid Y -sid Z" of a row (1-based)
service_args() {
  python3 -c 'import sys
rows = [l.split("\t") for l in open(sys.argv[1], encoding="utf-8-sig") if "\t" in l]
r = rows[int(sys.argv[2]) - 1]
print(f"-nid {r[5]} -tsid {r[6]} -sid {r[7]}")' "$1" "$2"
}
# tune <container> <BonDriver> <ChSet4> <row> <fake> <type/channel>: tune a row of
# a ChSet4 with EpgDataCap_Bon; true if the fake server got the stream request
tune() {
  local c=$1 bondriver=$2 file=$3 row=$4 server=$5 want=$6 n0 n1 args
  n0=$(naccess "$server" "GET /api/channels/$want/stream")
  read -ra args <<< "$(service_args "$file" "$row")"
  bon "$c" 6 -d "$bondriver" "${args[@]}" > "$TMP/tune.out" 2>&1
  n1=$(naccess "$server" "GET /api/channels/$want/stream")
  echo "tune $bondriver row $row (${args[*]}): stream requests for $want $n0 -> $n1"
  [ "$n1" -gt "$n0" ]
}

fake "$P4A" p4-a mixed
fake "$P4B" p4-b split
sleep 2

# ---------------------------------------------------------------- T40 first start
section "T40 first start without ChSet5: every backend is scanned and split by kind"
D40=$TMP/d40; mkdir "$D40"
# No EPG capture by these tuners: the capture that follows a scan would tune
# the fake servers and make the stream counts of tune() meaningless. EpgTimerSrv
# then declines the request (T49 checks a capture that starts).
O40=$TMP/o40; mkdir "$O40"
for b in "" _T _S _VM_T _VM_S; do printf '[BonDriver_LinuxMirakc%s.so]\nGetEpg=0\n' "$b"; done > "$O40/EpgTimerSrv.ini"
run "$C40" "$D40" --network "$NET" "${FAKESCAN[@]}" -v "$O40:/etc/edcb/overrides:ro" \
  -e EDCB_BACKEND_DEFAULT_URL=http://p4-a:40772 -e EDCB_BACKEND_VM_URL=http://p4-b:40772
wait_log "$C40" "starting EpgTimerSrv" 120 || echo "!! no start message"
sleep 3
docker logs "$C40" 2>&1 | grep -E "^provision: (WARNING: )?(first start|backend|chscan|create Setting|Setting)"
ok=1
chfiles "$D40" | tee "$TMP/t40"
want40=$(printf '%s\n' "BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt" "BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt" \
  "BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt" "BonDriver_LinuxMirakc_VM_S(LinuxMirakc).ChSet4.txt" \
  "BonDriver_LinuxMirakc_VM_T(LinuxMirakc).ChSet4.txt" "ChSet5.txt")
[ "$(cat "$TMP/t40")" = "$want40" ] || { echo "unexpected channel files"; ok=0; }
[ "$(nscan "$D40")" = 2 ] || { echo "expected 2 scans, got $(nscan "$D40")"; ok=0; }
# p4-a (mixed): spaces GR=0, BS=1, CS=2; M has everything
for kv in "=0 0 1 1 2" "_T=0 0" "_S=1 1 2" "_VM_T=0 0" "_VM_S=1 1 2"; do
  got=$(spaces "$(cs4 "$D40" "${kv%%=*}")")
  echo "spaces BonDriver_LinuxMirakc${kv%%=*}: $got"
  [ "$got" = "${kv#*=}" ] || ok=0
done
stat -c '%u:%g %n' "$D40"/Setting/*.txt | grep -v '^1000:1000 ' && { echo "not owned by 1000:1000"; ok=0; }
docker exec "$C40" sh -c 'ls /usr/local/lib/edcb | grep -- -scan-' && { echo "temporary BonDriver left"; ok=0; }
# EDCB lists every BonDriver with a ChSet4
docker exec "$C40" python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:5510/legacy/setting_bon.html').read().decode())" \
  > "$TMP/t40.html" 2>&1
grep -o 'BonDriver_LinuxMirakc[^<"]*\.so' "$TMP/t40.html" | sort -u
for b in "" _T _S _VM_T _VM_S; do
  grep -q "BonDriver_LinuxMirakc$b.so" "$TMP/t40.html" || { echo "EDCB does not list BonDriver_LinuxMirakc$b.so"; ok=0; }
done
# the space / ch of the split files select the right channel through the BonDriver
tune "$C40" BonDriver_LinuxMirakc_VM_S.so "$(cs4 "$D40" _VM_S)" 1 "$P4B" BS/BS01_0 || ok=0
tune "$C40" BonDriver_LinuxMirakc_VM_S.so "$(cs4 "$D40" _VM_S)" 3 "$P4B" CS/CS2 || ok=0
tune "$C40" BonDriver_LinuxMirakc_T.so "$(cs4 "$D40" _T)" 2 "$P4A" GR/26 || ok=0
# single-band BonDrivers first (EDCB uses the smallest Priority first)
grep -A4 '^\[BonDriver' "$D40/EpgTimerSrv.ini" | grep -E '^\[|^Priority'
python3 - "$D40/EpgTimerSrv.ini" <<'EOF2' || ok=0
import sys
prio, section = {}, None
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line.startswith("["):
        section = line[1:-1]
    elif line.startswith("Priority="):
        prio[section] = int(line[9:])
dual = [p for s, p in prio.items() if s in ("BonDriver_LinuxMirakc.so",)]
single = [p for s, p in prio.items() if s.endswith(("_T.so", "_S.so"))]
sys.exit(0 if dual and single and max(single) < min(dual) else 1)
EOF2
# the BonDrivers used for viewing: every BonDriver with tuners, written on the first start
echo "--- [TVTEST]"; grep -A6 '^\[TVTEST\]' "$D40/EpgTimerSrv.ini"
grep -A1 '^\[TVTEST\]' "$D40/EpgTimerSrv.ini" | grep -qx "Num=5" || { echo "the viewing list does not have 5 BonDrivers"; ok=0; }
# the request for an EPG capture after the scan reached EpgTimerSrv
docker logs "$C40" 2>&1 | grep "EPG capture" || { echo "no answer to the EPG capture request"; ok=0; }
[ -e "$D40/.provision/epgcap-pending" ] && { echo "EPG capture still pending"; ok=0; }
if [ $ok = 1 ]; then result T40 PASS; else result T40 FAIL; fi

# ---------------------------------------------------------------- T41 second start
section "T41 restart with ChSet5: no scan, no change"
chsums "$D40" > "$TMP/s41a"
since=$(date -u +%Y-%m-%dT%H:%M:%SZ); sleep 1
docker restart -t 120 "$C40" >/dev/null
wait_log "$C40" "starting EpgTimerSrv as" 90 "$since"; sleep 2
docker logs --since "$since" "$C40" 2>&1 | grep -E "^provision: (WARNING: )?(backend|chscan|.*scan|.*Setting/)"
ok=1
[ "$(nscan "$D40")" = 2 ] || { echo "scanned again"; ok=0; }
chsums "$D40" | diff "$TMP/s41a" - || { echo "channel files changed"; ok=0; }
docker logs --since "$since" "$C40" 2>&1 | grep -E "WARNING: .*(scan|channel)" && ok=0
if [ $ok = 1 ]; then result T41 PASS; else result T41 FAIL; fi

# ---------------------------------------------------------------- T42 drift
section "T42 the channels of a backend change: warning only, files unchanged"
docker rm -f "$P4B" >/dev/null
# same tuners, channels GR, BS, GR, CS: the second GR channel gets a space of its own
fake "$P4B2" p4-b split-interleaved
sleep 2
since=$(date -u +%Y-%m-%dT%H:%M:%SZ); sleep 1
docker restart -t 120 "$C40" >/dev/null
wait_log "$C40" "starting EpgTimerSrv as" 90 "$since"; sleep 2
docker logs --since "$since" "$C40" 2>&1 | grep -E "^provision: WARNING: .*(scan|channel)"
ok=1
docker logs --since "$since" "$C40" 2>&1 | grep -q "WARNING: backend VM: the channel list of the backend changed.*edcbctl chscan VM" || ok=0
docker logs --since "$since" "$C40" 2>&1 | grep -q "WARNING: backend DEFAULT: the channel list" && { echo "DEFAULT did not change"; ok=0; }
chsums "$D40" | diff "$TMP/s41a" - || { echo "channel files changed"; ok=0; }
[ "$(nscan "$D40")" = 2 ] || ok=0
docker exec "$C40" edcbctl backends | grep -E "^[A-Z]|channel scan"
if [ $ok = 1 ]; then result T42 PASS; else result T42 FAIL; fi

# ---------------------------------------------------------------- T43 edcbctl chscan <name>
section "T43 edcbctl chscan VM: only VM is scanned and split again"
ok=1
docker exec "$C40" edcbctl chscan VM > "$TMP/t43" 2>&1; rc=$?
cat "$TMP/t43"
[ $rc = 0 ] || { echo "exit $rc"; ok=0; }
[ "$(nscan "$D40")" = 3 ] || ok=0
[ "$(tail -1 "$D40/chscan.log")" = "CHSCAN BonDriver_LinuxMirakc-scan-VM.so" ] || ok=0
grep -q "Restart the container" "$TMP/t43" || ok=0
grep -q "EPG of the scanned channels is captured right after the restart" "$TMP/t43" || ok=0
[ -e "$D40/.provision/epgcap-pending" ] || { echo "no EPG capture pending after chscan"; ok=0; }
grep -q "^recording: no" "$TMP/t43" || ok=0
chsums "$D40" > "$TMP/s43"
for f in "BonDriver_LinuxMirakc(" "BonDriver_LinuxMirakc_T(" "BonDriver_LinuxMirakc_S("; do
  [ "$(grep -F "$f" "$TMP/s41a")" = "$(grep -F "$f" "$TMP/s43")" ] || { echo "$f changed"; ok=0; }
done
for kv in "_VM_T=0 2" "_VM_S=1 1 3"; do
  got=$(spaces "$(cs4 "$D40" "${kv%%=*}")")
  echo "spaces BonDriver_LinuxMirakc${kv%%=*}: $got"
  [ "$got" = "${kv#*=}" ] || ok=0
done
tune "$C40" BonDriver_LinuxMirakc_VM_T.so "$(cs4 "$D40" _VM_T)" 2 "$P4B2" GR/26 || ok=0
docker exec "$C40" edcbctl backends | grep -E "^[A-Z]|channel scan" | tee "$TMP/t43b"
grep -q "CHANGED" "$TMP/t43b" && ok=0
if [ $ok = 1 ]; then result T43 PASS; else result T43 FAIL; fi

# ---------------------------------------------------------------- T44 --rebuild
section "T44 edcbctl chscan --all --rebuild: ChSet5 backed up and made again, flags kept"
# turn off the EPG and search flags of the first service, add a service that no longer exists
python3 - "$D40/Setting/ChSet5.txt" <<'EOF'
import sys
path = sys.argv[1]
data = open(path, encoding="utf-8-sig").read().splitlines()
f = data[0].split("\t"); f[7] = f[8] = "0"; data[0] = "\t".join(f)
data.append("Old service\tnet\t9\t9\t9\t1\t0\t1\t1")
with open(path, "w", encoding="utf-8-sig") as out:
    out.write("\n".join(data) + "\n")
print("first service:", data[0])
EOF
first=$(python3 -c 'import sys; f = open(sys.argv[1], encoding="utf-8-sig").readline().split("\t"); print("\t".join(f[2:5]))' "$D40/Setting/ChSet5.txt")
ok=1
docker exec "$C40" edcbctl chscan --all --rebuild > "$TMP/t44" 2>&1; rc=$?
cat "$TMP/t44"
[ $rc = 0 ] || { echo "exit $rc"; ok=0; }
[ "$(nscan "$D40")" = 5 ] || ok=0
grep -q "Old service" "$D40/Setting/ChSet5.txt" && { echo "old service kept"; ok=0; }
grep -P "^[^\t]*\t[^\t]*\t\Q$first\E\t" "$D40/Setting/ChSet5.txt" | tee "$TMP/t44f"
grep -qP "\t0\t0$" "$TMP/t44f" || { echo "flags not kept"; ok=0; }
latest=$(find "$D40/.provision/backup" -mindepth 1 -maxdepth 1 | sort | tail -1)
grep -q "Old service" "$latest/Setting/ChSet5.txt" || { echo "no backup of the old ChSet5"; ok=0; }
stat -c '%u:%g' "$D40/Setting/ChSet5.txt" | grep -qx 1000:1000 || ok=0
if [ $ok = 1 ]; then result T44 PASS; else result T44 FAIL; fi
docker rm -f "$C40" >/dev/null

# ---------------------------------------------------------------- T45 never
section "T45 EDCB_CHSCAN=never: no scan without ChSet5"
D45=$TMP/d45; mkdir "$D45"
run "$C45" "$D45" --network "$NET" "${FAKESCAN[@]}" -e EDCB_CHSCAN=never -e EDCB_BACKEND_DEFAULT_URL=http://p4-a:40772
wait_log "$C45" "starting EpgTimerSrv" 90 || echo "!! no start message"
sleep 2
ok=1
[ "$(nscan "$D45")" = 0 ] || ok=0
[ -z "$(chfiles "$D45")" ] || { chfiles "$D45"; ok=0; }
docker logs "$C45" 2>&1 | grep -E "WARNING: .*(scan|channel)" && ok=0
if [ $ok = 1 ]; then result T45 PASS; else result T45 FAIL; fi
docker rm -f "$C45" >/dev/null

# ---------------------------------------------------------------- T46 existing data
section "T46 existing channel files (v1): nothing is scanned or changed"
D46=$TMP/d46; mkdir -p "$D46/Setting"
if [ -n "$REAL_INI" ] && [ -f "$REAL_INI/Setting/ChSet5.txt" ] && compgen -G "$REAL_INI/Setting/*.ChSet4.txt" >/dev/null; then
  kind46="real data"
  cp "$REAL_INI"/Setting/*.ChSet4.txt "$REAL_INI/Setting/ChSet5.txt" "$D46/Setting/"
else
  kind46="synthetic data"
  printf '\xef\xbb\xbfGR27\tGR Service A\tGR\t0\t0\t32736\t32736\t1024\t1\t0\t1\t1\n' > "$(cs4 "$D46" "")"
  printf '\xef\xbb\xbfGR Service A\tGR\t32736\t32736\t1024\t1\t0\t1\t1\n' > "$D46/Setting/ChSet5.txt"
fi
echo "using $kind46"
chown -R 1000:1000 "$D46"
chsums "$D46" > "$TMP/s46a"
run "$C46" "$D46" --network "$NET" "${FAKESCAN[@]}" -e MIRAKC_ADDRESS=p4-a -e MIRAKC_PORT=40772
wait_log "$C46" "starting EpgTimerSrv" 90 || echo "!! no start message"
sleep 2
since=$(date -u +%Y-%m-%dT%H:%M:%SZ); sleep 1
docker restart -t 120 "$C46" >/dev/null
wait_log "$C46" "starting EpgTimerSrv as" 90 "$since"; sleep 2
docker logs "$C46" 2>&1 | grep -E "^provision: (WARNING: )?.*(scan|channel|Setting/)"
ok=1
[ "$(nscan "$D46")" = 0 ] || ok=0
chsums "$D46" | diff "$TMP/s46a" - || { echo "channel files changed"; ok=0; }
docker exec "$C46" edcbctl backends | grep "channel scan"
if [ $ok = 1 ]; then result T46 "PASS ($kind46)"; else result T46 "FAIL ($kind46)"; fi
docker rm -f "$C46" >/dev/null

# ---------------------------------------------------------------- T47 real EpgDataCap_Bon
section "T47 the real EpgDataCap_Bon scans every channel; no services found: nothing changes"
D47=$TMP/d47; mkdir "$D47"
# short waits per channel (EDCB's defaults are 9 + 8 s)
printf '[CHSCAN]\nChChgTimeOut=2\nServiceChkTimeOut=1\n' > "$D47/BonCtrl.ini"
chown -R 1000:1000 "$D47"
declare -A s47
for ch in GR/27 GR/26 BS/BS01_0 BS/BS03_1 CS/CS2; do s47[$ch]=$(naccess "$P4A" "GET /api/channels/$ch/stream"); done
t0=$(date +%s)
run "$C47" "$D47" --network "$NET" -e EDCB_BACKEND_DEFAULT_URL=http://p4-a:40772
wait_log "$C47" "starting EpgTimerSrv" 180 || echo "!! no start message"
t1=$(date +%s)
sleep 2
docker logs "$C47" 2>&1 | grep -E "^provision: (WARNING: )?(first start|backend|chscan)"
echo "from docker run to the start of EpgTimerSrv: $((t1 - t0)) s"
ok=1
for ch in GR/27 GR/26 BS/BS01_0 BS/BS03_1 CS/CS2; do
  n=$(naccess "$P4A" "GET /api/channels/$ch/stream")
  echo "stream requests for $ch: ${s47[$ch]} -> $n"
  [ "$n" -gt "${s47[$ch]}" ] || ok=0
done
docker logs "$C47" 2>&1 | grep -q "WARNING: backend DEFAULT: the scan found no services" || ok=0
[ -z "$(chfiles "$D47")" ] || { echo "channel files were left:"; chfiles "$D47"; ok=0; }
docker exec "$C47" pgrep -x EpgTimerSrv >/dev/null || { echo "EpgTimerSrv not running"; ok=0; }
docker exec "$C47" sh -c 'ls /usr/local/lib/edcb | grep -- -scan-' && { echo "temporary BonDriver left"; ok=0; }
if [ $ok = 1 ]; then result T47 "PASS ($((t1 - t0)) s)"; else result T47 FAIL; fi
docker rm -f "$C47" >/dev/null

# ---------------------------------------------------------------- T48 edcbctl status
section "T48 edcbctl status: recording state and the next reservation from EpgTimerSrv"
D48=$TMP/d48; mkdir -p "$D48/Setting"
# one reservation in Setting/Reserve.txt (the format of Common/ParseTextInstances.cpp)
printf '\xef\xbb\xbf2030/01/01\t20:00:00\t00:30:00\tIntegration test\tTest station\t32736\t32736\t1024\t65535\t2\t0\t1\t1\t0\t0\t0\tcomment\t\t0\t0\t\t0\t0\t0\t0\t2030/01/01\t20:00:00\t0\t0\t0\t0\t0\t0\t\n' \
  > "$D48/Setting/Reserve.txt"
chown -R 1000:1000 "$D48"
run "$C48" "$D48" --network "$NET" -e EDCB_CHSCAN=never -e EDCB_BACKEND_DEFAULT_URL=http://p4-a:40772
wait_log "$C48" "starting EpgTimerSrv" 90 || echo "!! no start message"
sleep 3
ok=1
docker exec "$C48" edcbctl status > "$TMP/t48" 2>&1; rc=$?
cat "$TMP/t48"; echo "(exit $rc)"
[ $rc = 0 ] || ok=0
grep -qx "recording: no" "$TMP/t48" || ok=0
grep -q "^next reservation: 2030-01-01 20:00 (in .*) Integration test (Test station)$" "$TMP/t48" || ok=0
grep -qx "reservations: 1 enabled, 0 disabled" "$TMP/t48" || ok=0
docker stop -t 120 "$C48" >/dev/null
docker run --rm -v "$D48:/var/local/edcb" --entrypoint edcbctl "$IMG" status > "$TMP/t48b" 2>&1; rc=$?
cat "$TMP/t48b"; echo "(exit $rc without EpgTimerSrv)"
[ $rc = 1 ] || ok=0
if [ $ok = 1 ]; then result T48 PASS; else result T48 FAIL; fi
docker rm -f "$C48" >/dev/null

# ---------------------------------------------------------------- T49 EPG capture after the scan
section "T49 after the first scan, EpgTimerSrv starts an EPG capture without waiting for 23:00"
D49=$TMP/d49; mkdir "$D49"
run "$C49" "$D49" --network "$NET" "${FAKESCAN[@]}" -e EDCB_BACKEND_DEFAULT_URL=http://p4-a:40772
wait_log "$C49" "starting EpgTimerSrv" 90 || echo "!! no start message"
ok=1
wait_log "$C49" "EPG capture requested" 60 || { echo "no EPG capture request"; ok=0; }
docker logs "$C49" 2>&1 | grep "EPG capture"
# EpgTimerSrv starts it about 10 s after the request; nothing else uses a tuner here
n=0
for _ in $(seq 40); do
  n=$(docker exec "$C49" pgrep -cx EpgDataCap_Bon)
  [ "$n" -gt 0 ] && break
  sleep 1
done
echo "EpgDataCap_Bon processes: $n"
docker exec "$C49" ps -o args= -C EpgDataCap_Bon
[ "$n" -gt 0 ] || ok=0
[ -e "$D49/.provision/epgcap-pending" ] && { echo "EPG capture still pending"; ok=0; }
if [ $ok = 1 ]; then result T49 PASS; else result T49 FAIL; fi
docker rm -f "$C49" >/dev/null
