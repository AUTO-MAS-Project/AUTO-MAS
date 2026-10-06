"""共享 ref 池：``name="example_scripts"`` 全局唯一，各测试文件不得各自登记。

``ExampleQueueItem.info.script_id`` 写死 ``ref("example_scripts")``，名字由示例模型
定死；而 ``register_collection`` 对重名直接上抛。两个测试文件各建一份时，同目录
整体收集就会炸在第二个 import 上。故集合与 activate 都收到本模块，按需幂等热化。

池名带 ``example_`` 前缀是为了和 ``AppConfig.ScriptConfig`` 的 ``name="scripts"``
区分开：登记表是进程级的，示例模型不该占用生产配置的名字，否则一旦
``app.core.config`` 与本目录在同一进程里收集，两边必有一个登记失败。
"""

from __future__ import annotations

from app.config import ConfigCollection
from app.config.examples.reference_config import ExampleScript

scripts = ConfigCollection([ExampleScript], name="example_scripts")
_ready = False


async def ensure_scripts() -> ConfigCollection[ExampleScript]:
    """幂等热化共享脚本池并返回之。"""
    global _ready
    if not _ready:
        await scripts.activate()
        _ready = True
    return scripts
