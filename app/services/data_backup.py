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


import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

_DATABASE_FILES = {
    "data/data.db",
    "data/data.db-journal",
    "data/data.db-shm",
    "data/data.db-wal",
}


def _backup_database(source: Path, destination: Path) -> None:
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_db:
        with closing(sqlite3.connect(destination)) as destination_db:
            source_db.backup(destination_db)


def create_data_backup(root: Path | None = None) -> Path:
    """将用户数据、配置与历史记录打包到临时 ZIP 文件。"""

    root = Path.cwd() if root is None else root
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
                for directory_name in ("data", "config", "history"):
                    archive.writestr(f"{directory_name}/", b"")
                    source_directory = root / directory_name
                    if not source_directory.is_dir():
                        continue

                    for path in source_directory.rglob("*"):
                        archive_name = path.relative_to(root).as_posix()
                        if path.is_symlink() or archive_name in _DATABASE_FILES:
                            continue
                        if path.is_dir():
                            archive.writestr(f"{archive_name}/", b"")
                        elif path.is_file():
                            archive.write(path, archive_name)

                if database_snapshot.exists():
                    archive.write(database_snapshot, "data/data.db")

        return backup_path
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise
