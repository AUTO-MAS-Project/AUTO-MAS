"""通用翻译器 PoTranslator

加载一个或多个 gettext 翻译文件（.po/.mo）为内部映射，支持补充翻译（优先）
与按行翻译；文件地址可相对脚本母目录动态解析，便于在 AutoMAS 中跨专项复用
与内置补充翻译。

仅做日志/文案的字符串替换翻译，不做复数、上下文等高级 gettext 语义。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Union

from .po import parse_po

PathLike = Union[str, Path]


def _parse_mo(path: Path) -> dict[str, str]:
    """用 Python 标准库 gettext 读取 .mo 编译文件为映射（失败时返回空）"""
    import gettext

    result: dict[str, str] = {}
    try:
        with open(path, "rb") as f:
            translations = gettext.GNUTranslations(f)
        catalog = getattr(translations, "_catalog", {})
        for key, value in catalog.items():
            # 跳过空 msgid（文件头）；空 key 会在 replace 时污染整段文本
            if not key:
                continue
            if isinstance(key, str) and isinstance(value, str):
                result[key] = value
    except (OSError, ValueError, gettext.Error):
        pass
    return result


class PoTranslator:
    """gettext 翻译器

    用法::

        translator = (
            PoTranslator()
            .load(
                ["data/apps/ok-ww/repo/i18n/zh_CN/LC_MESSAGES/ok.po"],
                base=root_path,
            )
            .load_supplement({"open_daily": "每日一条龙"})
        )
        translated = translator.translate(line)
        translator.clear()  # 会话结束后释放
    """

    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        # 按「较长键优先」排好序的键列表；load 后固定，避免逐行翻译时反复重排
        self._sorted_keys: list[str] = []

    def _rebuild_sorted_keys(self) -> None:
        # 长键优先替换，避免短键命中长键内部造成碎片化翻译；
        # 排序结果在 load/load_supplement 后固定，缓存一次即可
        self._sorted_keys = sorted(self._map, key=len, reverse=True)

    def load(
        self,
        paths: Union[PathLike, Iterable[PathLike]],
        *,
        base: Optional[PathLike] = None,
    ) -> "PoTranslator":
        """加载一个或多个翻译文件（.po 解析 / .mo 用 gettext 读取）

        Args:
            paths: 翻译文件路径（单个或多个）；相对路径基于 base 动态解析。
            base: 脚本母目录（RootPath）等基准目录；相对路径相对它解析。

        Returns:
            self（支持链式调用）
        """
        items = [paths] if isinstance(paths, (str, Path)) else list(paths)
        for item in items:
            path = Path(item)
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            self._map.update(self._load_file(path))
        self._rebuild_sorted_keys()
        return self

    def load_supplement(
        self,
        paths: Union[PathLike, Iterable[PathLike]],
        *,
        base: Optional[PathLike] = None,
    ) -> "PoTranslator":
        """加载补充翻译文件（.po / .mo），优先于已加载的翻译

        补充翻译后加载、覆盖同名键，如 AutoMAS 项目自带的补充 .mo 或专项
        补充的关键节点文案；与 load 一样支持多个文件与相对路径解析。

        Args:
            paths: 补充翻译文件路径（单个或多个）
            base: 基准目录；相对路径相对它解析（如 AutoMAS 项目根）

        Returns:
            self（支持链式调用）
        """
        items = [paths] if isinstance(paths, (str, Path)) else list(paths)
        for item in items:
            path = Path(item)
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            self._map.update(self._load_file(path))
        self._rebuild_sorted_keys()
        return self

    def translate(self, text: str) -> str:
        """逐行翻译：命中的键替换为译文，未命中返回原文

        较长键优先替换，避免短键命中长键内部造成碎片化翻译。

        Args:
            text: 待翻译文本（可为整行日志）

        Returns:
            翻译后的文本
        """
        if not self._map or not text:
            return text
        for key in self._sorted_keys:
            if key in text:
                text = text.replace(key, self._map[key])
        return text

    def clear(self) -> None:
        """释放已加载的翻译（会话结束时调用，避免长驻内存）"""
        self._map.clear()
        self._sorted_keys = []

    @staticmethod
    def _load_file(path: Path) -> dict[str, str]:
        """按扩展名加载单个翻译文件（未知类型按 .po 处理）"""
        if path.suffix.lower() == ".mo":
            return _parse_mo(path)
        return parse_po(path)
