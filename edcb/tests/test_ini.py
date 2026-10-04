from edcb_provision.ini import IniFile, parse_values


def load(text, **kw):
    return IniFile.from_bytes(text.encode("utf-8") if isinstance(text, str) else text)


def test_get_follows_edcb_rules():
    f = load("[SET]\n  HttpPort = \"5510\"  \nEmpty=\nzero=0\n[Other]\nx=1\n")
    assert f.get("set", "httpport") == "5510"
    assert f.get("SET", "Empty") == ""
    assert f.get("SET", "zero") == "0"
    assert f.get("SET", "x") is None
    assert f.get("Other", "X") == "1"
    assert f.get("Missing", "x") is None


def test_comments_and_keys_outside_sections_are_not_keys():
    f = load("x=1\n[SET]\n;HttpPort=1\nHttpPort=2\n")
    assert f.get("SET", "HttpPort") == "2"
    assert f.keys("SET") == [("HttpPort", "2")]


def test_set_replaces_only_the_value_and_keeps_everything_else():
    text = ";comment\n[SET]\nA = 1\n\n; about B\nb=2\n[Next]\nc=3\n"
    f = load(text)
    assert f.set("SET", "B", "20") is True
    assert f.to_text() == ";comment\n[SET]\nA = 1\n\n; about B\nb=20\n[Next]\nc=3\n"
    assert f.set("SET", "a", "1") is False


def test_set_appends_after_the_last_key_of_the_section():
    f = load("[SET]\nA=1\n\n;comment of next\n[Next]\nc=3\n")
    f.set("SET", "New", "x")
    assert f.to_text() == "[SET]\nA=1\nNew=x\n\n;comment of next\n[Next]\nc=3\n"


def test_set_creates_the_section_and_the_file():
    f = IniFile()
    f.set("SET", "A", "1")
    f.set("SET", "B", "2")
    f.set("Other", "C", "3")
    assert f.to_text() == "[SET]\nA=1\nB=2\n[Other]\nC=3\n"


def test_missing_final_newline_is_handled():
    f = load("[SET]\nA=1")
    f.set("Other", "B", "2")
    assert f.to_text() == "[SET]\nA=1\n[Other]\nB=2\n"
    f = load("[SET]\nA=1")
    f.set("SET", "A", "2")
    assert f.to_text() == "[SET]\nA=2"


def test_bom_and_crlf_are_kept():
    f = IniFile.from_bytes(b"\xef\xbb\xbf[SET]\r\nA=1\r\n")
    f.set("SET", "A", "2")
    f.set("SET", "B", "3")
    assert f.to_bytes() == b"\xef\xbb\xbf[SET]\r\nA=2\r\nB=3\r\n"


def test_non_utf8_bytes_survive():
    data = "[SET]\r\n;日本語\r\nA=1\r\n".encode("cp932")
    f = IniFile.from_bytes(data)
    f.set("SET", "A", "2")
    assert f.to_bytes() == data.replace(b"A=1", b"A=2")


def test_duplicate_keys_change_the_first_and_warn():
    f = load("[SET]\nA=1\n[SET]\nA=2\n")
    assert f.get("SET", "A") == "1"
    f.set("SET", "A", "9")
    assert f.to_text() == "[SET]\nA=9\n[SET]\nA=2\n"
    assert f.warnings and "2 times" in f.warnings[0]


def test_duplicate_sections_act_as_one():
    f = load("[SET]\nA=1\n[X]\n[SET]\nB=2\n")
    assert f.get("SET", "B") == "2"
    f.set("SET", "C", "3")
    assert f.to_text() == "[SET]\nA=1\nC=3\n[X]\n[SET]\nB=2\n"


def test_delete():
    f = load("[SET]\nA=1\nB=2\n")
    assert f.delete("SET", "a") is True
    assert f.delete("SET", "a") is False
    assert f.to_text() == "[SET]\nB=2\n"


def test_malformed_header_ends_the_section():
    f = load("[SET]\nA=1\n[broken\nB=2\n")
    assert f.get("SET", "B") is None


def test_value_with_newline_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        IniFile().set("SET", "A", "1\n[X]")


def test_parse_values():
    values = parse_values(b"\xef\xbb\xbf; c\n[SET]\nHttpPort=5510\nhttpport=1\n[set]\nA=\n")
    assert values == {("SET", "HttpPort"): "5510", ("SET", "A"): ""}
