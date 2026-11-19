"""仅为真实 worker 集成测试提供可导入的函数实现。"""

import os
import time
from collections.abc import Mapping
from pathlib import Path

from pydantic import JsonValue

from app.core.log_flow.contracts import ReportedRecord, TextRecord
from app.models.log_flow import Node


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


class _SampleSource:
    def open(self):
        self.pending = True

    def poll(self):
        if self.pending:
            self.pending = False
            yield TextRecord(text="done:sample", source="mas")

    def close(self):
        yield ReportedRecord(node_type="普通", text="source tail")


class _SampleSink:
    def __init__(self, path: Path, mode: str) -> None:
        self.path = path
        self.mode = mode

    def open(self):
        self.path.write_text(f"pid:{os.getpid()}\n", encoding="utf-8")

    def write(self, node: Node):
        if self.mode == "fail":
            raise RuntimeError("sample sink failed")
        if self.mode == "block":
            time.sleep(60)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(f"{node.source}:{node.text}\n")

    def close(self):
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write("closed\n")


def sample_source(_options: Mapping[str, JsonValue]) -> _SampleSource:
    return _SampleSource()


def sample_sink(options: Mapping[str, JsonValue]) -> _SampleSink:
    return _SampleSink(Path(str(options["path"])), str(options["mode"]))


def sample_report(_entries):
    return [("普通", "sample report", None)]


def disabled_report(_entries):
    raise AssertionError("关闭通知时不得执行报告归并")
