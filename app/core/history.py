"""历史单次归档、查询和维护；与配置数据库及专项结果判断独立。"""

import asyncio
import copy
import json
import math
import os
import shutil
import sqlite3
import threading
from collections.abc import Callable, Sequence
from contextlib import closing, suppress
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import ClassVar, Literal, TypeVar, cast
from uuid import UUID, uuid4

from app.core import Config
from app.models.schema import (
    HistoryAggregate,
    HistoryAggregateError,
    HistoryAggregationItem,
    HistoryAttachment,
    HistoryAttachmentFile,
    HistoryBackupSnapshot,
    HistoryBucket,
    HistoryCleanupReport,
    HistoryCounterStatistic,
    HistoryCounterValue,
    HistoryDetail,
    HistoryIndexItem,
    HistoryKeyedSnapshotStatistic,
    HistoryRecord,
    HistoryRecordQuery,
    HistorySnapshotStatistic,
    HistoryStatistic,
    HistoryStorageIssue,
    HistoryUserOverview,
    HistoryWrite,
)
from app.utils import get_logger
from app.utils import io as _utils_io

logger = get_logger("历史记录")
_T = TypeVar("_T")


class HistoryStorageError(RuntimeError):
    """历史存储、查询或维护无法完成。"""


class HistoryNotFoundError(HistoryStorageError):
    """记录或附件不存在，或附件已不可用。"""


class HistorySaveError(HistoryStorageError):
    """保存失败时说明记录是否已入库及相关存储错误。"""

    def __init__(
        self,
        *,
        record_id: UUID | None,
        record_saved: bool,
        errors: Sequence[HistoryStorageIssue],
    ) -> None:
        self.record_id: UUID | None = record_id
        self.record_saved: bool = record_saved
        self.errors: tuple[HistoryStorageIssue, ...] = tuple(errors)
        super().__init__(
            "; ".join(f"{issue.stage}: {issue.message}" for issue in errors)
        )


def _add_counters(
    left: HistoryCounterValue, right: HistoryCounterValue
) -> HistoryCounterValue:
    """递归相加计数树，并拒绝结构冲突或非有限结果。"""

    if isinstance(left, dict) and isinstance(right, dict):
        result = copy.deepcopy(left)
        for key, value in right.items():
            result[key] = (
                _add_counters(result[key], value)
                if key in result
                else copy.deepcopy(value)
            )
        return result
    if isinstance(left, dict) or isinstance(right, dict):
        raise ValueError("计数结构冲突")
    try:
        value = left + right
    except OverflowError as error:
        raise ValueError("计数聚合超出有限数值范围") from error
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("计数聚合超出有限数值范围")
    return value


def aggregate_data(records: Sequence[HistoryAggregationItem]) -> HistoryAggregate:
    """按实际时间稳定聚合；冲突统计键整体失效，输入保持不变。"""

    result = HistoryAggregate()
    origins: dict[str, list[int]] = {}
    failed: dict[str, HistoryAggregateError] = {}
    ordered = sorted(
        enumerate(records), key=lambda item: (item[1].time.timestamp(), item[0])
    )
    for index, record in ordered:
        for key, statistic in record.data.items():
            origins.setdefault(key, []).append(index)
            if key in failed:
                failed[key].input_indices = list(origins[key])
                continue
            previous = result.data.get(key)
            if previous is None:
                result.data[key] = statistic.model_copy(deep=True)
                continue
            try:
                if type(previous) is not type(statistic):
                    raise ValueError("统计类型冲突")
                if isinstance(previous, HistoryCounterStatistic) and isinstance(
                    statistic, HistoryCounterStatistic
                ):
                    previous.value = _add_counters(previous.value, statistic.value)
                elif isinstance(previous, HistorySnapshotStatistic) and isinstance(
                    statistic, HistorySnapshotStatistic
                ):
                    result.data[key] = statistic.model_copy(deep=True)
                elif isinstance(previous, HistoryKeyedSnapshotStatistic) and isinstance(
                    statistic, HistoryKeyedSnapshotStatistic
                ):
                    previous.value.update(copy.deepcopy(statistic.value))
            except ValueError as error:
                _ = result.data.pop(key, None)
                issue = HistoryAggregateError(
                    key=key, message=str(error), input_indices=list(origins[key])
                )
                failed[key] = issue
                result.errors.append(issue)
    return result


class HistoryStore:
    VERSION: ClassVar[int] = 1
    CLOSE_TIMEOUT: ClassVar[float] = 2.0

    def __init__(self) -> None:
        """初始化历史目录、数据库位置及异步操作状态。"""

        self.root: Path = Config.history_path
        self.database: Path = Config.data_path / "history.db"
        self._lock: asyncio.Lock = asyncio.Lock()
        self._workers: dict[asyncio.Future[object], threading.Event] = {}
        self._workers_changed: asyncio.Event = asyncio.Event()
        self._initialized: bool = False
        self._closing: bool = False
        self._video_limit: int = 0

    async def _run(self, operation: Callable[[threading.Event], _T]) -> _T:
        """串行化完整操作；阻塞文件工作用守护线程，普通取消等待操作结束。"""

        async with self._lock:
            if self._closing:
                raise HistoryStorageError("历史服务已关闭")
            loop = asyncio.get_running_loop()
            future: asyncio.Future[object] = loop.create_future()
            cancel = threading.Event()
            self._workers[future] = cancel
            self._workers_changed.set()

            def finish(value: object, error: BaseException | None) -> None:
                if not future.done():
                    if error is None:
                        future.set_result(value)
                    else:
                        future.set_exception(error)

            def work() -> None:
                value: object = None
                error: BaseException | None = None
                try:
                    value = operation(cancel)
                except Exception as exc:
                    error = (
                        exc
                        if isinstance(exc, HistoryStorageError)
                        else HistoryStorageError(str(exc))
                    )
                    if error is not exc:
                        error.__cause__ = exc
                with suppress(RuntimeError):
                    _ = loop.call_soon_threadsafe(finish, value, error)

            threading.Thread(target=work, name="history-storage", daemon=True).start()
            interrupted = None
            try:
                while not future.done():
                    try:
                        _ = await asyncio.shield(future)
                    except asyncio.CancelledError as error:
                        interrupted = error
                return cast(_T, future.result())
            except Exception:
                if interrupted is not None:
                    logger.opt(exception=True).warning("取消期间历史存储操作失败")
                raise
            finally:
                _ = self._workers.pop(future, None)
                self._workers_changed.set()
                # 即使工作线程失败也继续传播取消，防止定时循环在关闭时恢复运行。
                if interrupted is not None:
                    raise interrupted

    def _connect(self, cancel: threading.Event) -> sqlite3.Connection:
        """创建启用外键和取消检查的 SQLite 连接。"""

        if cancel.is_set():
            raise HistoryStorageError("历史服务正在关闭，归档已停止")
        connection = sqlite3.connect(self.database, timeout=1)
        connection.row_factory = sqlite3.Row
        # 每条虚拟机指令尽早检查关闭信号；已进入底层 I/O 的提交仍可能完成，
        # 因此关闭超时只能报告保存状态未确认。
        connection.set_progress_handler(lambda: int(cancel.is_set()), 1)
        connection.execute("PRAGMA foreign_keys=ON").close()
        connection.execute("PRAGMA synchronous=FULL").close()
        return connection

    async def initialize(self, *, video_limit_bytes: int) -> None:
        """初始化历史存储，并应用视频容量限制。"""

        if self._initialized:
            return
        limit = video_limit_bytes

        def initialize_storage(cancel: threading.Event) -> None:
            """创建或校验数据库，清理孤立文件并恢复附件状态。"""

            self.database.parent.mkdir(parents=True, exist_ok=True)
            self.root.mkdir(parents=True, exist_ok=True)
            with closing(self._connect(cancel)) as connection:
                version = cast(
                    int, connection.execute("PRAGMA user_version").fetchone()[0]
                )
                if version == 0:
                    connection.execute("PRAGMA journal_mode=WAL").close()
                    if cancel.is_set():
                        raise HistoryStorageError("历史服务正在关闭，归档已停止")
                    connection.executescript("""
                        BEGIN;
                        CREATE TABLE IF NOT EXISTS records (
                            id TEXT PRIMARY KEY,
                            time TEXT NOT NULL, timestamp REAL NOT NULL, date TEXT NOT NULL,
                            username TEXT NOT NULL, script_name TEXT NOT NULL,
                            status TEXT NOT NULL, message TEXT NOT NULL, data TEXT NOT NULL,
                            log_path TEXT, log_text_fallback TEXT, storage_errors TEXT NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS attachments (
                        archive_order INTEGER PRIMARY KEY AUTOINCREMENT,
                        id TEXT NOT NULL UNIQUE,
                            record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                            kind TEXT NOT NULL, role TEXT NOT NULL, display_name TEXT NOT NULL,
                            relative_path TEXT, byte_size INTEGER NOT NULL,
                            saved_via TEXT, available INTEGER NOT NULL, unavailable_reason TEXT
                        );
                    CREATE TABLE IF NOT EXISTS pending_files (
                        attachment_id TEXT PRIMARY KEY,
                        record_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        target_path TEXT NOT NULL,
                        source_path TEXT,
                        byte_size INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    );
                        CREATE INDEX IF NOT EXISTS history_date ON records(date, timestamp, id);
                        CREATE INDEX IF NOT EXISTS history_user ON records(username, timestamp, id);
                        CREATE INDEX IF NOT EXISTS history_script ON records(script_name, timestamp, id);
                        CREATE INDEX IF NOT EXISTS history_attachments ON attachments(record_id);
                        PRAGMA user_version=1;
                        COMMIT;
                    """).close()
                elif version != self.VERSION:
                    raise HistoryStorageError("历史数据库版本不支持")
                if (
                    cast(str, connection.execute("PRAGMA quick_check").fetchone()[0])
                    != "ok"
                ):
                    raise HistoryStorageError("历史数据库损坏")
                for table in ("records", "attachments", "pending_files"):
                    connection.execute(f"SELECT * FROM {table} LIMIT 0").close()
                for row in cast(
                    list[sqlite3.Row],
                    connection.execute(
                        "SELECT target_path FROM pending_files"
                    ).fetchall(),
                ):
                    target = self._pending_target(cast(str, row["target_path"]))
                    if target is None:
                        continue
                    for path in (target, target.with_name(target.name + ".temp")):
                        path.unlink(missing_ok=True)
                connection.execute("DELETE FROM pending_files").close()
                complete_paths: set[str] = set()
                for row in cast(
                    list[sqlite3.Row],
                    connection.execute(
                        "SELECT relative_path FROM attachments WHERE relative_path IS NOT NULL UNION SELECT log_path FROM records WHERE log_path IS NOT NULL"
                    ).fetchall(),
                ):
                    complete_paths.add(cast(str, row["relative_path"]))
                # 持久化路径只在初始化或备份恢复后校验，运行期直接使用内部路径。
                record_directories: set[str] = set()
                for row in cast(
                    list[sqlite3.Row],
                    connection.execute("SELECT id, date FROM records").fetchall(),
                ):
                    record_directories.add(f"{row['date']}/{row['id']}")
                root = self.root.absolute()
                for day in self.root.iterdir():
                    if not day.is_dir():
                        continue
                    for directory in day.iterdir():
                        if f"{day.name}/{directory.name}" in record_directories:
                            continue
                        if cancel.is_set():
                            raise HistoryStorageError("历史服务正在关闭，归档已停止")
                        if directory.is_dir():
                            shutil.rmtree(directory)
                for relative in complete_paths | record_directories:
                    if cancel.is_set():
                        raise HistoryStorageError("历史服务正在关闭，归档已停止")
                    path = Path(os.path.abspath(self.root / relative))
                    if not path.is_relative_to(root) or path == root:
                        raise HistoryStorageError("历史文件路径越界")
                # 仅清理已登记目标对应的内部临时文件。
                for relative in complete_paths:
                    temporary_relative = relative + ".temp"
                    if temporary_relative not in complete_paths:
                        if cancel.is_set():
                            raise HistoryStorageError("历史服务正在关闭，归档已停止")
                        _ = (self.root / temporary_relative).unlink(missing_ok=True)
                rows = cast(
                    list[sqlite3.Row],
                    connection.execute(
                        "SELECT id, relative_path FROM attachments WHERE available=1"
                    ).fetchall(),
                )
                for raw_row in rows:
                    row = cast(dict[str, object], dict(raw_row))
                    if (
                        not row["relative_path"]
                        or not (self.root / cast(str, row["relative_path"])).is_file()
                    ):
                        connection.execute(
                            "UPDATE attachments SET available=0, unavailable_reason='missing' WHERE id=?",
                            (cast(str, row["id"]),),
                        ).close()
                if cancel.is_set():
                    raise HistoryStorageError("历史服务正在关闭，归档已停止")
                connection.commit()
            if cancel.is_set():
                raise HistoryStorageError("历史服务正在关闭，归档已停止")
            self._video_limit = limit
            with closing(self._connect(cancel)) as connection:
                report = self._enforce_quota(connection, cancel=cancel)
                if report.errors:
                    logger.warning(f"启动清理历史视频失败：{len(report.errors)} 项")
            self._initialized = True

        await self._run(initialize_storage)

    async def close(self, *, after: asyncio.Task[None] | None = None) -> None:
        """等待用户收尾；阻塞操作按期限请求取消，超时则保留保存状态未确认。"""

        try:
            while after is not None and not after.done():
                self._workers_changed.clear()
                pending = {future for future in self._workers if not future.done()}
                changed = asyncio.create_task(self._workers_changed.wait())
                try:
                    done, _ = await asyncio.wait(
                        {after, changed, *pending},
                        timeout=self.CLOSE_TIMEOUT / 2 if pending else None,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        break
                finally:
                    changed.cancel()
                    with suppress(asyncio.CancelledError):
                        await changed
        finally:
            self._closing = True
            pending = set(self._workers)
            if pending:
                _, pending = await asyncio.wait(pending, timeout=self.CLOSE_TIMEOUT / 2)
            for future in pending:
                self._workers[future].set()
            if pending:
                _, pending = await asyncio.wait(pending, timeout=self.CLOSE_TIMEOUT / 2)
            for future in pending:
                if not future.done():
                    future.set_exception(
                        HistoryStorageError("历史服务关闭期限已到，保存状态未确认")
                    )
            self._initialized = False

    def _pending_target(self, value: str) -> Path | None:
        """旧备份中的绝对暂存路径不得操作当前历史目录之外的文件。"""

        target = Path(os.path.abspath(value))
        try:
            root = self.root.resolve()
            resolved = target.resolve()
        except (OSError, RuntimeError):
            return None
        return target if resolved != root and resolved.is_relative_to(root) else None

    async def record(self, record: HistoryWrite) -> HistoryRecord:
        """校验并一次性保存一条任务记录；存储不完整时抛出带状态的异常。"""

        record = HistoryWrite.model_validate(record.model_dump())
        if not self._initialized:
            raise HistoryStorageError("历史服务尚未初始化")
        return await self._run(lambda cancel: self._save(record, cancel))

    def _save(self, record: HistoryWrite, cancel: threading.Event) -> HistoryRecord:
        """归档日志和附件后，在一个事务中写入记录及附件元数据。"""

        errors: list[HistoryStorageIssue] = []
        record_id = None
        try:
            with closing(self._connect(cancel)) as connection:
                record_id = uuid4()
                attachment_ids = [uuid4() for _ in record.attachments]
                relative = f"{record.time.date().isoformat()}/{record_id}"
                directory = self.root / relative
                directory_ready = False
                try:
                    if cancel.is_set():
                        raise HistoryStorageError("历史服务正在关闭，归档已停止")
                    directory.mkdir(parents=True, exist_ok=False)
                    directory_ready = True
                except OSError as error:
                    errors.append(
                        HistoryStorageIssue(
                            stage="mkdir",
                            target_path=str(directory),
                            error_type=type(error).__name__,
                            message=str(error),
                        )
                    )
                log_path = None
                fallback = record.logs
                if directory_ready:
                    log_target = directory / "0.log"
                    try:
                        if cancel.is_set():
                            raise HistoryStorageError("历史服务正在关闭，归档已停止")
                        _utils_io.write_file(log_target, record.logs)
                        log_path = f"{relative}/0.log"
                        fallback = None
                    except OSError as error:
                        errors.append(
                            HistoryStorageIssue(
                                stage="write_log",
                                target_path=str(log_target),
                                error_type=type(error).__name__,
                                message=str(error),
                            )
                        )
                attachments: list[HistoryAttachment] = []
                for index, source in enumerate(record.attachments):
                    if cancel.is_set():
                        raise HistoryStorageError("历史服务正在关闭，归档已停止")
                    attachment = HistoryAttachment(
                        id=attachment_ids[index],
                        record_id=record_id,
                        kind=source.kind,
                        role=source.role,
                        display_name=source.display_name,
                    )
                    attachments.append(attachment)
                    if not directory_ready:
                        attachment.unavailable_reason = "directory_unavailable"
                        continue
                    target = directory / f"{index + 1}{source.path.suffix}"
                    attachment.relative_path = target.relative_to(self.root).as_posix()
                    try:
                        if not source.path.is_file():
                            raise OSError(f"附件不是可读普通文件：{source.path}")
                        size = source.path.stat().st_size
                        attachment.byte_size = size
                        if source.kind == "video":
                            quota = self._enforce_quota(
                                connection,
                                extra=size,
                                protected_record_id=record_id,
                                cancel=cancel,
                            )
                            errors.extend(quota.errors)
                            if self._video_usage(connection) + size > self._video_limit:
                                attachment.unavailable_reason = "quota"
                                errors.append(
                                    HistoryStorageIssue(
                                        stage="quota",
                                        attachment_index=index,
                                        source_path=str(source.path),
                                        target_path=str(target),
                                        error_type="OSError",
                                        message="视频容量不足",
                                    )
                                )
                                continue
                        connection.execute(
                            """
                            INSERT INTO pending_files
                                (attachment_id, record_id, kind, target_path,
                                 source_path, byte_size, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                str(attachment.id),
                                str(record_id),
                                source.kind,
                                str(self.root / attachment.relative_path),
                                str(source.path),
                                size,
                                record.time.isoformat(),
                            ),
                        ).close()
                        connection.commit()
                        move_issue = None
                        if source.archive_mode == "move":
                            try:
                                if cancel.is_set():
                                    raise HistoryStorageError(
                                        "历史服务正在关闭，归档已停止"
                                    )
                                _ = source.path.rename(target)
                                attachment.saved_via = "move"
                                attachment.available = True
                            except OSError as error:
                                move_issue = HistoryStorageIssue(
                                    stage="move",
                                    attachment_index=index,
                                    source_path=str(source.path),
                                    target_path=str(target),
                                    error_type=type(error).__name__,
                                    message=str(error),
                                )
                                errors.append(move_issue)
                        if not attachment.available:
                            temporary = target.with_name(target.name + ".temp")
                            try:
                                with (
                                    source.path.open("rb") as reader,
                                    temporary.open("xb") as writer,
                                ):
                                    while True:
                                        if cancel.is_set():
                                            raise HistoryStorageError(
                                                "历史服务正在关闭，归档已停止"
                                            )
                                        chunk = reader.read(1024 * 1024)
                                        if not chunk:
                                            break
                                        _ = writer.write(chunk)
                                    writer.flush()
                                    _ = os.fsync(writer.fileno())
                                if cancel.is_set():
                                    raise HistoryStorageError(
                                        "历史服务正在关闭，归档已停止"
                                    )
                                _ = temporary.rename(target)
                                attachment.saved_via = "copy"
                                attachment.available = True
                                if move_issue is not None:
                                    move_issue.recovered = True
                            except OSError as copy_error:
                                errors.append(
                                    HistoryStorageIssue(
                                        stage="copy",
                                        attachment_index=index,
                                        source_path=str(source.path),
                                        target_path=str(target),
                                        error_type=type(copy_error).__name__,
                                        message=str(copy_error),
                                    )
                                )
                                attachment.unavailable_reason = "archive_failed"
                            finally:
                                try:
                                    temporary.unlink(missing_ok=True)
                                except OSError as cleanup_error:
                                    errors.append(
                                        HistoryStorageIssue(
                                            stage="cleanup",
                                            attachment_index=index,
                                            target_path=str(temporary),
                                            error_type=type(cleanup_error).__name__,
                                            message=str(cleanup_error),
                                        )
                                    )
                    except OSError as error:
                        errors.append(
                            HistoryStorageIssue(
                                stage=source.archive_mode,
                                attachment_index=index,
                                source_path=str(source.path),
                                target_path=str(target),
                                error_type=type(error).__name__,
                                message=str(error),
                            )
                        )
                        attachment.unavailable_reason = "archive_failed"
                if cancel.is_set():
                    raise HistoryStorageError("历史服务正在关闭，归档已停止")
                with connection:
                    connection.execute(
                        "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(record_id),
                            record.time.isoformat(),
                            record.time.timestamp(),
                            record.time.date().isoformat(),
                            record.username,
                            record.script_name,
                            record.status,
                            record.message,
                            json.dumps(
                                {
                                    key: value.model_dump(mode="json")
                                    for key, value in record.data.items()
                                },
                                ensure_ascii=False,
                                allow_nan=False,
                            ),
                            log_path,
                            fallback,
                            json.dumps(
                                [issue.model_dump() for issue in errors],
                                ensure_ascii=False,
                            ),
                        ),
                    ).close()
                    connection.executemany(
                        """
                        INSERT INTO attachments
                            (id, record_id, kind, role, display_name, relative_path,
                             byte_size, saved_via, available, unavailable_reason)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                str(item.id),
                                str(item.record_id),
                                item.kind,
                                item.role,
                                item.display_name,
                                item.relative_path,
                                item.byte_size,
                                item.saved_via,
                                int(item.available),
                                item.unavailable_reason,
                            )
                            for item in attachments
                        ],
                    ).close()
                    connection.execute(
                        "DELETE FROM pending_files WHERE record_id=?",
                        (str(record_id),),
                    ).close()
                    if cancel.is_set():
                        raise HistoryStorageError("历史服务正在关闭，归档已停止")
                result = HistoryRecord(
                    id=record_id,
                    time=record.time,
                    username=record.username,
                    script_name=record.script_name,
                    status=record.status,
                    message=record.message,
                    data=record.data,
                    attachments=attachments,
                    storage_errors=errors,
                    storage_error_count=len(errors),
                    log_path=log_path,
                    has_log_fallback=fallback is not None,
                )
        except Exception as error:
            errors.append(
                HistoryStorageIssue(
                    stage="database",
                    target_path=str(self.database),
                    error_type=type(error).__name__,
                    message=str(error),
                )
            )
            raise HistorySaveError(
                record_id=record_id, record_saved=False, errors=errors
            ) from error
        if any(not issue.recovered for issue in errors):
            raise HistorySaveError(
                record_id=record_id, record_saved=True, errors=errors
            )
        return result

    def _select(
        self,
        connection: sqlite3.Connection,
        query: HistoryRecordQuery,
        *,
        columns: tuple[str, ...],
        limited: bool = True,
    ) -> list[sqlite3.Row]:
        """按查询条件读取所需列，并按时间倒序排列。"""

        where: list[str] = []
        args: list[object] = []
        for column, operator, value in (
            ("date", ">=", query.start_date.isoformat() if query.start_date else None),
            ("date", "<=", query.end_date.isoformat() if query.end_date else None),
            ("username", "=", query.username),
            ("script_name", "=", query.script_name),
            ("status", "=", query.status),
        ):
            if value is not None:
                where.append(f"{column} {operator} ?")
                args.append(value)
        statement = f"SELECT {', '.join(columns)} FROM records"
        if where:
            statement += " WHERE " + " AND ".join(where)
        statement += " ORDER BY timestamp DESC, id DESC"
        if limited:
            statement += " LIMIT ?"
            args.append(query.limit)
        return cast(
            list[sqlite3.Row],
            connection.execute(statement, args).fetchall(),
        )

    async def get_detail(self, *, record_id: UUID) -> HistoryDetail:
        """读取记录详情、日志内容，并检查附件是否仍可用。"""

        if not self._initialized:
            raise HistoryStorageError("历史服务尚未初始化")

        def read(cancel: threading.Event) -> HistoryDetail:
            with closing(self._connect(cancel)) as connection:
                row = cast(
                    sqlite3.Row | None,
                    connection.execute(
                        "SELECT * FROM records WHERE id=?", (str(record_id),)
                    ).fetchone(),
                )
                if row is None:
                    raise HistoryNotFoundError(f"历史记录不存在：{record_id}")
                storage_errors = cast(
                    list[object], json.loads(cast(str, row["storage_errors"]))
                )
                attachments = [
                    HistoryAttachment.model_validate(
                        cast(dict[str, object], dict(item))
                    )
                    for item in cast(
                        list[sqlite3.Row],
                        connection.execute(
                            "SELECT * FROM attachments WHERE record_id=? ORDER BY id",
                            (str(record_id),),
                        ).fetchall(),
                    )
                ]
                detail = HistoryDetail.model_validate(
                    {
                        "id": UUID(cast(str, row["id"])),
                        "time": datetime.fromisoformat(cast(str, row["time"])),
                        "username": cast(str, row["username"]),
                        "script_name": cast(str, row["script_name"]),
                        "status": cast(
                            Literal["success", "error", "skipped", "cancelled"],
                            row["status"],
                        ),
                        "message": cast(str, row["message"]),
                        "data": json.loads(cast(str, row["data"])),
                        "storage_errors": storage_errors,
                        "storage_error_count": len(storage_errors),
                        "has_log_fallback": row["log_text_fallback"] is not None,
                        "log_path": cast(str | None, row["log_path"]),
                        "attachments": attachments,
                    }
                )
                reason = None
                if detail.log_path is not None:
                    try:
                        content = _utils_io.read_file(self.root / detail.log_path)
                        if isinstance(content, str):
                            detail.log_content = content
                    except (OSError, UnicodeError) as error:
                        reason = type(error).__name__
                if detail.log_content is None and detail.has_log_fallback:
                    fallback_row = cast(
                        sqlite3.Row | None,
                        connection.execute(
                            "SELECT log_text_fallback FROM records WHERE id=?",
                            (str(record_id),),
                        ).fetchone(),
                    )
                    if fallback_row is None:
                        raise HistoryNotFoundError("历史记录日志缺失")
                    detail.log_content = cast(str, fallback_row[0])
                detail.log_available = detail.log_content is not None
                detail.log_unavailable_reason = (
                    None if detail.log_available else reason or "missing"
                )
                for item in detail.attachments:
                    if item.available and (
                        not item.relative_path
                        or not (self.root / item.relative_path).is_file()
                    ):
                        item.available = False
                        item.unavailable_reason = "missing"
                return detail

        return await self._run(read)

    async def get_attachment(self, *, attachment_id: UUID) -> HistoryAttachmentFile:
        """解析可用附件的归档路径；不存在或缺失时抛出异常。"""

        if not self._initialized:
            raise HistoryStorageError("历史服务尚未初始化")

        def read(cancel: threading.Event) -> HistoryAttachmentFile:
            with closing(self._connect(cancel)) as connection:
                row = cast(
                    sqlite3.Row | None,
                    connection.execute(
                        "SELECT * FROM attachments WHERE id=?",
                        (str(attachment_id),),
                    ).fetchone(),
                )
                if row is None:
                    raise HistoryNotFoundError("历史附件不存在")
                item = HistoryAttachment.model_validate(
                    cast(dict[str, object], dict(row))
                )
                if not item.available or not item.relative_path:
                    raise HistoryNotFoundError(
                        item.unavailable_reason or "历史附件不可用"
                    )
                path = self.root / item.relative_path
                if not path.is_file():
                    raise HistoryNotFoundError("历史附件文件缺失")
                return HistoryAttachmentFile(
                    id=item.id,
                    record_id=item.record_id,
                    kind=item.kind,
                    role=item.role,
                    display_name=item.display_name,
                    relative_path=item.relative_path,
                    byte_size=item.byte_size,
                    saved_via=item.saved_via,
                    available=item.available,
                    unavailable_reason=item.unavailable_reason,
                    path=path,
                )

        return await self._run(read)

    async def search(
        self,
        *,
        start_date: date,
        end_date: date,
        mode: Literal["DAILY", "WEEKLY", "MONTHLY"],
    ) -> dict[str, dict[str, HistoryBucket]]:
        """按日、周或月分组查询记录并聚合统计数据。"""

        if not self._initialized:
            raise HistoryStorageError("历史服务尚未初始化")

        def read(cancel: threading.Event) -> dict[str, dict[str, HistoryBucket]]:
            groups: dict[str, dict[str, list[sqlite3.Row]]] = {}
            with closing(self._connect(cancel)) as connection:
                rows = self._select(
                    connection,
                    HistoryRecordQuery(start_date=start_date, end_date=end_date),
                    columns=(
                        "id",
                        "time",
                        "date",
                        "username",
                        "script_name",
                        "status",
                        "message",
                        "data",
                        "storage_errors",
                    ),
                    limited=False,
                )
                for row in reversed(rows):
                    day = date.fromisoformat(cast(str, row["date"]))
                    if mode == "WEEKLY":
                        day -= timedelta(days=day.weekday())
                    elif mode == "MONTHLY":
                        day = day.replace(day=1)
                    groups.setdefault(day.isoformat(), {}).setdefault(
                        cast(str, row["username"]), []
                    ).append(row)
                result: dict[str, dict[str, HistoryBucket]] = {}
                for day, users in groups.items():
                    result[day] = {}
                    for user, entries in users.items():
                        aggregate = aggregate_data(
                            [
                                HistoryAggregationItem(
                                    time=datetime.fromisoformat(cast(str, row["time"])),
                                    data=cast(
                                        dict[str, HistoryStatistic],
                                        json.loads(cast(str, row["data"])),
                                    ),
                                )
                                for row in entries
                            ]
                        )
                        for error in aggregate.errors:
                            error.record_ids = [
                                UUID(cast(str, entries[index]["id"]))
                                for index in error.input_indices
                            ]
                        result[day][user] = HistoryBucket(
                            index=[
                                HistoryIndexItem(
                                    id=UUID(cast(str, row["id"])),
                                    time=datetime.fromisoformat(cast(str, row["time"])),
                                    username=cast(str, row["username"]),
                                    script_name=cast(str, row["script_name"]),
                                    status=cast(
                                        Literal[
                                            "success",
                                            "error",
                                            "skipped",
                                            "cancelled",
                                        ],
                                        row["status"],
                                    ),
                                    message=cast(str, row["message"]),
                                    storage_error_count=len(
                                        cast(
                                            list[object],
                                            json.loads(
                                                cast(str, row["storage_errors"])
                                            ),
                                        )
                                    ),
                                )
                                for row in entries
                            ],
                            data=aggregate.data,
                            aggregate_errors=aggregate.errors,
                        )
                return result

        return await self._run(read)

    async def get_overview(self, *, day: date) -> dict[str, HistoryUserOverview]:
        """汇总指定日期各用户的执行次数、失败记录和最近时间。"""

        if not self._initialized:
            raise HistoryStorageError("历史服务尚未初始化")

        def read(cancel: threading.Event) -> dict[str, HistoryUserOverview]:
            with closing(self._connect(cancel)) as connection:
                result: dict[str, HistoryUserOverview] = {}
                for row in self._select(
                    connection,
                    HistoryRecordQuery(start_date=day, end_date=day),
                    columns=("id", "time", "username", "status", "message"),
                    limited=False,
                ):
                    overview = result.setdefault(
                        cast(str, row["username"]), HistoryUserOverview()
                    )
                    overview.execute_count += 1
                    if overview.latest_time is None:
                        overview.latest_time = datetime.fromisoformat(
                            cast(str, row["time"])
                        )
                    if row["status"] == "error":
                        overview.error_count += 1
                        overview.error_info[UUID(cast(str, row["id"]))] = cast(
                            str, row["message"]
                        )
                return result

        return await self._run(read)

    def _video_usage(
        self,
        connection: sqlite3.Connection,
        pending: Sequence[HistoryAttachment] = (),
    ) -> int:
        """计算已归档及待写入视频文件占用的空间。"""

        paths: list[str] = []
        for row in cast(
            list[sqlite3.Row],
            connection.execute(
                "SELECT relative_path FROM attachments WHERE kind='video' AND relative_path IS NOT NULL"
            ).fetchall(),
        ):
            paths.append(cast(str, row["relative_path"]))
        paths.extend(
            item.relative_path
            for item in pending
            if item.kind == "video" and item.relative_path
        )
        total = 0
        for relative in set(paths):
            target = self.root / relative
            # 复制失败且清理失败的半成品也占配额，不能当成已释放空间。
            for file in (target, target.with_name(target.name + ".temp")):
                if file.is_file():
                    total += file.stat().st_size
        total += sum(
            cast(int, row["byte_size"])
            for row in cast(
                list[sqlite3.Row],
                connection.execute(
                    "SELECT byte_size, target_path FROM pending_files WHERE kind='video'"
                ).fetchall(),
            )
            if self._pending_target(cast(str, row["target_path"])) is not None
        )
        return total

    def _enforce_quota(
        self,
        connection: sqlite3.Connection,
        *,
        extra: int = 0,
        pending: Sequence[HistoryAttachment] = (),
        protected_record_id: UUID | None = None,
        cancel: threading.Event,
    ) -> HistoryCleanupReport:
        """按容量上限清理旧视频并更新附件可用状态。"""

        report = HistoryCleanupReport()
        if extra > self._video_limit:
            return report
        usage = self._video_usage(connection, pending)
        pending_targets: dict[UUID, Path] = {}
        pending_candidates: list[HistoryAttachment] = []
        for row in cast(
            list[sqlite3.Row],
            connection.execute(
                """
                SELECT attachment_id, record_id, target_path, byte_size
                FROM pending_files
                WHERE kind='video'
                ORDER BY created_at, rowid
                """
            ).fetchall(),
        ):
            pending_record_id = UUID(cast(str, row["record_id"]))
            if (
                protected_record_id is not None
                and pending_record_id == protected_record_id
            ):
                continue
            pending_id = UUID(cast(str, row["attachment_id"]))
            target = self._pending_target(cast(str, row["target_path"]))
            if target is None:
                continue
            pending_targets[pending_id] = target
            pending_candidates.append(
                HistoryAttachment(
                    id=pending_id,
                    record_id=pending_record_id,
                    kind="video",
                    role="pending",
                    display_name=target.name,
                    relative_path=target.relative_to(self.root).as_posix()
                    if target.is_relative_to(self.root)
                    else None,
                    byte_size=cast(int, row["byte_size"]),
                    available=True,
                )
            )
        candidates = [
            HistoryAttachment.model_validate(cast(dict[str, object], dict(row)))
            for row in cast(
                list[sqlite3.Row],
                connection.execute(
                    "SELECT * FROM attachments WHERE kind='video' AND relative_path IS NOT NULL ORDER BY archive_order"
                ).fetchall(),
            )
        ]
        candidates = pending_candidates + candidates
        candidates.extend(item for item in pending if item.kind == "video")
        for item in candidates:
            if item.id in pending_targets:
                target = pending_targets[item.id]
            elif not item.relative_path:
                continue
            else:
                target = self.root / item.relative_path
            if usage + extra <= self._video_limit:
                break
            if cancel.is_set():
                raise HistoryStorageError("历史服务正在关闭，归档已停止")
            is_pending = item.id in pending_targets
            for file in (target, target.with_name(target.name + ".temp")):
                try:
                    size = file.stat().st_size if file.is_file() else 0
                    file.unlink(missing_ok=True)
                    if not is_pending:
                        usage -= size
                    report.reclaimed_bytes += size
                    if file == target:
                        report.deleted_videos += int(size > 0)
                except OSError as error:
                    report.errors.append(
                        HistoryStorageIssue(
                            stage="cleanup",
                            target_path=str(file),
                            error_type=type(error).__name__,
                            message=str(error),
                        )
                    )
            if (
                not target.exists()
                and not target.with_name(target.name + ".temp").exists()
            ):
                if item.id in pending_targets:
                    try:
                        connection.execute(
                            "DELETE FROM pending_files WHERE attachment_id=?",
                            (str(item.id),),
                        ).close()
                        connection.commit()
                        usage -= item.byte_size
                    except sqlite3.Error as error:
                        report.errors.append(
                            HistoryStorageIssue(
                                stage="cleanup",
                                target_path=str(target),
                                error_type=type(error).__name__,
                                message=str(error),
                            )
                        )
                elif item in pending:
                    item.available = False
                    item.unavailable_reason = "quota"
                else:
                    connection.execute(
                        "UPDATE attachments SET available=0, unavailable_reason='quota' WHERE id=?",
                        (str(item.id),),
                    ).close()
                    if cancel.is_set():
                        raise HistoryStorageError("历史服务正在关闭，归档已停止")
                    connection.commit()
        return report

    async def set_video_limit(self, *, limit_bytes: int) -> HistoryCleanupReport:
        """更新视频容量上限并立即清理超额文件。"""

        if not self._initialized:
            raise HistoryStorageError("历史服务尚未初始化")

        def maintain(cancel: threading.Event) -> HistoryCleanupReport:
            self._video_limit = limit_bytes
            with closing(self._connect(cancel)) as connection:
                return self._enforce_quota(connection, cancel=cancel)

        return await self._run(maintain)

    async def prune(self, *, today: date, retention_days: int) -> HistoryCleanupReport:
        """删除超过保留期限的记录目录和数据库记录。"""

        if not self._initialized:
            raise HistoryStorageError("历史服务尚未初始化")

        def maintain(cancel: threading.Event) -> HistoryCleanupReport:
            report = HistoryCleanupReport()
            if retention_days == 0:
                return report
            cutoff = (today - timedelta(days=retention_days)).isoformat()
            with closing(self._connect(cancel)) as connection:
                for row in cast(
                    list[sqlite3.Row],
                    connection.execute(
                        "SELECT id, date FROM records WHERE date < ?", (cutoff,)
                    ).fetchall(),
                ):
                    if cancel.is_set():
                        raise HistoryStorageError("历史服务正在关闭，归档已停止")
                    target = self.root / cast(str, row["date"]) / cast(str, row["id"])
                    try:
                        size = 0
                        if target.exists():
                            size = sum(
                                file.stat().st_size
                                for file in target.rglob("*")
                                if file.is_file()
                            )
                            shutil.rmtree(target)
                        if cancel.is_set():
                            raise HistoryStorageError("历史服务正在关闭，归档已停止")
                        with connection:
                            connection.execute(
                                "DELETE FROM records WHERE id=?",
                                (cast(str, row["id"]),),
                            ).close()
                        report.deleted_records += 1
                        report.reclaimed_bytes += size
                    except OSError as error:
                        report.errors.append(
                            HistoryStorageIssue(
                                stage="cleanup",
                                target_path=str(target),
                                error_type=type(error).__name__,
                                message=str(error),
                            )
                        )
            return report

        return await self._run(maintain)

    async def export_snapshot(self, *, destination: Path) -> HistoryBackupSnapshot:
        """导出一致的 SQLite 快照及其日志和可用附件。"""

        if not self._initialized:
            raise HistoryStorageError("历史服务尚未初始化")
        destination = destination.absolute()
        if destination.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("历史快照不能保存在历史目录内")

        def export(cancel: threading.Event) -> HistoryBackupSnapshot:
            destination.mkdir(parents=True, exist_ok=True)
            database = destination / "history.db"
            history = destination / "history"
            if database.exists() or history.exists():
                raise HistoryStorageError("历史快照目标已存在")
            history.mkdir()
            with (
                closing(self._connect(cancel)) as source,
                closing(sqlite3.connect(database)) as target,
            ):

                def backup_progress(_status: int, _remaining: int, _total: int) -> None:
                    if cancel.is_set():
                        raise HistoryStorageError("历史服务正在关闭，归档已停止")

                source.backup(target, pages=128, progress=backup_progress)
                # 未完成归档不属于快照，恢复后也不能沿用原安装的清理路径。
                target.execute("DELETE FROM pending_files").close()
                target.commit()
                paths = [
                    cast(str, row["log_path"])
                    for row in cast(
                        list[sqlite3.Row],
                        source.execute(
                            "SELECT log_path FROM records WHERE log_path IS NOT NULL"
                        ).fetchall(),
                    )
                ]
                paths.extend(
                    cast(str, row["relative_path"])
                    for row in cast(
                        list[sqlite3.Row],
                        source.execute(
                            "SELECT relative_path FROM attachments WHERE available=1 AND relative_path IS NOT NULL"
                        ).fetchall(),
                    )
                )
                for relative in set(paths):
                    if cancel.is_set():
                        raise HistoryStorageError("历史服务正在关闭，归档已停止")
                    original = self.root / relative
                    if original.is_file():
                        output = history / relative
                        _ = output.parent.mkdir(parents=True, exist_ok=True)
                        _ = shutil.copy2(original, output)
            return HistoryBackupSnapshot(
                destination=destination,
                database=database,
                history=history,
            )

        return await self._run(export)


History = HistoryStore()

__all__ = ["History"]
