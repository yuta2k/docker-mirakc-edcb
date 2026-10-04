ARG ARCH=
FROM ${ARCH}mirakc/mirakc:debian

# libaribb25 is pinned to a commit; the build fails if the fetched source is not at that commit
ARG LIBARIBB25_REPO=https://github.com/tsukumijima/libaribb25.git
ARG LIBARIBB25_COMMIT=dc1d96a90ea554d8997b238fd6712eccf553cdb3

RUN BUILD_DEPENDENCIES="ca-certificates git build-essential cmake libpcsclite-dev pkg-config" && \
  apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y --no-install-recommends \
    $BUILD_DEPENDENCIES \
    libpcsclite1 \
    pcscd && \
\
  ( \
  git init -q /tmp/libaribb25 && \
  cd /tmp/libaribb25 && \
  git fetch -q --depth 1 "$LIBARIBB25_REPO" "$LIBARIBB25_COMMIT" && \
  git -c advice.detachedHead=false checkout -q FETCH_HEAD && \
  test "$(git rev-parse HEAD)" = "$LIBARIBB25_COMMIT" && \
  echo "Fetched $LIBARIBB25_REPO at $LIBARIBB25_COMMIT" && \
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

# Debian's pcscd is built with polkit, and without polkitd/D-Bus in the container
# it refuses clients: arib-b25-stream-test fails with "B_CAS_CARD::init() : code=-3"
# and mirakc answers 404 to decode=1 streams
ENTRYPOINT ["sh", "-c", "pcscd --disable-polkit && /usr/local/bin/mirakc"]
