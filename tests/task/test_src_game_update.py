import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.task.SRC.tools import game_update
from app.task.SRC.tools.game_update import UpdateSource, ensure_game_updated
from app.utils import game_apk
from app.utils.constants import STARRAIL_CN_UPDATE_LINK_URL

_CN_APK_LOCATION = (
    "https://autopatchcn.bhsr.com/client/4.5.0/20260813_Ae542B66B5C7"
    "/Android_apk/gw_An/StarRail_4.5.0.apk"
)
"""国服官服更新入口 302 后的真实地址（2026-09-16 实测，2026-09-17 复测仍为单跳）"""

_MIDDLE_LOCATION = "https://redirect.example.com/step2"
"""多跳场景的中间跳转地址，文件名不含版本号"""

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


class _FakeStreamResponse:
    def __init__(self, url: str, location: str | None) -> None:
        self.url = url
        self.is_redirect = location is not None
        self.headers = {"location": location} if location else {}


class _FakeStream:
    def __init__(self, url: str, location: str | None) -> None:
        self._url = url
        self._location = location

    async def __aenter__(self) -> _FakeStreamResponse:
        return _FakeStreamResponse(self._url, self._location)

    async def __aexit__(self, *_args: object) -> bool:
        return False


class _FakeAsyncClient:
    def __init__(self, routes: dict[str, str | None], **_kwargs: object) -> None:
        self._routes = routes

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    def stream(self, _method: str, url: str, **_kwargs: object) -> _FakeStream:
        return _FakeStream(url, self._routes.get(url))


def _patch_redirect(
    monkeypatch: pytest.MonkeyPatch, routes: dict[str, str | None]
) -> None:
    """按 URL 精确映射跳转目标；未登记的 URL 视为不再跳转"""

    def factory(*_args: object, **_kwargs: object) -> _FakeAsyncClient:
        return _FakeAsyncClient(routes)

    monkeypatch.setattr(game_apk.httpx, "AsyncClient", factory)


def test_resolve_download_link_parses_cn_apk(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_redirect(monkeypatch, {"https://link.example.com/cn": _CN_APK_LOCATION})

    resolved = asyncio.run(
        game_update._resolve_download_link("https://link.example.com/cn")
    )

    assert resolved is not None
    assert resolved[0].endswith("StarRail_4.5.0.apk")
    assert resolved[1] == "4.5.0"


def test_resolve_download_link_follows_multiple_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 中间跳转地址的文件名不含版本号，跟随到最终地址后才解析成功
    _patch_redirect(
        monkeypatch,
        {
            "https://link.example.com/cn": _MIDDLE_LOCATION,
            _MIDDLE_LOCATION: _CN_APK_LOCATION,
        },
    )

    resolved = asyncio.run(
        game_update._resolve_download_link("https://link.example.com/cn")
    )

    assert resolved is not None
    assert resolved[0].endswith("StarRail_4.5.0.apk")
    assert resolved[1] == "4.5.0"


def test_resolve_download_link_gives_up_after_max_hops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 构造一条明显超过跟随上限（5 跳）的重定向链
    routes: dict[str, str | None] = {
        f"https://hop{i}.example.com/next": f"https://hop{i + 1}.example.com/next"
        for i in range(10)
    }
    routes["https://link.example.com/cn"] = "https://hop0.example.com/next"
    _patch_redirect(monkeypatch, routes)

    assert (
        asyncio.run(
            game_update._resolve_download_link("https://link.example.com/cn")
        )
        is None
    )


def test_fetch_update_source_non_apk_cannot_auto_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_redirect(monkeypatch, {STARRAIL_CN_UPDATE_LINK_URL: _NON_APK_LOCATION})

    source = asyncio.run(game_update.fetch_update_source("CN-Official"))

    # 入口万一不指向安卓包：仍能取到版本，但不能拿去 adb install
    assert source is not None
    assert source.version == "4.5.0"
    assert not source.can_auto_install


def test_resolve_download_link_without_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_redirect(monkeypatch, {"https://link.example.com": None})

    assert (
        asyncio.run(game_update._resolve_download_link("https://link.example.com"))
        is None
    )


def test_fetch_update_source_cn_can_auto_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_redirect(monkeypatch, {STARRAIL_CN_UPDATE_LINK_URL: _CN_APK_LOCATION})

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


class _FakeDownloadStream:
    """流式响应桩：按预设的分块序列输出内容"""

    def __init__(self, chunks: list[bytes], headers: dict[str, str], delay: float):
        self._chunks = chunks
        self._delay = delay
        self.headers = headers
        self.is_redirect = False
        self.url = "https://cdn.example.com/StarRail_4.5.0.apk"

    def raise_for_status(self) -> None:
        return None

    async def __aenter__(self) -> "_FakeDownloadStream":
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    async def aiter_bytes(self, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield chunk


class _FakeDownloadClient:
    """下载客户端桩：跳过重定向直接给出最终响应"""

    def __init__(
        self,
        chunks: list[bytes],
        headers: dict[str, str],
        delay: float = 0.0,
        **_kwargs: object,
    ) -> None:
        self._chunks = chunks
        self._headers = headers
        self._delay = delay

    async def __aenter__(self) -> "_FakeDownloadClient":
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    def stream(self, *_args: object, **_kwargs: object) -> _FakeDownloadStream:
        return _FakeDownloadStream(self._chunks, self._headers, self._delay)


def test_download_apk_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """正常流式下载：内容落盘、体积达标后重命名为目标文件"""

    size = game_apk.APK_MIN_BYTES + 1
    monkeypatch.setattr(
        game_apk.httpx,
        "AsyncClient",
        lambda *_a, **_kw: _FakeDownloadClient(
            [b"\0" * size], {"content-length": str(size)}
        ),
    )

    target = tmp_path / "game.apk"
    result = asyncio.run(
        game_apk.download_apk("https://cdn.example.com/StarRail_4.5.0.apk", target)
    )

    assert result == target
    assert target.stat().st_size == size
    assert not Path(f"{target}.downloading").exists()


def test_download_apk_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """下载总时长超过上限：抛出带"超时"的异常，且临时文件被清理"""

    chunks = [b"\0" * (1024 * 1024)] * 10

    def factory(*_a: object, **_kw: object) -> _FakeDownloadClient:
        return _FakeDownloadClient(
            chunks, {"content-length": "0"}, delay=0.02
        )

    monkeypatch.setattr(game_apk.httpx, "AsyncClient", factory)

    target = tmp_path / "game.apk"
    with pytest.raises(RuntimeError, match="超时"):
        asyncio.run(
            game_apk.download_apk(
                "https://cdn.example.com/StarRail_4.5.0.apk",
                target,
                timeout=0.05,
            )
        )

    assert not Path(f"{target}.downloading").exists()
