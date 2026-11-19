"""独立采集进程入口，仅通过标准管道与宿主交换消息。"""

from __future__ import annotations

import os
import sys
import time
from contextlib import ExitStack
from importlib import import_module
from io import BufferedWriter
from queue import Empty, Queue
from threading import Thread
from typing import cast

from app.models.log_flow import Node, NodeAttributes, NodeDisplayStatus, NodeSource
from app.models.notification.report import Node as LegacyReportNode
from app.plugin.runtime.loader import prefer_package_source
from app.utils.common.log.sources import LogReadLimitExceeded, LogSource

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
    PostProcessor,
    Ready,
    ReportedRecord,
    ReportEntry,
    ResultItem,
    TextRecord,
    WithdrawnRecord,
    WorkerFactorySpec,
    WorkerMessage,
)
from .extensions import Sink, Source, create_extension
from .processor import (
    GeneralRuleProcessor,
    RuleNodeProcessor,
    TextProcessor,
    build_custom_processor,
    load_functions,
)

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
    if (package := config.plugin_package) is not None:
        from pathlib import Path

        root = Path(package.import_root)
        sys.path[:0] = [package.sdk_root, package.import_root, package.dependency_root]
        prefer_package_source(package.name, root)
    with ExitStack() as cleanup:
        _run_pipeline(config, pipe, cleanup)


def _run_pipeline(
    config: PipelineSpec, pipe: BufferedWriter, cleanup: ExitStack
) -> None:
    functions = load_functions(config.functions)
    postprocessor: PostProcessor | None = None
    if (postprocess := config.postprocess) is not None:
        if isinstance(postprocess, WorkerFactorySpec):
            implementation = create_extension(postprocess)
            name = postprocess.factory.name
        else:
            implementation = getattr(
                import_module(postprocess.module), postprocess.attribute
            )
            name = postprocess.name
        if not callable(implementation):
            raise TypeError(f"报告归并器不可调用：{name}")
        postprocessor = cast(PostProcessor, implementation)

    processors: dict[NodeSource, TextProcessor] = {}

    def release_processor(source_name: NodeSource) -> None:
        if (processor := processors.pop(source_name, None)) is not None:
            for _ in processor.close():
                pass

    def build_processor(source_name: NodeSource) -> TextProcessor:
        if config.processor is not None:
            processor = build_custom_processor(config.processor)
            cleanup.callback(release_processor, source_name)
            return processor
        if config.general_patterns is not None:
            return GeneralRuleProcessor(config.general_patterns, config.general_hooks)
        return RuleNodeProcessor(config, functions)

    if config.file is not None:
        processors["file"] = build_processor("file")
    if config.accept_push:
        processors["push"] = build_processor("push")
    if config.accept_mas:
        processors["mas"] = build_processor("mas")
    custom_source = (
        cast(Source, create_extension(config.source))
        if config.source is not None
        else None
    )
    sink: Sink | None = None
    if custom_source is not None:
        processors["custom"] = build_processor("custom")
        custom_source.open()

        def release_source() -> None:
            if not closing_source:
                for _ in custom_source.close():
                    pass

        cleanup.callback(release_source)
    closing_source = False
    sink_error = ""
    if config.sink is not None:
        try:
            candidate = cast(Sink, create_extension(config.sink))
            candidate.open()
        except Exception as exc:
            sink_error = f"open: {type(exc).__name__}"
        else:
            sink = candidate

            def release_sink() -> None:
                if not closing_sink:
                    candidate.close()

            cleanup.callback(release_sink)
    closing_sink = False
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
    collected: dict[str | int, ResultItem] = {}
    revisions: dict[str, int] = {}

    def emit(
        result: tuple[str, str],
        *,
        source_name: NodeSource,
        timestamp: float | None,
        node_id: str | None = None,
        withdrawn: bool = False,
        status: NodeDisplayStatus | None = None,
        attributes: NodeAttributes = (),
    ) -> None:
        nonlocal sequence, observed_bytes, sink_error
        sequence += 1
        node_type, text = result
        stable_id = f"{source_name}/{node_id}" if node_id is not None else None
        revision = 1
        if stable_id is not None:
            revision = revisions.get(stable_id, 0) + 1
            revisions[stable_id] = revision
        if postprocessor is not None:
            key = stable_id if stable_id is not None else sequence
            if withdrawn:
                collected.pop(key, None)
            else:
                collected[key] = (node_type, text, timestamp)
        if status is None:
            legacy = LegacyReportNode.from_text(text)
            status = legacy.status if legacy is not None else "info"
        node = Node(
            sequence=sequence,
            node_type=node_type,
            text=text,
            source=source_name,
            timestamp=timestamp,
            node_id=stable_id,
            revision=revision,
            withdrawn=withdrawn,
            status=status,
            attributes=attributes,
        )
        observed_bytes += _send(
            pipe,
            Observed(node=node),
        )
        if sequence > MAX_NODE_FRAMES or observed_bytes > MAX_NODE_BYTES:
            raise LogReadLimitExceeded("观察节点容量已满")
        if sink is not None and not sink_error:
            try:
                sink.write(node)
            except Exception as exc:
                sink_error = f"write: {type(exc).__name__}"

    last_timestamp: dict[NodeSource, float | None] = {}

    def process_record(record: InputRecord, *, source_name: NodeSource) -> None:
        if isinstance(record, WithdrawnRecord):
            emit(
                ("", ""),
                source_name=source_name,
                timestamp=None,
                node_id=record.node_id,
                withdrawn=True,
            )
        elif isinstance(record, ReportedRecord):
            emit(
                (record.node_type, record.text),
                source_name=source_name,
                timestamp=record.timestamp,
                node_id=record.node_id,
                status=record.status,
                attributes=record.attributes,
            )
        else:
            last_timestamp[source_name] = record.timestamp
            for result in processors[source_name].process(record.text):
                emit(result, source_name=source_name, timestamp=record.timestamp)

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
            source_name = record.source if isinstance(record, TextRecord) else "push"
            if source_name not in processors:
                raise ValueError("该会话未声明消息来源")
            process_record(record, source_name=source_name)
        if source is not None:
            for line in source.read_new():
                timestamp = time.time()
                last_timestamp["file"] = timestamp
                for result in processors["file"].process(line):
                    emit(result, source_name="file", timestamp=timestamp)
        if custom_source is not None:
            closing_source = closing
            for record in custom_source.close() if closing else custom_source.poll():
                process_record(record, source_name="custom")
        if closing:
            break
    reader.join()
    for source_name in tuple(processors):
        processor = processors.pop(source_name)
        for result in processor.close():
            emit(
                result,
                source_name=source_name,
                timestamp=last_timestamp.get(source_name),
            )
    if postprocessor is not None:
        for node_type, text, timestamp in postprocessor(list(collected.values())):
            _send(
                pipe,
                FinalEntry(
                    entry=ReportEntry(
                        node_type=node_type, text=text, timestamp=timestamp
                    )
                ),
            )
    if sink is not None:
        closing_sink = True
        try:
            sink.close()
        except Exception as exc:
            if not sink_error:
                sink_error = f"close: {type(exc).__name__}"
    _send(
        pipe, Closed(has_final_report=postprocessor is not None, sink_error=sink_error)
    )


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
