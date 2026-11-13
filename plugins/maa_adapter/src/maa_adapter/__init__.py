"""最新 dev MAA 专项的独立测试插件入口。"""

from auto_mas_core import PLUGIN_API_VERSION

from maa_adapter.plugin import Plugin as PLUGIN

__all__ = ["PLUGIN", "PLUGIN_API_VERSION"]
