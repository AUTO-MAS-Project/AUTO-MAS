"""采集进程内的自定义来源和输出契约。"""

from collections.abc import Iterable
from importlib import import_module
from typing import Protocol

from .contracts import InputRecord, WorkerFactorySpec
from .observation import Node


class Source(Protocol):
    """按批返回当前可读记录；关闭时返回最后一批并释放资源。

    close() 也承担部分初始化失败后的清理。
    """

    def open(self) -> None: ...
    def poll(self) -> Iterable[InputRecord]: ...
    def close(self) -> Iterable[InputRecord]: ...


class Sink(Protocol):
    """在观察消息发出后消费节点，并在关闭时结算或清理部分初始化。"""

    def open(self) -> None: ...
    def write(self, node: Node) -> None: ...
    def close(self) -> None: ...


def create_extension(spec: WorkerFactorySpec) -> object:
    ref = spec.factory
    factory = getattr(import_module(ref.module), ref.attribute)
    return factory(spec.options)
