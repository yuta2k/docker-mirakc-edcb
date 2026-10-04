"""Copy EDCB's debug logs to standard output (EDCB_LOG_STDOUT).

EDCB writes its debug logs only to files in /var/local/edcb. This follows
EpgTimerSrvDebugLog.txt and EpgDataCap_Bon_DebugLog-*.txt, including files
that appear later, and prints new lines with the name of the log. Lines that
were already in a file when following started are not printed again.
"""

import glob
import os
import signal
import sys
import time

PATTERNS = ["EpgTimerSrvDebugLog.txt", "EpgDataCap_Bon_DebugLog-*.txt"]


def _label(path):
    name = os.path.basename(path)
    if name == "EpgTimerSrvDebugLog.txt":
        return "EpgTimerSrv"
    return name.removesuffix(".txt").replace("_DebugLog", "")


class Follower:
    def __init__(self, root, out=sys.stdout):
        self.root = root
        self.out = out
        self.files = {}  # path -> [inode, offset, pending bytes]

    def scan(self, initial=False):
        for pattern in PATTERNS:
            for path in glob.glob(os.path.join(self.root, pattern)):
                if path in self.files:
                    continue
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                self.files[path] = [st.st_ino, st.st_size if initial else 0, b""]

    def poll(self):
        for path, entry in list(self.files.items()):
            try:
                st = os.stat(path)
            except OSError:
                del self.files[path]
                continue
            if st.st_ino != entry[0] or st.st_size < entry[1]:
                entry[:] = [st.st_ino, 0, b""]  # replaced or truncated
            if st.st_size == entry[1]:
                continue
            try:
                with open(path, "rb") as f:
                    f.seek(entry[1])
                    data = f.read()
            except OSError:
                continue
            entry[1] += len(data)
            data = entry[2] + data
            *lines, entry[2] = data.split(b"\n")
            label = _label(path)
            for line in lines:
                text = line.decode("utf-8", errors="replace").lstrip("\ufeff").rstrip("\r")
                print(f"[{label}] {text}", file=self.out)
        self.out.flush()


def main(argv=None, root="/var/local/edcb", interval=1.0):
    """argv: [ready_file]. The ready file is created once the existing logs
    have been measured, so that the caller can start EDCB without its first
    lines being taken for old ones."""
    argv = sys.argv[1:] if argv is None else argv
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(True))
    signal.signal(signal.SIGINT, lambda *_: stop.append(True))
    f = Follower(root)
    f.scan(initial=True)
    if argv:
        with open(argv[0], "w"):
            pass
    while not stop:
        time.sleep(interval)
        f.scan()
        f.poll()
    f.poll()  # print what was written while stopping
    return 0


if __name__ == "__main__":
    sys.exit(main())
