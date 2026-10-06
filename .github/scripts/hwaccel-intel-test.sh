#!/bin/sh
# Build the sample edcb/hwaccel/intel/Dockerfile and check the result.
#
# Usage: hwaccel-intel-test.sh <base image> <QSVEncC version or "">
#
# Checks that ffmpeg lists h264_qsv and h264_vaapi, that vainfo is installed,
# that qsvencc --version works when QSVEncC was added, and runs the smoke test.
# No GPU is needed: only the installation is checked.
set -u

base=$1
qsvencc=$2
image=edcb:hwaccel-intel${qsvencc:+-qsvencc}
dir=$(dirname "$0")
status=0

fail() {
  echo "::error::$*"
  status=1
}

echo "Building the sample on $base (QSVENCC_VERSION='$qsvencc')"
if ! docker buildx build --load -t "$image" \
  --build-arg BASE_IMAGE="$base" \
  --build-arg QSVENCC_VERSION="$qsvencc" \
  "$dir/../../edcb/hwaccel/intel"; then
  fail "the sample did not build (QSVENCC_VERSION='$qsvencc')"
  exit 1
fi

encoders=$(docker run --rm --entrypoint ffmpeg "$image" -hide_banner -encoders 2>&1)
for e in h264_qsv h264_vaapi; do
  if printf '%s\n' "$encoders" | grep -q " $e "; then
    echo "ffmpeg encoder $e: found"
  else
    fail "ffmpeg does not list $e"
  fi
done

docker run --rm --entrypoint sh "$image" -c 'command -v vainfo' || fail "vainfo is not installed"

if [ -n "$qsvencc" ]; then
  if out=$(docker run --rm --entrypoint qsvencc "$image" --version 2>&1); then
    printf '%s\n' "$out" | head -n 3
  else
    printf '%s\n' "$out"
    fail "qsvencc --version failed"
  fi
fi

"$dir/smoke-test.sh" "$image" || status=1
exit $status
