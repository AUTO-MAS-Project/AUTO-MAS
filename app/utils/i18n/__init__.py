"""i18n 通用翻译能力

提供 PoTranslator：加载 .po/.mo 翻译文件为内部映射，支持补充翻译（优先）与
按行翻译，供日志采集（log_box 前置翻译）、专项适配等场景复用。
"""

from .po import parse_po
from .translator import PoTranslator

__all__ = ["PoTranslator", "parse_po"]
