"""系统通知的平台分发；依赖只在准备发送器时装配。"""

import sys
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .contracts import PrepareSender

    prepare_sender: PrepareSender


def __getattr__(name: str):
    if name != "prepare_sender":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    backend = ".windows" if sys.platform == "win32" else ".common"
    value = import_module(backend, __name__).prepare_sender
    globals()[name] = value
    return value


__all__ = ["prepare_sender"]
