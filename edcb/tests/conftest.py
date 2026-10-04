import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EDCB_DIR = os.path.dirname(HERE)
LIB = os.path.join(EDCB_DIR, "rootfs", "usr", "local", "lib", "edcb-provision")
sys.path.insert(0, LIB)


@pytest.fixture
def tree(tmp_path):
    """An image-like layout: EDCB root, overrides, share and EDCB's ini/."""
    from edcb_provision.provision import Paths

    root = tmp_path / "edcb"
    overrides = tmp_path / "overrides"
    share = tmp_path / "share"
    edcb_ini = tmp_path / "src-ini"
    root.mkdir()
    (share / "HttpPublic" / "legacy").mkdir(parents=True)
    (share / "HttpPublic" / "legacy" / "util.lua").write_bytes(
        b"ALLOW_SETTING=edcb.GetPrivateProfile('LEGACY','ALLOW_SETTING','0','.provision/webui.ini')=='1'\r\n"
    )
    (share / "HttpPublic" / "index.html").write_bytes(b"<html></html>\n")
    (share / "Setting").mkdir()
    (share / "Setting" / "HttpPublic.ini").write_bytes("[SET]\n;既定値\n".encode("cp932"))
    (share / "Setting" / "XCODE_OPTIONS.lua").write_bytes(b"XCODE_OPTIONS={}\n")
    edcb_ini.mkdir()
    (edcb_ini / "Bitrate.ini").write_bytes("[BITRATE]\r\n;地上波\r\nFFFFFFFFFFFF=16860\r\n".encode("cp932"))
    (edcb_ini / "BonCtrl.ini").write_bytes(b"[SET]\r\nFFFFFFFF=B25Decoder.dll\r\n")
    (edcb_ini / "ContentTypeText.txt").write_bytes(b".ts\tvideo/MP2T\r\n")
    return Paths(str(root), str(overrides), str(share), str(edcb_ini))
