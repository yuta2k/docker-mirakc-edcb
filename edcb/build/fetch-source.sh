#!/bin/sh
# Fetch an upstream repository at a pinned commit.
#
# Usage: fetch-source.sh <repo-url> <ref> <commit> <dest>
#
#   <ref>     Tag (or branch) to fetch. Empty to fetch <commit> directly.
#   <commit>  Full 40-character commit SHA-1. The checked out HEAD must be
#             this commit, otherwise the build fails. This catches a tag
#             that was moved or a ref/commit pair that does not match.
#
# Submodules are checked out at the commits recorded in the repository.
set -eu

if [ $# -ne 4 ]; then
  echo "usage: $0 <repo-url> <ref> <commit> <dest>" >&2
  exit 1
fi
repo=$1
ref=$2
commit=$3
dest=$4

if ! printf '%s' "$commit" | grep -Eqx '[0-9a-f]{40}'; then
  echo "ERROR: commit for $repo must be a full 40-character SHA-1 (got '$commit')" >&2
  exit 1
fi

git init -q "$dest"
cd "$dest"
git remote add origin "$repo"
git fetch -q --depth 1 origin "${ref:-$commit}"
git -c advice.detachedHead=false checkout -q FETCH_HEAD

actual=$(git rev-parse HEAD)
if [ "$actual" != "$commit" ]; then
  echo "ERROR: $repo ${ref:+$ref }is at $actual, expected $commit" >&2
  echo "ERROR: update the pinned commit in edcb/Dockerfile if this is intended" >&2
  exit 1
fi

if [ -f .gitmodules ]; then
  git submodule -q update --init --recursive
fi

echo "Fetched $repo ${ref:+$ref }at $actual"
