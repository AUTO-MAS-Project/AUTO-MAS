"""MaaFW 增量更新读取器与限速器的 SDK 导出。

实现已随 MFW 收口并入 ``app.utils.common.zip_range``，这里按符号转发，
与 ``auto_mas_core.host.utils_common_zip_range`` 指向同一份实现。
"""

from auto_mas_core.host.utils_common_zip_range import (  # noqa: F401 - 复用同一份惰性导出。
    RangeHTTPReader as RangeHTTPReader,
    RangeSpeedGuard as RangeSpeedGuard,
)

__all__ = ["RangeHTTPReader", "RangeSpeedGuard"]