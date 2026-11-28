"""游戏升级在真实隔离文件上保留设备身份、账号覆盖及代理计次。"""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.core.config.game_upgrade import RECORD, migrate_game_documents
from app.utils import io


def collection(*entries):
    return {
        "order": [{"uid": uid, "type": kind} for uid, kind, _ in entries],
        "data": {uid: payload for uid, _, payload in entries},
    }


@pytest.mark.parametrize("interrupt", [False, True])
def test_mixed_emulators_and_account_paths_survive_upgrade_and_retry(
    tmp_path, monkeypatch, interrupt
):
    """混合安装拆分、同路径复用、多路径独立，并保留已成功账号计次。"""
    emulator, script_id, first, second, same_path, inherited = (
        str(uuid4()) for _ in range(6)
    )
    game_a = tmp_path / "client-a.exe"
    game_b = tmp_path / "client-b.exe"
    game_a.touch()
    game_b.touch()
    emulators = collection(
        (
            emulator,
            "EmulatorConfig",
            {
                "Info": {
                    "Type": "emulator2",
                    "Name": "mixed",
                    "Paths": [
                        {
                            "pathId": "mu",
                            "type": "mumu",
                            "installPath": str(tmp_path / "missing-mumu"),
                            "alias": "MuMu",
                        },
                        {
                            "pathId": "ld",
                            "type": "ldplayer",
                            "installPath": str(tmp_path / "missing-ld"),
                            "alias": "LD",
                        },
                    ],
                    "Slots": [
                        {
                            "slot": 2,
                            "pathId": "mu",
                            "nativeIndex": "0",
                            "state": "active",
                        },
                        {
                            "slot": 5,
                            "pathId": "ld",
                            "nativeIndex": "1",
                            "state": "active",
                        },
                        {
                            "slot": 7,
                            "pathId": "",
                            "nativeIndex": "",
                            "state": "tombstone",
                        },
                    ],
                    "Baselines": {"2": {"width": 1280}},
                    "ConfigGuard": True,
                }
            },
        )
    )
    emulator_script = str(uuid4())
    scripts = collection(
        (emulator_script, "SrcConfig", {"Emulator": {"Id": emulator, "Index": "2"}}),
        (
            script_id,
            "ZzzOdConfig",
            {
                "Game": {"Enabled": False, "CloseOnFinish": False, "Path": str(game_b)},
                "UserData": collection(
                    (
                        first,
                        "ZzzOdUserConfig",
                        {"Game": {"GamePath": str(game_a)}, "Data": {"ProxyTimes": 4}},
                    ),
                    (
                        second,
                        "ZzzOdUserConfig",
                        {"Game": {"GamePath": str(game_b)}, "Data": {"ProxyTimes": 7}},
                    ),
                    (
                        same_path,
                        "ZzzOdUserConfig",
                        {"Game": {"GamePath": str(game_a)}, "Data": {"ProxyTimes": 2}},
                    ),
                    (inherited, "ZzzOdUserConfig", {"Data": {"ProxyTimes": 1}}),
                ),
            },
        ),
    )
    io.write_file(tmp_path / "emulators.yaml", emulators)
    io.write_file(tmp_path / "scripts.yaml", scripts)
    original = deepcopy(scripts)
    write = io.write_file
    if interrupt:
        with monkeypatch.context() as failure:

            def fail_scripts(path, payload, **kwargs):
                if path == tmp_path / "scripts.yaml":
                    raise OSError("disk write interrupted")
                return write(path, payload, **kwargs)

            failure.setattr(io, "write_file", fail_scripts)
            with pytest.raises(OSError):
                migrate_game_documents(tmp_path)
        assert io.read_dict_file(tmp_path / "scripts.yaml") == original
        partial_games = io.read_dict_file(tmp_path / "games.yaml")

    migrate_game_documents(tmp_path)
    games = io.read_dict_file(tmp_path / "games.yaml")
    migrated = io.read_dict_file(tmp_path / "scripts.yaml")
    if interrupt:
        assert games == partial_games
    assert len(games["order"]) == 4
    users = migrated["data"][script_id]["UserData"]["data"]
    assert users[second]["game"] == migrated["data"][script_id]["game"]
    assert "game" not in users[inherited]
    assert users[first]["game"] == users[same_path]["game"]
    assert users[first]["game"]["game_id"] != users[second]["game"]["game_id"]
    assert [users[uid]["Data"]["ProxyTimes"] for uid in (first, second, same_path)] == [
        4,
        7,
        2,
    ]
    assert migrated["data"][script_id]["Game"] == original["data"][script_id]["Game"]
    binding = migrated["data"][emulator_script]["game"]
    mu = games["data"][binding["game_id"]]
    assert mu["devices"]["data"][binding["device_id"]]["info"]["index"] == "0"
    assert mu["info"]["baselines"][binding["device_id"]] == {"width": 1280}
    assert any(
        device["info"]["slot"] == 7 and device["info"]["tombstone"]
        for device in mu["devices"]["data"].values()
    )
    assert io.read_dict_file(tmp_path / "legacy-game" / "scripts.yaml") == original
    before = (
        (tmp_path / "games.yaml").read_bytes(),
        (tmp_path / "scripts.yaml").read_bytes(),
    )
    migrate_game_documents(tmp_path)
    assert before == (
        (tmp_path / "games.yaml").read_bytes(),
        (tmp_path / "scripts.yaml").read_bytes(),
    )
    assert io.read_dict_file(tmp_path / RECORD)["complete"]


def test_legacy_json_account_paths_are_mapped_before_schema_conversion(tmp_path):
    sid, uid = str(uuid4()), str(uuid4())
    client = tmp_path / "game.exe"
    client.touch()
    user = {"Switch": {"GamePath": str(client)}, "Data": {"ProxyTimes": 3}}
    scripts = {
        "instances": [{"uid": sid, "type": "BetterGIConfig"}],
        sid: {
            "SubConfigsInfo": {
                "UserData": {
                    "instances": [{"uid": uid, "type": "BetterGIUserConfig"}],
                    uid: user,
                }
            },
        },
    }
    io.write_file(tmp_path / "ScriptConfig.json", scripts)
    migrate_game_documents(tmp_path)
    target = io.read_dict_file(tmp_path / "ScriptConfig.json")
    mapped = target[sid]["SubConfigsInfo"]["UserData"][uid]
    assert (
        mapped["game"]["game_id"] in io.read_dict_file(tmp_path / "games.yaml")["data"]
    )
    assert mapped["Data"] == user["Data"]


@pytest.mark.parametrize(
    ("field", "value", "target_field", "expected"),
    [
        ("Arguments", "-krqlv=sd", "arguments", ["-krqlv=sd"]),
        ("Type", "Client", "launch_with_launcher", False),
        ("Path", "other-launcher.exe", "launch_path", "other-launcher.exe"),
    ],
    ids=["arguments", "launch-mode", "launcher-path"],
)
def test_shared_client_with_different_launch_settings_migrates_separately(
    tmp_path, field, value, target_field, expected
):
    first, second = str(uuid4()), str(uuid4())
    client = tmp_path / "game.exe"
    launcher = tmp_path / "launcher.exe"
    client.touch()
    launcher.touch()
    game = {
        "ClientPath": str(client),
        "Path": str(launcher),
        "Type": "Launcher",
        "Arguments": "-krqlv=hd",
    }
    if field == "Path":
        (tmp_path / value).touch()
        value = expected = str(tmp_path / value)
    script_path = tmp_path / "scripts.yaml"
    io.write_file(
        script_path,
        collection(
            (first, "OkwwConfig", {"Game": game}),
            (second, "OkwwConfig", {"Game": {**game, field: value}}),
        ),
    )

    migrate_game_documents(tmp_path)

    bindings = io.read_dict_file(script_path)["data"]
    games = io.read_dict_file(tmp_path / "games.yaml")["data"]
    first_id, second_id = (bindings[uid]["game"]["game_id"] for uid in (first, second))
    assert first_id != second_id
    first_info = games[first_id]["info"]
    assert first_info["arguments"] == ["-krqlv=hd"]
    assert first_info["launch_with_launcher"] is True
    assert first_info["launch_path"] == str(launcher)
    assert games[second_id]["info"][target_field] == expected
