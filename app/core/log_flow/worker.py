"""独立采集进程入口，仅通过标准管道与宿主交换消息。"""

from __future__ import annotations

import os
import sys
import time
from importlib import import_module
from io import BufferedWriter
from queue import Empty, Queue
from threading import Thread
from typing import cast

from app.models.log_flow import Node, NodeSource
from app.utils.common.log.sources import LogReadLimitExceeded, LogSource
from app.utils.common.log_box.pipeline import PostProcessor, ResultItem

from .contracts import (
    INPUT_RECORD,
    MAX_FRAME_BYTES,
    MAX_NODE_BYTES,
    MAX_NODE_FRAMES,
    MAX_PENDING_RECORDS,
    Closed,
    Failed,
    FinalEntry,
    InputRecord,
    Observed,
    PipelineSpec,
    Ready,
    ReportedRecord,
    ReportEntry,
    WorkerMessage,
)
from .processor import GeneralRuleProcessor, RuleNodeProcessor, load_functions

_POLL_SECONDS = 0.05
_MAX_FILE_READ_BYTES = 1024 * 1024


def _send(pipe: BufferedWriter, message: WorkerMessage) -> int:
    frame = message.model_dump_json().encode("utf-8")
    if len(frame) >= MAX_FRAME_BYTES:
        raise LogReadLimitExceeded("日志节点超出进程消息容量")
    pipe.write(frame + b"\n")
    pipe.flush()
    return len(frame) + 1


def _read_inbox(inbox: Queue[InputRecord | Exception | None]) -> None:
    # 单独的缓冲对象归读线程所有；故障路径可先还回摘要再退出，不等待 stdin 的全局缓冲锁。
    try:
        with os.fdopen(os.dup(sys.stdin.fileno()), "rb") as inputs:
            while frame := inputs.readline(MAX_FRAME_BYTES + 1):
                if len(frame) > MAX_FRAME_BYTES or not frame.endswith(b"\n"):
                    raise ValueError("无效的 LogFlow 上报消息")
                inbox.put(INPUT_RECORD.validate_json(frame))
    except (OSError, ValueError) as exc:
        inbox.put(exc)
    else:
        inbox.put(None)


def _collect(config: PipelineSpec, pipe: BufferedWriter) -> None:
    functions = load_functions(config.functions)
    postprocessor: PostProcessor | None = None
    if (ref := config.postprocess) is not None:
        implementation = getattr(import_module(ref.module), ref.attribute)
        if not callable(implementation):
            raise TypeError(f"报告归并器不可调用：{ref.name}")
        postprocessor = cast(PostProcessor, implementation)

    def build_processor() -> GeneralRuleProcessor | RuleNodeProcessor:
        if config.general_patterns is not None:
            return GeneralRuleProcessor(config.general_patterns, config.general_hooks)
        return RuleNodeProcessor(config, functions)

    processors: dict[NodeSource, GeneralRuleProcessor | RuleNodeProcessor] = {}
    if config.file is not None:
        processors["file"] = build_processor()
    if config.accept_push:
        processors["push"] = build_processor()
    if config.accept_mas:
        processors["mas"] = build_processor()
    source = None
    if config.file is not None:
        source = LogSource(
            config.file.path,
            start_from_end=config.file.start_from_end,
            rotated_name=config.file.rotated_name,
            max_read_bytes=_MAX_FILE_READ_BYTES,
            strict_io=True,
        )
        source.open()
    inbox: Queue[InputRecord | Exception | None] = Queue(MAX_PENDING_RECORDS)
    reader = Thread(target=_read_inbox, args=(inbox,), daemon=True)
    reader.start()
    _send(pipe, Ready(pid=os.getpid()))
    sequence = 0
    observed_bytes = 0
    collected: list[ResultItem] = []

    def emit(
        result: tuple[str, str], *, source_name: NodeSource, timestamp: float | None
    ) -> None:
        nonlocal sequence, observed_bytes
        sequence += 1
        node_type, text = result
        if postprocessor is not None:
            collected.append((node_type, text, timestamp))
        observed_bytes += _send(
            pipe,
            Observed(
                node=Node(
                    sequence=sequence,
                    node_type=node_type,
                    text=text,
                    source=source_name,
                    timestamp=timestamp,
                )
            ),
        )
        if sequence > MAX_NODE_FRAMES or observed_bytes > MAX_NODE_BYTES:
            raise LogReadLimitExceeded("观察节点容量已满")

    last_timestamp: dict[NodeSource, float | None] = {}
    while True:
        try:
            record = inbox.get(timeout=_POLL_SECONDS)
        except Empty:
            record = None
            closing = False
        else:
            closing = record is None
        if isinstance(record, Exception):
            raise record
        if record is not None:
            source_name = (
                "push" if isinstance(record, ReportedRecord) else record.source
            )
            if source_name not in processors:
                raise ValueError("该会话未声明消息来源")
            if isinstance(record, ReportedRecord):
                emit(
                    (record.node_type, record.text),
                    source_name="push",
                    timestamp=record.timestamp,
                )
            else:
                last_timestamp[record.source] = record.timestamp
                for result in processors[record.source].process(record.text):
                    emit(result, source_name=record.source, timestamp=record.timestamp)
        if source is not None:
            for line in source.read_new():
                timestamp = time.time()
                last_timestamp["file"] = timestamp
                for result in processors["file"].process(line):
                    emit(result, source_name="file", timestamp=timestamp)
        if closing:
            break
    reader.join()
    for source_name, processor in processors.items():
        for result in processor.close():
            emit(
                result,
                source_name=source_name,
                timestamp=last_timestamp.get(source_name),
            )
    if postprocessor is not None:
        for node_type, text, timestamp in postprocessor(collected):
            _send(
                pipe,
                FinalEntry(
                    entry=ReportEntry(
                        node_type=node_type, text=text, timestamp=timestamp
                    )
                ),
            )
    _send(pipe, Closed(has_final_report=postprocessor is not None))


def main() -> int:
    # 保留专用输出句柄，普通 print / 日志不混入节点协议。
    with os.fdopen(os.dup(sys.stdout.fileno()), "wb") as pipe:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        try:
            frame = sys.stdin.buffer.readline(MAX_FRAME_BYTES + 1)
            if len(frame) > MAX_FRAME_BYTES or not frame.endswith(b"\n"):
                raise ValueError("无效的 LogFlow 启动消息")
            _collect(PipelineSpec.model_validate_json(frame), pipe)
        except BrokenPipeError:
            return 1  # 宿主已关闭本轮输出，不再写入。
        except LogReadLimitExceeded as exc:
            _send(pipe, Failed(reason="capacity", detail=str(exc)))
            return 1
        except Exception as exc:
            _send(pipe, Failed(detail=f"{type(exc).__name__}: {str(exc)[:512]}"))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
