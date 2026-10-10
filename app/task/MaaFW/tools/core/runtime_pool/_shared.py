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


def output_tail(text: str, limit: int) -> str:
    """子进程输出过长时只留结尾：traceback 与 uv / pip 的报错原因都在最后几行，
    截开头恰好把它们丢掉。"""

    if len(text) <= limit:
        return text
    return "…" + text[-limit:]


_LOCKS_GUARD = threading.Lock()
_POOL_LOCKS: dict[str, threading.RLock] = {}


def pool_lock(root: Path) -> threading.RLock:
    """按池根键的进程内可重入锁：同一个根不管建多少个 pool 对象都是同一把。"""

    key = os.path.normcase(str(Path(root).resolve()))
    with _LOCKS_GUARD:
        return _POOL_LOCKS.setdefault(key, threading.RLock())


_ACTIVE_STAGING_GUARD = threading.Lock()
#: 正在池锁外铺着的 ``.staging`` 条目名（binding / native 暂存目录、下载中的 wheel）。
#: 名字带 uuid，按名字就能唯一认出。回收的 ``_sweep_staging`` 持池锁扫 ``.staging``，
#: binding 的下载 / 铺目录 / 自检却在池锁外跑（见 ``binding.ensure_binding``），不登记的话
#: 正铺到一半的目录会被当成遗留物删掉。
_ACTIVE_STAGING: set[str] = set()


def register_active_staging(path: Path) -> None:
    """登记一个即将创建的暂存条目。必须在创建之前登记：扫描看到它时它一定已在册。"""

    with _ACTIVE_STAGING_GUARD:
        _ACTIVE_STAGING.add(path.name)


def release_active_staging(*paths: Path | None) -> None:
    with _ACTIVE_STAGING_GUARD:
        for path in paths:
            if path is not None:
                _ACTIVE_STAGING.discard(path.name)


def is_active_staging(path: Path) -> bool:
    with _ACTIVE_STAGING_GUARD:
        return path.name in _ACTIVE_STAGING


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


def venv_base_python_missing(venv_path: str | os.PathLike[str]) -> bool:
    """venv 自己的文件都在，但 ``pyvenv.cfg`` 里 ``home`` 指向的基解释器已经不存在。

    Windows 上 venv 的 python.exe 只是启动器，启动时靠 ``home`` 找标准库与 DLL，不是
    自包含的——``home`` 目录被删掉、或整个安装目录被挪走之后，venv 静默失效（启动器报
    ``No Python at '...'``，exit 103），哪怕 venv 自己的文件一个没少。agent 隔离 venv 与运行池
    的 base venv 都会碰上：引导解释器是另一个 venv（受管模式下的监督器 venv）后来被重建，
    或者用户把 AUTO-MAS 整个搬了家（池托管解释器 ``<pool>/python`` 跟着走了，``home`` 还是旧路径）。

    ``home`` 行缺失或读不出时不判定失效，交给调用方已有的结构完整性检查处理。
    """

    try:
        text = (Path(venv_path) / "pyvenv.cfg").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return False

    home: str | None = None
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip().casefold() == "home":
            home = value.strip()
    if not home:
        return False

    exe_name = "python.exe" if os.name == "nt" else "python"
    return not (Path(home) / exe_name).is_file()


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
