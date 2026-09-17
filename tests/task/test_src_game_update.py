import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.task.SRC.tools import game_update
from app.task.SRC.tools.game_update import UpdateSource, ensure_game_updated
from app.utils import game_apk

_CN_APK_LOCATION = (
    "https://autopatchcn.bhsr.com/client/4.5.0/20260813_Ae542B66B5C7"
    "/Android_apk/gw_An/StarRail_4.5.0.apk"
)
"""国服官服更新入口 302 后的真实地址（2026-09-16 实测）"""

_NON_APK_LOCATION = (
    "https://cdn.example.com/hkrpg/4.5.0/20260813_Ae542B66B5C7"
    "/Windows_pkg/4.5.0_setup.exe"
)
"""入口跳转后不是安卓安装包的情形，用于兜底分支"""


def test_client_version_comparison() -> None:
    assert game_update.is_client_outdated("4.4.0", "4.5.0")
    assert game_update.is_client_outdated("4.4.9", "4.5.0")
    assert not game_update.is_client_outdated("4.5.0", "4.5.0")
    assert not game_update.is_client_outdated("4.5.1", "4.5.0")

    # 段数不等时按缺失段补 0 比较（入口可能只给出 4.5 这种两段版本）
    assert game_update.is_client_outdated("4.4.0", "4.5")
    assert not game_update.is_client_outdated("4.5.0", "4.5")

    # 任一侧解析不出数字时不下判断，避免误拦正常代理
    assert not game_update.is_client_outdated("unknown", "4.5.0")
    assert not game_update.is_client_outdated("4.5.0", "")


class _FakeResponse:
    def __init__(self, location: str | None) -> None:
        self.headers = {"location": location} if location else {}
        self.request = SimpleNamespace(url="https://link.example.com/android_default")


class _FakeAsyncClient:
    def __init__(self, location: str | None, **_kwargs: object) -> None:
        self._location = location

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    async def get(self, url: str, **_kwargs: object) -> _FakeResponse:
        return _FakeResponse(self._location)


def _patch_redirect(monkeypatch: pytest.MonkeyPatch, location: str | None) -> None:
    def factory(*_args: object, **_kwargs: object) -> _FakeAsyncClient:
        return _FakeAsyncClient(location)

    monkeypatch.setattr(game_apk.httpx, "AsyncClient", factory)


def test_resolve_download_link_parses_cn_apk(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_redirect(monkeypatch, _CN_APK_LOCATION)

    resolved = asyncio.run(game_apk.resolve_download_link("https://link.example.com/cn"))

    assert resolved is not None
    assert resolved[0].endswith("StarRail_4.5.0.apk")
    assert resolved[1] == "4.5.0"


def test_fetch_update_source_non_apk_cannot_auto_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_redirect(monkeypatch, _NON_APK_LOCATION)

    source = asyncio.run(game_update.fetch_update_source("CN-Official"))

    # 入口万一不指向安卓包：仍能取到版本，但不能拿去 adb install
    assert source is not None
    assert source.version == "4.5.0"
    assert not source.can_auto_install


def test_resolve_download_link_without_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_redirect(monkeypatch, None)

    assert asyncio.run(game_apk.resolve_download_link("https://link.example.com")) is None


def test_fetch_update_source_cn_can_auto_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_redirect(monkeypatch, _CN_APK_LOCATION)

    source = asyncio.run(game_update.fetch_update_source("CN-Official"))

    assert source is not None
    assert source.version == "4.5.0"
    assert source.can_auto_install


def test_fetch_update_source_without_public_entry() -> None:
    # 渠道服不在映射表中，未发请求就应返回 None
    assert asyncio.run(game_update.fetch_update_source("CN-Bilibili")) is None


def _patch_installed(monkeypatch: pytest.MonkeyPatch, installed: str | None) -> None:
    async def fake_installed(
        adb_path: Path | None, adb_address: str, package_name: str
    ) -> str | None:
        return installed

    monkeypatch.setattr(game_update, "get_installed_client_version", fake_installed)


def _patch_source(
    monkeypatch: pytest.MonkeyPatch,
    version: str | None,
    can_auto_install: bool = True,
) -> None:
    async def fake_fetch(server: str) -> UpdateSource | None:
        if version is None:
            return None
        suffix = "apk" if can_auto_install else "exe"
        return UpdateSource(
            version=version,
            download_url=f"https://cdn.example.com/StarRail_{version}.{suffix}",
            can_auto_install=can_auto_install,
        )

    monkeypatch.setattr(game_update, "fetch_update_source", fake_fetch)


def _run(**overrides: object) -> game_update.GameUpdateResult:
    kwargs: dict[str, object] = {
        "adb_path": None,
        "adb_address": "127.0.0.1:16384",
        "server": "CN-Official",
        "package_name": "com.miHoYo.hkrpg",
        "apk_dir": Path("data/GameApk"),
        "if_auto_install": True,
        "time_limit": 60,
    }
    kwargs.update(overrides)
    return asyncio.run(ensure_game_updated(**kwargs))  # type: ignore[arg-type]


def test_up_to_date_skips_update(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_source(monkeypatch, "4.5.0")
    _patch_installed(monkeypatch, "4.5.0")

    assert _run().status == "UpToDate"


def test_non_apk_source_requires_manual_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_source(monkeypatch, "4.5.0", can_auto_install=False)
    _patch_installed(monkeypatch, "4.4.0")

    result = _run()

    assert result.status == "NeedManualUpdate"
    assert "未提供安卓安装包直链" in result.message


def test_auto_install_disabled_requires_manual_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_source(monkeypatch, "4.5.0")
    _patch_installed(monkeypatch, "4.4.0")

    result = _run(if_auto_install=False)

    assert result.status == "NeedManualUpdate"
    assert "未开启自动安装" in result.message


def test_unreadable_installed_version_does_not_block_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_source(monkeypatch, "4.5.0")
    _patch_installed(monkeypatch, None)

    assert _run().status == "Skipped"


def test_missing_adb_address_skips_check(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_source(monkeypatch, "4.5.0")
    _patch_installed(monkeypatch, "4.4.0")

    assert _run(adb_address="Unknown").status == "Skipped"


def test_unavailable_source_skips_check(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_source(monkeypatch, None)
    _patch_installed(monkeypatch, "4.4.0")

    assert _run().status == "Skipped"


def test_server_without_public_entry_skips_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_installed(monkeypatch, "4.4.0")

    assert _run(server="CN-Bilibili").status == "Skipped"
