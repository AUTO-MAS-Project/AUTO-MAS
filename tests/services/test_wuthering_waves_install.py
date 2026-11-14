"""启动器多档位记录按当前选择定位客户端，旧记录保留目录兼容。"""

import base64
import json

import pytest

from app.services import wuthering_waves


def test_resource_records_use_existing_client_outside_launcher_tree(tmp_path):
    launcher = tmp_path / "launcher" / "launcher.exe"
    launcher.parent.mkdir()
    launcher.touch()
    client = (
        tmp_path
        / "separate-game-drive"
        / "Client"
        / "Binaries"
        / "Win64"
        / "Client-Win64-Shipping.exe"
    )
    client.parent.mkdir(parents=True)
    client.touch()
    install_dir = client.parents[3]
    # 同一官方启动器会保留 HD/UHD 等多条目录绑定；旧画质目录可能已移走。
    records = {
        "resources": json.dumps(
            [
                {"bundleName": "HD", "installDirPath": str(tmp_path / "removed")},
                {"bundleName": "UHD", "installDirPath": str(install_dir)},
            ]
        )
    }
    preference = launcher.parent / "kr_game_cache" / "kr_game_temp.bin"
    preference.parent.mkdir()
    decoded = json.dumps(records).encode("utf-8")
    preference.write_bytes(base64.b64encode(bytes(value ^ 0x63 for value in decoded)))

    assert wuthering_waves.resolve_wuthering_waves_process_path(launcher) == client


@pytest.mark.parametrize("game", ["Aki", "OtherGame"])
def test_launcher_selection_uses_current_game_instead_of_recent(tmp_path, game):
    launcher = tmp_path / "launcher.exe"
    launcher.touch()
    state = launcher.parent / "kr_game_cache" / "platform_ui_state.bin"
    state.parent.mkdir()
    decoded = json.dumps(
        {
            "activeGameScope": {"gameIdentity": game, "bundleName": "UHD"},
            "recentGames": {"Aki": {"bundleName": "HD"}},
        }
    ).encode("utf-8")
    state.write_bytes(base64.b64encode(bytes(value ^ 0x63 for value in decoded)))

    if game == "Aki":
        assert (
            wuthering_waves.read_wuthering_waves_launcher_selection(launcher) == "uhd"
        )
    else:
        with pytest.raises(ValueError):
            wuthering_waves.read_wuthering_waves_launcher_selection(launcher)


def test_corrupted_platform_selection_is_not_treated_as_legacy_launcher(tmp_path):
    launcher = tmp_path / "launcher.exe"
    launcher.touch()
    state = launcher.parent / "kr_game_cache" / "platform_ui_state.bin"
    state.parent.mkdir()
    state.write_bytes(b"invalid base64")

    with pytest.raises(ValueError):
        wuthering_waves.read_wuthering_waves_launcher_selection(launcher)


@pytest.mark.parametrize(
    ("selection", "selected_client_exists"),
    [("HD", True), ("UHD", True), ("HD", False)],
)
def test_resource_directory_follows_current_launcher_bundle(
    tmp_path, selection, selected_client_exists
):
    launcher = tmp_path / "launcher.exe"
    launcher.touch()
    resources = []
    for bundle in ("SD", "HD"):
        install = tmp_path / bundle
        client = install / "Client/Binaries/Win64/Client-Win64-Shipping.exe"
        client.parent.mkdir(parents=True)
        if bundle != selection or selected_client_exists:
            client.touch()
        resources.append({"bundleName": bundle, "installDirPath": str(install)})
    cache = tmp_path / "kr_game_cache"
    cache.mkdir()
    for name, payload in (
        (
            "kr_game_temp.bin",
            {
                "installDirPath": str(tmp_path / "SD"),
                "resources": json.dumps(resources),
            },
        ),
        (
            "platform_ui_state.bin",
            {"activeGameScope": {"gameIdentity": "Aki", "bundleName": selection}},
        ),
    ):
        raw = json.dumps(payload).encode("utf-8")
        (cache / name).write_bytes(
            base64.b64encode(bytes(value ^ 0x63 for value in raw))
        )

    if selection == "HD":
        assert wuthering_waves.resolve_wuthering_waves_install_dir(launcher) == (
            tmp_path / "HD"
        )
    else:
        with pytest.raises(ValueError):
            wuthering_waves.resolve_wuthering_waves_install_dir(launcher)
    if selection == "HD" and selected_client_exists:
        expected = tmp_path / "HD/Client/Binaries/Win64/Client-Win64-Shipping.exe"
        assert (
            wuthering_waves.resolve_wuthering_waves_process_path(launcher) == expected
        )
    else:
        # 当前档位记录或客户端缺失时，不能回退到仍有效的其它档位安装。
        with pytest.raises(ValueError):
            wuthering_waves.resolve_wuthering_waves_process_path(launcher)
