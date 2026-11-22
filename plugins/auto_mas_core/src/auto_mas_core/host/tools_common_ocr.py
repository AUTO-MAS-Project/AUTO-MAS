"""真实宿主模块 app.tools.common.ocr 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["Box", "OCRItem", "ocr_image"]

if TYPE_CHECKING:
    from app.tools.common.ocr import Box as Box
    from app.tools.common.ocr import OCRItem as OCRItem
    from app.tools.common.ocr import ocr_image as ocr_image
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.tools.common.ocr 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return getattr(import_module("app.tools.common.ocr"), name)
