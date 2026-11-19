"""仅为真实 worker 集成测试提供可导入的函数实现。"""

import os
from collections.abc import Mapping

from pydantic import JsonValue


def report_worker_pid(_text: str, _args: list[str | int]) -> str:
    return str(os.getpid())


class _PrefixProcessor:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.count = 0

    def process(self, line: str):
        if line.startswith("done:"):
            self.count += 1
            yield "普通", f"{self.prefix}{line.strip().removeprefix('done:')}"

    def close(self):
        yield "普通", f"合计: {self.count}"


def prefix_processor(options: Mapping[str, JsonValue]) -> _PrefixProcessor:
    prefix = options["prefix"]
    assert isinstance(prefix, str)
    return _PrefixProcessor(prefix)
