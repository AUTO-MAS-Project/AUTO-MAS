"""真实配置启动链使用隔离数据目录，替换系统副作用，保留真实信号与持久化。"""

import os
import subprocess
import sys
from pathlib import Path


def test_empty_profile_initializes_config_and_community_subscriptions(tmp_path):
    source_root = Path(__file__).resolve().parents[2]
    code = """
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.config import NodeState
from app.core import Community, Config
from app.models.config import ToolsConfig
from app.services import System, telemetry

async def run():
    with (
        patch.object(System, 'set_SelfStart', new_callable=AsyncMock) as startup,
        patch.object(System, 'set_Sleep', new_callable=AsyncMock) as sleep,
        patch.object(telemetry, 'set_telemetry_enabled', new_callable=Mock),
    ):
        await Config.init_config()
        if Config.temp_task:
            await asyncio.gather(*tuple(Config.temp_task))
        await Config.flush()
        startup.assert_awaited_once_with(Config.setting.Start.IfSelfStart)
        sleep.assert_awaited_once_with(Config.setting.Function.IfAllowSleep)
        assert Config.setting.activation_state == NodeState.ACTIVE
        assert Config.ToolsConfig.activation_state == NodeState.ACTIVE
        assert Config.config_path == Path.cwd() / 'config'
        assert (Config.config_path / 'setting.yaml').is_file()
        assert (Config.config_path / 'tools.yaml').is_file()
        assert not Config.ScriptConfig
        assert not Config.ToolsConfig.GameSign_Accounts
        assert 'app.core.maa_manager' not in sys.modules
        revision = Community._activity_cache_revision
        await Config.ToolsConfig.update(
            ToolsConfig.model_validate({'GameSign': {
                'ActivityEnabled': not Config.ToolsConfig.GameSign.ActivityEnabled,
            }}),
            check_visibility=False,
        )
        assert Community._activity_cache_revision == revision + 1
        await Config.flush()

asyncio.run(run())
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "PYTHONPATH": str(source_root),
            "PYTHONIOENCODING": "utf-8",
            "AUTO_MAS_ENV": "development",
            "AUTO_MAS_SUPERVISED": "1",
        },
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
