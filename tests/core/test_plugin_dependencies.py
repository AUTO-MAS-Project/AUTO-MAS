"""联合解析保留禁用插件，并将目标宿主真实依赖写入 SDK 发行元数据。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

from app.plugin.uv import precheck


@pytest.mark.asyncio
async def test_joint_solver_uses_one_environment_for_all_plugins(monkeypatch):
    """验证依赖预检在同一次解析中联合考虑全部插件与目标 core，防止逐包检查漏掉交叉冲突。"""
    invocations = []

    async def execute(*args, **kwargs):
        """核对临时 core 元数据和两个插件共同进入解析命令，再返回共享依赖冲突结果。"""
        invocations.append(args)
        links = precheck.Path(args[args.index("--find-links") + 1])
        wheel = next(links.glob("*.whl"))
        with ZipFile(wheel) as archive:
            metadata = archive.read(
                next(name for name in archive.namelist() if name.endswith("/METADATA"))
            ).decode()
        assert "Requires-Dist: shared-lib==2" in metadata
        assert "plugin-a==1" in args and "plugin-b==2" in args
        return SimpleNamespace(
            returncode=1, stderr="No solution found: conflicting shared-lib", stdout=""
        )

    monkeypatch.setattr(precheck.ProcessRunner, "run_process", execute)
    monkeypatch.setattr(precheck, "ensure", lambda: "uv")
    monkeypatch.setattr(
        precheck,
        "candidates",
        lambda: ["https://first.test/simple", "https://second.test/simple"],
    )
    result = await precheck.resolve_environment(
        targets=["plugin-a==1", "plugin-b==2"],
        core_version="v5.8.0",
        dependencies=["shared-lib==2"],
    )
    assert not result.ok
    assert len(invocations) == 2
    assert "conflicting shared-lib" in result.detail


@pytest.mark.asyncio
async def test_solver_tries_next_source_when_release_is_not_mirrored(monkeypatch):
    """首源尚未收录已发布版本时继续解析，不能把缺包误判为永久依赖冲突。"""
    mirrors = ["https://mirror.test/simple", "https://official.test/simple"]
    attempted = []

    async def execute(*args, **kwargs):
        """模拟镜像缺包和官方源已有包，并确认切源不放宽宿主及插件版本。"""
        mirror = args[args.index("--index-url") + 1]
        attempted.append(mirror)
        assert "auto_mas_core==5.9.0b1" in args
        assert "plugin-a==1.0" in args
        return SimpleNamespace(
            returncode=1 if mirror == mirrors[0] else 0,
            stderr="No solution found: there is no version of plugin-a==1.0"
            if mirror == mirrors[0]
            else "",
            stdout="",
        )

    mark_ok = AsyncMock()
    monkeypatch.setattr(precheck.ProcessRunner, "run_process", execute)
    monkeypatch.setattr(precheck, "ensure", lambda: "uv")
    monkeypatch.setattr(precheck, "candidates", lambda: mirrors)
    monkeypatch.setattr(precheck, "mark_ok", mark_ok)
    result = await precheck.resolve_environment(
        targets=["plugin-a==1.0"],
        core_version="v5.9.0-beta.1",
        dependencies=["shared-lib==2"],
    )
    assert result.ok
    assert attempted == mirrors
    mark_ok.assert_awaited_once_with(mirrors[1])
