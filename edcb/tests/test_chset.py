import pytest

from edcb_provision import chset

BOM = chset.BOM


def ch(type_, channel):
    return {"type": type_, "channel": channel, "name": channel}


def row(name, space, ch_, onid=1, tsid=2, sid=3):
    return f"{name}\t{name} service\tnet\t{space}\t{ch_}\t{onid}\t{tsid}\t{sid}\t1\t0\t1\t0"


def chset4(*rows, ending="\n"):
    return BOM + "".join(r + ending for r in rows).encode()


def rows_of(data):
    assert data.startswith(BOM)
    return [line.split("\t")[0] for line in data[len(BOM) :].decode().splitlines()]


def test_spaces_follow_runs_of_one_type():
    assert chset.spaces([]) == []
    assert chset.spaces([ch("GR", "27"), ch("GR", "26")]) == ["GR"]
    assert chset.spaces([ch("GR", "27"), ch("BS", "BS01_0"), ch("CS", "CS2")]) == ["GR", "BS", "CS"]
    # the same type again later is a new space, like the BonDriver's InitChannel
    assert chset.spaces([ch("GR", "27"), ch("BS", "BS01_0"), ch("GR", "26")]) == ["GR", "BS", "GR"]


@pytest.mark.parametrize(
    "spaces, rows, expected",
    [
        # terrestrial only
        (["GR"], [row("a", 0, 0), row("b", 0, 1)], {"M": ["a", "b"], "T": ["a", "b"], "S": []}),
        # satellite only
        (["BS", "CS"], [row("a", 0, 0), row("b", 1, 0)], {"M": ["a", "b"], "T": [], "S": ["a", "b"]}),
        # both
        (
            ["GR", "BS", "CS"],
            [row("g", 0, 0), row("b", 1, 0), row("b2", 1, 1), row("c", 2, 0)],
            {"M": ["g", "b", "b2", "c"], "T": ["g"], "S": ["b", "b2", "c"]},
        ),
        # one type in two places
        (
            ["GR", "BS", "GR", "CS"],
            [row("g1", 0, 0), row("b", 1, 0), row("g2", 2, 0), row("c", 3, 0)],
            {"M": ["g1", "b", "g2", "c"], "T": ["g1", "g2"], "S": ["b", "c"]},
        ),
        # SKY belongs to neither T nor S
        (["GR", "SKY"], [row("g", 0, 0), row("s", 1, 0)], {"M": ["g", "s"], "T": ["g"], "S": []}),
    ],
)
def test_split_by_kind(spaces, rows, expected):
    files, counts, warnings = chset.split(chset4(*rows), spaces)
    assert {k: rows_of(v) for k, v in files.items()} == expected
    assert counts == {k: len(v) for k, v in expected.items()}
    assert warnings == []


def test_split_keeps_rows_byte_for_byte():
    rows = [row("ｇ１", 0, 5, 32736, 32736, 1024), row("b", 1, 7, 4, 16400, 101)]
    files, _, _ = chset.split(chset4(*rows), ["GR", "BS"])
    assert files["M"] == chset4(*rows)
    assert files["T"] == chset4(rows[0])
    assert files["S"] == chset4(rows[1])


def test_split_keeps_crlf_and_adds_a_bom():
    data = "".join(r + "\r\n" for r in [row("g", 0, 0), row("b", 1, 0)]).encode()
    files, _, _ = chset.split(data, ["GR", "BS"])
    assert files["T"] == BOM + (row("g", 0, 0) + "\r\n").encode()
    assert files["M"] == BOM + data


def test_split_drops_lines_edcb_ignores_and_ends_the_last_line():
    data = BOM + ("no tab here\n" + row("g", 0, 0) + "\n\n" + row("b", 1, 0)).encode()
    files, counts, _ = chset.split(data, ["GR", "BS"])
    assert counts == {"M": 2, "T": 1, "S": 1}
    assert files["S"] == chset4(row("b", 1, 0))


def test_split_keeps_unknown_spaces_for_dual_tuners_only():
    files, counts, warnings = chset.split(chset4(row("g", 0, 0), row("x", 4, 0)), ["GR"])
    assert counts == {"M": 2, "T": 1, "S": 0}
    assert len(warnings) == 1 and "space 4" in warnings[0]


def chset5(*services, bom=True, ending="\n"):
    lines = [f"{name}\tnet\t{onid}\t{tsid}\t{sid}\t1\t0\t{epg}\t{search}" for name, onid, tsid, sid, epg, search in services]
    return (BOM if bom else b"") + "".join(line + ending for line in lines).encode()


def test_restore_flags_puts_back_epg_and_search_flags():
    before = chset5(("a", 1, 2, 3, 0, 0), ("b", 1, 2, 4, 1, 0), ("gone", 9, 9, 9, 0, 0))
    after = chset5(("a", 1, 2, 3, 1, 1), ("b", 1, 2, 4, 1, 1), ("new", 5, 6, 7, 1, 1), ending="\r\n")
    data, changed = chset.restore_flags(after, chset.service_flags(before))
    assert changed == 2
    assert data == chset5(("a", 1, 2, 3, 0, 0), ("b", 1, 2, 4, 1, 0), ("new", 5, 6, 7, 1, 1), ending="\r\n")


def test_restore_flags_without_changes_keeps_the_file():
    data = chset5(("a", 1, 2, 3, 1, 1), bom=False)
    assert chset.restore_flags(data, chset.service_flags(data)) == (data, 0)


def test_channels_hash_changes_with_order_and_content():
    a = [ch("GR", "27"), ch("BS", "BS01_0")]
    assert chset.channels_hash(a) == chset.channels_hash([dict(c, name="other") for c in a])
    assert chset.channels_hash(a) != chset.channels_hash(a[::-1])
    assert chset.channels_hash(a) != chset.channels_hash(a + [ch("CS", "CS2")])


def test_split_real_data():
    """Split a real scan, if given (never commit one: it is the user's channel layout).

    EDCB_TEST_CHSET4: a ChSet4 made by a scan with BonDriver_LinuxMirakc.so.
    EDCB_TEST_BACKEND_JSON: .provision/backend-<NAME>.json of the same backend.
    """
    import json
    import os

    path = os.environ.get("EDCB_TEST_CHSET4")
    backend = os.environ.get("EDCB_TEST_BACKEND_JSON")
    if not path or not backend:
        pytest.skip("EDCB_TEST_CHSET4 / EDCB_TEST_BACKEND_JSON are not set")
    with open(path, "rb") as f:
        scan = f.read()
    with open(backend, encoding="utf-8") as f:
        space_types = chset.spaces(json.load(f)["channels"])
    files, counts, warnings = chset.split(scan, space_types)
    assert warnings == []
    _, lines = chset.split_lines(scan)
    assert files["M"] == chset.join_lines(lines)
    assert counts["T"] + counts["S"] <= counts["M"]
    for kind, allowed in (("T", {"GR"}), ("S", {"BS", "CS"})):
        _, rows = chset.split_lines(files[kind])
        for line in rows:
            assert space_types[int(line.split(b"\t")[3])] in allowed
    # every row of a GR / BS / CS space is in T or S, unchanged
    _, t_rows = chset.split_lines(files["T"])
    _, s_rows = chset.split_lines(files["S"])
    assert sorted(t_rows + s_rows) == sorted(
        line for line in lines if space_types[int(line.split(b"\t")[3])] in ("GR", "BS", "CS")
    )


def test_positions_and_scanned_positions():
    channels = [ch("GR", "27"), ch("GR", "26"), ch("BS", "BS01_0"), ch("GR", "20")]
    assert [(s, c, x["channel"]) for s, c, x in chset.positions(channels)] == [
        (0, 0, "27"),
        (0, 1, "26"),
        (1, 0, "BS01_0"),
        (2, 0, "20"),
    ]
    assert chset.scanned_positions(chset4(row("a", 0, 1), row("b", 0, 1, sid=4), row("c", 2, 0))) == {(0, 1), (2, 0)}
