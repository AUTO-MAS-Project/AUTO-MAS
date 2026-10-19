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
from typing import TypeVar

from app.models.schema import (
    HistoryAggregate,
    HistoryAggregateError,
    HistoryAggregationItem,
    HistoryAttachment,
    HistoryAttachmentFile,
    HistoryBackupSnapshot,
    HistoryBucket,
    HistoryCleanupReport,
    HistoryDetail,
    HistoryIndexItem,
    HistoryRecord,
    HistoryRecordQuery,
    HistoryStorageIssue,
    HistoryUserOverview,
    HistoryWrite,
)
from app.utils import get_logger

logger = get_logger("历史记录")
_T = TypeVar("_T")
_VERSION = 1
_CLOSE_TIMEOUT = 2.0


class HistoryStorageError(RuntimeError):
    """历史存储、查询或维护无法完成。"""


class HistoryNotFoundError(HistoryStorageError):
    """记录或附件不存在，或附件已不可用。"""


class HistorySaveError(HistoryStorageError):
    def __init__(
        self,
        *,
        record_id: int | None,
        record_saved: bool,
        errors: Sequence[HistoryStorageIssue],
    ) -> None:
        self.record_id = record_id
        self.record_saved = record_saved
        self.errors = tuple(errors)
        super().__init__(
            "; ".join(f"{issue.stage}: {issue.message}" for issue in errors)
        )


def _add_counters(left, right):
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


def aggregate_history(records: Sequence[HistoryAggregationItem]) -> HistoryAggregate:
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
                if previous.kind != statistic.kind:
                    raise ValueError("统计类型冲突")
                if statistic.kind == "counter":
                    previous.value = _add_counters(previous.value, statistic.value)
                elif statistic.kind == "snapshot":
                    result.data[key] = statistic.model_copy(deep=True)
                else:
                    previous.value.update(copy.deepcopy(statistic.value))
            except ValueError as error:
                result.data.pop(key, None)
                issue = HistoryAggregateError(
                    key=key, message=str(error), input_indices=list(origins[key])
                )
                failed[key] = issue
                result.errors.append(issue)
    return result


def _issue(stage, error, *, index=None, source=None, target=None, recovered=False):
    return HistoryStorageIssue(
        stage=stage,
        attachment_index=index,
        source_path=str(source) if source is not None else None,
        target_path=str(target) if target is not None else None,
        error_type=type(error).__name__,
        message=str(error),
        recovered=recovered,
    )


def _check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise HistoryStorageError("历史服务正在关闭，归档已停止")


def _check_tree(path: Path) -> None:
    """升级和维护删除前拒绝链接，避免递归进入其他用户目录。"""

    if path.is_symlink() or path.is_junction():
        raise HistoryStorageError(f"历史目录不能是符号链接或联接：{path}")
    if path.exists():
        for current, directories, files in os.walk(path, followlinks=False):
            for name in directories + files:
                child = Path(current) / name
                if child.is_symlink() or child.is_junction():
                    raise HistoryStorageError(f"历史目录包含链接：{child}")


class HistoryStore:
    def __init__(self, *, root: Path, database: Path) -> None:
        self.root = Path(root).absolute()
        self.database = Path(database).absolute()
        self.marker = self.database.parent / "history-storage.json"
        self._lock = asyncio.Lock()
        self._workers: dict[asyncio.Future, threading.Event] = {}
        self._initialized = False
        self._closing = False
        self._video_limit = 0

    async def _run(self, operation: Callable[[threading.Event], _T]) -> _T:
        """串行化完整操作；阻塞文件工作用守护线程，普通取消等待操作结束。"""

        async with self._lock:
            if self._closing:
                raise HistoryStorageError("历史服务已关闭")
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            cancel = threading.Event()
            self._workers[future] = cancel

            def finish(value, error):
                if not future.done():
                    if error is None:
                        future.set_result(value)
                    else:
                        future.set_exception(error)

            def work():
                value = error = None
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
                    loop.call_soon_threadsafe(finish, value, error)

            threading.Thread(target=work, name="history-storage", daemon=True).start()
            interrupted = None
            try:
                while not future.done():
                    try:
                        await asyncio.shield(future)
                    except asyncio.CancelledError as error:
                        interrupted = error
                value = future.result()
                if interrupted is not None:
                    raise interrupted
                return value
            finally:
                self._workers.pop(future, None)

    def _require_ready(self) -> None:
        if not self._initialized:
            raise HistoryStorageError("历史服务尚未初始化")

    def _connect(self, cancel: threading.Event) -> sqlite3.Connection:
        _check_cancel(cancel)
        connection = sqlite3.connect(self.database, timeout=1)
        connection.row_factory = sqlite3.Row
        # 取消可能发生在 Python 最后一次检查与 SQLite 真正提交之间。
        # 每条指令都检查关闭信号，阻止已废弃的事务随后继续提交。
        connection.set_progress_handler(lambda: int(cancel.is_set()), 1)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _path(self, relative: str) -> Path:
        if self.root.is_symlink() or self.root.is_junction():
            raise HistoryStorageError("历史目录不能是链接")
        path = self.root / relative
        resolved = path.resolve()
        if (
            not resolved.is_relative_to(self.root.resolve())
            or resolved == self.root.resolve()
        ):
            raise HistoryStorageError("历史文件路径越界")
        current = path
        while current != self.root:
            if current.is_symlink() or current.is_junction():
                raise HistoryStorageError("历史文件不能是链接")
            current = current.parent
        return path

    def _write_marker(self, state: str, cancel: threading.Event) -> None:
        _check_cancel(cancel)
        temporary = self.marker.with_suffix(".json.part")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump({"version": _VERSION, "state": state}, file)
            file.flush()
            os.fsync(file.fileno())
        _check_cancel(cancel)
        temporary.replace(self.marker)

    def _validate_database(self, connection: sqlite3.Connection) -> None:
        if connection.execute("PRAGMA user_version").fetchone()[0] != _VERSION:
            raise HistoryStorageError("历史数据库版本不支持")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise HistoryStorageError("历史数据库损坏")
        for table in ("records", "attachments", "sequences", "pending_files"):
            connection.execute(f"SELECT * FROM {table} LIMIT 0")

    async def initialize(self, *, video_limit_bytes: int) -> None:
        if type(video_limit_bytes) is not int or video_limit_bytes < 0:
            raise ValueError("视频容量必须是非负整数")
        if self._initialized:
            return
        await self._run(lambda cancel: self._initialize(video_limit_bytes, cancel))

    def _initialize(self, limit: int, cancel: threading.Event) -> None:
        if self.database.is_relative_to(self.root):
            raise HistoryStorageError("历史数据库不能位于附件目录内")
        if self.database.is_symlink() or self.marker.is_symlink():
            raise HistoryStorageError("历史数据库和升级标记不能是链接")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        _check_tree(self.root)
        state = None
        if self.marker.exists():
            marker = json.loads(self.marker.read_text(encoding="utf-8"))
            if marker.get("version") != _VERSION or marker.get("state") not in (
                "cleaning",
                "initializing",
                "ready",
            ):
                raise HistoryStorageError("历史升级标记无效")
            state = marker["state"]
        elif self.database.exists():
            raise HistoryStorageError("已有历史数据库但缺少升级标记，请恢复同根备份")

        if state is None or state == "cleaning":
            if self.database.exists():
                raise HistoryStorageError("历史清理阶段意外存在数据库，拒绝自动清空")
            self._write_marker("cleaning", cancel)
            for old in (self.root, self.database.parent / "replays"):
                _check_tree(old)
                _check_cancel(cancel)
                if old.exists():
                    shutil.rmtree(old)
            self._write_marker("initializing", cancel)
            state = "initializing"

        if state == "ready" and not self.database.is_file():
            raise HistoryStorageError("已初始化的历史数据库缺失，请恢复备份")
        self.root.mkdir(parents=True, exist_ok=True)
        with closing(self._connect(cancel)) as connection:
            if state == "initializing":
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, _VERSION):
                    raise HistoryStorageError("历史数据库版本不支持")
                connection.execute("PRAGMA journal_mode=WAL")
                _check_cancel(cancel)
                connection.executescript("""
                    BEGIN;
                    CREATE TABLE IF NOT EXISTS records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        time TEXT NOT NULL, timestamp REAL NOT NULL, date TEXT NOT NULL,
                        username TEXT NOT NULL, script_name TEXT NOT NULL,
                        status TEXT NOT NULL, message TEXT NOT NULL, data TEXT NOT NULL,
                        log_path TEXT, log_text_fallback TEXT, storage_errors TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS attachments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                        kind TEXT NOT NULL, role TEXT NOT NULL, display_name TEXT NOT NULL,
                        relative_path TEXT, byte_size INTEGER NOT NULL,
                        saved_via TEXT, available INTEGER NOT NULL, unavailable_reason TEXT
                    );
                    CREATE TABLE IF NOT EXISTS sequences (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
                    CREATE TABLE IF NOT EXISTS pending_files (
                        attachment_id INTEGER PRIMARY KEY, record_id INTEGER NOT NULL,
                        kind TEXT NOT NULL, relative_path TEXT NOT NULL UNIQUE
                    );
                    CREATE INDEX IF NOT EXISTS history_date ON records(date, timestamp, id);
                    CREATE INDEX IF NOT EXISTS history_user ON records(username, timestamp, id);
                    CREATE INDEX IF NOT EXISTS history_script ON records(script_name, timestamp, id);
                    CREATE INDEX IF NOT EXISTS history_attachments ON attachments(record_id);
                    PRAGMA user_version=1;
                    COMMIT;
                """)
            self._validate_database(connection)
            # 仅清理已登记目标对应的内部临时文件；原始扩展名也可能是 .part。
            complete_paths = {
                row[0]
                for row in connection.execute(
                    "SELECT relative_path FROM attachments WHERE relative_path IS NOT NULL "
                    "UNION SELECT relative_path FROM pending_files "
                    "UNION SELECT log_path FROM records WHERE log_path IS NOT NULL"
                )
            }
            for relative in complete_paths:
                temporary_relative = relative + ".part"
                if temporary_relative not in complete_paths:
                    _check_cancel(cancel)
                    self._path(temporary_relative).unlink(missing_ok=True)
            rows = connection.execute(
                "SELECT id, relative_path FROM attachments WHERE available=1"
            ).fetchall()
            for row in rows:
                if (
                    not row["relative_path"]
                    or not self._path(row["relative_path"]).is_file()
                ):
                    connection.execute(
                        "UPDATE attachments SET available=0, unavailable_reason='missing' WHERE id=?",
                        (row["id"],),
                    )
            for row in connection.execute("SELECT * FROM pending_files").fetchall():
                target = self._path(row["relative_path"])
                if target.is_file():
                    logger.warning(f"保留未提交历史附件：{target}")
                else:
                    connection.execute(
                        "DELETE FROM pending_files WHERE attachment_id=?",
                        (row["attachment_id"],),
                    )
            _check_cancel(cancel)
            connection.commit()
        self._write_marker("ready", cancel)
        self._video_limit = limit
        with closing(self._connect(cancel)) as connection:
            report = self._enforce_quota(connection, cancel=cancel)
            if report.errors:
                logger.warning(f"启动清理历史视频失败：{len(report.errors)} 项")
        self._initialized = True

    async def close(self) -> None:
        self._closing = True
        pending = set(self._workers)
        if pending:
            _, pending = await asyncio.wait(pending, timeout=_CLOSE_TIMEOUT / 2)
        for future in pending:
            self._workers[future].set()
        if pending:
            _, pending = await asyncio.wait(pending, timeout=_CLOSE_TIMEOUT / 2)
        for future in pending:
            if not future.done():
                future.set_exception(
                    HistoryStorageError("历史服务关闭期限已到，保存状态未确认")
                )
        self._initialized = False

    def _reserve_ids(
        self, *, connection: sqlite3.Connection, count: int, cancel: threading.Event
    ):
        _check_cancel(cancel)
        # 独立提交序号，最终记录事务回滚也不会重新使用已搬移文件的编号。
        with connection:
            record_id = connection.execute(
                "INSERT INTO sequences VALUES ('record', 1) ON CONFLICT(name) DO UPDATE SET value=value+1 RETURNING value"
            ).fetchone()[0]
            attachment_id = connection.execute(
                "INSERT INTO sequences VALUES ('attachment', ?) ON CONFLICT(name) DO UPDATE SET value=value+excluded.value RETURNING value",
                (count,),
            ).fetchone()[0]
            _check_cancel(cancel)
        return record_id, attachment_id - count + 1

    async def save(self, record: HistoryWrite) -> HistoryRecord:
        # 重新校验阻止 model_construct、事后原位修改绕过纯参数验证。
        record = HistoryWrite.model_validate(
            record.model_dump(mode="python", warnings=False)
        )
        json.dumps(record.model_dump(mode="json"), allow_nan=False)
        self._require_ready()
        return await self._run(lambda cancel: self._save(record, cancel))

    def _save(self, record: HistoryWrite, cancel: threading.Event) -> HistoryRecord:
        errors: list[HistoryStorageIssue] = []
        record_id = None
        try:
            with closing(self._connect(cancel)) as connection:
                record_id, attachment_id = self._reserve_ids(
                    connection=connection, count=len(record.attachments), cancel=cancel
                )
                relative = f"{record.time.date().isoformat()}/{record_id}"
                directory = self._path(relative)
                while directory.exists():
                    record_id, attachment_id = self._reserve_ids(
                        connection=connection,
                        count=len(record.attachments),
                        cancel=cancel,
                    )
                    relative = f"{record.time.date().isoformat()}/{record_id}"
                    directory = self._path(relative)
                directory_ready = False
                try:
                    _check_cancel(cancel)
                    directory.mkdir(parents=True, exist_ok=False)
                    directory_ready = True
                except OSError as error:
                    errors.append(_issue("mkdir", error, target=directory))
                log_path = None
                fallback = record.logs
                if directory_ready:
                    log_target = directory / "0.log"
                    try:
                        _check_cancel(cancel)
                        with log_target.open("x", encoding="utf-8", newline="") as file:
                            file.write(record.logs)
                            file.flush()
                            os.fsync(file.fileno())
                        log_path = f"{relative}/0.log"
                        fallback = None
                    except OSError as error:
                        errors.append(_issue("write_log", error, target=log_target))
                        self._remove_partial(log_target, errors)
                attachments = []
                # 只在本次 save 内记账，最终事务一并移除。SQL提交失败后仍能识别
                # 已搬走的视频并计入配额，不需要恢复草稿或反推文件类别。
                if directory_ready:
                    with connection:
                        _check_cancel(cancel)
                        connection.executemany(
                            "INSERT INTO pending_files VALUES (?, ?, ?, ?)",
                            [
                                (
                                    attachment_id + index,
                                    record_id,
                                    source.kind,
                                    f"{relative}/{index + 1}{source.path.suffix}",
                                )
                                for index, source in enumerate(record.attachments)
                            ],
                        )
                        _check_cancel(cancel)
                for index, source in enumerate(record.attachments):
                    _check_cancel(cancel)
                    attachment = HistoryAttachment(
                        id=attachment_id + index,
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
                        if source.path.is_symlink() or not source.path.is_file():
                            raise OSError(f"附件不是可读普通文件：{source.path}")
                        size = source.path.stat().st_size
                        attachment.byte_size = size
                        if source.kind == "video":
                            quota = self._enforce_quota(
                                connection,
                                extra=size,
                                pending=attachments[:-1],
                                active_record_id=record_id,
                                cancel=cancel,
                            )
                            errors.extend(quota.errors)
                            if (
                                size > self._video_limit
                                or self._video_usage(connection, attachments[:-1])
                                + size
                                > self._video_limit
                            ):
                                attachment.unavailable_reason = "quota"
                                errors.append(
                                    _issue(
                                        "quota",
                                        OSError("视频容量不足"),
                                        index=index,
                                        source=source.path,
                                        target=target,
                                    )
                                )
                                continue
                        self._archive(
                            source=source.path,
                            target=target,
                            attachment=attachment,
                            errors=errors,
                            index=index,
                            cancel=cancel,
                        )
                    except OSError as error:
                        errors.append(
                            _issue(
                                "move",
                                error,
                                index=index,
                                source=source.path,
                                target=target,
                            )
                        )
                        errors.append(
                            _issue(
                                "copy",
                                error,
                                index=index,
                                source=source.path,
                                target=target,
                            )
                        )
                        attachment.unavailable_reason = "archive_failed"
                _check_cancel(cancel)
                with connection:
                    connection.execute(
                        "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            record_id,
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
                    )
                    connection.executemany(
                        "INSERT INTO attachments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            (
                                item.id,
                                item.record_id,
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
                    )
                    connection.execute(
                        "DELETE FROM pending_files WHERE record_id=?", (record_id,)
                    )
                    _check_cancel(cancel)
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
        except HistorySaveError:
            raise
        except Exception as error:
            errors.append(_issue("database", error, target=self.database))
            raise HistorySaveError(
                record_id=record_id, record_saved=False, errors=errors
            ) from error
        if errors:
            raise HistorySaveError(
                record_id=record_id, record_saved=True, errors=errors
            )
        return result

    @staticmethod
    def _remove_partial(path: Path, errors: list[HistoryStorageIssue], *, index=None):
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            errors.append(_issue("cleanup", error, index=index, target=path))

    def _archive(self, *, source, target, attachment, errors, index, cancel):
        try:
            _check_cancel(cancel)
            if target.exists():
                raise FileExistsError(target)
            source.rename(target)
            attachment.saved_via = "move"
            attachment.available = True
            return
        except OSError as error:
            move_issue = _issue(
                "move", error, index=index, source=source, target=target
            )
            errors.append(move_issue)
        temporary = target.with_name(target.name + ".part")
        try:
            with source.open("rb") as reader, temporary.open("xb") as writer:
                while True:
                    _check_cancel(cancel)
                    chunk = reader.read(1024 * 1024)
                    if not chunk:
                        break
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            _check_cancel(cancel)
            if target.exists():
                raise FileExistsError(target)
            temporary.rename(target)
            attachment.saved_via = "copy"
            attachment.available = True
            move_issue.recovered = True
        except OSError as error:
            errors.append(
                _issue("copy", error, index=index, source=source, target=target)
            )
            attachment.unavailable_reason = "archive_failed"
        finally:
            self._remove_partial(temporary, errors, index=index)

    def _record(self, connection, record_id: int) -> HistoryRecord:
        row = connection.execute(
            "SELECT * FROM records WHERE id=?", (record_id,)
        ).fetchone()
        if row is None:
            raise HistoryNotFoundError(f"历史记录不存在：{record_id}")
        values = dict(row)
        fallback = values.pop("log_text_fallback")
        values.pop("timestamp")
        values.pop("date")
        values["data"] = json.loads(values["data"])
        values["storage_errors"] = json.loads(values["storage_errors"])
        values["storage_error_count"] = len(values["storage_errors"])
        values["has_log_fallback"] = fallback is not None
        values["attachments"] = [
            HistoryAttachment(**dict(item))
            for item in connection.execute(
                "SELECT * FROM attachments WHERE record_id=? ORDER BY id", (record_id,)
            )
        ]
        return HistoryRecord(**values)

    @staticmethod
    def _index(row):
        return HistoryIndexItem(
            **{
                key: row[key]
                for key in (
                    "id",
                    "time",
                    "username",
                    "script_name",
                    "status",
                    "message",
                )
            },
            storage_error_count=len(json.loads(row["storage_errors"])),
        )

    def _select(self, connection, query: HistoryRecordQuery, *, limited=True):
        where, args = [], []
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
        statement = "SELECT * FROM records"
        if where:
            statement += " WHERE " + " AND ".join(where)
        statement += " ORDER BY timestamp DESC, id DESC"
        if limited:
            statement += " LIMIT ?"
            args.append(query.limit)
        return connection.execute(statement, args).fetchall()

    async def list_records(
        self, *, query: HistoryRecordQuery
    ) -> list[HistoryIndexItem]:
        self._require_ready()

        def read(cancel):
            with closing(self._connect(cancel)) as connection:
                return [self._index(row) for row in self._select(connection, query)]

        return await self._run(read)

    async def get_detail(self, *, record_id: int) -> HistoryDetail:
        self._require_ready()

        def read(cancel):
            with closing(self._connect(cancel)) as connection:
                record = self._record(connection, record_id)
                detail = HistoryDetail(**record.model_dump())
                reason = None
                if record.log_path is not None:
                    try:
                        detail.log_content = self._path(record.log_path).read_text(
                            encoding="utf-8"
                        )
                    except (OSError, UnicodeError) as error:
                        reason = type(error).__name__
                if detail.log_content is None and record.has_log_fallback:
                    detail.log_content = connection.execute(
                        "SELECT log_text_fallback FROM records WHERE id=?", (record_id,)
                    ).fetchone()[0]
                detail.log_available = detail.log_content is not None
                detail.log_unavailable_reason = (
                    None if detail.log_available else reason or "missing"
                )
                for item in detail.attachments:
                    if item.available and (
                        not item.relative_path
                        or not self._path(item.relative_path).is_file()
                    ):
                        item.available = False
                        item.unavailable_reason = "missing"
                return detail

        return await self._run(read)

    async def resolve_attachment(self, *, attachment_id: int) -> HistoryAttachmentFile:
        self._require_ready()

        def read(cancel):
            with closing(self._connect(cancel)) as connection:
                row = connection.execute(
                    "SELECT * FROM attachments WHERE id=?", (attachment_id,)
                ).fetchone()
                if row is None:
                    raise HistoryNotFoundError("历史附件不存在")
                item = HistoryAttachment(**dict(row))
                if not item.available or not item.relative_path:
                    raise HistoryNotFoundError(
                        item.unavailable_reason or "历史附件不可用"
                    )
                path = self._path(item.relative_path)
                if not path.is_file():
                    raise HistoryNotFoundError("历史附件文件缺失")
                return HistoryAttachmentFile(**item.model_dump(), path=path)

        return await self._run(read)

    async def search(
        self, *, start_date: date, end_date: date, mode: str
    ) -> dict[str, dict[str, HistoryBucket]]:
        self._require_ready()
        if start_date > end_date or mode not in ("DAILY", "WEEKLY", "MONTHLY"):
            raise ValueError("历史查询日期或分组无效")

        def read(cancel):
            groups = {}
            with closing(self._connect(cancel)) as connection:
                rows = self._select(
                    connection,
                    HistoryRecordQuery(start_date=start_date, end_date=end_date),
                    limited=False,
                )
                for row in reversed(rows):
                    day = date.fromisoformat(row["date"])
                    if mode == "WEEKLY":
                        day -= timedelta(days=day.weekday())
                    elif mode == "MONTHLY":
                        day = day.replace(day=1)
                    groups.setdefault(day.isoformat(), {}).setdefault(
                        row["username"], []
                    ).append(row)
                result = {}
                for day, users in groups.items():
                    result[day] = {}
                    for user, entries in users.items():
                        aggregate = aggregate_history(
                            [
                                HistoryAggregationItem(
                                    time=row["time"], data=json.loads(row["data"])
                                )
                                for row in entries
                            ]
                        )
                        for error in aggregate.errors:
                            error.record_ids = [
                                entries[index]["id"] for index in error.input_indices
                            ]
                        result[day][user] = HistoryBucket(
                            index=[self._index(row) for row in entries],
                            data=aggregate.data,
                            aggregate_errors=aggregate.errors,
                        )
                return result

        return await self._run(read)

    async def get_overview(self, *, day: date) -> dict[str, HistoryUserOverview]:
        self._require_ready()

        def read(cancel):
            with closing(self._connect(cancel)) as connection:
                result = {}
                for row in self._select(
                    connection,
                    HistoryRecordQuery(start_date=day, end_date=day),
                    limited=False,
                ):
                    overview = result.setdefault(row["username"], HistoryUserOverview())
                    overview.execute_count += 1
                    if overview.latest_time is None:
                        overview.latest_time = datetime.fromisoformat(row["time"])
                    if row["status"] == "error":
                        overview.error_count += 1
                        overview.error_info[row["id"]] = row["message"]
                return result

        return await self._run(read)

    def _video_usage(self, connection, pending=()):
        paths = [
            row[0]
            for row in connection.execute(
                "SELECT relative_path FROM attachments WHERE kind='video' AND relative_path IS NOT NULL"
            )
        ]
        paths.extend(
            item.relative_path
            for item in pending
            if item.kind == "video" and item.relative_path
        )
        paths.extend(
            row[0]
            for row in connection.execute(
                "SELECT relative_path FROM pending_files WHERE kind='video'"
            )
        )
        total = 0
        for relative in set(paths):
            target = self._path(relative)
            # 复制失败且清理失败的半成品也占配额，不能当成已释放空间。
            for file in (target, target.with_name(target.name + ".part")):
                if file.is_file():
                    total += file.stat().st_size
        return total

    def _enforce_quota(
        self, connection, *, extra=0, pending=(), active_record_id=None, cancel
    ):
        report = HistoryCleanupReport()
        if extra > self._video_limit:
            return report
        usage = self._video_usage(connection, pending)
        candidates = [
            HistoryAttachment(**dict(row))
            for row in connection.execute(
                "SELECT * FROM attachments WHERE kind='video' AND relative_path IS NOT NULL ORDER BY id"
            )
        ]
        candidates.extend(
            item for item in pending if item.kind == "video" and item.relative_path
        )
        orphan_ids = set()
        for row in connection.execute(
            "SELECT * FROM pending_files WHERE kind='video' ORDER BY attachment_id"
        ):
            if row["record_id"] == active_record_id:
                continue
            orphan_ids.add(row["attachment_id"])
            candidates.append(
                HistoryAttachment(
                    id=row["attachment_id"],
                    record_id=row["record_id"],
                    kind="video",
                    role="",
                    display_name="",
                    relative_path=row["relative_path"],
                )
            )
        candidates.sort(key=lambda item: item.id)
        for item in candidates:
            if usage + extra <= self._video_limit:
                break
            _check_cancel(cancel)
            target = self._path(item.relative_path)
            for file in (target, target.with_name(target.name + ".part")):
                try:
                    size = file.stat().st_size if file.is_file() else 0
                    file.unlink(missing_ok=True)
                    usage -= size
                    report.reclaimed_bytes += size
                    if file == target:
                        report.deleted_videos += int(size > 0)
                except OSError as error:
                    report.errors.append(_issue("cleanup", error, target=file))
            if not target.exists():
                if item in pending:
                    item.available = False
                    item.unavailable_reason = "quota"
                else:
                    connection.execute(
                        "UPDATE attachments SET available=0, unavailable_reason='quota' WHERE id=?",
                        (item.id,),
                    )
                    _check_cancel(cancel)
                    connection.commit()
                if (
                    item.id in orphan_ids
                    and not target.with_name(target.name + ".part").exists()
                ):
                    connection.execute(
                        "DELETE FROM pending_files WHERE attachment_id=?", (item.id,)
                    )
                    _check_cancel(cancel)
                    connection.commit()
        return report

    async def set_video_limit(self, *, limit_bytes: int) -> HistoryCleanupReport:
        self._require_ready()
        if type(limit_bytes) is not int or limit_bytes < 0:
            raise ValueError("视频容量必须是非负整数")

        def maintain(cancel):
            self._video_limit = limit_bytes
            with closing(self._connect(cancel)) as connection:
                return self._enforce_quota(connection, cancel=cancel)

        return await self._run(maintain)

    async def prune(self, *, today: date, retention_days: int) -> HistoryCleanupReport:
        self._require_ready()
        if type(retention_days) is not int or retention_days < 0:
            raise ValueError("历史保留天数必须是非负整数")

        def maintain(cancel):
            report = HistoryCleanupReport()
            if retention_days == 0:
                return report
            cutoff = (today - timedelta(days=retention_days)).isoformat()
            with closing(self._connect(cancel)) as connection:
                for row in connection.execute(
                    "SELECT id, date FROM records WHERE date < ?", (cutoff,)
                ).fetchall():
                    _check_cancel(cancel)
                    target = self._path(f"{row['date']}/{row['id']}")
                    try:
                        _check_tree(target)
                        size = (
                            sum(
                                file.stat().st_size
                                for file in target.rglob("*")
                                if file.is_file()
                            )
                            if target.exists()
                            else 0
                        )
                        if target.exists():
                            shutil.rmtree(target)
                        _check_cancel(cancel)
                        with connection:
                            connection.execute(
                                "DELETE FROM records WHERE id=?", (row["id"],)
                            )
                        report.deleted_records += 1
                        report.reclaimed_bytes += size
                    except OSError as error:
                        report.errors.append(_issue("cleanup", error, target=target))
            return report

        return await self._run(maintain)

    async def export_snapshot(self, *, destination: Path) -> HistoryBackupSnapshot:
        self._require_ready()
        destination = Path(destination).absolute()
        if destination.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("历史快照不能保存在历史目录内")

        def export(cancel):
            destination.mkdir(parents=True, exist_ok=True)
            database = destination / "history.db"
            history = destination / "history"
            marker = destination / self.marker.name
            if database.exists() or history.exists() or marker.exists():
                raise HistoryStorageError("历史快照目标已存在")
            history.mkdir()
            with (
                closing(self._connect(cancel)) as source,
                closing(sqlite3.connect(database)) as target,
            ):
                source.backup(
                    target, pages=128, progress=lambda *args: _check_cancel(cancel)
                )
                paths = [
                    row[0]
                    for row in source.execute(
                        "SELECT log_path FROM records WHERE log_path IS NOT NULL"
                    )
                ]
                paths.extend(
                    row[0]
                    for row in source.execute(
                        "SELECT relative_path FROM attachments WHERE available=1 AND relative_path IS NOT NULL"
                    )
                )
                paths.extend(
                    row[0]
                    for row in source.execute("SELECT relative_path FROM pending_files")
                )
                for relative in set(paths):
                    _check_cancel(cancel)
                    original = self._path(relative)
                    if original.is_file():
                        output = history / relative
                        output.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(original, output)
            _check_cancel(cancel)
            shutil.copy2(self.marker, marker)
            return HistoryBackupSnapshot(
                destination=destination,
                database=database,
                history=history,
                marker=marker,
            )

        return await self._run(export)


history_store = HistoryStore(
    root=Path.cwd() / "history", database=Path.cwd() / "data/history.db"
)
