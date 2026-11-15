"""升级准入必须考虑仍安装在共享环境中的插件，不依赖插件能否导入。"""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import psutil
import pytest
from starlette.requests import Request

from app.api.update import CoreUpgradePrecheckIn, precheck_core_upgrade
from app.models.config import PluginRecord, PluginRegistryCollection
from app.plugin.types import PluginCodeDrift, PluginState
from app.plugin.uv import precheck


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift", [PluginCodeDrift.NORMAL, PluginCodeDrift.PACKAGE_REMOVED]
)
async def test_upgrade_precheck_keeps_import_failed_plugin_constraints(
    isolated_app_paths, monkeypatch, tmp_path, drift
):
    """导入失败但仍安装的插件与目标宿主冲突时，升级接口必须拒绝并返回原因。"""
    metadata = tmp_path / "broken_plugin-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Name: broken-plugin\nVersion: 1.0\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": "broken",
                "package_name": "broken-plugin",
                "version": "1.0",
                "source": "installed",
                "state": PluginState.FAULT_LOAD,
                "code_drift": drift,
                "last_error": "ImportError: missing dependency",
            }
        },
    )
    await registry.commit()
    monkeypatch.setattr(isolated_app_paths, "plugin_registry", registry)

    async def execute(*args, **kwargs):
        """在 uv 边界模拟故障插件的真实依赖冲突，遗漏该发行包时解析会错误成功。"""
        conflict = "broken-plugin==1.0" in args
        return SimpleNamespace(
            returncode=1 if conflict else 0,
            stderr="No solution found: broken-plugin requires shared-lib<2"
            if conflict
            else "",
            stdout="",
        )

    monkeypatch.setattr(precheck.ProcessRunner, "run_process", execute)
    monkeypatch.setattr(precheck, "ensure", lambda: "uv")
    monkeypatch.setattr(precheck, "candidates", lambda: ["https://index.test/simple"])
    # 不读写镜像偏好；待测逻辑仍运行真实目标构建、联合解析及 API 结果组装。
    monkeypatch.setattr(precheck, "mark_ok", AsyncMock())
    result = await precheck_core_upgrade(
        CoreUpgradePrecheckIn(version="v5.9.0-beta.1", dependencies=["shared-lib==2"]),
        Request({"type": "http"}),
    )
    assert not result.compatible
    assert "broken-plugin requires shared-lib<2" in result.conflicts[0].message


@pytest.mark.asyncio
async def test_disconnected_precheck_stops_solver_before_releasing_plugin_lock(
    isolated_app_paths, monkeypatch, tmp_path
):
    """取消升级请求后回收解析进程树并释放锁，不继续尝试下一镜像。"""
    from app.core import Plugin
    from app.utils.common.process import runner

    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    monkeypatch.setattr(isolated_app_paths, "plugin_registry", registry)
    disconnected = asyncio.Event()
    processes = []
    child_file = tmp_path / "child.pid"
    create = runner.create_subprocess

    async def execute(*args, **kwargs):
        """仅替换外部命令为本地进程树，仍运行真实解析、取消及进程回收代码。"""
        process = await create(
            sys.executable,
            "-I",
            "-c",
            "import subprocess, sys, time; from pathlib import Path; "
            "child = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(30)']); "
            f"Path({str(child_file)!r}).write_text(str(child.pid)); time.sleep(30)",
            **kwargs,
        )
        processes.append(process)
        return process

    async def receive():
        """通过 ASGI 连接状态模拟前端 AbortSignal 断开请求。"""
        return {"type": "http.disconnect" if disconnected.is_set() else "http.request"}

    monkeypatch.setattr(runner, "create_subprocess", execute)
    monkeypatch.setattr(precheck, "ensure", lambda: "uv")
    monkeypatch.setattr(precheck, "candidates", lambda: ["first", "second"])
    task = asyncio.create_task(
        precheck_core_upgrade(
            CoreUpgradePrecheckIn(version="v5.9.0", dependencies=["shared-lib==2"]),
            Request({"type": "http"}, receive),
        )
    )
    child_pid = None
    try:
        async with asyncio.timeout(5):
            while not child_file.is_file():
                await asyncio.sleep(0.01)
        child_pid = int(child_file.read_text())
        assert Plugin._busy.locked()
        disconnected.set()
        done, _ = await asyncio.wait({task}, timeout=5)
        assert done, "请求断开后预检仍在运行"
        assert task.cancelled()
        assert len(processes) == 1
        assert processes[0].returncode is not None
        assert not psutil.pid_exists(child_pid)
        async with Plugin._hold():
            pass
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        # 失败时也回收测试创建的进程，不能把进程泄漏留给后续用例。
        for pid in [*(process.pid for process in processes), child_pid]:
            if pid is not None and psutil.pid_exists(pid):
                try:
                    psutil.Process(pid).kill()
                except psutil.NoSuchProcess:
                    pass
        for process in processes:
            await process.wait()
