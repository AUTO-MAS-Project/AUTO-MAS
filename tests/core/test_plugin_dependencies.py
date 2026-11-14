"""联合解析保留禁用插件，并将目标宿主真实依赖写入 SDK 发行元数据。"""

from types import SimpleNamespace
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
    monkeypatch.setattr(precheck, "candidates", lambda: ["https://index.test/simple"])
    result = await precheck.resolve_environment(
        targets=["plugin-a==1", "plugin-b==2"],
        core_version="v5.8.0",
        dependencies=["shared-lib==2"],
    )
    assert not result.ok
    assert len(invocations) == 1
