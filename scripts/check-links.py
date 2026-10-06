#!/usr/bin/env python3
"""Check the relative links of the Markdown files of the repository.

A link to a file must point to an existing file or directory, and a link with
a #fragment to a Markdown file must name one of its headings (GitHub's anchor
rules). Links with a scheme (https:, mailto:) are not checked.

Usage: check-links.py [file.md ...]   (default: every *.md that git does not ignore)
Exits 1 if a link is broken.
"""

import os
import re
import subprocess
import sys
import unicodedata

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^()\s]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def strip_code(lines):
    """Lines outside fenced code blocks, with inline code removed."""
    out, fenced = [], False
    for line in lines:
        if FENCE_RE.match(line):
            fenced = not fenced
            out.append("")
            continue
        out.append("" if fenced else re.sub(r"`[^`]*`", "", line))
    return out


def slug(text):
    """GitHub's anchor of a heading: lower case, punctuation removed, spaces to -."""
    text = re.sub(r"`([^`]*)`", r"\1", text)  # inline code keeps its text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links keep their text
    text = text.lower()
    kept = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch in "-_" or ch == " " or cat[0] in "LMN":
            kept.append(ch)
    return "".join(kept).replace(" ", "-")


def anchors(path, cache={}):
    if path not in cache:
        seen, result = {}, set()
        with open(path, encoding="utf-8") as f:
            raw = f.read().splitlines()
        fenced = False
        for line in raw:
            if FENCE_RE.match(line):
                fenced = not fenced
                continue
            m = None if fenced else HEADING_RE.match(line)
            if not m:
                continue
            base = slug(m.group(2))
            n = seen.get(base, 0)
            seen[base] = n + 1
            result.add(base if n == 0 else f"{base}-{n}")
        cache[path] = result
    return cache[path]


def check(md):
    errors = []
    with open(md, encoding="utf-8") as f:
        lines = strip_code(f.read().splitlines())
    for no, line in enumerate(lines, 1):
        for target in LINK_RE.findall(line):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
                continue
            path, _, frag = target.partition("#")
            dest = os.path.normpath(os.path.join(os.path.dirname(md), path)) if path else md
            if not os.path.exists(dest):
                errors.append(f"{md}:{no}: {target}: {dest} does not exist")
                continue
            if frag and dest.endswith(".md") and frag not in anchors(dest):
                errors.append(f"{md}:{no}: {target}: no heading #{frag} in {dest}")
    return errors


def main(argv):
    files = argv or subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"], capture_output=True, text=True, check=True
    ).stdout.split()
    errors = [e for md in files for e in check(md)]
    for e in errors:
        print(e)
    print(f"{len(files)} files, {len(errors)} broken links")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
