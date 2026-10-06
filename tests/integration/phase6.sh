# shellcheck shell=bash
# Phase 6: the documents. Runs the steps of Setup.md from an empty folder (T60)
# and the migration of docs/migration-v1-to-v2.md from a v1-like folder (T61)
# with Docker Compose, in the order the documents give them.
#
# What differs from the documents, and why:
# - The images are not built by Compose: a compose.test.yml (named in .env by
#   COMPOSE_FILE) points the services at $IMG and $MIRAKC_IMG, which T0 and T50
#   build. It also shortens the health check interval.
# - The host ports are $PORT_* on 127.0.0.1, set in .env with an address as
#   Setup.md describes (EDCB_HOST_HTTP_PORT=<address>:<port>).
# - Instead of cloning GitHub, the folder is a copy of the files tracked in this
#   repository (the working tree, so uncommitted changes are tested). For T61 a
#   local git repository with two commits stands in for the v1 checkout and v2.
# - The v1 containers run "sleep" in the test images; only their names, the
#   volume and "down" matter for the migration. Their names and the volume name
#   carry $PREFIX so that the real "edcb" / "mirakc" containers are never touched.
# - mirakc runs mirakc/config-sample.yml without tuners.
# shellcheck disable=SC2154  # IMG, MIRAKC_IMG, TMP, REPO, PREFIX and the ports are set by run.sh

P6SETUP=${PREFIX}-p6setup
P6MIGRATE=${PREFIX}-p6migrate

# repo_copy <dir>: the files tracked in the repository, from the working tree
repo_copy() {
  mkdir -p "$1"
  (cd "$REPO" && git -c safe.directory="$REPO" ls-files -z | tar --null -T - -cf -) | tar -xf - -C "$1"
}

# test_overlay <dir>: compose.test.yml and .env (see the header)
test_overlay() {
  cat > "$1/compose.test.yml" <<EOF
services:
  mirakc:
    image: $MIRAKC_IMG
    pull_policy: never
  edcb:
    image: $IMG
    pull_policy: never
    healthcheck:
      interval: 5s
      start_period: 60s
EOF
  cat > "$1/.env" <<EOF
COMPOSE_FILE=compose.yml:compose.override.yml:compose.test.yml
EDCB_HOST_HTTP_PORT=127.0.0.1:$PORT_HTTP
EDCB_HOST_TCP_PORT=127.0.0.1:$PORT_HTTP2
EOF
}

# dc <dir> <args...>: docker compose in <dir>
dc() { local d=$1; shift; (cd "$d" && docker compose "$@"); }

http_code() { curl -s -o /dev/null -w '%{http_code}' -m 10 "$@"; }

if ! docker compose version >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
  result T60 "SKIP docker compose or git is not available"
  result T61 "SKIP docker compose or git is not available"
  return 0
fi
if ! docker image inspect "$IMG" >/dev/null 2>&1 || ! docker image inspect "$MIRAKC_IMG" >/dev/null 2>&1; then
  result T60 "SKIP the edcb or mirakc test image is missing"
  result T61 "SKIP the edcb or mirakc test image is missing"
  return 0
fi
docker compose version

# ---------------------------------------------------------------- T60 Setup.md
section "T60 Setup.md: from an empty folder to EDCB with HTTPS"
D60=$TMP/$P6SETUP
repo_copy "$D60"
track_project "$P6SETUP"
track_volume "${P6SETUP}_mirakc-epg"
ok=1
# 最短の手順
cp "$D60/mirakc/config-sample.yml" "$D60/mirakc/config.yml"
cp "$D60/compose.override-sample.yml" "$D60/compose.override.yml"
test_overlay "$D60"
dc "$D60" config > "$TMP/t60-config.yml" || { echo "!! docker compose config failed"; ok=0; }
grep -q '^name: '"$P6SETUP"'$' "$TMP/t60-config.yml" || { echo "!! the project name is not the folder name"; ok=0; }
grep -n 'container_name' "$TMP/t60-config.yml" && { echo "!! a fixed container name"; ok=0; }
t0=$(date +%s)
dc "$D60" up -d || { echo "!! docker compose up failed"; ok=0; }
C60=${P6SETUP}-edcb-1
track "$C60"; track "${P6SETUP}-mirakc-1"
# the first start scans the one channel of the sample config (its tuner cannot open)
wait_health "$C60" healthy 400 || ok=0
echo "from docker compose up to healthy: $(($(date +%s) - t0)) s"
docker logs "$C60" 2>&1 | grep -E '^(entrypoint|provision):' | head -n 60
docker volume inspect "${P6SETUP}_mirakc-epg" >/dev/null 2>&1 || { echo "!! no volume ${P6SETUP}_mirakc-epg"; ok=0; }
for path in /E3/ /legacy/; do
  code=$(http_code "http://127.0.0.1:$PORT_HTTP$path")
  echo "GET $path -> $code"
  [ "$code" = 200 ] || ok=0
done
# 起動: edcbctl backends
dc "$D60" exec -T edcb edcbctl backends > "$TMP/t60-backends" 2>&1; rc=$?
cat "$TMP/t60-backends"; echo "(backends exit $rc)"
[ $rc = 0 ] || ok=0
grep -q '^DEFAULT: http://mirakc:40772 (reachable)$' "$TMP/t60-backends" || ok=0
# 初回に書かれる設定
for kv in 'HttpNumThreads=50' 'EnableTCPSrv=1' 'CompatFlags=4095' 'EnableHttpSrv=1'; do
  grep -qx "$kv" "$D60/edcb/ini/EpgTimerSrv.ini" || { echo "!! no $kv"; ok=0; }
done
# WebUI での設定: allow-setting
dc "$D60" exec -T edcb edcbctl allow-setting on || ok=0
dc "$D60" exec -T edcb edcbctl allow-setting status | tee "$TMP/t60-allow"
grep -q 'allowed' "$TMP/t60-allow" || ok=0
dc "$D60" exec -T edcb edcbctl allow-setting off || ok=0
# 更新: edcbctl status
dc "$D60" exec -T edcb edcbctl status || { echo "!! edcbctl status failed"; ok=0; }
dc "$D60" exec -T edcb edcbctl provision --diff || ok=0
# HTTPS: the certificate, the published port (here on 127.0.0.1) and docker compose up -d
openssl req -new -newkey rsa:2048 -nodes -x509 -days 1 -sha256 -subj /CN=edcb \
  -addext "subjectAltName = IP:127.0.0.1" -keyout "$TMP/t60-key.pem" -out "$TMP/t60-cert.pem" 2>/dev/null
cat "$TMP/t60-cert.pem" "$TMP/t60-key.pem" > "$D60/edcb/ini/ssl_cert.pem"
chown 1000:1000 "$D60/edcb/ini/ssl_cert.pem"
cat > "$D60/compose.test-https.yml" <<EOF
services:
  edcb:
    ports:
      - 127.0.0.1:$PORT_HTTPS:5511
EOF
sed -i 's/^COMPOSE_FILE=.*/&:compose.test-https.yml/' "$D60/.env"
since=$(date -u +%Y-%m-%dT%H:%M:%SZ); sleep 1
dc "$D60" up -d || ok=0
wait_log "$C60" "starting EpgTimerSrv as" 120 "$since" || ok=0
wait_health "$C60" healthy 120 || ok=0
grep -x 'HttpPort=5510,5520,5511s,5521s' "$D60/edcb/ini/EpgTimerSrv.ini" || { echo "!! HttpPort was not written"; ok=0; }
code=$(http_code -k "https://127.0.0.1:$PORT_HTTPS/E3/")
echo "GET https://.../E3/ -> $code"
[ "$code" = 200 ] || ok=0
dc "$D60" down -t 120 || ok=0
[ -z "$(docker ps -aq --filter "name=^/${P6SETUP}-")" ] || { echo "!! containers left after down"; ok=0; }
if [ $ok = 1 ]; then result T60 "PASS the steps of Setup.md, HTTPS included"; else result T60 FAIL; fi

# ---------------------------------------------------------------- T61 migration
section "T61 docs/migration-v1-to-v2.md: from a v1 folder with root-owned data to v2"
D61=$TMP/$P6MIGRATE
SRC61=$TMP/p6-src
V1VOL=${PREFIX}-v1_mirakc_epg
track_project "$P6MIGRATE"
track "${PREFIX}-v1-edcb"; track "${PREFIX}-v1-mirakc"
track_volume "$V1VOL"
track_volume "${P6MIGRATE}_mirakc-epg"
track "${P6MIGRATE}-edcb-1"; track "${P6MIGRATE}-mirakc-1"
ok=1
G=(git -c user.name=edcbtest -c user.email=edcbtest@example.invalid -c init.defaultBranch=main
  -c pull.ff=only -c advice.detachedHead=false)

# the "upstream": commit v1 (compose-sample.yml, no compose.yml) and commit v2 (this tree)
repo_copy "$SRC61"
mv "$SRC61/compose.yml" "$TMP/p6-compose.yml"
cp "$HERE/fixtures/v1-compose-sample.yml" "$SRC61/compose-sample.yml"
"${G[@]}" -C "$SRC61" init -q && "${G[@]}" -C "$SRC61" add -A && "${G[@]}" -C "$SRC61" commit -qm v1
rm "$SRC61/compose-sample.yml"; mv "$TMP/p6-compose.yml" "$SRC61/compose.yml"
"${G[@]}" -C "$SRC61" add -A && "${G[@]}" -C "$SRC61" commit -qm v2
# the user's v1 folder
"${G[@]}" clone -q "$SRC61" "$D61" && "${G[@]}" -C "$D61" reset -q --hard HEAD~1
python3 - "$D61/compose-sample.yml" "$D61/compose.yml" "$PREFIX" "$IMG" "$MIRAKC_IMG" "$PORT_HTTP" "$PORT_HTTP2" <<'EOF'
import sys
src, dst, prefix, img, mimg, http, tcp = sys.argv[1:]
s = open(src).read()
for old, new in (
    ("    container_name: mirakc\n",
     f"    container_name: {prefix}-v1-mirakc\n    image: {mimg}\n    entrypoint: [sleep, infinity]\n"),
    ("    container_name: edcb\n",
     f"    container_name: {prefix}-v1-edcb\n    image: {img}\n    entrypoint: [sleep, infinity]\n"),
    ("      - /dev/bus:/dev/bus\n", "      - /dev/null:/dev/v1-null\n"),
    ("      - 4510:4510\n", f"      - 127.0.0.1:{tcp}:4510\n"),
    ("      - 5510:5510\n", f"      - 127.0.0.1:{http}:5510\n"),
    ("    name: mirakc_epg\n", f"    name: {prefix}-v1_mirakc_epg\n"),
):
    assert s.count(old) == 1, old
    s = s.replace(old, new)
open(dst, "w").write(s)
EOF
cp "$D61/mirakc/config-sample.yml" "$D61/mirakc/config.yml"
# v1 data, owned by root (v1 without user:)
mkdir -p "$D61/edcb/ini/Setting"
if [ -n "$REAL_INI" ] && [ -f "$REAL_INI/Setting/ChSet5.txt" ] && compgen -G "$REAL_INI/Setting/*.ChSet4.txt" >/dev/null; then
  kind61="real data"
  cp "$REAL_INI"/*.ini "$D61/edcb/ini/"
  cp "$REAL_INI"/Setting/*.ChSet4.txt "$REAL_INI/Setting/ChSet5.txt" "$D61/edcb/ini/Setting/"
else
  kind61="synthetic data"
  printf '[SET]\nHttpAccessControlList=+127.0.0.1,+192.168.0.0/16\nSaveDebugLog=0\n\n[BonDriver_LinuxMirakc.so]\nCount=2\nGetEpg=1\nEPGCount=0\nPriority=0\n' \
    > "$D61/edcb/ini/EpgTimerSrv.ini"
  printf '[SET]\nSaveLogo=0\n' > "$D61/edcb/ini/EpgDataCap_Bon.ini"
  printf '\xef\xbb\xbfGR27\tGR Service A\tGR\t0\t0\t32736\t32736\t1024\t1\t0\t1\t1\n' \
    > "$D61/edcb/ini/Setting/BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt"
  printf '\xef\xbb\xbfGR Service A\tGR\t32736\t32736\t1024\t1\t0\t1\t1\n' > "$D61/edcb/ini/Setting/ChSet5.txt"
fi
# A v1 folder with HTTPS ports in HttpPort also has ssl_cert.pem; without it EDCB
# opens no HTTP port at all. Put a test certificate (the real key is not copied).
if grep -qiE '^[[:space:]]*HttpPort[[:space:]]*=.*[0-9]s' "$D61/edcb/ini/EpgTimerSrv.ini" 2>/dev/null; then
  echo "HttpPort has HTTPS ports: adding a test ssl_cert.pem"
  openssl req -new -newkey rsa:2048 -nodes -x509 -days 1 -sha256 -subj /CN=edcb \
    -keyout "$TMP/t61-key.pem" -out "$TMP/t61-cert.pem" 2>/dev/null
  cat "$TMP/t61-cert.pem" "$TMP/t61-key.pem" > "$D61/edcb/ini/ssl_cert.pem"
fi
# one reservation (the line of T48)
printf '\xef\xbb\xbf2030/01/01\t20:00:00\t00:30:00\tIntegration test\tTest station\t32736\t32736\t1024\t65535\t2\t0\t1\t1\t0\t0\t0\tcomment\t\t0\t0\t\t0\t0\t0\t0\t2030/01/01\t20:00:00\t0\t0\t0\t0\t0\t0\t\n' \
  > "$D61/edcb/ini/Setting/Reserve.txt"
chown -R 0:0 "$D61/edcb/ini"
echo "using $kind61"
dc "$D61" up -d || { echo "!! the v1 containers did not start"; ok=0; }
docker ps --filter "name=^/${PREFIX}-v1-" --format '{{.Names}} {{.Status}}'

# 1. 今の状態を控える
(cd "$D61" && git rev-parse HEAD > v1-commit.txt && docker compose config > v1-config.txt) || ok=0
echo "owner of edcb/ini: $(stat -c '%u:%g' "$D61/edcb/ini/EpgTimerSrv.ini")"
# 何が変わるか: git pull stops at the untracked compose.yml
if (cd "$D61" && "${G[@]}" pull -q) > "$TMP/t61-pull" 2>&1; then
  echo "!! git pull did not stop at compose.yml"; ok=0
else
  grep -A1 'untracked working tree files would be overwritten' "$TMP/t61-pull" | grep -q 'compose.yml' ||
    { cat "$TMP/t61-pull"; ok=0; }
fi
# 2. 退避する
mv "$D61/compose.yml" "$D61/compose.yml.v1"
cp -a "$D61/edcb/ini" "$D61/edcb/ini.v1-backup"
dc "$D61" -f compose.yml.v1 images || ok=0
# 3. 更新する
(cd "$D61" && git status --short && "${G[@]}" pull -q) || { echo "!! git pull failed"; ok=0; }
[ -f "$D61/compose.yml" ] && [ ! -e "$D61/compose-sample.yml" ] || { echo "!! not at v2"; ok=0; }
# 4. compose.override.yml と edcb.env を作る
cp "$D61/compose.override-sample.yml" "$D61/compose.override.yml"
cp "$D61/edcb.env-sample" "$D61/edcb.env"
mkdir -p "$D61/rec"
{
  echo "services:"
  if [ -e /dev/bus/usb ]; then
    printf '  mirakc:\n    devices:\n      - /dev/bus/usb:/dev/bus/usb\n'
  fi
  printf '  edcb:\n    volumes:\n      - ./rec:/recorded\n'
} > "$D61/compose.override.yml"
printf 'PUID=1000\nPGID=1000\n' >> "$D61/edcb.env"
test_overlay "$D61"
dc "$D61" config > "$TMP/t61-config.yml" || { echo "!! docker compose config failed"; ok=0; }
grep -n 'container_name' "$TMP/t61-config.yml" && { echo "!! a fixed container name"; ok=0; }
# 5. ビルドする: skipped (the test images are used)
# 6. v1 のコンテナを止めて削除する
dc "$D61" -f compose.yml.v1 down || ok=0
[ -z "$(docker ps -aq --filter "name=^/${PREFIX}-v1-")" ] || { echo "!! v1 containers left"; ok=0; }
# 7. 所有者を合わせる
chown -R 1000:1000 "$D61/edcb/ini" "$D61/rec"
# 8. 起動する
dc "$D61" up -d || ok=0
C61=${P6MIGRATE}-edcb-1
wait_health "$C61" healthy 300 || ok=0
docker logs "$C61" 2>&1 | grep -E '^(entrypoint|provision):' | head -n 60
docker logs "$C61" 2>&1 | grep -q 'not writable' && { echo "!! not writable"; ok=0; }
# ChSet5.txt exists: no scan
docker logs "$C61" 2>&1 | grep -q '^provision: chscan ' && { echo "!! a channel scan ran"; ok=0; }
if [ -e /dev/bus/usb ]; then
  docker logs "${P6MIGRATE}-mirakc-1" 2>&1 | grep -q 'WARNING: /dev/bus/usb' && { echo "!! the USB warning"; ok=0; }
fi
# 9. 動作を確かめる. The ACL of the v1 data is kept as it is, and it may not
# allow the Docker network that connections to the published port come from;
# so the WebUI is checked from inside the container (127.0.0.1), and the
# result through the published port is only shown.
for path in /E3/ /legacy/; do
  code=$(docker exec "$C61" python3 -c 'import sys, urllib.request
try:
    print(urllib.request.urlopen("http://127.0.0.1:5510" + sys.argv[1], timeout=10).status)
except Exception as e:
    print(getattr(e, "code", 0))' "$path")
  echo "GET $path in the container -> $code, through the published port -> $(http_code "http://127.0.0.1:$PORT_HTTP$path")"
  [ "$code" = 200 ] || ok=0
done
dc "$D61" exec -T edcb edcbctl backends || ok=0
dc "$D61" exec -T edcb edcbctl status > "$TMP/t61-status" 2>&1
cat "$TMP/t61-status"
grep -q '^next reservation: 2030-01-01 20:00 .*Integration test' "$TMP/t61-status" || ok=0
# 初回の起動で足されるもの: no existing key changed; the channel files are the same
python3 - "$D61/edcb/ini.v1-backup" "$D61/edcb/ini" <<'EOF' || ok=0
import glob, os, sys

def load(path):
    keys, sec = {}, None
    data = open(path, "rb").read()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    for line in data.decode("utf-8", "surrogateescape").splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            sec = s[1:-1].strip().lower()
        elif "=" in s and sec is not None:
            k, v = s.split("=", 1)
            keys.setdefault((sec, k.strip().lower()), v.strip())
    return keys

old, new = sys.argv[1:]
changed = added = 0
for p in sorted(glob.glob(os.path.join(old, "*.ini"))):
    rel = os.path.relpath(p, old)
    a, b = load(p), load(os.path.join(new, rel))
    for k, v in a.items():
        if b.get(k) != v:
            print(f"changed: {rel} [{k[0]}] {k[1]}: {v!r} -> {b.get(k)!r}")
            changed += 1
    for k in sorted(set(b) - set(a)):
        print(f"added: {rel} [{k[0]}] {k[1]}={b[k]}")
        added += 1
print(f"ini keys: {changed} changed, {added} added")
sys.exit(1 if changed else 0)
EOF
for f in "$D61"/edcb/ini.v1-backup/Setting/*.ChSet4.txt "$D61/edcb/ini.v1-backup/Setting/ChSet5.txt"; do
  cmp -s "$f" "$D61/edcb/ini/Setting/$(basename "$f")" || { echo "!! changed: $(basename "$f")"; ok=0; }
done
docker ps --filter "name=^/${P6MIGRATE}-" --format '{{.Names}}' | grep -qx "$C61" || ok=0
docker volume inspect "${P6MIGRATE}_mirakc-epg" >/dev/null 2>&1 || { echo "!! no new volume"; ok=0; }
# 10. 片付ける
docker volume rm "$V1VOL" >/dev/null || { echo "!! cannot remove $V1VOL"; ok=0; }
dc "$D61" down -t 120 || ok=0
if [ $ok = 1 ]; then result T61 "PASS ($kind61)"; else result T61 "FAIL ($kind61)"; fi
