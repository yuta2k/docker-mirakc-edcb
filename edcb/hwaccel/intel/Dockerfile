# Sample: add Intel hardware encoding (QSV / VA-API) to the edcb image.
# amd64 only. Use it from compose.override.yml (see compose.override-sample.yml):
#
#   services:
#     edcb:
#       build:
#         context: edcb/hwaccel/intel
#       devices:
#         - /dev/dri
#
# By default only packages of Ubuntu's repositories are added: the Intel media
# driver (iHD, VA-API) and the VPL GPU runtime. The ffmpeg of the image is
# already built with VA-API and VPL, so h264_vaapi and h264_qsv work with them.
# - QSV (h264_qsv, QSVEncC --backend qsv) needs Gen12 (Tiger Lake) or later:
#   Ubuntu 26.04 has no Media SDK runtime (libmfx1) for older GPUs.
# - VA-API (h264_vaapi, QSVEncC --backend vaapi) works with Gen8 (Broadwell)
#   or later.
#
# QSVEncC is added only when QSVENCC_VERSION is given (a release of
# https://github.com/rigaya/QSVEnc, e.g. 8.32). QSVENCC_SHA256, if given, is
# checked against the downloaded .deb.
#
# The group of /dev/dri/renderD* is added to the user that runs EDCB on start,
# so group_add is not needed.

# The published image. Prefer a version tag (BASE_IMAGE=...:<version>). To extend
# an image built locally instead, build it first and give its name:
#   docker build -t edcb-local edcb
#   (compose.override.yml: build: args: BASE_IMAGE: edcb-local)
ARG BASE_IMAGE=ghcr.io/yuta2k/docker-mirakc-edcb/edcb:latest
FROM ${BASE_IMAGE}

ARG QSVENCC_VERSION=
ARG QSVENCC_SHA256=

RUN arch=$(dpkg --print-architecture) && \
  if [ "$arch" != amd64 ]; then \
    echo "this sample supports amd64 only (got $arch)" >&2; exit 1; \
  fi && \
  apt-get update && \
  apt-get install -y --no-install-recommends \
    # VA-API driver for Broadwell and later (iHD; multiverse)
    intel-media-va-driver-non-free \
    # VPL runtime for QSV on Tiger Lake and later
    libmfx-gen1.2 \
    # to check the driver: vainfo --display drm --device /dev/dri/renderD128
    vainfo && \
  if [ -n "$QSVENCC_VERSION" ]; then \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    deb="qsvencc_${QSVENCC_VERSION}_amd64.deb" && \
    curl -fsSL --retry 3 -o "/tmp/$deb" \
      "https://github.com/rigaya/QSVEnc/releases/download/${QSVENCC_VERSION}/$deb" && \
    if [ -n "$QSVENCC_SHA256" ]; then \
      echo "$QSVENCC_SHA256  /tmp/$deb" | sha256sum -c -; \
    fi && \
    apt-get install -y --no-install-recommends "/tmp/$deb" && \
    rm "/tmp/$deb" && \
    apt-get purge -y curl && \
    apt-get autoremove -y; \
  fi && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*
