"""Apply a plan (see config.py) to the ini files under the EDCB root."""

import copy
import os
import re
from dataclasses import dataclass

from . import fsutil, ini


@dataclass
class Change:
    file: str
    section: str
    key: str
    old: str | None  # None: the key was absent
    new: str | None  # None: the key is deleted
    source: str

    def describe(self):
        return f"{self.file} [{self.section}] {self.key}: {_fmt(self.old)} -> {_fmt(self.new)} ({self.source})"


def _fmt(value):
    return "(absent)" if value is None else f'"{value}"'


@dataclass
class FileResult:
    file: str
    existed: bool
    new: ini.IniFile
    changes: list


def compute(plan, root):
    """Return a FileResult for every file the plan touches, with its changes."""
    results = []
    for rel in plan.files():
        path = os.path.join(root, rel)
        existed = os.path.isfile(path)
        try:
            original = ini.IniFile.load(path) if existed else ini.IniFile()
        except OSError as e:
            plan.warnings.append(f"{rel} is skipped: {e}")
            continue
        new = copy.deepcopy(original)
        changes = []
        for e in (e for e in plan.entries if e.file == rel):
            old = original.get(e.section, e.key)
            if e.force:
                if e.value is None:
                    if new.delete(e.section, e.key):
                        changes.append(Change(rel, e.section, e.key, old, None, e.source))
                elif new.get(e.section, e.key) != e.value:
                    new.set(e.section, e.key, e.value)
                    changes.append(Change(rel, e.section, e.key, old, e.value, e.source))
            else:
                # absence is judged on the original file, so that an anchor
                # written in this same run does not count as present
                if original.get(e.section, e.anchor or e.key) is None and old is None:
                    new.set(e.section, e.key, e.value)
                    changes.append(Change(rel, e.section, e.key, None, e.value, e.source))
        for t in (t for t in plan.trims if t.file == rel):
            pattern = re.compile(re.escape(t.prefix) + r"(\d+)", re.IGNORECASE)
            for name, value in original.keys(t.section):
                m = pattern.fullmatch(name)
                if m and int(m.group(1)) >= t.start and new.delete(t.section, name):
                    changes.append(Change(rel, t.section, name, value, None, t.source))
        for w in new.warnings:
            plan.warnings.append(f"{rel}: {w}")
        if changes:
            results.append(FileResult(rel, existed, new, changes))
    return results


def write(results, root, backup, owner):
    for r in results:
        if r.existed:
            backup.save(r.file)
        fsutil.write_atomic(os.path.join(root, r.file), r.new.to_bytes(), owner)
