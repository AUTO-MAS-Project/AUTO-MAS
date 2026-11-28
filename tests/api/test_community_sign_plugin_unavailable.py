"""签到插件未启用时，用户看到的是「去插件市场安装」而不是一次签到失败。

守的是：
- 插件服务缺失时，编排层抛的是专用异常，不是通用 RuntimeError；
- 手动签到接口据此回 503 并原样带出安装引导，而不是 500「签到失败」；
- 定时触发遇到同一情况只记一行警告，不让调度把这次触发当成任务失败。

破坏方式：把 _run_plugin_sign_in 的专用异常改回 RuntimeError、去掉 API 的
503 分支、或在 timer 里让该异常走 task 来源的 re-raise，对应用例随即变红。
"""

import pytest

import app.core.community.sign as community_sign
from app.api.community import accounts as community_api
from app.core.community.sign import CommunitySignPluginUnavailableError
from app.core.plugin import Plugin as plugin_core
from app.plugin.errors import PluginError

SERVICE_NAME = "signflow.sign"


def _missing_service(*_args, **_kwargs):
    """模拟插件未安装：服务表里没有签到服务。"""

    raise PluginError(f"服务未注册: {SERVICE_NAME}")


@pytest.fixture
def no_plugin_service(monkeypatch):
    """让服务注册表按「未注册」响应，并挡掉系统时间自检的网络请求。"""

    monkeypatch.setattr(plugin_core.services, "require", _missing_service)
    monkeypatch.setattr(
        community_sign._tool_community_sign_provider,
        "check_community_system_time",
        _noop_system_time_check,
    )


async def _noop_system_time_check(**_kwargs) -> None:
    return None


@pytest.mark.asyncio
async def test_manual_sign_reports_missing_plugin_with_install_hint(
    isolated_app_paths, no_plugin_service
):
    """手动签到时插件没装，接口回 503 并带出可执行的安装引导。"""

    response = await community_api.manual_sign_flow()

    assert response.code == 503
    assert response.status == "error"
    assert "插件市场" in response.message


@pytest.mark.asyncio
async def test_scheduled_trigger_skips_without_marking_failure(
    isolated_app_paths, no_plugin_service
):
    """自动触发时插件没装，本次触发安静跳过，不抛给调度层。"""

    from app.core.timer import MainTimer

    results = await MainTimer._execute_community_sign(source="scheduled")

    assert results == []


def test_unavailable_error_is_a_runtime_error():
    """保留 RuntimeError 基类：既有 except Exception 的调用方仍能兜住。"""

    assert issubclass(CommunitySignPluginUnavailableError, RuntimeError)
