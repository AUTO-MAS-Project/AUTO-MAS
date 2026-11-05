"""全部内置接入、家族复用、宿主服务绑定与冷导入边界。"""

import importlib
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
            "task_resources",
            "emulator_binding",
        },
    ),
    ("BetterGI", "BetterGI", "BetterGIManager", {"prepare_user_update"}),
    (
        "Maa",
        "MAA",
        "MaaManager",
        {
            "prepare_user_update",
            "user_config_directory",
            "task_resources",
            "emulator_binding",
        },
    ),
    (
        "Src",
        "SRC",
        "SrcManager",
        {"prepare_user_update", "task_resources", "emulator_binding"},
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
            "task_resources",
            "emulator_binding",
        },
    ),
    ("Okww", "Okww", "OkwwManager", {"initialize_user", "import_config"}),
    ("General", "general", "GeneralManager", {"task_resources", "emulator_binding"}),
    ("OkNte", "OkNte", "OkNteManager", set()),
    ("HSR", "HSR", "HSRManager", set()),
    ("BAAH", "BAAH", "BAAHManager", {"task_resources", "emulator_binding"}),
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
@pytest.mark.parametrize("name", [name for name, *_ in EXPECTED] + ["M9A", "MSS"])
async def test_mfw_cleanup_applies_to_every_builtin_but_reconcile_only_family(
    name, tmp_path, monkeypatch
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
    entry_type = getattr(models, name + "Config")
    config.ScriptConfig = ConfigCollection.build([entry_type])
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
