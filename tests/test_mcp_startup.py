"""执行真实 main lifespan 编排，隔离系统、存储及游戏服务边界。"""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import uvicorn

import app.core as core
import app.core.mcp as mcp
import main
from app.core.lifecycle import _ShutdownCoordinator
from app.core.runtime_tasks import OwnedTaskRegistry


@pytest.mark.parametrize("failure", [False, True])
def test_business_ready_and_timer_precede_blocked_or_failed_mcp(
    monkeypatch, isolated_app_paths, failure
):
    from app.config import config_manager
    from app.services import System, obs_replay
    from app.task.MAA.stage import maa_stage_service

    registry = OwnedTaskRegistry()
    monkeypatch.setattr(core, "RuntimeTasks", registry)
    monkeypatch.setattr(mcp, "RuntimeTasks", registry)
    monkeypatch.setattr(core, "ShutdownCoordinator", _ShutdownCoordinator())
    monkeypatch.setenv("AUTO_MAS_ENABLE_MCP", "1")
    service = mcp.McpService()
    monkeypatch.setattr(core, "MCP", service)
    import app.api.core as core_api

    monkeypatch.setattr(core_api, "MCP", service)
    monkeypatch.setattr(main, "is_admin", lambda: True)
    monkeypatch.setattr(main, "configure_temporary_directory", lambda _: None)
    entered = threading.Event()
    release = threading.Event()
    calls = []

    async def timer_start():
        calls.append("timer")

    def blocked_build(*args):
        entered.set()
        assert release.wait(10)
        raise RuntimeError("injected MCP failure")

    monkeypatch.setattr(mcp, "_build_mcp", blocked_build)
    monkeypatch.setattr(core.Config, "init_config", AsyncMock())
    monkeypatch.setattr(
        core.Config,
        "setting",
        SimpleNamespace(
            Replay=SimpleNamespace(VideoStorageLimitMiB=0),
            Function=SimpleNamespace(HistoryRetentionTime=1),
        ),
    )
    monkeypatch.setattr(core.Config, "bind_script_config_handler", lambda *args: None)
    monkeypatch.setattr(core.Config, "set_restore_pool_resolver", lambda *args: None)
    monkeypatch.setattr(core.TaskManager, "bind_manager_factories", lambda *args: None)
    for owner, methods in [
        (core.History, ["initialize", "prune", "close"]),
        (core.MainTimer, ["stop"]),
        (core.Notify, ["start", "close"]),
        (core.DesktopGuard, ["start", "stop"]),
        (core.EmulatorManager, ["startup_avd_update"]),
        (core.TaskManager, ["stop_task"]),
        (core.MainConnection, ["begin_shutdown", "cancel_hook_tasks"]),
        (core.Dispatcher, ["shutdown"]),
        (core.Updater, ["cancel_download"]),
        (System, ["cancel_power_task"]),
        (obs_replay.ObsReplay, ["cleanup_temporary", "stop"]),
        (maa_stage_service, ["get_stage"]),
        (config_manager, ["flush"]),
        (
            core.Config.maafw_maintenance,
            [
                "migrate_embedded_copies_to_payloads",
                "clean_agent_venvs",
                "clean_embedded_copies",
                "clean_runtime_blobs",
                "clean_update_cache",
                "clean_runtime_pool",
            ],
        ),
    ]:
        for method in methods:
            monkeypatch.setattr(owner, method, AsyncMock())
    monkeypatch.setattr(core.MainTimer, "start", timer_start)
    monkeypatch.setattr(core.Publisher, "send", AsyncMock(return_value=False))

    class Server:
        def __init__(self, config):
            self.app = config.app

        async def serve(self):
            async with self.app.router.lifespan_context(self.app):
                try:
                    assert await asyncio.to_thread(entered.wait, 5)
                    assert calls == ["timer"]
                    assert self.app.state.background_status == "ready"
                    assert self.app.state.background_error is None
                    assert service.status().state == "running"
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=self.app),
                        base_url="http://localhost",
                    ) as client:
                        assert (await client.get("/api/core/health")).json()[
                            "backgroundStatus"
                        ] == "ready"
                        assert (await client.get("/mcp")).status_code == 404
                    if failure:
                        release.set()
                        await service._task
                        assert service.status().state == "failed"
                        assert self.app.state.background_status == "ready"
                finally:
                    release.set()

    monkeypatch.setattr(uvicorn, "Server", Server)
    main.main.__wrapped__()
    assert service.status().state == "cancelled"
