"""全部内置接入、家族复用、宿主服务绑定与冷导入边界。"""

import importlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import ConfigCollection
from app.core.config.manager import AppConfig
from app.models import config as models
from app.task.builtin_registration import build_builtin_script_capabilities

# 固定迁移前的能力契约；可选钩子缺省是明确不支持，不要求各专项长成同一形状。
EXPECTED = [
    (
        "MaaEnd",
        "MaaEnd",
        "MaaEndManager",
        {
            "initialize",
            "validate_update",
            "import_config",
            "emulator_binding",
        },
    ),
    ("BetterGI", "BetterGI", "BetterGIManager", {"prepare_user_update"}),
    (
        "Src",
        "SRC",
        "SrcManager",
        {"prepare_user_update", "emulator_binding"},
    ),
    (
        "ZzzOd",
        "ZzzOd",
        "ZzzOdManager",
        {"prepare_script_removal", "prepare_user_update", "prepare_user_removal"},
    ),
    (
        "MaaFW",
        "MaaFW",
        "MaaFWEmbeddedManager",
        {
            "clone_script",
            "after_script_removal",
            "prepare_user_update",
            "prepare_user_read",
            "initialize_user",
            "emulator_binding",
        },
    ),
    ("Okww", "Okww", "OkwwManager", {"initialize_user", "import_config"}),
    ("General", "general", "GeneralManager", {"emulator_binding"}),
    ("OkNte", "OkNte", "OkNteManager", set()),
    ("HSR", "HSR", "HSRManager", set()),
    ("BAAH", "BAAH", "BAAHManager", {"emulator_binding"}),
    ("Whimbox", "Whimbox", "WhimboxManager", set()),
]


def capabilities():
    return build_builtin_script_capabilities(
        maaend=Mock(), zzzod=Mock(prepare_script_removal=AsyncMock())
    )


def config_host(caps):
    config = AppConfig.__new__(AppConfig)
    config.work_path = Path.cwd()
    config.data_path = config.work_path / "data"
    config.config_path = config.work_path / "config"
    config._script_config_handlers = {}
    config._restore_pool_resolver = None
    for entry_type, handler in caps.config_handlers:
        config.bind_script_config_handler(entry_type, handler)
    config.set_restore_pool_resolver(caps.resolve_restore_pools)
    return config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry_type", [models.MaaFWConfig, models.M9AConfig, models.MSSConfig]
)
async def test_family_uses_specific_user_class_before_handler(entry_type):
    caps = capabilities()
    caps = replace(
        caps,
        config_handlers=tuple(
            (
                t,
                replace(h, initialize_user=AsyncMock())
                if t is models.MaaFWConfig
                else h,
            )
            for t, h in caps.config_handlers
        ),
    )
    config = config_host(caps)
    config.ScriptConfig = ConfigCollection[models.ScriptConfigType].build([entry_type])
    await config.ScriptConfig.activate()
    sid = config.ScriptConfig.add(entry_type)
    await config.ScriptConfig.commit()
    uid, user = await config.add_user(str(sid))
    assert type(user) is entry_type.USER_CONFIG_CLASS
    assert (
        config._get_script_config_handler(config.ScriptConfig[sid])
        is dict(caps.config_handlers)[models.MaaFWConfig]
    )


@pytest.mark.asyncio
async def test_bound_maaend_and_zzzod_services_do_not_cross_hosts():
    instances = []
    for _ in range(2):
        maaend = Mock(initialize=AsyncMock(), import_config=AsyncMock())
        zzzod = Mock(prepare_script_removal=AsyncMock())
        caps = build_builtin_script_capabilities(maaend=maaend, zzzod=zzzod)
        instances.append((config_host(caps), maaend, zzzod))
    for config, maaend, zzzod in reversed(instances):
        end = models.MaaEndConfig()
        zzz = models.ZzzOdConfig()
        await config._initialize_script_config(end)
        config._get_script_config_handler(end).validate_update({})
        await config._get_script_config_handler(end).import_config(
            end, Path("test"), user_id=None
        )
        await config._get_script_config_handler(zzz).prepare_script_removal(zzz)
        maaend.initialize.assert_awaited_once_with(end)
        maaend.import_config.assert_awaited_once_with(end, Path("test"), user_id=None)
        zzzod.prepare_script_removal.assert_awaited_once_with(zzz)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_type", list(models.CLASS_BOOK.values()))
async def test_mfw_cleanup_applies_to_every_builtin_but_reconcile_only_family(
    entry_type, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    events = []
    lifecycle = importlib.import_module(
        "app.task.MaaFW.tools.embedded.script_lifecycle"
    )

    async def cleanup(sid):
        assert not (tmp_path / "data" / sid).exists()
        events.append("cleanup")

    monkeypatch.setattr(lifecycle, "cleanup_script_files", cleanup)
    monkeypatch.setattr(
        lifecycle, "after_script_removal", lambda: events.append("after")
    )
    config = config_host(capabilities())
    config.ScriptConfig = ConfigCollection[models.ScriptConfigType].build([entry_type])
    config.QueueConfig = {}
    await config.ScriptConfig.activate()
    sid = config.ScriptConfig.add(entry_type)
    await config.ScriptConfig.commit()
    (tmp_path / "data" / str(sid)).mkdir(parents=True)
    await config.del_script(str(sid))
    assert sid not in config.ScriptConfig
    assert events == (
        ["after", "cleanup"]
        if issubclass(entry_type, models.MaaFWConfig)
        else ["cleanup"]
    )


def test_cold_declarations_and_parent_packages_do_not_load_execution_or_config(
    tmp_path,
):
    root = Path(__file__).resolve().parents[2]
    code = r"""
import importlib, json, sys, asyncio
from unittest.mock import patch
folders = ["SRC","general","MaaEnd","MaaFW","Okww","OkNte","HSR","BetterGI","ZzzOd","BAAH","Whimbox"]
with patch("asyncio.create_task",side_effect=AssertionError("spawn")):
    for folder in folders:
        importlib.import_module("app.task."+folder+".registration")
forbidden = [n for n in sys.modules if n in {"app.core.config.manager","app.core.task_manager"} or (n.startswith("app.task.") and (n.endswith((".manager",".embedded_manager",".restore_service",".AutoProxy")) or ".tools.core.runner" in n))]
assert not forbidden, forbidden
assert not __import__("pathlib").Path("config").exists()
assert not __import__("pathlib").Path("data").exists()
# 合法包导出沿用惰性属性访问；以替身验证，无需加载真实执行链。
from types import ModuleType
m=ModuleType("app.task.SRC.manager")
sentinel=object()
m.SrcManager=sentinel
sys.modules[m.__name__]=m
from app.task.SRC import SrcManager
import app.task as task
assert SrcManager is sentinel and task.SrcManager is sentinel
print(json.dumps({"ok":True}))
"""
    env = {**os.environ, "PYTHONPATH": str(root), "AUTO_MAS_TELEMETRY": "disabled"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"ok": True}
