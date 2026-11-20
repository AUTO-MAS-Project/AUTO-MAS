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

from app.models.log_flow import (
    Node,
    NodeAttributes,
    NodeDisplayStatus,
    NodeSource,
    ReportEntry,
)
from app.plugin.runtime.loader import prefer_package_source
from app.utils.common.log.flow_file import FlowFileSource, LogReadLimitExceeded

from .contracts import (
    INPUT_RECORD,
    MAX_FRAME_BYTES,
    MAX_NODE_BYTES,
    MAX_NODE_FRAMES,
    MAX_PENDING_RECORDS,
    Closed,
    Failed,
    FinalEntry,
    FinalReportReady,
    InputRecord,
    Observed,
    PipelineSpec,
    PostProcessor,
    Ready,
    ReportedRecord,
    TextRecord,
    WithdrawnRecord,
    WorkerFactorySpec,
    WorkerMessage,
)
from .extensions import Sink, Source, create_extension
from .processor import (
    GeneralRuleProcessor,
    OpenableProcessor,
    ProcessorOutput,
    RuleNodeProcessor,
    TextProcessor,
    load_functions,
)

_POLL_SECONDS = 0.05
_MAX_FILE_READ_BYTES = 1024 * 1024


def _send(
    pipe: BufferedWriter, message: WorkerMessage, *, remaining_bytes: int | None = None
) -> int:
    frame = message.model_dump_json().encode("utf-8") + b"\n"
    if len(frame) > MAX_FRAME_BYTES:
        raise LogReadLimitExceeded("日志节点超出进程消息容量")
    if remaining_bytes is not None and len(frame) > remaining_bytes:
        raise LogReadLimitExceeded("采集输出字节容量已满")
    pipe.write(frame)
    pipe.flush()
    return len(frame)


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
        try:
            _run_pipeline(config, pipe, cleanup)
        except Exception as failure:
            # 扩展清理仍需执行，宿主按管线原始失败原因生成摘要。
            try:
                cleanup.close()
            except Exception as cleanup_failure:
                raise failure from cleanup_failure
            raise


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

    def add_processor(source_name: NodeSource) -> None:
        if config.processor is not None:
            processor = cast(TextProcessor, create_extension(config.processor))
            processors[source_name] = processor
            cleanup.callback(release_processor, source_name)
            if isinstance(processor, OpenableProcessor):
                processor.open()
        elif config.general_patterns is not None:
            processors[source_name] = GeneralRuleProcessor(
                config.general_patterns,
                config.general_hooks,
                log_time=config.general_log_time if source_name == "mas" else None,
            )
        else:
            processors[source_name] = RuleNodeProcessor(config, functions)

    if config.file is not None:
        add_processor("file")
    if config.accept_push:
        add_processor("push")
    if config.accept_mas:
        add_processor("mas")
    custom_source = (
        cast(Source, create_extension(config.source))
        if config.source is not None
        else None
    )
    sink: Sink | None = None
    closing_source = False
    if custom_source is not None:
        add_processor("custom")

        def release_source() -> None:
            if not closing_source:
                for _ in custom_source.close():
                    pass

        cleanup.callback(release_source)
        custom_source.open()
    sink_error = ""
    closing_sink = False
    if config.sink is not None:
        try:
            sink = cast(Sink, create_extension(config.sink))

            def release_sink(candidate: Sink) -> None:
                if not closing_sink:
                    candidate.close()

            cleanup.callback(release_sink, sink)
            sink.open()
        except Exception as exc:
            sink_error = f"open: {type(exc).__name__}"
    source = None
    if config.file is not None:
        source = FlowFileSource(
            config.file.path,
            start_from_end=config.file.start_from_end,
            rotated_name=config.file.rotated_name,
            max_read_bytes=_MAX_FILE_READ_BYTES,
        )
        source.open(cursor=config.file.start_cursor)
    inbox: Queue[InputRecord | Exception | None] = Queue(MAX_PENDING_RECORDS)
    reader = Thread(target=_read_inbox, args=(inbox,), daemon=True)
    reader.start()
    _send(pipe, Ready(pid=os.getpid()))
    sequence = 0
    observed_bytes = 0
    observation_full = False
    observation_capacity_error = ""
    collected: dict[str | int, ReportEntry] = {}
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
        nonlocal sequence, observed_bytes, sink_error, observation_full
        nonlocal observation_capacity_error
        if observation_full:
            return
        if sequence == MAX_NODE_FRAMES:
            observation_full = True
            observation_capacity_error = "观察节点容量已满"
            return
        node_type, text = result
        stable_id = f"{source_name}/{node_id}" if node_id is not None else None
        revision = 1
        if stable_id is not None:
            revision = revisions.get(stable_id, 0) + 1
        node = Node(
            sequence=sequence + 1,
            node_type=node_type,
            text=text,
            source=source_name,
            timestamp=timestamp,
            node_id=stable_id,
            revision=revision,
            withdrawn=withdrawn,
            status=status or "info",
            attributes=attributes,
        )
        frame = Observed(node=node).model_dump_json().encode("utf-8") + b"\n"
        if len(frame) > MAX_FRAME_BYTES:
            observation_capacity_error = "日志节点超出进程消息容量"
            return
        if observed_bytes + len(frame) > MAX_NODE_BYTES:
            observation_full = True
            observation_capacity_error = "观察节点字节容量已满"
            return
        pipe.write(frame)
        pipe.flush()
        observed_bytes += len(frame)
        sequence += 1
        if stable_id is not None:
            revisions[stable_id] = revision
        if postprocessor is not None:
            key = stable_id if stable_id is not None else sequence
            if withdrawn or config.report_order == "last_updated":
                collected.pop(key, None)
            if not withdrawn:
                collected[key] = ReportEntry.from_node(node)
        if sink is not None and not sink_error:
            try:
                sink.write(node)
            except Exception as exc:
                sink_error = f"write: {type(exc).__name__}"

    last_timestamp: dict[NodeSource, float | None] = {}
    file_capacity_error = ""

    def emit_processed(
        result: ProcessorOutput, *, source_name: NodeSource, timestamp: float | None
    ) -> None:
        if isinstance(result, WithdrawnRecord):
            emit(
                ("", ""),
                source_name=source_name,
                timestamp=None,
                node_id=result.node_id,
                withdrawn=True,
            )
        elif isinstance(result, ReportedRecord):
            emit(
                (result.node_type, result.text),
                source_name=source_name,
                timestamp=result.timestamp
                if result.timestamp is not None
                else timestamp,
                node_id=result.node_id,
                status=result.status,
                attributes=result.attributes,
            )
        else:
            emit(result, source_name=source_name, timestamp=timestamp)

    def process_text(
        line: str, *, source_name: NodeSource, timestamp: float | None
    ) -> None:
        last_timestamp[source_name] = timestamp
        for result in processors[source_name].process(line):
            emit_processed(result, source_name=source_name, timestamp=timestamp)

    def process_record(record: InputRecord, *, source_name: NodeSource) -> None:
        if isinstance(record, TextRecord):
            process_text(
                record.text, source_name=source_name, timestamp=record.timestamp
            )
        else:
            emit_processed(record, source_name=source_name, timestamp=None)

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
        while source is not None:
            try:
                lines = source.read_new()
            except LogReadLimitExceeded as exc:
                if len(processors) == 1:
                    raise
                # 文件读取超限只停止这个来源，让其他来源继续交接。
                file_capacity_error = str(exc)
                source = None
                break
            for line in lines:
                process_text(line, source_name="file", timestamp=time.time())
            if not closing or not source.has_more:
                break
        if custom_source is not None:
            closing_source = closing
            for record in custom_source.close() if closing else custom_source.poll():
                process_record(record, source_name="custom")
        if closing:
            break
    reader.join()
    for processor_source in tuple(processors):
        processor = processors.pop(processor_source)
        for result in processor.close():
            emit_processed(
                result,
                source_name=processor_source,
                timestamp=last_timestamp.get(processor_source),
            )
    if postprocessor is not None:
        final_bytes = 0
        entries = postprocessor(list(collected.values()))
        for count, entry in enumerate(entries):
            if count == MAX_NODE_FRAMES:
                raise LogReadLimitExceeded("最终报告容量已满")
            final_bytes += _send(
                pipe,
                FinalEntry(entry=entry),
                remaining_bytes=MAX_NODE_BYTES - final_bytes,
            )
        _send(pipe, FinalReportReady())
    if sink is not None:
        closing_sink = True
        try:
            sink.close()
        except Exception as exc:
            if not sink_error:
                sink_error = f"close: {type(exc).__name__}"
    _send(
        pipe,
        Closed(
            sink_error=sink_error,
            capacity_error=observation_capacity_error or file_capacity_error,
        ),
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
