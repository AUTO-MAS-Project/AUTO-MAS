"""BetterGI「脚本配置」来源：脚本级共享段的对齐与读写路由。"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.api.scripts import _bettergi_owner_config, _bettergi_uses_script_source
from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.task.proxy_helpers import CONFIG_SOURCE_SCRIPT


def _user_config(mode: str) -> BetterGIUserConfig:
    config = BetterGIUserConfig()
    asyncio.run(config.set("Info", "Mode", mode))
    return config


def _fake_script_config(user_id: str, user_config: object) -> SimpleNamespace:
    return SimpleNamespace(UserData={uuid.UUID(user_id): user_config})


def test_script_and_user_one_dragon_sections_stay_in_sync() -> None:
    """脚本级共享段必须与用户级 OneDragon 段同键同默认值（模型注释承诺的对齐）。

    加字段只改一处（例如只加 OneDragon 而漏加脚本级）时本用例会红。
    """

    script_section = asyncio.run(BetterGIConfig().toDict()).get("OneDragon")
    user_section = asyncio.run(BetterGIUserConfig().toDict()).get("OneDragon")

    assert script_section is not None
    assert script_section == user_section


@pytest.mark.parametrize("mode", ["用户", "直控"])
def test_non_script_source_keeps_user_config(mode: str) -> None:
    user_id = str(uuid.uuid4())
    user_cfg = _user_config(mode)
    script_cfg = _fake_script_config(user_id, user_cfg)

    assert _bettergi_uses_script_source(script_cfg, user_id) is False
    assert _bettergi_owner_config(script_cfg, user_id) is user_cfg


def test_script_source_routes_to_script_level_section() -> None:
    user_id = str(uuid.uuid4())
    user_cfg = _user_config(CONFIG_SOURCE_SCRIPT)
    script_cfg = _fake_script_config(user_id, user_cfg)

    assert _bettergi_uses_script_source(script_cfg, user_id) is True
    assert _bettergi_owner_config(script_cfg, user_id) is script_cfg
