"""Keep the WebUI files (HttpPublic) in the volume in sync with the image.

The WebUI writes into HttpPublic at run time (EMWUI's library thumbnails under
video/thumbs, and transcode logs under legacy/log and api/log when XCODE_LOG is
on), so HttpPublic stays in the volume (docs/v2/design.md, chapter 6). The
image carries the reference copy. When it differs from the copy installed last
time, the files that differ are backed up and replaced:

- a file of the image that is missing or different in the volume is copied;
- a file installed last time that is no longer in the image is removed, if
  it is unchanged since it was installed;
- any other file in the volume (thumbnails, logs, the old EMWUI/ folder) is
  left alone.

When the image is unchanged, only missing files are restored.
"""

import hashlib
import os

from . import fsutil

STATE_KEY = "httppublic"
TARGET = "HttpPublic"


def manifest(src):
    files = {}
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            files[os.path.relpath(path, src)] = fsutil.sha256_file(path)
    return files


def tree_hash(files):
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(f"{rel}\0{files[rel]}\n".encode("utf-8", errors="surrogateescape"))
    return h.hexdigest()


def sync(root, src, state, backup, owner, *, dry_run, log, warn):
    if not os.path.isdir(src):
        warn(f"{src} is missing; HttpPublic is not updated")
        return 0
    files = manifest(src)
    digest = tree_hash(files)
    recorded = state.section(STATE_KEY)
    old_files = recorded.get("files", {})
    unchanged_image = recorded.get("tree") == digest

    added = replaced = removed = 0
    for rel, sha in files.items():
        dst_rel = os.path.join(TARGET, rel)
        dst = os.path.join(root, dst_rel)
        if os.path.isfile(dst):
            if unchanged_image or fsutil.sha256_file(dst) == sha:
                continue
            replaced += 1
            if not dry_run:
                backup.save(dst_rel)
        else:
            if os.path.lexists(dst):
                warn(f"{dst_rel} is not a regular file; not replaced")
                continue
            added += 1
        if not dry_run:
            fsutil.copy_file(os.path.join(src, rel), dst, owner)

    if not unchanged_image:
        for rel, sha in old_files.items():
            if rel in files:
                continue
            dst_rel = os.path.join(TARGET, rel)
            dst = os.path.join(root, dst_rel)
            if not os.path.isfile(dst):
                continue
            if fsutil.sha256_file(dst) != sha:
                warn(f"{dst_rel} is no longer part of the WebUI but was edited; left in place")
                continue
            removed += 1
            if not dry_run:
                backup.save(dst_rel)
                os.remove(dst)

    if added or replaced or removed:
        what = "would update" if dry_run else "updated"
        log(f"{TARGET}: {what} ({added} added, {replaced} replaced, {removed} removed)")
    if not dry_run:
        recorded["tree"] = digest
        recorded["files"] = files
    return added + replaced + removed
