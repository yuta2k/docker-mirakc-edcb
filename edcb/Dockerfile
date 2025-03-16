ARG ARCH=
ARG EDCB_CHECKOUT=
ARG BON_DRIVER_CHECKOUT=
ARG EMWUI_CHECKOUT=

FROM ${ARCH}ubuntu:24.04 AS build
WORKDIR /app

RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    curl \
    build-essential \
    # EDCB dependencies
    liblua5.2-dev \
    lua-zlib

# BonDriver_LinuxMirakc
RUN git clone https://github.com/matching/BonDriver_LinuxMirakc.git --recurse-submodules && \
  cd BonDriver_LinuxMirakc && \
  if [ -n "$BON_DRIVER_CHECKOUT" ]; then git checkout $BON_DRIVER_CHECKOUT; fi && \
  make

# EDCB_Material_WebUI
RUN git clone https://github.com/EMWUI/EDCB_Material_WebUI.git && \
  cd EDCB_Material_WebUI && \
  if [ -n "$EMWUI_CHECKOUT" ]; then git checkout $EMWUI_CHECKOUT; fi

# Lua modules for EDCB
RUN curl -L https://github.com/xtne6f/lua/archive/refs/heads/v5.2-luabinaries.tar.gz | tar xz && \
  (cd lua-5.2-luabinaries && make liblua5.2.so) && \
  curl -L https://github.com/xtne6f/lua-zlib/archive/refs/heads/v0.5-lua52.tar.gz | tar xz && \
  (cd lua-zlib-0.5-lua52 && make libzlib52.so)

# EDCB
RUN git clone https://github.com/tkntrec/EDCB.git && \
  cd EDCB && \
  if [ -n "$EDCB_CHECKOUT" ]; then git checkout $EDCB_CHECKOUT; fi && \
  cd Document/Unix && \
  make && \
  make extra


FROM ${ARCH}ubuntu:24.04

ENV MIRKAC_ADDRESS=
ENV MIRAKC_PORT=
ENV UMASK=

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# copy EDCB_Material_WebUI
# (setup on entrypoint.sh)
COPY --from=build /app/EDCB_Material_WebUI /usr/local/src/EDCB_Material_WebUI

# copy Lua modules for EDCB
RUN mkdir -p /usr/local/lib/lua/5.2
COPY --from=build /app/lua-5.2-luabinaries/liblua5.2.so /usr/local/lib/liblua5.2.so
COPY --from=build /app/lua-zlib-0.5-lua52/libzlib52.so /usr/local/lib/lua/5.2/libzlib52.so
RUN ldconfig

COPY --from=build /app/EDCB /usr/local/src/EDCB
RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y --no-install-recommends \
    make \
    liblua5.2-0 \
    ffmpeg && \
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
RUN ln -s /usr/local/lib/edcb/BonDriver_LinuxMirakc.so /usr/local/lib/edcb/BonDriver_LinuxMirakc_S.so && \
  ln -s /usr/local/lib/edcb/BonDriver_LinuxMirakc.so /usr/local/lib/edcb/BonDriver_LinuxMirakc_T.so && \
  # allow generate sed temporary file by other user (on entrypoint.sh)
  chmod 777 /var/local/BonDriver_LinuxMirakc && \
  chmod 666 /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini && \
  ln -s /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini /usr/local/lib/edcb/BonDriver_LinuxMirakc.so.ini && \
  ln -s /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini /usr/local/lib/edcb/BonDriver_LinuxMirakc_S.so.ini && \
  ln -s /var/local/BonDriver_LinuxMirakc/BonDriver_LinuxMirakc.so.ini /usr/local/lib/edcb/BonDriver_LinuxMirakc_T.so.ini

EXPOSE 4510 5510
ENTRYPOINT ["/entrypoint.sh"]
