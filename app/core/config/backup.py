#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

from app.config import config_manager
from app.core import Config, History
from app.models.schema import HistoryBackupSnapshot
from app.utils import io as _utils_io

# 不进备份包: MaaFW 运行环境池、内嵌副本与共用库 (都可由来源 / 更新重建, 生产可达 GB 级;
# 副本里的共用库是硬链接, 按路径逐个读会把同一份字节打进去两遍)、更新包下载缓存 (每个
# 200 MB 上下, 重下即可) 与原生日志 (单个可达百 MB)
_EXCLUDED_DIRS = {
    "data/replays",
    "data/history-capture",
    "config/maafw_runtime_pool",
    "config/maafw_agent_venvs",
    "data/mfw",
    "data/maafw_blobs",
    "data/maafw_update_cache",
}
# MFW 每次运行另存的原生日志与项目 agent 日志（本次新增部分，每次最多 8 MB）
_EXCLUDED_SUFFIXES = (".maafw.log", ".project.log")

_DATABASE_FILES = {
    "data/data.db",
    "data/data.db-journal",
    "data/data.db-shm",
    "data/data.db-wal",
    "data/history.db",
    "data/history.db-journal",
    "data/history.db-shm",
    "data/history.db-wal",
}


def _backup_database(source: Path, destination: Path) -> None:
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_db:
        with closing(sqlite3.connect(destination)) as destination_db:
            source_db.backup(destination_db)


async def create_data_backup(root: Path | None = None) -> Path:
    """从内存导出明文配置，并与用户数据、历史记录一起打包。"""

    root = Config.work_path if root is None else root
    snapshot = tempfile.TemporaryDirectory(prefix="auto-mas-config-export-")
    config_export = Path(snapshot.name) / "config"
    config_export.mkdir()
    try:
        await config_manager.export(config_export)
        history_snapshot = await History.export_snapshot(
            destination=Path(snapshot.name) / "history-snapshot"
        )
    except BaseException:
        snapshot.cleanup()
        raise

    def pack() -> Path:
        # 压缩线程负责临时目录生命周期，取消请求也不能提前删掉其输入。
        with snapshot:
            return _create_data_backup(
                root=root,
                config_export=config_export,
                history_snapshot=history_snapshot,
            )

    task = asyncio.create_task(asyncio.to_thread(pack))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:

        def discard_result(completed: asyncio.Task[Path]) -> None:
            if not completed.cancelled() and completed.exception() is None:
                completed.result().unlink(missing_ok=True)

        task.add_done_callback(discard_result)
        raise


def _create_data_backup(
    *, root: Path, config_export: Path, history_snapshot: HistoryBackupSnapshot
) -> Path:
    """配置根使用固定的内存导出文件，其余文件沿用整包备份规则。"""
    exported_files = {
        path.relative_to(config_export).as_posix(): path
        for path in config_export.rglob("*")
        if path.is_file()
    }
    temporary = tempfile.NamedTemporaryFile(
        prefix="auto-mas-backup-", suffix=".zip", delete=False
    )
    backup_path = Path(temporary.name)
    temporary.close()

    try:
        with tempfile.TemporaryDirectory(prefix="auto-mas-database-") as temp_dir:
            database_path = root / "data" / "data.db"
            database_snapshot = Path(temp_dir) / "data.db"
            if database_path.is_file():
                _backup_database(database_path, database_snapshot)

            with zipfile.ZipFile(
                backup_path, mode="w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for directory_name in ("data", "config"):
                    archive.writestr(f"{directory_name}/", b"")
                    source_directory = root / directory_name
                    if not source_directory.is_dir():
                        continue

                    for path in source_directory.rglob("*"):
                        archive_name = path.relative_to(root).as_posix()
                        if directory_name == "config" and (
                            path.relative_to(source_directory).as_posix()
                            in exported_files
                        ):
                            continue
                        if path.is_symlink() or archive_name in _DATABASE_FILES:
                            continue
                        if archive_name in _EXCLUDED_DIRS or any(
                            archive_name.startswith(f"{d}/") for d in _EXCLUDED_DIRS
                        ):
                            continue
                        if path.name.endswith(_EXCLUDED_SUFFIXES):
                            continue
                        if path.is_dir():
                            archive.writestr(f"{archive_name}/", b"")
                        elif path.is_file():
                            if directory_name == "config":
                                # 只在复制时与原子写互斥；慢压缩不持有实时配置句柄。
                                # 每个文件压缩后立即释放副本，额外空间不累计到整棵配置树。
                                with tempfile.TemporaryDirectory(
                                    dir=temp_dir
                                ) as copied_dir:
                                    copied = Path(copied_dir) / path.name
                                    if not _utils_io.copy_file_snapshot(path, copied):
                                        continue
                                    archive.write(copied, archive_name)
                            else:
                                archive.write(path, archive_name)

                # 原配置尚未写盘或已从磁盘移除，也必须包含已登记的内存配置。
                for name, path in exported_files.items():
                    archive.write(path, f"config/{name}")

                if database_snapshot.exists():
                    archive.write(database_snapshot, "data/data.db")
                # 历史只从协调后的快照树打包，活动WAL及附件树不能混入。
                archive.write(history_snapshot.database, "data/history.db")
                archive.writestr("history/", b"")
                for path in history_snapshot.history.rglob("*"):
                    if path.is_file():
                        archive.write(
                            path,
                            f"history/{path.relative_to(history_snapshot.history).as_posix()}",
                        )

        return backup_path
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise
