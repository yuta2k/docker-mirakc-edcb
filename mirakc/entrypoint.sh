#!/bin/sh
# Start pcscd in the container unless the host's pcscd is used, then mirakc.
#
# The bundled pcscd is not started when
# - DISABLE_PCSCD=1 (the same variable as Mirakurun's image), or
# - the host's pcscd socket is mounted at /run/pcscd/pcscd.comm (the socket
#   itself or the /run/pcscd directory).
#
# A socket that is not mounted is left over from an earlier run of this
# container (docker restart keeps the file system) and is removed.
set -eu

SOCKET_DIR=/run/pcscd
SOCKET=$SOCKET_DIR/pcscd.comm

log() {
  echo "entrypoint: $*"
}

# is_mounted <path>: a mount point in this container (the 5th field of mountinfo)
is_mounted() {
  awk -v p="$1" '$5 == p { found = 1 } END { exit !found }' /proc/self/mountinfo
}

pcscd_version() {
  pcscd --version 2>/dev/null | sed -n 's/.*version \([0-9][0-9.]*\).*/\1/p' | head -n 1
}

if [ "${DISABLE_PCSCD:-}" = 1 ]; then
  log "DISABLE_PCSCD=1: the bundled pcscd is not started"
elif is_mounted "$SOCKET" || is_mounted "$SOCKET_DIR"; then
  if [ -S "$SOCKET" ]; then
    log "$SOCKET is mounted: using the host's pcscd (pcsc-lite in this image: $(pcscd_version))"
  else
    # starting our own pcscd would put its socket into the host's directory
    log "WARNING: $SOCKET_DIR is mounted, but $SOCKET is not a socket; is pcscd running on the host?" \
      "The bundled pcscd is not started, so the card reader is not available."
  fi
else
  log "starting the bundled pcscd (pcsc-lite $(pcscd_version))"
  # compose.yml passes no devices: the card reader comes from compose.override.yml
  if [ ! -d /dev/bus/usb ]; then
    log "WARNING: /dev/bus/usb is not available, so the bundled pcscd sees no USB card reader" \
      "and decoding (decode=1) fails. Add /dev/bus/usb:/dev/bus/usb to the devices of mirakc" \
      "in compose.override.yml, mount the host's /run/pcscd/pcscd.comm, or set DISABLE_PCSCD=1."
  fi
  # left over from an earlier run: pcscd refuses to start if the old PID is in use
  rm -f "$SOCKET" "$SOCKET_DIR/pcscd.pid"
  # Debian's pcscd is built with polkit, and without polkitd/D-Bus in the container
  # it refuses every client, root included: arib-b25-stream-test fails with
  # "B_CAS_CARD::init() : code=-3" and mirakc answers 404 to decode=1 streams
  pcscd --disable-polkit
fi

exec /usr/local/bin/mirakc "$@"
