"""MaaFW 项目更新核心包：Mirror酱 查版本 → 自动分流 Mirror酱 / GitHub。

回包形状、错误码与 GitHub 资产命名均取自 2026-08-31 对线上 API 的实测契约，
不是凭记忆写的。所有网络访问都用 httpx.MockTransport 拦截，不联网。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

import app.core  # noqa: F401  (bootstraps app package the same way other tests do)

from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWInterface
from app.task.MaaFW.tools.core.automas_maafw_project_update import updater
from app.task.MaaFW.tools.core.automas_maafw_project_update.updater import (
    MaaFWProjectUpdateError,
    MaaFWProjectUpdateResult,
)
from app.utils.constants import MIRROR_ERROR_INFO


TEST_CDK = "0001bf52TESTCDK0000000001"
SHA256 = "5cfab41aeadc" + "0" * 52
GITHUB_REPO = "https://github.com/TanyaShue/MaaYYs"
MIRROR_DATA_BASE = {
    "version_number": 19,
    "channel": "stable",
    "os": "windows",
    "arch": "amd64",
    "release_note": "fix",
}
# code -> 服务端 msg 原文（实测）
CDK_ERROR_MESSAGES = {
    7001: "The cdk has expired",
    7002: "KEY_INVALID",
    7003: "Your cdk has reached the most downloads today",
    7004: "Current cdk cannot download this resource, please check your cdk type",
    7005: "Your cdk has been blocked",
}
CDK_STATUS_BY_CODE = {
    7001: "expired",
    7002: "invalid",
    7003: "quota",
    7004: "mismatched",
    7005: "blocked",
}
CONTRACT_FIELDS = (
    "updated",
    "previous_version",
    "version_name",
    "source",
    "cdk_status",
    "cdk_message",
    "cdk_expired_time",
    "message",
    "skipped_reason",
)


# --------------------------------------------------------------- fixtures


def _interface(**overrides: Any) -> MaaFWInterface:
    payload: dict[str, Any] = {
        "interface_version": 2,
        "name": "MaaYYs",
        "mirrorchyan_rid": "MaaYYs",
        "github": GITHUB_REPO,
        "version": "v3.14.8",
    }
    payload.update(overrides)
    return MaaFWInterface.model_validate(payload)


def _mirror_update_with_url(version: str = "v3.15.0") -> tuple[int, dict[str, Any]]:
    return 200, {
        "code": 0,
        "msg": "success",
        "data": {
            **MIRROR_DATA_BASE,
            "version_name": version,
            "url": "https://mirrorchyan.com/api/resources/download/signed-token",
            "sha256": SHA256,
            "update_type": "full",
            "cdk_expired_time": 1801411200,
        },
    }


def _mirror_update_without_url(version: str = "v3.15.0") -> tuple[int, dict[str, Any]]:
    return 200, {
        "code": 0,
        "msg": f"current resource latest version is {version}",
        "data": {**MIRROR_DATA_BASE, "version_name": version},
    }


def _mirror_latest(version: str = "v3.14.8") -> tuple[int, dict[str, Any]]:
    return 200, {
        "code": 0,
        "msg": "current version is latest",
        "data": {**MIRROR_DATA_BASE, "version_name": version},
    }


def _mirror_cdk_error(code: int, version: str = "v3.15.0") -> tuple[int, dict[str, Any]]:
    return 403, {
        "code": code,
        "msg": CDK_ERROR_MESSAGES[code],
        "data": {**MIRROR_DATA_BASE, "version_name": version},
    }


def _github_release(tag: str, assets: list[str]) -> dict[str, Any]:
    return {
        "tag_name": tag,
        "name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "id": index,
                "name": name,
                "size": 1024 * index,
                "browser_download_url": (
                    f"https://github.com/TanyaShue/MaaYYs/releases/download/{tag}/{name}"
                ),
            }
            for index, name in enumerate(assets, start=1)
        ],
    }


class FakeServer:
    """Route mirrorchyan.com / api.github.com requests to canned responses."""

    def __init__(
        self,
        mirror: tuple[int, dict[str, Any]] | Callable[[httpx.Request], httpx.Response],
        github: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.mirror = mirror
        self.github = github or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.url.host
        if host == "mirrorchyan.com":
            if callable(self.mirror):
                return self.mirror(request)
            status, body = self.mirror
            return httpx.Response(status, json=body, request=request)
        if host == "api.github.com":
            for tag, body in self.github.items():
                if request.url.path.endswith(f"/releases/tags/{tag}"):
                    return httpx.Response(200, json=body, request=request)
            return httpx.Response(404, json={"message": "Not Found"}, request=request)
        raise AssertionError(f"unexpected host {host}")

    def mirror_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == "mirrorchyan.com"]

    def github_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == "api.github.com"]


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _install(monkeypatch: pytest.MonkeyPatch, server: FakeServer) -> None:
    """Route every ``httpx.AsyncClient`` the updater opens through ``server``."""

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("proxy", None)
        kwargs["transport"] = httpx.MockTransport(server)
        return _REAL_ASYNC_CLIENT(*args, **kwargs)

    monkeypatch.setattr(updater.httpx, "AsyncClient", factory)


def _discover(
    interface: MaaFWInterface,
    config: dict[str, Any] | None,
    logs: list[str] | None = None,
) -> updater.MaaFWProjectUpdateDiscovery | None:
    return asyncio.run(
        updater.discover_maafw_project_update(
            interface,
            source_config=config,
            send_log=logs.append if logs is not None else None,
        )
    )


def _make_project(tmp_path: Path, name: str = "MaaYYs-win-x86_64-v3.14.8-MXU") -> Path:
    project = tmp_path / name
    project.mkdir()
    (project / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "MaaYYs",
                "mirrorchyan_rid": "MaaYYs",
                "github": GITHUB_REPO,
                "version": "v3.14.8",
            }
        ),
        encoding="utf-8",
    )
    return project


def _update(
    project: Path,
    interface: MaaFWInterface,
    *,
    mirror_cdk: str = "",
    logs: list[str] | None = None,
) -> MaaFWProjectUpdateResult:
    return asyncio.run(
        updater.update_maafw_project_if_needed(
            project,
            interface,
            mirror_cdk=mirror_cdk,
            channel="stable",
            send_log=logs.append if logs is not None else None,
            project_lock_already_held=False,
        )
    )


def _fake_apply(monkeypatch: pytest.MonkeyPatch) -> list[updater.MaaFWProjectUpdateCandidate]:
    applied: list[updater.MaaFWProjectUpdateCandidate] = []

    async def fake_apply(project_path: Path, candidate: Any, **kwargs: Any) -> dict[str, Any]:
        applied.append(candidate)
        return {
            "operationId": "op-1",
            "planId": candidate.plan_id,
            "finalFingerprint": "fp",
            "packageType": "full",
            "resumedFrom": 0,
        }

    monkeypatch.setattr(updater, "apply_maafw_project_update", fake_apply)
    return applied


# ------------------------------------------------------- CDK ok / absent


def test_valid_cdk_downloads_from_mirrorchyan(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer(_mirror_update_with_url())
    _install(monkeypatch, server)
    logs: list[str] = []

    discovery = _discover(_interface(), {"mirror_cdk": TEST_CDK, "channel": "stable"}, logs)

    assert discovery is not None and discovery.installable
    assert discovery.candidate is not None
    assert discovery.candidate.source == "mirrorchyan"
    assert discovery.package_source == "mirrorchyan"
    assert discovery.candidate.download_url.startswith(
        "https://mirrorchyan.com/api/resources/download/"
    )
    # Mirror酱 回了 sha256 就带进 candidate，下载后由 transport 校验
    assert discovery.candidate.sha256 == SHA256
    assert discovery.cdk_status == "ok"
    assert discovery.cdk_message == ""
    assert discovery.cdk_expired_time == 1801411200
    assert discovery.version_name == "v3.15.0"
    assert discovery.previous_version == "v3.14.8"
    assert discovery.skipped_reason is None
    assert "Mirror酱" in discovery.message
    assert not server.github_requests()
    params = server.mirror_requests()[0].url.params
    assert params["cdk"] == TEST_CDK
    assert params["current_version"] == "v3.14.8"
    assert params["channel"] == "stable"
    assert params["user_agent"]


def test_missing_cdk_with_update_falls_back_to_github(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = FakeServer(
        _mirror_update_without_url(),
        {"v3.15.0": _github_release("v3.15.0", ["MaaYYs-win-x86_64-v3.15.0-MXU.zip"])},
    )
    _install(monkeypatch, server)

    discovery = _discover(_interface(), {"channel": "stable"})

    assert discovery is not None and discovery.installable
    assert discovery.candidate is not None
    assert discovery.candidate.source == "github_release"
    assert discovery.package_source == "github"
    assert discovery.candidate.download_url.endswith("MaaYYs-win-x86_64-v3.15.0-MXU.zip")
    # 版本身份仍以 Mirror酱 为准
    assert discovery.version == "v3.15.0"
    assert discovery.candidate.version == "v3.15.0"
    assert discovery.cdk_status == "absent"
    assert discovery.cdk_message == ""
    assert discovery.cdk_expired_time is None
    assert "GitHub" in discovery.message
    assert "cdk" not in server.mirror_requests()[0].url.params
    assert server.github_requests()[0].url.path == (
        "/repos/TanyaShue/MaaYYs/releases/tags/v3.15.0"
    )


def test_missing_cdk_up_to_date_reports_skipped_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    server = FakeServer(_mirror_latest("v3.14.8"))
    _install(monkeypatch, server)
    project = _make_project(tmp_path)

    assert _discover(_interface(), {"channel": "stable"}) is None

    result = _update(project, _interface())
    assert result.checked is True
    assert result.updated is False
    assert result.update_available is False
    assert result.source is None
    assert result.previous_version == "v3.14.8"
    assert result.version_name == "v3.14.8"
    assert result.cdk_status == "absent"
    assert result.cdk_message == ""
    assert result.skipped_reason is not None and "已是最新" in result.skipped_reason
    assert not server.github_requests()


def test_missing_github_repo_reports_version_but_not_installable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    server = FakeServer(_mirror_update_without_url())
    _install(monkeypatch, server)
    interface = _interface(github=None)

    discovery = _discover(interface, {"channel": "stable"})
    assert discovery is not None
    assert discovery.installable is False
    assert discovery.candidate is None
    assert discovery.version_name == "v3.15.0"
    assert discovery.skipped_reason is not None
    assert "github" in discovery.skipped_reason.lower()
    assert "未配置 Mirror酱 CDK" in discovery.skipped_reason

    result = _update(_make_project(tmp_path), interface)
    assert result.updated is False
    assert result.update_available is True
    assert result.installable is False
    assert result.source is None
    assert result.version_name == "v3.15.0"
    assert result.skipped_reason == discovery.skipped_reason
    assert result.cdk_status == "absent"
    assert not server.github_requests()


# ------------------------------------------------------- CDK 7001-7005


@pytest.mark.parametrize("code", sorted(CDK_ERROR_MESSAGES))
def test_cdk_business_error_keeps_version_and_falls_back_to_github(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    server = FakeServer(
        _mirror_cdk_error(code),
        {"v3.15.0": _github_release("v3.15.0", ["MaaYYs-win-x86_64-v3.15.0-MXU.zip"])},
    )
    _install(monkeypatch, server)
    interface = _interface()

    # 底层检查：7xxx 不再抛错，version_name 照样回来
    mirror_discovery = asyncio.run(
        updater._check_mirrorchyan_update(
            interface,
            current_version="v3.14.8",
            mirror_cdk=TEST_CDK,
            channel="stable",
            proxy=None,
        )
    )
    assert mirror_discovery is not None
    assert mirror_discovery.version == "v3.15.0"
    assert mirror_discovery.candidate is None
    assert mirror_discovery.cdk_status == CDK_STATUS_BY_CODE[code]
    assert mirror_discovery.cdk_message == MIRROR_ERROR_INFO[code]
    assert mirror_discovery.provider_error_code == code

    # 上层分流：自动改走 GitHub，CDK 状态原样带出
    logs: list[str] = []
    discovery = _discover(interface, {"mirror_cdk": TEST_CDK, "channel": "stable"}, logs)
    assert discovery is not None and discovery.installable
    assert discovery.candidate is not None
    assert discovery.package_source == "github"
    assert discovery.candidate.download_url.endswith("MaaYYs-win-x86_64-v3.15.0-MXU.zip")
    assert discovery.cdk_status == CDK_STATUS_BY_CODE[code]
    assert discovery.cdk_message == MIRROR_ERROR_INFO[code]
    assert discovery.cdk_expired_time is None
    assert discovery.provider_error_code == code
    assert any(MIRROR_ERROR_INFO[code] in line for line in logs)


def test_cdk_error_when_already_latest_is_not_fatal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    server = FakeServer(_mirror_cdk_error(7003, version="v3.14.8"))
    _install(monkeypatch, server)

    result = _update(_make_project(tmp_path), _interface(), mirror_cdk=TEST_CDK)
    assert result.updated is False
    assert result.update_available is False
    assert result.cdk_status == "quota"
    assert result.cdk_message == MIRROR_ERROR_INFO[7003]
    assert result.version_name == "v3.14.8"
    assert result.skipped_reason is not None and "已是最新" in result.skipped_reason


# ------------------------------------------------ fatal MirrorChyan codes


@pytest.mark.parametrize(
    "code,http_status,server_message",
    [
        (8001, 404, "resource not found"),
        (8004, 400, "invalid channel"),
        (1001, 400, "invalid params"),
        (-1, 500, "internal error"),
    ],
)
def test_version_lookup_failures_raise_with_provider_code(
    monkeypatch: pytest.MonkeyPatch, code: int, http_status: int, server_message: str
) -> None:
    server = FakeServer((http_status, {"code": code, "msg": server_message, "data": None}))
    _install(monkeypatch, server)
    # 8001 的场景：多平台资源但没带 os/arch
    interface = _interface(mirrorchyan_multiplatform=code == 8001)

    with pytest.raises(MaaFWProjectUpdateError) as excinfo:
        _discover(interface, {"mirror_cdk": TEST_CDK, "channel": "stable"})

    assert excinfo.value.provider_error_code == code
    if code in MIRROR_ERROR_INFO:
        assert MIRROR_ERROR_INFO[code] in str(excinfo.value)
    else:
        assert MIRROR_ERROR_INFO[1] in str(excinfo.value)
    assert not server.github_requests()


def test_multiplatform_resource_sends_os_and_arch(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer(_mirror_latest("v2.26.0"))
    _install(monkeypatch, server)

    _discover(
        _interface(name="MaaEnd", mirrorchyan_rid="MaaEnd", version="v2.26.0", mirrorchyan_multiplatform=True),
        {"channel": "stable"},
    )

    params = server.mirror_requests()[0].url.params
    assert params["os"] == "win"
    assert params["arch"] == "x86_64"


# --------------------------------------------------- GitHub asset naming


def test_github_asset_selection_follows_release_naming() -> None:
    select = updater._select_github_release_asset

    maaend = _github_release(
        "v2.26.0",
        [
            "MaaEnd-linux-x86_64-v2.26.0.zip",
            "MaaEnd-macos-aarch64-v2.26.0.zip",
            "MaaEnd-win-x86_64-v2.26.0.zip",
        ],
    )
    url, reason = select(maaend, r"\.zip$", project_name="MaaEnd", prefer_windows_x64=True)
    assert reason == ""
    assert url.endswith("MaaEnd-win-x86_64-v2.26.0.zip")

    maayys = _github_release("v3.15.0", ["MaaYYs-win-x86_64-v3.15.0-MXU.zip"])
    url, reason = select(maayys, r"\.zip$", project_name="MaaYYs", prefer_windows_x64=True)
    assert reason == ""
    assert url.endswith("MaaYYs-win-x86_64-v3.15.0-MXU.zip")

    m9a = _github_release(
        "v4.7.1",
        ["M9A-win-x86_64-v4.7.1-MXU.zip", "M9A-win-x86_64-v4.7.1-MFAA.zip"],
    )
    url, reason = select(
        m9a, r"\.zip$", project_name="M9A", project_shell_hint="MXU", prefer_windows_x64=True
    )
    assert reason == "" and url.endswith("M9A-win-x86_64-v4.7.1-MXU.zip")
    url, reason = select(
        m9a,
        r"\.zip$",
        project_name="M9A",
        project_shell_hint="MFAAvalonia",
        prefer_windows_x64=True,
    )
    assert reason == "" and url.endswith("M9A-win-x86_64-v4.7.1-MFAA.zip")
    url, reason = select(m9a, r"\.zip$", project_name="M9A", prefer_windows_x64=True)
    assert url is None and "ambiguous" in reason


def test_m9a_variant_inferred_from_rid_when_no_shell_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = FakeServer(
        _mirror_update_without_url("v4.7.1"),
        {
            "v4.7.1": _github_release(
                "v4.7.1",
                ["M9A-win-x86_64-v4.7.1-MFAA.zip", "M9A-win-x86_64-v4.7.1-MXU.zip"],
            )
        },
    )
    _install(monkeypatch, server)
    interface = _interface(
        name="M9A",
        mirrorchyan_rid="M9A-MXU",
        github="https://github.com/MAA1999/M9A",
        version="v4.7.0",
    )

    discovery = _discover(interface, {"channel": "stable"})

    assert discovery is not None and discovery.candidate is not None
    assert discovery.candidate.download_url.endswith("M9A-win-x86_64-v4.7.1-MXU.zip")


def test_shell_hint_from_install_directory_name(tmp_path: Path) -> None:
    # 目录名带变体、interface.json 的 rid 没有后缀、目录里也没有 mxu.exe 之类标记
    project = _make_project(tmp_path, "MaaYYs-win-x86_64-v3.14.8-MXU")
    assert updater.detect_maafw_project_shell_hint(project) == "MXU"

    plain = _make_project(tmp_path, "SomeProject")
    assert updater.detect_maafw_project_shell_hint(plain) == ""


def test_github_advanced_parameters_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer(
        _mirror_update_without_url(),
        {"v3.15.0": _github_release("v3.15.0", ["MaaYYs-win-x86_64-v3.15.0-MXU.zip"])},
    )
    _install(monkeypatch, server)
    legacy_config = {
        "package_source": "github_release",
        "source": "github",
        "repo": "someone-else/other-repo",
        "github_repo": "someone-else/other-repo",
        "tag": "v0.0.1",
        "github_tag": "v0.0.1",
        "asset_pattern": r"never-matches\.7z$",
        "token": "ghp_should_not_be_sent",
        "channel": "stable",
    }

    discovery = _discover(_interface(), legacy_config)

    assert discovery is not None and discovery.installable
    request = server.github_requests()[0]
    assert request.url.path == "/repos/TanyaShue/MaaYYs/releases/tags/v3.15.0"
    assert "authorization" not in {k.lower() for k in request.headers}


def test_github_lookup_failure_does_not_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def github_rate_limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "API rate limit exceeded"}, request=request)

    class RateLimitedServer(FakeServer):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            if request.url.host == "api.github.com":
                self.requests.append(request)
                return github_rate_limited(request)
            return super().__call__(request)

    server = RateLimitedServer(_mirror_update_without_url())
    _install(monkeypatch, server)

    result = _update(_make_project(tmp_path), _interface())
    assert result.updated is False
    assert result.update_available is True
    assert result.installable is False
    assert result.skipped_reason is not None and "GitHub" in result.skipped_reason
    assert result.version_name == "v3.15.0"


# --------------------------------------------------------- result object


def _assert_contract_fields(obj: Any) -> None:
    for name in CONTRACT_FIELDS:
        sentinel = object()
        assert getattr(obj, name, sentinel) is not sentinel, name
        assert obj.get(name, sentinel) is not sentinel, name
        assert obj.get(name) == getattr(obj, name), name
    assert obj.get("definitely-not-a-field", "dflt") == "dflt"


def test_update_result_exposes_contract_fields_for_mirrorchyan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    server = FakeServer(_mirror_update_with_url())
    _install(monkeypatch, server)
    applied = _fake_apply(monkeypatch)

    result = _update(_make_project(tmp_path), _interface(), mirror_cdk=TEST_CDK)

    _assert_contract_fields(result)
    assert result.updated is True
    assert result.previous_version == "v3.14.8"
    assert result.version_name == "v3.15.0"
    assert result.source == "mirrorchyan"
    assert result.cdk_status == "ok"
    assert result.cdk_message == ""
    assert result.cdk_expired_time == 1801411200
    assert result.skipped_reason is None
    assert "v3.15.0" in result.message
    assert applied and applied[0].sha256 == SHA256


def test_update_result_exposes_contract_fields_for_github_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    server = FakeServer(
        _mirror_cdk_error(7001),
        {"v3.15.0": _github_release("v3.15.0", ["MaaYYs-win-x86_64-v3.15.0-MXU.zip"])},
    )
    _install(monkeypatch, server)
    applied = _fake_apply(monkeypatch)

    result = _update(_make_project(tmp_path), _interface(), mirror_cdk=TEST_CDK)

    _assert_contract_fields(result)
    assert result.updated is True
    assert result.source == "github"
    assert result.cdk_status == "expired"
    assert result.cdk_message == MIRROR_ERROR_INFO[7001]
    assert result.cdk_expired_time is None
    assert result.version_name == "v3.15.0"
    assert applied and applied[0].source == "github_release"


def test_discovery_exposes_contract_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer(_mirror_update_with_url())
    _install(monkeypatch, server)

    discovery = _discover(_interface(), {"mirror_cdk": TEST_CDK})

    assert discovery is not None
    _assert_contract_fields(discovery)
    assert discovery.updated is False


# ------------------------------------------------------------- CDK 保密


def test_cdk_never_appears_in_logs_or_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    logs: list[str] = []
    server = FakeServer(
        _mirror_cdk_error(7003),
        {"v3.15.0": _github_release("v3.15.0", ["MaaYYs-win-x86_64-v3.15.0-MXU.zip"])},
    )
    _install(monkeypatch, server)
    _fake_apply(monkeypatch)
    _update(_make_project(tmp_path), _interface(), mirror_cdk=TEST_CDK, logs=logs)
    assert logs, "expected update logs"
    assert all(TEST_CDK not in line for line in logs)
    assert all(TEST_CDK[:8] not in line for line in logs)

    # 传输层错误信息里带完整 URL（含 cdk=...）也必须打码
    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection refused for {request.url}", request=request)

    logs.clear()
    _install(monkeypatch, FakeServer(failing))
    with pytest.raises(MaaFWProjectUpdateError) as excinfo:
        _update(_make_project(tmp_path, "Other"), _interface(), mirror_cdk=TEST_CDK, logs=logs)
    assert TEST_CDK not in str(excinfo.value)
    assert "cdk=***" in str(excinfo.value)
    assert all(TEST_CDK not in line for line in logs)
