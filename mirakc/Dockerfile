ARG ARCH=
FROM ${ARCH}mirakc/mirakc:debian

RUN BUILD_DEPENDENCIES="ca-certificates git build-essential cmake libpcsclite-dev pkg-config" && \
  apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y --no-install-recommends \
    $BUILD_DEPENDENCIES \
    libpcsclite1 \
    pcscd && \
\
  ( \
  cd /tmp && \
  git clone https://github.com/tsukumijima/libaribb25.git && \
  cd libaribb25 && \
  cmake -B build && \
  cd build && \
  make && \
  make install \
  ) && \
\
  rm -rf /tmp/libaribb25 && \
  apt-get remove -y $BUILD_DEPENDENCIES && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["sh", "-c", "pcscd && /usr/local/bin/mirakc"]
