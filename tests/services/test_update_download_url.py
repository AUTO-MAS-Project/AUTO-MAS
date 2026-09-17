import pytest

from app.services.update import _UpdateHandler


def _handler(remote_version: str = "v1.2.3") -> _UpdateHandler:
    handler = _UpdateHandler()
    handler.remote_version = remote_version
    return handler


def test_download_url_builds_all_pure_sources() -> None:
    handler = _handler("v9.9.9")

    assert (
        handler._get_download_url("GitHub")
        == "https://github.com/AUTO-MAS-Project/AUTO-MAS/releases/download/"
        "v9.9.9/AUTO-MAS-Lite-Setup-v9.9.9-x64.zip"
    )
    assert (
        handler._get_download_url("AutoSite")
        == "https://download.auto-mas.top/d/AUTO-MAS/AUTO-MAS-Lite-Setup-v9.9.9-x64.zip"
    )
    assert (
        handler._get_download_url("CNB")
        == "https://cnb.cool/AUTO-MAS-Project/AUTO-MAS/-/releases/download/"
        "v9.9.9/AUTO-MAS-Lite-Setup-v9.9.9-x64.zip"
    )


def test_download_url_prefers_frozen_version_and_mirror_override() -> None:
    handler = _handler("v1.0.0")

    assert "v2.0.0" in handler._get_download_url("GitHub", download_version="v2.0.0")
    assert (
        handler._get_download_url(
            "MirrorChyan", mirror_chyan_download_url="https://mirror.example/once"
        )
        == "https://mirror.example/once"
    )


def test_mirror_chyan_uses_cached_url_when_no_override() -> None:
    handler = _handler()
    handler.mirror_chyan_download_url = "https://mirror.example/cached"

    assert handler._get_download_url("MirrorChyan") == "https://mirror.example/cached"


def test_mirror_chyan_without_url_falls_back_to_autosite() -> None:
    handler = _handler()
    handler.mirror_chyan_download_url = None

    assert (
        handler._get_download_url("MirrorChyan")
        == "https://download.auto-mas.top/d/AUTO-MAS/AUTO-MAS-Lite-Setup-v1.2.3-x64.zip"
    )


def test_unknown_download_source_raises_value_error() -> None:
    handler = _handler()

    with pytest.raises(ValueError, match=r"未知的下载源: bogus"):
        handler._get_download_url("bogus")


def test_download_url_requires_remote_version() -> None:
    handler = _UpdateHandler()

    with pytest.raises(ValueError, match=r"未检测到可用的远程版本"):
        handler._get_download_url("GitHub")
