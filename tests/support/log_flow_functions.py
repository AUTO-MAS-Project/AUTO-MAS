"""仅为真实 worker 集成测试提供可导入的函数实现。"""

import os


def report_worker_pid(_text: str, _args: list[str | int]) -> str:
    return str(os.getpid())
