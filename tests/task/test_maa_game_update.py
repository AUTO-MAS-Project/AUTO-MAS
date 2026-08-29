import asyncio
from pathlib import Path

import pytest

from app.task.MAA.tools import game_update
from app.task.MAA.tools.game_update import GameVersion, ensure_game_updated


def test_client_version_comparison() -> None:
    assert game_update.is_client_outdated("2.7.60", "2.7.61")
    assert game_update.is_client_outdated("2.6.99", "2.7.0")
    assert not game_update.is_client_outdated("2.7.61", "2.7.61")
    assert not game_update.is_client_outdated("2.7.62", "2.7.61")

    # 段数不等时按缺失段补 0 比较
    assert game_update.is_client_outdated("2.7", "2.7.1")
    assert not game_update.is_client_outdated("2.7.0", "2.7")

    # 任一侧解析不出数字时不下判断，避免误拦正常代理
    assert not game_update.is_client_outdated("unknown", "2.7.61")
    assert not game_update.is_client_outdated("2.7.61", "")


def _patch_versions(
    monkeypatch: pytest.MonkeyPatch,
    remote: GameVersion | None,
    installed: str | None,
) -> None:
    async def fake_fetch(server: str) -> GameVersion | None:
        return remote

    async def fake_installed(
        adb_path: Path | None, adb_address: str, package_name: str
    ) -> str | None:
        return installed

    monkeypatch.setattr(game_update, "fetch_game_version", fake_fetch)
    monkeypatch.setattr(game_update, "get_installed_client_version", fake_installed)


def _run(**overrides) -> game_update.GameUpdateResult:
    kwargs = {
        "adb_path": None,
        "adb_address": "127.0.0.1:16384",
        "server": "Official",
        "package_name": "com.hypergryph.arknights",
        "apk_dir": Path("data/GameApk"),
        "if_auto_install": True,
        "time_limit": 60,
    }
    kwargs.update(overrides)
    return asyncio.run(ensure_game_updated(**kwargs))


def test_up_to_date_reports_resource_version(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_versions(
        monkeypatch, GameVersion("2.7.61", "26-08-17-11-25-42_dbc172"), "2.7.61"
    )

    result = _run()

    assert result.status == "UpToDate"
    assert result.resource_version == "26-08-17-11-25-42_dbc172"


def test_non_official_server_requires_manual_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_versions(monkeypatch, GameVersion("2.7.61", "res-a"), "2.7.60")

    result = _run(server="Bilibili", package_name="com.hypergryph.arknights.bilibili")

    assert result.status == "NeedManualUpdate"
    assert "仅官服支持自动更新" in result.message
    assert result.resource_version == "res-a"


def test_auto_install_disabled_requires_manual_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_versions(monkeypatch, GameVersion("2.7.61", "res-a"), "2.7.60")

    result = _run(if_auto_install=False)

    assert result.status == "NeedManualUpdate"
    assert "未开启自动安装" in result.message


def test_unreadable_installed_version_does_not_block_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_versions(monkeypatch, GameVersion("2.7.61", "res-a"), None)

    result = _run()

    assert result.status == "Skipped"
    assert result.resource_version == "res-a"


def test_missing_adb_address_skips_check(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_versions(monkeypatch, GameVersion("2.7.61", "res-a"), "2.7.60")

    assert _run(adb_address="Unknown").status == "Skipped"


def test_server_without_version_api_skips_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_versions(monkeypatch, None, "2.7.60")

    assert _run(server="YoStarEN").status == "Skipped"
