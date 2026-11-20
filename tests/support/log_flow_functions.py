"""仅为真实 worker 集成测试提供可导入的函数实现。"""

import os
import time
from collections.abc import Mapping
from pathlib import Path

from pydantic import JsonValue

from app.core.log_flow.contracts import ReportedRecord, TextRecord
from app.models.log_flow import Node, ReportEntry


def report_worker_pid(_text: str, _args: list[str | int]) -> str:
    return str(os.getpid())


class _PrefixProcessor:
    def __init__(self, prefix: str, release_marker: Path | None) -> None:
        self.prefix = prefix
        self.release_marker = release_marker

    def open(self) -> None:
        self.count = 0

    def process(self, line: str):
        if line == "crash":
            raise RuntimeError("sample processor failed")
        if line.startswith("done:"):
            self.count += 1
            yield "普通", f"{self.prefix}{line.strip().removeprefix('done:')}"

    def close(self):
        if self.release_marker is not None:
            self.release_marker.write_text("released", encoding="utf-8")
        yield "普通", f"合计: {self.count}"


def prefix_processor(options: Mapping[str, JsonValue]) -> _PrefixProcessor:
    prefix = options["prefix"]
    assert isinstance(prefix, str)
    marker = options.get("release_marker")
    return _PrefixProcessor(prefix, Path(str(marker)) if marker is not None else None)


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
        if self.mode == "fail_open":
            raise RuntimeError("sample sink failed during open")

    def write(self, node: Node):
        if self.mode == "fail":
            raise RuntimeError("sample sink failed")
        if self.mode == "block":
            time.sleep(60)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(f"{node.source}:{node.text}\n")

    def close(self):
        if self.mode == "block_close":
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write("closing\n")
            time.sleep(60)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write("closed\n")
        if self.mode == "fail_close":
            raise RuntimeError("sample sink failed during close")


def sample_source(_options: Mapping[str, JsonValue]) -> _SampleSource:
    return _SampleSource()


def oversized_source(_options: Mapping[str, JsonValue]) -> _SampleSource:
    class OversizedSource(_SampleSource):
        def poll(self):
            return ()

        def close(self):
            yield TextRecord(text="x" * 65536)
            yield TextRecord(text="done:tail")

    return OversizedSource()


def blocking_start_source(options: Mapping[str, JsonValue]) -> _SampleSource:
    Path(str(options["pid_path"])).write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(60)
    return _SampleSource()


def sample_sink(options: Mapping[str, JsonValue]) -> _SampleSink:
    return _SampleSink(Path(str(options["path"])), str(options["mode"]))


class _FailingInitializer:
    def __init__(self, path: Path) -> None:
        self.path = path

    def open(self) -> None:
        self.path.write_text("opened\n", encoding="utf-8")
        raise RuntimeError("sample input failed during open")

    def poll(self):
        raise AssertionError("source must not poll after failed open")

    def process(self, _line: str):
        raise AssertionError("processor must not process after failed open")

    def close(self):
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write("closed\n")
        return (ReportedRecord(node_type="普通", text="unfinished tail"),)


def failing_initializer(options: Mapping[str, JsonValue]) -> _FailingInitializer:
    return _FailingInitializer(Path(str(options["path"])))


def sample_report(_entries):
    return [ReportEntry(node_type="普通", text="sample report")]


def maaend_flow_report(entries):
    from app.task.MaaEnd.push_log import maaend_resolve

    return [
        ReportEntry(node_type=node_type, text=text, timestamp=timestamp)
        for node_type, text, timestamp in maaend_resolve(
            [(entry.node_type, entry.text, entry.timestamp) for entry in entries]
        )
    ]


def oknte_flow_report(entries):
    from app.task.OkNte.push_log import oknte_resolve

    return [
        ReportEntry(node_type=node_type, text=text, timestamp=timestamp)
        for node_type, text, timestamp in oknte_resolve(
            [(entry.node_type, entry.text, entry.timestamp) for entry in entries]
        )
    ]


def disabled_report(_entries):
    raise AssertionError("关闭通知时不得执行报告归并")
