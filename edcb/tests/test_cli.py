from edcb_provision import cli, legacy


def test_allow_setting(tree, capsys):
    env = {"EDCB_PROVISION_ROOT": tree.root}
    assert cli.main(["allow-setting", "status"], env) == 0
    assert "not set (denied)" in capsys.readouterr().out
    assert cli.main(["allow-setting", "on"], env) == 0
    assert "allowed" in capsys.readouterr().out
    assert legacy.get(tree.root) is True
    assert cli.main(["allow-setting", "off"], env) == 0
    assert legacy.get(tree.root) is False


def test_allow_setting_warns_about_unpatched_util_lua(tree, capsys):
    env = {"EDCB_PROVISION_ROOT": tree.root}
    import os

    os.makedirs(os.path.join(tree.root, "HttpPublic", "legacy"))
    with open(os.path.join(tree.root, "HttpPublic", "legacy", "util.lua"), "w") as f:
        f.write("ALLOW_SETTING=false\n")
    assert cli.main(["allow-setting", "on"], env) == 1
    assert "does not read this switch" in capsys.readouterr().err


def test_provision_diff(tree, capsys):
    env = {
        "EDCB_PROVISION_ROOT": tree.root,
        "EDCB_PROVISION_OVERRIDES": tree.overrides,
        "EDCB_PROVISION_SHARE": tree.share,
        "EDCB_PROVISION_EDCB_INI": tree.edcb_ini,
    }
    assert cli.main(["provision", "--diff"], env) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "CompatFlags" in out
    import os

    assert os.listdir(tree.root) == []
