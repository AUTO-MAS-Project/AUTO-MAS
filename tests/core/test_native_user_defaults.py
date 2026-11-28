"""新账号默认值：插件版 MaaEnd 与内置专项一样按「原生 + 不覆写」建号。"""

import pytest

from app.core import Config, Plugin
from app.models.config import ScriptEntry
from app.utils import BASE_NATIVE


class _PluginMaaEndConfig(ScriptEntry):
    """插件版 MaaEnd 的托管类：只出现在插件登记表里，不在内置名单。"""


class _OtherPluginConfig(ScriptEntry):
    """别的插件专项：没有列进名单，行为不能跟着变。"""


@pytest.fixture
def plugin_script_classes(monkeypatch):
    """按插件登记的脚本键登记假类，模拟已启用插件贡献的 script_classes。"""
    monkeypatch.setattr(
        Plugin,
        "script_classes",
        lambda: {"MaaEnd": _PluginMaaEndConfig, "Other": _OtherPluginConfig},
    )


def test_plugin_maaend_user_defaults_are_native(plugin_script_classes):
    """插件版 MaaEnd 也按原生来源、不覆写常规配置；认的是名单里的 "MaaEnd" 键。"""
    assert Config._native_user_defaults(_PluginMaaEndConfig()) == {
        "Info": {"Base": BASE_NATIVE, "IfQuickConfig": False}
    }


def test_other_plugin_script_keeps_model_defaults(plugin_script_classes):
    """名单外的插件专项不放行，返回 None 交给配置模型自己的缺省值。"""
    assert Config._native_user_defaults(_OtherPluginConfig()) is None


def test_missing_maaend_plugin_keeps_model_defaults(monkeypatch):
    """MaaEnd 插件没启用时名单里没有这个键：返回 None，不是抛错。"""
    monkeypatch.setattr(Plugin, "script_classes", lambda: {})
    assert Config._native_user_defaults(_PluginMaaEndConfig()) is None
