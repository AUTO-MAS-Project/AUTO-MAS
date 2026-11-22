#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""宿主起 worker 子进程用的两个值，按本模块自己的位置算，搬目录、装成包都跟着走。

- ``WORKER_MODULE``：``python -m`` 的模块路径（与 ``worker.py`` 同一个包）；
- ``IMPORT_ROOT``：要放进 worker 的 ``PYTHONPATH`` 的导入根，即顶层包所在的目录
  （源码树里是 MAS 源码根，与 ``Config.source_path`` 是同一个目录）。

只用标准库，宿主导入它不会带起 maa 或运行器的其余模块。
"""

from __future__ import annotations

from pathlib import Path

WORKER_MODULE = f"{__package__}.worker"
IMPORT_ROOT = Path(__file__).resolve().parents[len(__package__.split("."))]

__all__ = ["IMPORT_ROOT", "WORKER_MODULE"]
