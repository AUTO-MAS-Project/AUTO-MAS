"""升级准入必须考虑仍安装在共享环境中的插件，不依赖插件能否导入。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.update import CoreUpgradePrecheckIn, precheck_core_upgrade
from app.models.config import PluginRecord, PluginRegistryCollection
from app.plugin.types import PluginState
from app.plugin.uv import precheck


@pytest.mark.asyncio
async def test_upgrade_precheck_keeps_import_failed_plugin_constraints(
    isolated_app_paths, monkeypatch
):
    """导入失败但仍安装的插件与目标宿主冲突时，升级接口必须拒绝并返回原因。"""
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
        CoreUpgradePrecheckIn(version="v5.9.0-beta.1", dependencies=["shared-lib==2"])
    )
    assert not result.compatible
    assert "broken-plugin requires shared-lib<2" in result.conflicts[0].message
