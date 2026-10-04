ARG ARCH=

# Upstream sources. These defaults are the only place where the versions are pinned.
# Each *_COMMIT must be a full SHA-1; the build fails if the fetched source is not at that commit.
ARG EDCB_REPO=https://github.com/xtne6f/EDCB.git
ARG EDCB_REF=work-plus-s-260904
ARG EDCB_COMMIT=ebf50c730ccf8c1732e0bd8a4e2a3417a94d9b2b
ARG BON_DRIVER_REPO=https://github.com/matching/BonDriver_LinuxMirakc.git
ARG BON_DRIVER_COMMIT=cfbefc6d21dab4009db5f124984c1b720b76d869
ARG EMWUI_REPO=https://github.com/EMWUI/EDCB_Material_WebUI.git
ARG EMWUI_COMMIT=4e5b5c865a481cc8f443d6d468ee9571a8bfcf20
ARG LUA_REPO=https://github.com/xtne6f/lua.git
ARG LUA_COMMIT=00e941f334ea08557a8c0c428203456387d54eb3
ARG LUA_ZLIB_REPO=https://github.com/xtne6f/lua-zlib.git
ARG LUA_ZLIB_COMMIT=dc3ea17156ad727398ab39501d3cd03e32324165

# default of Prealloc in Write_Default.so.ini (see edcb/patches/edcb/0001-*.patch)
# 0: no preallocation, 1: preallocate (upstream behavior), 2: no preallocation on btrfs
ARG EDCB_PREALLOC_DEFAULT=2

FROM ${ARCH}ubuntu:24.04 AS build
# ARGs declared before FROM are only visible in FROM lines; redeclare to use them in this stage
ARG EDCB_REPO
ARG EDCB_REF
ARG EDCB_COMMIT
ARG BON_DRIVER_REPO
ARG BON_DRIVER_COMMIT
ARG EMWUI_REPO
ARG EMWUI_COMMIT
ARG LUA_REPO
ARG LUA_COMMIT
ARG LUA_ZLIB_REPO
ARG LUA_ZLIB_COMMIT
ARG EDCB_PREALLOC_DEFAULT
WORKDIR /app

RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    # used by "make extra" to download the extra tools
    curl \
    build-essential \
    # EDCB dependencies
    liblua5.2-dev \
    lua-zlib

COPY --chmod=755 build/fetch-source.sh /usr/local/bin/fetch-source

# BonDriver_LinuxMirakc
RUN fetch-source "$BON_DRIVER_REPO" "" "$BON_DRIVER_COMMIT" BonDriver_LinuxMirakc && \
  cd BonDriver_LinuxMirakc && \
  make

# EDCB_Material_WebUI
RUN fetch-source "$EMWUI_REPO" "" "$EMWUI_COMMIT" EDCB_Material_WebUI

# Lua modules for EDCB
RUN fetch-source "$LUA_REPO" "" "$LUA_COMMIT" lua && \
  (cd lua && make liblua5.2.so) && \
  fetch-source "$LUA_ZLIB_REPO" "" "$LUA_ZLIB_COMMIT" lua-zlib && \
  (cd lua-zlib && make libzlib52.so)

# EDCB
# apply edcb/patches/edcb/*.patch in order (see each patch for details)
# --keep-cr: EDCB sources use CRLF line endings, which git am strips by default
COPY patches/edcb/ /app/edcb-patches/
RUN case "$EDCB_PREALLOC_DEFAULT" in 0|1|2) ;; \
    *) echo "EDCB_PREALLOC_DEFAULT must be 0, 1 or 2" >&2; exit 1 ;; \
  esac && \
  fetch-source "$EDCB_REPO" "$EDCB_REF" "$EDCB_COMMIT" EDCB && \
  cd EDCB && \
  set -- /app/edcb-patches/*.patch && \
  if [ ! -f "$1" ]; then echo "no patches found in /app/edcb-patches" >&2; exit 1; fi && \
  git -c user.name=docker-mirakc-edcb -c user.email=docker-mirakc-edcb@localhost \
    am --3way --keep-cr "$@" && \
  echo "Applied $# patch(es) on top of $EDCB_COMMIT:" && \
  git log --oneline "$EDCB_COMMIT..HEAD" && \
  cd Document/Unix && \
  CPPFLAGS="-DWRITE_DEFAULT_PREALLOC_DEFAULT=$EDCB_PREALLOC_DEFAULT" make && \
  make extra

# WebUI files installed into the volume at start-up (see edcb_provision/httppublic.py):
# the files "make setup_ini" would copy from EDCB, and EMWUI.
# legacy/util.lua is patched so that "edcbctl allow-setting" works without a restart.
COPY --chmod=755 build/patch-legacy-util.sh /usr/local/bin/patch-legacy-util
RUN mkdir -p /app/share/HttpPublic /app/share/Setting && \
  cp -R EDCB/ini/HttpPublic/index.html EDCB/ini/HttpPublic/favicon.ico EDCB/ini/HttpPublic/legacy \
    /app/share/HttpPublic/ && \
  cp -R EDCB_Material_WebUI/HttpPublic/. /app/share/HttpPublic/ && \
  cp -R EDCB_Material_WebUI/Setting/. /app/share/Setting/ && \
  patch-legacy-util /app/share/HttpPublic/legacy/util.lua

FROM ${ARCH}ubuntu:24.04
ARG EDCB_REPO
ARG EDCB_REF
ARG EDCB_COMMIT
ARG BON_DRIVER_REPO
ARG BON_DRIVER_COMMIT
ARG EMWUI_REPO
ARG EMWUI_COMMIT

# upstream versions this image was built from
LABEL io.github.yuta2k.docker-mirakc-edcb.edcb.repo="$EDCB_REPO" \
  io.github.yuta2k.docker-mirakc-edcb.edcb.ref="$EDCB_REF" \
  io.github.yuta2k.docker-mirakc-edcb.edcb.commit="$EDCB_COMMIT" \
  io.github.yuta2k.docker-mirakc-edcb.bondriver.repo="$BON_DRIVER_REPO" \
  io.github.yuta2k.docker-mirakc-edcb.bondriver.commit="$BON_DRIVER_COMMIT" \
  io.github.yuta2k.docker-mirakc-edcb.emwui.repo="$EMWUI_REPO" \
  io.github.yuta2k.docker-mirakc-edcb.emwui.commit="$EMWUI_COMMIT"

ENV TZ=Asia/Tokyo

# WebUI files and EMWUI's initial Setting/ files (copied into the volume on start-up)
COPY --from=build /app/share /usr/local/share/edcb

# copy Lua modules for EDCB
RUN mkdir -p /usr/local/lib/lua/5.2
COPY --from=build /app/lua/liblua5.2.so /usr/local/lib/liblua5.2.so
COPY --from=build /app/lua-zlib/libzlib52.so /usr/local/lib/lua/5.2/libzlib52.so
RUN ldconfig

COPY --from=build /app/EDCB /usr/local/src/EDCB
RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y --no-install-recommends \
    make \
    liblua5.2-0 \
    ffmpeg \
    # provisioning (edcbctl), health check
    python3 \
    # ps and pidwait in the entrypoint
    procps \
    tzdata && \
\
  # install EDCB
  ( \
    cd /usr/local/src/EDCB/Document/Unix && \
    make install && \
    make install_extra \
  ) && \
\
#   # install Intel Media Driver
#   # https://dgpu-docs.intel.com/driver/client/overview.html#installing-client-gpus-on-ubuntu-desktop-24-04-lts
#   INTEL_MEDIA_DRIVER_DEPENDENCIES="gnupg ca-certificates wget" && \
#   apt-get install -y --no-install-recommends $INTEL_MEDIA_DRIVER_DEPENDENCIES && \
#   wget -qO - https://repositories.intel.com/gpu/intel-graphics.key | \
#     gpg --yes --dearmor --output /usr/share/keyrings/intel-graphics.gpg && \
#   echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu noble unified" | \
#     tee /etc/apt/sources.list.d/intel-gpu-noble.list && \
#   apt-get update && \
#   apt-get install -y --no-install-recommends libva-dev libmfx-dev intel-media-va-driver-non-free && \
#   # install QSVEncC
#   wget https://github.com/rigaya/QSVEnc/releases/download/7.82/qsvencc_7.82_Ubuntu24.04_amd64.deb && \
#   apt-get install -y ./qsvencc_7.82_Ubuntu24.04_amd64.deb && \
#   rm qsvencc_7.82_Ubuntu24.04_amd64.deb && \
#   apt-get remove -y $INTEL_MEDIA_DRIVER_DEPENDENCIES && \
# \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

# setup BonDriver_LinuxMirakc
# after created /usr/local/lib/edcb/ by EDCB installation
COPY --from=build /app/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so /usr/local/lib/edcb/BonDriver_LinuxMirakc.so
COPY --from=build /app/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini_sample /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini
# (written by the entrypoint, which runs as root)
RUN ln -s /usr/local/lib/edcb/BonDriver_LinuxMirakc.so /usr/local/lib/edcb/BonDriver_LinuxMirakc_S.so && \
  ln -s /usr/local/lib/edcb/BonDriver_LinuxMirakc.so /usr/local/lib/edcb/BonDriver_LinuxMirakc_T.so && \
  ln -s /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini /usr/local/lib/edcb/BonDriver_LinuxMirakc.so.ini && \
  ln -s /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini /usr/local/lib/edcb/BonDriver_LinuxMirakc_S.so.ini && \
  ln -s /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini /usr/local/lib/edcb/BonDriver_LinuxMirakc_T.so.ini

# entrypoint, edcbctl and the provisioning (Python, standard library only)
COPY rootfs/ /
RUN python3 -m compileall -q /usr/local/lib/edcb-provision

# EpgTimerSrv is running; if HTTP is enabled, the first HttpPort accepts connections
HEALTHCHECK --interval=1m --timeout=15s --start-period=2m --retries=3 \
  CMD ["env", "PYTHONPATH=/usr/local/lib/edcb-provision", "python3", "-m", "edcb_provision.healthcheck"]

# 4510: TCP (EpgTimerNW etc.), 5510: HTTP, 5511: HTTPS, 5520 / 5521: EMWUI's SSE (HTTP / HTTPS)
EXPOSE 4510 5510 5511 5520 5521
ENTRYPOINT ["/entrypoint.sh"]
