# shellcheck shell=bash
# Phase 5: the mirakc container (bundled or host pcscd), the sample image for
# Intel hardware encoding and edcbctl prune. Sourced by run.sh after phase4.sh;
# T58 uses the test network ($NET), fake() of phase3.sh and $FAKESCAN of phase4.sh.
# No tuner, card reader or GPU is needed: only what the containers start is checked.
# shellcheck disable=SC2154  # IMG, TMP, REPO, NET, FAKESCAN etc. are set by run.sh / phase3.sh / phase4.sh

C51=$(cname 51); C52=$(cname 52); C53=$(cname 53); C54=$(cname 54); C57=$(cname 57)
C58=$(cname 58); P5A=$(cname p5-a); P5B=$(cname p5-b)

# the mirakc config: the sample (its tuner command is never run; mirakc starts without tuners in use)
MCONF=$TMP/mirakc-config.yml
cp "$REPO/mirakc/config-sample.yml" "$MCONF"

# mirakc_run <name> [docker run options...]: start the mirakc test image as compose does (init: true)
mirakc_run() {
  local name=$1; shift
  track "$name"
  docker run -d --name "$name" --init -e RUST_LOG=info \
    -v "$MCONF:/etc/mirakc/config.yml:ro" --tmpfs /var/lib/mirakc/epg "$@" "$MIRAKC_IMG" >/dev/null
}
# npcscd <container>: number of pcscd processes
# shellcheck disable=SC2016  # expands inside the container
npcscd() { docker exec "$1" sh -c 'cat /proc/[0-9]*/comm 2>/dev/null' | grep -cx pcscd; }
# nmirakc <container>: number of mirakc processes
# shellcheck disable=SC2016
nmirakc() { docker exec "$1" sh -c 'cat /proc/[0-9]*/comm 2>/dev/null' | grep -cx mirakc; }

# ---------------------------------------------------------------- T50 mirakc image
section "T50 the mirakc image builds"
if [ "$SKIP_BUILD" = 1 ] && docker image inspect "$MIRAKC_IMG" >/dev/null 2>&1; then
  result T50 "SKIP build skipped and $MIRAKC_IMG exists"
elif docker build -t "$MIRAKC_IMG" "$REPO/mirakc" > "$TMP/mirakc-build.log" 2>&1; then
  tail -n 5 "$TMP/mirakc-build.log"
  result T50 "PASS docker build mirakc/"
else
  tail -n 40 "$TMP/mirakc-build.log"
  result T50 "FAIL docker build mirakc/"
fi
if ! docker image inspect "$MIRAKC_IMG" >/dev/null 2>&1; then
  for t in T51 T52 T53 T54 T55; do result "$t" "SKIP no mirakc image"; done
else
  docker run --rm --entrypoint sh "$MIRAKC_IMG" -c 'mirakc --version; pcscd --version | head -n 1; grep PRETTY /etc/os-release'

  # ---------------------------------------------------------------- T51 bundled pcscd
  section "T51 without a socket, the bundled pcscd starts"
  mirakc_run "$C51"
  wait_log "$C51" "entrypoint: starting the bundled pcscd" 30 || echo "!! no entrypoint message"
  sleep 3
  docker logs "$C51" 2>&1 | head -n 8
  n=$(npcscd "$C51"); m=$(nmirakc "$C51")
  echo "pcscd: $n, mirakc: $m"
  if [ "$n" = 1 ] && [ "$m" = 1 ] && docker logs "$C51" 2>&1 | grep -q "starting the bundled pcscd (pcsc-lite [0-9]"; then
    result T51 "PASS pcscd and mirakc run; the log names the bundled pcscd and its version"
  else
    result T51 "FAIL pcscd=$n mirakc=$m"
  fi

  # ---------------------------------------------------------------- T52 host socket
  section "T52 with a socket mounted at /run/pcscd/pcscd.comm, the bundled pcscd does not start"
  python3 -c 'import socket, sys; socket.socket(socket.AF_UNIX).bind(sys.argv[1])' "$TMP/pcscd.comm"
  mirakc_run "$C52" -v "$TMP/pcscd.comm:/run/pcscd/pcscd.comm"
  wait_log "$C52" "entrypoint: " 30 || echo "!! no entrypoint message"
  sleep 3
  docker logs "$C52" 2>&1 | head -n 4
  n=$(npcscd "$C52"); m=$(nmirakc "$C52")
  echo "pcscd: $n, mirakc: $m"
  if [ "$n" = 0 ] && [ "$m" = 1 ] && docker logs "$C52" 2>&1 | grep -q "is mounted: using the host's pcscd"; then
    result T52 "PASS no pcscd; mirakc runs; the log says the host's pcscd is used"
  else
    result T52 "FAIL pcscd=$n mirakc=$m"
  fi

  # ---------------------------------------------------------------- T53 DISABLE_PCSCD
  section "T53 DISABLE_PCSCD=1: the bundled pcscd does not start"
  mirakc_run "$C53" -e DISABLE_PCSCD=1
  wait_log "$C53" "entrypoint: " 30 || echo "!! no entrypoint message"
  sleep 3
  docker logs "$C53" 2>&1 | head -n 4
  n=$(npcscd "$C53"); m=$(nmirakc "$C53")
  echo "pcscd: $n, mirakc: $m"
  if [ "$n" = 0 ] && [ "$m" = 1 ] && docker logs "$C53" 2>&1 | grep -q "DISABLE_PCSCD=1"; then
    result T53 "PASS no pcscd; mirakc runs"
  else
    result T53 "FAIL pcscd=$n mirakc=$m"
  fi

  # ---------------------------------------------------------------- T54 docker stop
  section "T54 docker stop ends mirakc quickly"
  ok=1
  for c in "$C51" "$C52"; do
    t0=$(date +%s.%N)
    docker stop -t 10 "$c" >/dev/null
    t1=$(date +%s.%N)
    secs=$(python3 -c "print(f'{$t1 - $t0:.1f}')")
    code=$(docker inspect -f '{{.State.ExitCode}}' "$c")
    echo "$c: stopped in $secs s, exit code $code"
    python3 -c "import sys; sys.exit(0 if $t1 - $t0 < 8 else 1)" || ok=0
  done
  # without --init (the entrypoint execs mirakc, which is then PID 1)
  track "$C54"
  docker run -d --name "$C54" -e RUST_LOG=info -v "$MCONF:/etc/mirakc/config.yml:ro" \
    --tmpfs /var/lib/mirakc/epg "$MIRAKC_IMG" >/dev/null
  sleep 5
  t0=$(date +%s.%N); docker stop -t 10 "$C54" >/dev/null; t1=$(date +%s.%N)
  secs=$(python3 -c "print(f'{$t1 - $t0:.1f}')")
  echo "$C54 (no --init): stopped in $secs s, exit code $(docker inspect -f '{{.State.ExitCode}}' "$C54")"
  python3 -c "import sys; sys.exit(0 if $t1 - $t0 < 8 else 1)" || ok=0
  if [ "$ok" = 1 ]; then
    result T54 "PASS every container stopped well within the 10 s timeout"
  else
    result T54 "FAIL a container took the timeout"
  fi

  # ---------------------------------------------------------------- T55 restart
  section "T55 docker restart: the socket left by the bundled pcscd does not count as the host's"
  since=$(date +%s)
  docker start "$C51" >/dev/null
  wait_log "$C51" "entrypoint: " 30 "$since" || echo "!! no entrypoint message"
  sleep 3
  docker logs --since "$since" "$C51" 2>&1 | head -n 4
  n=$(npcscd "$C51"); m=$(nmirakc "$C51")
  echo "pcscd: $n, mirakc: $m"
  if [ "$n" = 1 ] && [ "$m" = 1 ] && docker logs --since "$since" "$C51" 2>&1 | grep -q "starting the bundled pcscd"; then
    result T55 "PASS the bundled pcscd starts again"
  else
    result T55 "FAIL pcscd=$n mirakc=$m"
  fi
fi

# ---------------------------------------------------------------- T56 compose without mirakc
section "T56 compose.override.yml with mirakc disabled: only edcb is started"
if ! docker compose version >/dev/null 2>&1; then
  result T56 "SKIP docker compose is not available"
else
D56=$TMP/d56; mkdir "$D56"
cp "$REPO/compose.yml" "$D56/"
printf 'services:\n  mirakc:\n    profiles: [disabled]\n' > "$D56/compose.override.yml"
services=$(cd "$D56" && env -u COMPOSE_PROJECT_NAME -u COMPOSE_FILE docker compose config --services 2>&1)
echo "services: $services"
if [ "$services" = edcb ]; then
  result T56 "PASS docker compose config succeeds and lists edcb only"
else
  result T56 "FAIL got: $services"
fi
fi

# ---------------------------------------------------------------- T57 hwaccel sample
section "T57 the sample image for Intel hardware encoding"
arch=$(docker image inspect -f '{{.Architecture}}' "$IMG")
if [ "$arch" != amd64 ]; then
  result T57 "SKIP the sample is amd64 only (image: $arch)"
else
  qsv=${EDCBTEST_QSVENCC_VERSION:-}
  if [ -z "$qsv" ]; then
    qsv=$(curl -fsSL https://api.github.com/repos/rigaya/QSVEnc/releases/latest |
      python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])' 2>/dev/null)
  fi
  echo "QSVEncC: ${qsv:-unknown}"
  ok=1
  for v in "" "$qsv"; do
    tag=$IMG-hwaccel${v:+-qsvencc}
    if ! docker build -t "$tag" --build-arg BASE_IMAGE="$IMG" --build-arg QSVENCC_VERSION="$v" \
      "$REPO/edcb/hwaccel/intel" > "$TMP/hw-build.log" 2>&1; then
      tail -n 30 "$TMP/hw-build.log"; echo "!! build failed (QSVENCC_VERSION='$v')"; ok=0; continue
    fi
    enc=$(docker run --rm --entrypoint ffmpeg "$tag" -hide_banner -encoders 2>&1 | grep -E ' h264_(qsv|vaapi) ')
    echo "$tag: $enc" | tr '\n' ' '; echo
    [ "$(printf '%s\n' "$enc" | grep -c .)" = 2 ] || { echo "!! h264_qsv / h264_vaapi missing"; ok=0; }
    docker run --rm --entrypoint sh "$tag" -c 'command -v vainfo' >/dev/null || { echo "!! no vainfo"; ok=0; }
    if [ -n "$v" ]; then
      docker run --rm --entrypoint qsvencc "$tag" --version 2>&1 | head -n 3
      docker run --rm --entrypoint qsvencc "$tag" --version >/dev/null 2>&1 || { echo "!! qsvencc --version failed"; ok=0; }
    fi
    [ -z "$qsv" ] && break
  done
  [ -n "$qsv" ] || { echo "!! the latest QSVEncC release is unknown; set EDCBTEST_QSVENCC_VERSION"; ok=0; }
  # EpgTimerSrv starts from the sample image as from the base image
  D57=$TMP/d57; mkdir "$D57"
  IMG=$IMG-hwaccel run "$C57" "$D57"
  wait_log "$C57" "starting EpgTimerSrv" 60 || echo "!! no start message"
  wait_health "$C57" healthy 90 || ok=0
  if [ "$ok" = 1 ]; then
    result T57 "PASS builds without and with QSVEncC $qsv; h264_qsv, h264_vaapi, vainfo, qsvencc; EpgTimerSrv healthy"
  else
    result T57 "FAIL see above"
  fi
fi

# ---------------------------------------------------------------- T58 prune
section "T58 a removed backend: kept and reported on start, removed by edcbctl prune"
fake "$P5A" p5-a mixed
fake "$P5B" p5-b split
sleep 2
D58=$TMP/d58; mkdir "$D58"
# the files prune may change (not the logs, nor epgcap-pending, which the start removes in the background)
t58_sums() {
  (cd "$D58" && sha256sum EpgTimerSrv.ini Setting/*.ChSet4.txt Setting/ChSet5.txt \
    .provision/state.json .provision/backend-*.json .provision/scan-*.ChSet4.txt 2>/dev/null)
}
run "$C58" "$D58" --network "$NET" "${FAKESCAN[@]}" \
  -e EDCB_BACKEND_DEFAULT_URL=http://p5-a:40772 -e EDCB_BACKEND_VM_URL=http://p5-b:40772
wait_log "$C58" "starting EpgTimerSrv" 120 || echo "!! no start message"
docker rm -f "$C58" >/dev/null
# the same volume without backend VM
run "$C58" "$D58" --network "$NET" "${FAKESCAN[@]}" -e EDCB_BACKEND_DEFAULT_URL=http://p5-a:40772
wait_log "$C58" "starting EpgTimerSrv" 60 || echo "!! no start message"
sleep 2
ok=1
docker logs "$C58" 2>&1 | grep -E "prune|delete /usr/local/lib/edcb" | tee "$TMP/t58-start"
grep -q "edcbctl prune --diff" "$TMP/t58-start" || { echo "!! no hint on start"; ok=0; }
vm="$D58/Setting/BonDriver_LinuxMirakc_VM_T(LinuxMirakc).ChSet4.txt"
[ -f "$vm" ] || { echo "!! the ChSet4 of VM was removed on start"; ok=0; }
grep -qi '^\[BonDriver_LinuxMirakc_VM_T.so\]' "$D58/EpgTimerSrv.ini" || { echo "!! the section was removed on start"; ok=0; }
before=$(t58_sums)
chset5=$(sha256sum < "$D58/Setting/ChSet5.txt")
docker exec "$C58" edcbctl prune --diff > "$TMP/t58-diff" 2>&1; rc=$?
cat "$TMP/t58-diff"
after=$(t58_sums)
[ "$rc" = 0 ] && [ "$before" = "$after" ] || { echo "!! --diff exited $rc or changed files"; ok=0; }
grep -q "remove section \[BonDriver_LinuxMirakc_VM_T.so\]" "$TMP/t58-diff" || ok=0
docker exec "$C58" edcbctl prune > "$TMP/t58-prune" 2>&1; rc=$?
cat "$TMP/t58-prune"
[ "$rc" = 0 ] || { echo "!! prune exited $rc"; ok=0; }
grep -q "docker compose restart edcb" "$TMP/t58-prune" || { echo "!! no restart hint"; ok=0; }
[ ! -e "$vm" ] || { echo "!! the ChSet4 of VM is still there"; ok=0; }
grep -qi '^\[BonDriver_LinuxMirakc_VM' "$D58/EpgTimerSrv.ini" && { echo "!! a section of VM is still there"; ok=0; }
compgen -G "$D58/.provision/*-VM.*" && { echo "!! .provision files of VM are still there"; ok=0; }
[ "$(sha256sum < "$D58/Setting/ChSet5.txt")" = "$chset5" ] || { echo "!! ChSet5 changed"; ok=0; }
sed -n '/^\[TVTEST\]/,/^\[/p' "$D58/EpgTimerSrv.ini"
since=$(date +%s)
docker restart "$C58" >/dev/null
wait_log "$C58" "starting EpgTimerSrv" 60 "$since" || echo "!! no start message after the restart"
if docker logs --since "$since" "$C58" 2>&1 | grep "prune"; then
  echo "!! still reported after prune"; ok=0
fi
if [ "$ok" = 1 ]; then
  result T58 "PASS kept on start with a hint; --diff changes nothing; prune removes ChSet4, sections, viewing rows and .provision files; ChSet5 kept; no hint afterwards"
else
  result T58 "FAIL see above"
fi
