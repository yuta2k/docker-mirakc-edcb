#!/bin/sh

# === setup BonDriver_LinuxMirakc ===

# write mirakc server settings to BonDriver_LinuxMirakc.so.ini
# due to BonDriver_LinuxMirakc can not resolve host name currently

# typo correction for under v1.0.4 compose.yml
if [ -z "$MIRAKC_ADDRESS" ] && [ -n "$MIRKAC_ADDRESS" ]; then MIRAKC_ADDRESS=$MIRKAC_ADDRESS; fi
if [ -z "$MIRAKC_PORT" ] && [ -n "$MIRKAC_PORT" ]; then MIRAKC_PORT=$MIRKAC_PORT; fi

MIRAKC_IP_ADDRESS=$(getent ahosts $MIRAKC_ADDRESS | sed -n 's/ *STREAM.*//p' | head -n 1)
if [ -z "$MIRAKC_IP_ADDRESS" ]; then
  echo "ERROR: Could not resolve IP address for mirakc server."
  exit 1
fi
if [ -z "$MIRAKC_PORT" ]; then
  echo "ERROR: MIRAKC_PORT is not set."
  exit 1
fi

sed -i "s/^SERVER_HOST=.*/SERVER_HOST=\"$MIRAKC_IP_ADDRESS\"/" /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini
sed -i "s/^SERVER_PORT=.*/SERVER_PORT=\"$MIRAKC_PORT\"/" /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini

# === end of setup BonDriver_LinuxMirakc ===


# clean old *.fifo files made by SrvPipe from the previous run
rm -f /var/local/edcb/*.fifo

if [ -n "$UMASK" ]; then umask $UMASK; fi

# first run or updated: copy EDCB_Material_WebUI to volume
cp -rn /usr/local/src/EDCB_Material_WebUI/Setting /var/local/edcb/
cp -ru /usr/local/src/EDCB_Material_WebUI/HttpPublic /var/local/edcb/

# first run or updated: setup EDCB ini files
(cd /usr/local/src/EDCB/Document/Unix && make -s setup_ini)

terminate_edcb() {
  # terminal EpgTimerSrv and all child processes such as EpgDataCap_Bon
  kill -TERM -$PGID
  pidwait -g $PGID > /dev/null 2>&1
}

# see: https://docs.docker.jp/engine/reference/builder.html#exec-entrypoint
trap terminate_edcb HUP INT QUIT TERM

setsid EpgTimerSrv &
SRV_PID=$!
PGID=$(ps -o pgid= -p $SRV_PID | tr -d ' ')

# wait for terminate_edcb() or unexpected exit EpgTimerSrv
wait $SRV_PID
