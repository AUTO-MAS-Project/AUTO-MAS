"""i18n 通用翻译能力

提供 PoTranslator：加载 .po/.mo 翻译文件为内部映射，支持补充翻译（优先）与
按行翻译，供日志采集（log_box 前置翻译）、专项适配等场景复用。
"""

from .po import parse_mo, parse_po
from .translator import PoTranslator

__all__ = ["PoTranslator", "parse_mo", "parse_po"]


def _get_public_export(name):
    raise AttributeError(name)


_SUBMODULES = {"po": ".po", "translator": ".translator"}


def __getattr__(name):
    if name in _SUBMODULES:
        from importlib import import_module

        value = import_module(_SUBMODULES[name], __name__)
        globals()[name] = value
        return value
    return _get_public_export(name)
