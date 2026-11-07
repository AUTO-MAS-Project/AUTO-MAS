"""OK-WW 收尾属性初始化回归测试。

`prepare()` 在 RootPath、日志监控等步骤都可能抛错；这些异常发生后任务框架
仍会进入收尾，而 `final_task()` 第一行就读取 `run_book`。该属性必须在
`__init__` 中先初始化，否则 prepare 失败会变成收尾阶段的 AttributeError，
并跳过进程清理与配置恢复。
"""

import uuid
from types import SimpleNamespace

from app.task.Okww.AutoProxy import AutoProxyTask


def test_run_book_initialized_before_prepare():
    uid = uuid.uuid4()
    script_info = SimpleNamespace(
        task_info=SimpleNamespace(),
        user_list=[SimpleNamespace(user_id=str(uid), name="用户")],
        current_index=0,
    )
    proxy = AutoProxyTask(
        script_info=script_info,
        script_config=SimpleNamespace(),
        user_config={uid: SimpleNamespace()},
        game_manager=None,
    )

    assert proxy.run_book is False
