#!/bin/bash

if [ "$1" != "true" ] && [ "$1" != "false" ]; then
  echo "Usage: chlegacyset.sh <true|false>"
  exit 1
fi

docker compose exec edcb sed -i "s/ALLOW_SETTING=.*/ALLOW_SETTING=$1/" /var/local/edcb/HttpPublic/legacy/util.lua
