"""运行池各模块共用的文件系统与时间小工具（只用标准库）。

``pool.py``（runtime venv）与 ``binding.py``（按版本 binding / native 目录）都要：
按池根取进程内锁、拒绝 reparse point、原子写 JSON、rmtree 时清只读位、
UTC 时间串。抽出来是为了两边互不 import——``pool.py`` 的回收要扫 binding 目录，
``binding.py`` 的换入要拿池锁，放在一个文件里就绕成环。
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import threading
import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MaaFWRuntimePoolError(RuntimeError):
    """Raised when a managed MaaFW runtime pool operation is unsafe or invalid."""


_LOCKS_GUARD = threading.Lock()
_POOL_LOCKS: dict[str, threading.RLock] = {}


def pool_lock(root: Path) -> threading.RLock:
    """按池根键的进程内可重入锁：同一个根不管建多少个 pool 对象都是同一把。"""

    key = os.path.normcase(str(Path(root).resolve()))
    with _LOCKS_GUARD:
        return _POOL_LOCKS.setdefault(key, threading.RLock())


def assert_not_reparse(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    if path.is_symlink() or bool(file_attributes & reparse_flag):
        raise MaaFWRuntimePoolError(f"reparse points are not allowed: {path}")


def assert_existing_chain_has_no_reparse(path: Path) -> None:
    existing: list[Path] = []
    current = path
    while True:
        if current.exists() or current.is_symlink():
            existing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for item in reversed(existing):
        assert_not_reparse(item)


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _clear_readonly_and_retry(func: Any, path: str, _exc_info: Any) -> None:
    """``shutil.rmtree`` 的 onexc：只读位（git 对象、发行包里的资源）清掉再试一次。"""

    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        # 真被映射 / 占用的文件这里也删不掉，交给调用方按残留处理
        pass


def remove_tree_best_effort(path: Path) -> bool:
    """尽力删整棵目录，返回是否删干净了。不抛：残留由调用方如实报告。

    第一遍没删干净就歇一下再来一遍：刚写出来的文件常被杀软 / 索引器短暂占住
    （本地测试里刚解出来的 .pyc 就被拦下过一次），几百毫秒后就放开了。
    """

    for attempt in range(2):
        if attempt:
            time.sleep(0.3)
        try:
            shutil.rmtree(path, onexc=_clear_readonly_and_retry)
        except OSError:
            pass
        if not path.exists() and not path.is_symlink():
            return True
    return False


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_time(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def parse_time(value: Any) -> datetime:
    """空值当纪元起点（「从没用过」），格式坏的照旧抛 ValueError。"""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        return datetime.fromtimestamp(0, timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
