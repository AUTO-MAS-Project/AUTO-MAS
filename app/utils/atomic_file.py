"""同目录临时文件与原子替换工具。"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(
    path: Path,
    content: str,
    *,
    backup: bool = True,
    fsync: bool = True,
) -> None:
    """原子替换文本文件，失败时保留原文件与可用恢复副本。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    backup_path = path.with_name(f"{path.name}.bak")
    owns_backup = False
    if backup and path.exists() and not backup_path.exists():
        shutil.copy2(path, backup_path)
        owns_backup = True

    temp_path: Path | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            suffix=".tmp",
            prefix=f"{path.name}.",
            dir=str(path.parent),
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                if fsync:
                    os.fsync(stream.fileno())
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

        os.replace(temp_path, path)
        temp_path = None
    except BaseException as write_error:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

        restore_error: Exception | None = None
        if owns_backup and backup_path.exists():
            try:
                shutil.copy2(backup_path, path)
            except Exception as exc:
                restore_error = exc
        if restore_error is not None:
            raise RuntimeError(
                "atomic text write failed and backup restoration failed; "
                f"backup retained at {backup_path}"
            ) from write_error
        raise
    else:
        if owns_backup:
            backup_path.unlink(missing_ok=True)


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    backup: bool = True,
    fsync: bool = True,
    indent: int = 4,
) -> None:
    """序列化完成后原子替换 JSON 文件。"""
    content = json.dumps(payload, ensure_ascii=False, indent=indent)
    atomic_write_text(path, content, backup=backup, fsync=fsync)
