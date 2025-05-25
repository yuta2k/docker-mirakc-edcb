#!/bin/sh

# write mirakc server settings to BonDriver_LinuxMirakc.so.ini
# due to BonDriver_LinuxMirakc can not resolve host name currently
MIRAKC_IP_ADDRESS=$(getent hosts $MIRAKC_ADDRESS | awk '{ print $1 }')
sed -i "s/^SERVER_HOST=.*/SERVER_HOST=\"$MIRAKC_IP_ADDRESS\"/" /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini
sed -i "s/^SERVER_PORT=.*/SERVER_PORT=\"$MIRAKC_PORT\"/" /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini

# clean old *.fifo files made by SrvPipe from the previous run
rm -f /var/local/edcb/*.fifo

if [ -n "$UMASK" ]; then
  umask $UMASK
fi

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
