"""log_box 采集工厂

顶层入口：``from mas_script import log_box``。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Optional, Union

from .collect import LogCollect

PathLike = Union[str, Path]


class LogBox:
    """log_box 采集工厂：get_collect 创建日志采集会话"""

    def get_collect(
        self,
        paths: Optional[Union[PathLike, Iterable[PathLike]]] = None,
        *,
        sink: Optional[Callable[[str, str], None]] = None,
        start_from_end: bool = True,
    ) -> LogCollect:
        """创建日志采集会话

        Args:
            paths: 日志位置（单个或多个文件）；None 时回退到环境变量
                ``MAS_SCRIPT_LOG_PATH``（MAS 配置的日志位置）。
            sink: MAS 进程宿主注入的 push_log 写入回调 sink(log_type, text)；
                缺省时结果走 @@LOGBOX@@ 标记回传（脚本子进程宿主）。
            start_from_end: 是否从文件末尾起始采集（仅采集会话内新增内容）。

        Returns:
            LogCollect 实例
        """
        return LogCollect(paths, sink=sink, start_from_end=start_from_end)


log_box = LogBox()
