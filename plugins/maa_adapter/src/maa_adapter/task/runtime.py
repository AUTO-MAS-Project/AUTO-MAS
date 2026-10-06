"""MAA 任务准备期运行时快照（设备句柄 + 原生配置路径）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from auto_mas_core import DeviceHandle


@dataclass
class MaaRuntime:
    """Expander.prepare 构建，经 worker.runtime 传给模式执行器。"""

    maa_set_path: Path
    temp_path: Path
    device: DeviceHandle | None
    begin_time: str

    @classmethod
    def empty(cls) -> MaaRuntime:
        return cls(
            maa_set_path=Path("."),
            temp_path=Path("."),
            device=None,
            begin_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
