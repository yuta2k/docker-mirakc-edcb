"""Line-preserving editor for EDCB ini files.

EDCB (Common/PathUtil.cpp, the non-Windows GetPrivateProfileToString and
WritePrivateProfileString) reads ini files like this, and this module follows
the same rules so that it sees the same values as EDCB:

- Section names and key names are compared case-insensitively.
- Leading and trailing spaces, tabs and CR are ignored, also around the key
  name before "=". Leading spaces of the value are ignored.
- A value enclosed in matching double or single quotes is unquoted.
- Several blocks with the same section name act as one section; the first
  matching key in file order wins.

Unlike configparser, only the lines of the keys that are changed are touched.
Comments, blank lines, key order and the case of names are kept. The BOM and
the line endings of the original file are kept.
"""

import re
from dataclasses import dataclass

BOM = "﻿"

_KEY_RE = re.compile(r"^[ \t]*(?P<key>[^=]*?)[ \t]*=")


def _strip(s):
    return s.strip(" \t\r")


def _norm(name):
    return name.casefold()


def unquote(value):
    if len(value) > 1 and value[0] in "\"'" and value[0] == value[-1]:
        return value[1:-1]
    return value


@dataclass
class _Line:
    text: str  # without the line ending
    section: str | None = None  # normalized section name for header lines
    key: str | None = None  # normalized key name for key lines


class IniFile:
    """An ini file kept as a list of lines."""

    def __init__(self, text="", *, bom=False, newline="\n"):
        self.bom = bom
        self.newline = newline
        self.warnings = []
        self._lines = []
        self._trailing_newline = True
        if text:
            self._parse(text)

    # ----- loading and saving -----

    @classmethod
    def from_bytes(cls, data):
        text = data.decode("utf-8", errors="surrogateescape")
        bom = text.startswith(BOM)
        if bom:
            text = text[1:]
        newline = "\r\n" if "\r\n" in text else "\n"
        return cls(text, bom=bom, newline=newline)

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls.from_bytes(f.read())

    def to_bytes(self):
        return self.to_text().encode("utf-8", errors="surrogateescape")

    def to_text(self):
        body = self.newline.join(line.text for line in self._lines)
        if self._lines and self._trailing_newline:
            body += self.newline
        return (BOM if self.bom else "") + body

    def _parse(self, text):
        raw_lines = text.split("\n")
        if raw_lines and raw_lines[-1] == "":
            raw_lines.pop()
        else:
            self._trailing_newline = False
        section = None
        for raw in raw_lines:
            raw = raw.removesuffix("\r")
            line = _Line(raw)
            stripped = _strip(raw)
            if stripped.startswith("["):
                section = _norm(stripped[1:-1]) if stripped.endswith("]") else None
                line.section = section
            elif section is not None and not stripped.startswith(";"):
                m = _KEY_RE.match(raw)
                if m and m.group("key"):
                    line.key = _norm(m.group("key"))
            self._lines.append(line)
        # a header line marks a section; key lines need to know their section
        self._index()

    def _index(self):
        section = None
        self._owner = []
        for line in self._lines:
            if line.section is not None or _strip(line.text).startswith("["):
                section = line.section
            self._owner.append(section)

    # ----- queries -----

    def sections(self):
        seen = []
        for line in self._lines:
            if line.section is not None and line.section not in seen:
                seen.append(line.section)
        return seen

    def section_names(self):
        """Like sections(), but spelled as in the file (the first spelling)."""
        return _sections_as_written(self)

    def _find(self, section, key):
        section, key = _norm(section), _norm(key)
        return [
            i
            for i, line in enumerate(self._lines)
            if line.key == key and self._owner[i] == section
        ]

    def has_section(self, section):
        return _norm(section) in self.sections()

    def get(self, section, key):
        """Return the value as EDCB reads it, or None if the key is absent.

        A key with an empty value exists and returns "".
        """
        found = self._find(section, key)
        if not found:
            return None
        return self._value_of(found[0])

    def _value_of(self, index):
        text = self._lines[index].text
        value = text[text.index("=") + 1 :]
        return unquote(_strip(value))

    def keys(self, section):
        """Return (key as written, value) pairs of a section in file order."""
        section = _norm(section)
        result = []
        for i, line in enumerate(self._lines):
            if line.key is not None and self._owner[i] == section:
                name = _strip(line.text[: line.text.index("=")])
                result.append((name, self._value_of(i)))
        return result

    # ----- edits -----

    def set(self, section, key, value):
        """Set a key. Return True if the file changed."""
        value = str(value)
        if "\n" in value or "\r" in value:
            raise ValueError(f"value for {key} contains a line break")
        found = self._find(section, key)
        if found:
            if len(found) > 1:
                self.warnings.append(
                    f"[{section}] {key} appears {len(found)} times; only the first one was changed"
                )
            i = found[0]
            text = self._lines[i].text
            eq = text.index("=")
            rest = text[eq + 1 :]
            lead = rest[: len(rest) - len(rest.lstrip(" \t"))]
            new_text = text[: eq + 1] + lead + value
            if new_text == text:
                return False
            self._lines[i].text = new_text
            return True
        self._insert(section, key, value)
        return True

    def delete(self, section, key):
        """Delete every occurrence of a key. Return True if the file changed."""
        found = self._find(section, key)
        for i in reversed(found):
            del self._lines[i]
        if found:
            self._index()
        return bool(found)

    def delete_section(self, section):
        """Delete every block of a section, with the lines up to the next header. Return True if the file changed."""
        norm = _norm(section)
        keep = [line for i, line in enumerate(self._lines) if self._owner[i] != norm]
        if len(keep) == len(self._lines):
            return False
        self._lines = keep
        self._index()
        return True

    def _insert(self, section, key, value):
        norm = _norm(section)
        header = None
        last_key = None
        for i, line in enumerate(self._lines):
            if line.section == norm:
                if header is not None:
                    # a later block with the same name: EDCB reads it as the same
                    # section, but new keys go to the first block
                    break
                header = i
                last_key = i
            elif header is not None:
                if line.section is not None or _strip(line.text).startswith("["):
                    break
                if line.key is not None:
                    last_key = i
        new_line = _Line(f"{key}={value}", key=_norm(key))
        if header is None:
            self._lines.append(_Line(f"[{section}]", section=norm))
            self._lines.append(new_line)
            self._trailing_newline = True
        else:
            self._lines.insert(last_key + 1, new_line)
        self._index()


def parse_values(data):
    """Parse ini bytes into {(section, key): value} keeping the names as written.

    Used for the override files. Later duplicates are ignored, as EDCB does.
    """
    ini = IniFile.from_bytes(data)
    result = {}
    seen = set()
    for section in _sections_as_written(ini):
        for key, value in ini.keys(section):
            ident = (_norm(section), _norm(key))
            if ident in seen:
                continue
            seen.add(ident)
            result[(section, key)] = value
    return result


def _sections_as_written(ini):
    names = []
    seen = set()
    for line in ini._lines:
        if line.section is not None and line.section not in seen:
            seen.add(line.section)
            names.append(_strip(line.text)[1:-1])
    return names
