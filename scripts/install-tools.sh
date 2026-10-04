#!/bin/sh
# Install the pinned lint tools used by scripts/check.sh into .tools/bin.
#
# Usage: install-tools.sh
#
# Downloads the release binaries of shellcheck and actionlint from GitHub
# for linux x86_64 or aarch64 and verifies them against the sha256 sums
# below. A tool that is already installed at the pinned version is skipped.
#
# To update a tool, change its version and both checksums. actionlint
# publishes actionlint_<version>_checksums.txt with each release; the
# archives of shellcheck have to be downloaded and passed to sha256sum.
set -eu

SHELLCHECK_VERSION=0.11.0
SHELLCHECK_SHA256_X86_64=8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198
SHELLCHECK_SHA256_AARCH64=12b331c1d2db6b9eb13cfca64306b1b157a86eb69db83023e261eaa7e7c14588

ACTIONLINT_VERSION=1.7.12
ACTIONLINT_SHA256_AMD64=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8
ACTIONLINT_SHA256_ARM64=325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6

root=$(cd "$(dirname "$0")/.." && pwd)
bindir=$root/.tools/bin

if [ "$(uname -s)" != Linux ]; then
  echo "ERROR: only Linux is supported (got $(uname -s))" >&2
  exit 1
fi
case $(uname -m) in
  x86_64 | amd64)
    sc_arch=x86_64 sc_sum=$SHELLCHECK_SHA256_X86_64
    al_arch=amd64 al_sum=$ACTIONLINT_SHA256_AMD64
    ;;
  aarch64 | arm64)
    sc_arch=aarch64 sc_sum=$SHELLCHECK_SHA256_AARCH64
    al_arch=arm64 al_sum=$ACTIONLINT_SHA256_ARM64
    ;;
  *)
    echo "ERROR: unsupported architecture $(uname -m)" >&2
    exit 1
    ;;
esac

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# fetch <url> <sha256> <file>: download <url> to <file> and verify it
fetch() {
  echo "Downloading $1"
  curl -fsSL --retry 3 -o "$3" "$1"
  if ! printf '%s  %s\n' "$2" "$3" | sha256sum -c --status -; then
    echo "ERROR: sha256 mismatch for $1" >&2
    echo "  expected: $2" >&2
    echo "  actual:   $(sha256sum "$3" | cut -d ' ' -f 1)" >&2
    exit 1
  fi
}

mkdir -p "$bindir"

if [ -x "$bindir/shellcheck" ] &&
   "$bindir/shellcheck" --version | grep -qx "version: $SHELLCHECK_VERSION"; then
  echo "shellcheck $SHELLCHECK_VERSION is already installed"
else
  archive=$tmp/shellcheck.tar.xz
  fetch "https://github.com/koalaman/shellcheck/releases/download/v$SHELLCHECK_VERSION/shellcheck-v$SHELLCHECK_VERSION.linux.$sc_arch.tar.xz" \
    "$sc_sum" "$archive"
  tar -xJf "$archive" -C "$tmp"
  install -m 0755 "$tmp/shellcheck-v$SHELLCHECK_VERSION/shellcheck" "$bindir/shellcheck"
  echo "Installed shellcheck $SHELLCHECK_VERSION"
fi

if [ -x "$bindir/actionlint" ] &&
   "$bindir/actionlint" --version | head -n 1 | grep -qx "$ACTIONLINT_VERSION"; then
  echo "actionlint $ACTIONLINT_VERSION is already installed"
else
  archive=$tmp/actionlint.tar.gz
  fetch "https://github.com/rhysd/actionlint/releases/download/v$ACTIONLINT_VERSION/actionlint_${ACTIONLINT_VERSION}_linux_$al_arch.tar.gz" \
    "$al_sum" "$archive"
  tar -xzf "$archive" -C "$tmp" actionlint
  install -m 0755 "$tmp/actionlint" "$bindir/actionlint"
  echo "Installed actionlint $ACTIONLINT_VERSION"
fi
