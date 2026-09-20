from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .installer import (
    AUTO_MAS_UV_CACHE_DIR_ENV,
    _clean_process_environment,
    _find_uv_executable,
    _resolve_uv_cache_dir_with_source,
    _uv_version,
)

# prune 只在任务收尾时作为维护步骤跑，慢了就该放弃而不是拖住任务结束。
# 真机上曾在共享缓存上卡满 300 秒，任务才得以继续。
UV_CACHE_PRUNE_TIMEOUT_SECONDS = 60


def prune_uv_cache(
    pool_root: str | Path,
    *,
    dry_run: bool = True,
    bootstrap_python: str | Path | None = None,
    uv_executable: str | Path | None = None,
) -> dict[str, Any]:
    """Preview or run uv's own safe cache-prune operation for one pool.

    Preview mode never invokes uv and therefore cannot promise an exact
    reclaimable byte count: uv decides which entries are dangling or cached
    environments at execution time.  The returned before/after snapshots,
    command, executable version, output, and status make the operation
    auditable without deleting the cache directory directly.
    """

    root = Path(pool_root).resolve()
    cache_path, injected = _resolve_uv_cache_dir_with_source(root)
    try:
        relative_to_pool = cache_path.relative_to(root).as_posix()
    except ValueError:
        # 受监督时 cache_path 可能是 Runtime 注入的共享缓存目录，不在 pool_root
        # 之内——不是错误，只是「相对池目录」这个概念本身不适用。
        relative_to_pool = None
    result: dict[str, Any] = {
        "kind": "uv",
        "scope": "pool",
        "dryRun": bool(dry_run),
        "attempted": False,
        "status": "preview" if dry_run else "pending",
        "cachePath": str(cache_path),
        "relativeToPool": relative_to_pool,
        "previewExact": False,
        "observedAt": _format_time(),
    }

    if cache_path.is_symlink():
        result.update(
            {
                "status": "unsafe",
                "error": "uv cache path is a symbolic link; prune was refused",
                "before": _empty_stats(cache_path),
            }
        )
        return result

    if injected:
        # 注入的缓存是 Runtime 主项目也在用的共享缓存，归 Runtime 管：池不能
        # 替它 prune（会动到主项目的 wheel），也不该为此在任务收尾时等待。
        result.update(
            {
                "status": "skipped",
                "injected": True,
                "reason": (
                    "uv cache directory is injected by the supervisor via "
                    f"{AUTO_MAS_UV_CACHE_DIR_ENV}; prune is left to its owner"
                ),
                "before": _empty_stats(cache_path),
            }
        )
        return result

    before = _directory_stats(cache_path)
    result["before"] = before

    bootstrap = str(bootstrap_python or sys.executable)
    resolved_uv = (
        str(Path(uv_executable).resolve())
        if uv_executable is not None
        else _find_uv_executable(bootstrap)
    )
    if resolved_uv is None:
        result.update(
            {
                "status": "unavailable",
                "error": ("uv executable was not found; cache prune was not attempted"),
                "uv": {"available": False, "executable": None, "version": None},
            }
        )
        return result

    command = [
        resolved_uv,
        "cache",
        "prune",
        "--cache-dir",
        str(cache_path),
        "--no-config",
        "--color",
        "never",
        "--no-progress",
    ]
    result.update(
        {
            "uv": {
                "available": True,
                "executable": resolved_uv,
                "version": _uv_version(resolved_uv),
            },
            "command": command,
        }
    )

    if not before["exists"]:
        result["status"] = "absent"
        return result
    if dry_run:
        return result

    result["attempted"] = True
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=UV_CACHE_PRUNE_TIMEOUT_SECONDS,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root,
            env=_cache_environment(cache_path),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result.update(
            {
                "status": "error",
                "error": f"uv cache prune could not be executed: {exc}",
                "after": _directory_stats(cache_path),
            }
        )
        return result

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    after = _directory_stats(cache_path)
    result.update(
        {
            "exitCode": int(completed.returncode),
            "stdout": stdout,
            "stderr": stderr,
            "after": after,
            "removedBytes": max(0, before["sizeBytes"] - after["sizeBytes"]),
            "removedFiles": max(0, before["fileCount"] - after["fileCount"]),
        }
    )
    if completed.returncode == 0:
        result["status"] = "pruned"
    else:
        detail = stderr or stdout or "no output"
        result.update(
            {
                "status": "error",
                "error": (
                    f"uv cache prune failed (exit={completed.returncode}): "
                    f"{detail[:800]}"
                ),
            }
        )
    return result


def clean_uv_cache(
    pool_root: str | Path,
    *,
    bootstrap_python: str | Path | None = None,
    uv_executable: str | Path | None = None,
) -> dict[str, Any]:
    """整个清掉池自己的 uv 缓存（``uv cache clean``）。

    与 ``prune_uv_cache`` 的差别：prune 只删 uv 自己认为悬空的条目，旧版本
    maafw / numpy 的解包目录在索引里都还「可达」，prune 一个字节也不会动；
    池里的 runtime 是从这份缓存硬链接出来的，旧 runtime 删掉之后那些文件就只剩
    缓存这一个链接，要真正腾出磁盘只能 clean。

    只在池里已无旧身份 runtime 时调（见 ``pool_reconcile``）：缓存一清，离线用户
    就再也建不出新 runtime，所以「还有旧 runtime 等着被新身份替换」时不能清。
    受监督时注入的共享缓存归 Runtime 管，这里同样跳过。
    """

    root = Path(pool_root).resolve()
    cache_path, injected = _resolve_uv_cache_dir_with_source(root)
    result: dict[str, Any] = {
        "kind": "uv",
        "scope": "pool",
        "operation": "clean",
        "attempted": False,
        "status": "pending",
        "cachePath": str(cache_path),
        "observedAt": _format_time(),
    }
    if cache_path.is_symlink():
        result.update(
            {
                "status": "unsafe",
                "error": "uv cache path is a symbolic link; clean was refused",
                "before": _empty_stats(cache_path),
            }
        )
        return result
    if injected:
        result.update(
            {
                "status": "skipped",
                "injected": True,
                "reason": (
                    "uv cache directory is injected by the supervisor via "
                    f"{AUTO_MAS_UV_CACHE_DIR_ENV}; clean is left to its owner"
                ),
                "before": _empty_stats(cache_path),
            }
        )
        return result

    before = _directory_stats(cache_path)
    result["before"] = before
    if not before["exists"]:
        result["status"] = "absent"
        return result

    bootstrap = str(bootstrap_python or sys.executable)
    resolved_uv = (
        str(Path(uv_executable).resolve())
        if uv_executable is not None
        else _find_uv_executable(bootstrap)
    )
    if resolved_uv is None:
        result.update(
            {
                "status": "unavailable",
                "error": "uv executable was not found; cache clean was not attempted",
                "uv": {"available": False, "executable": None, "version": None},
            }
        )
        return result

    command = [
        resolved_uv,
        "cache",
        "clean",
        "--cache-dir",
        str(cache_path),
        "--no-config",
        "--color",
        "never",
        "--no-progress",
    ]
    result.update(
        {
            "uv": {
                "available": True,
                "executable": resolved_uv,
                "version": _uv_version(resolved_uv),
            },
            "command": command,
            "attempted": True,
        }
    )
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=UV_CACHE_PRUNE_TIMEOUT_SECONDS,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root,
            env=_cache_environment(cache_path),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result.update(
            {
                "status": "error",
                "error": f"uv cache clean could not be executed: {exc}",
                "after": _directory_stats(cache_path),
            }
        )
        return result

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    after = _directory_stats(cache_path)
    result.update(
        {
            "exitCode": int(completed.returncode),
            "stdout": stdout,
            "stderr": stderr,
            "after": after,
            "removedBytes": max(0, before["sizeBytes"] - after["sizeBytes"]),
            "removedFiles": max(0, before["fileCount"] - after["fileCount"]),
        }
    )
    if completed.returncode == 0:
        result["status"] = "cleaned"
    else:
        detail = stderr or stdout or "no output"
        result.update(
            {
                "status": "error",
                "error": (
                    f"uv cache clean failed (exit={completed.returncode}): "
                    f"{detail[:800]}"
                ),
            }
        )
    return result


def _directory_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_stats(path)
    if not path.is_dir():
        return {
            **_empty_stats(path),
            "exists": True,
            "isDirectory": False,
        }

    file_count = 0
    directory_count = 1
    size_bytes = 0
    errors: list[str] = []
    for current_root, directory_names, file_names in os.walk(
        path,
        followlinks=False,
    ):
        directory_count += len(directory_names)
        current_path = Path(current_root)
        for name in file_names:
            file_path = current_path / name
            try:
                size_bytes += file_path.stat(follow_symlinks=False).st_size
                file_count += 1
            except OSError as exc:
                errors.append(f"{file_path}: {exc}")
    return {
        "path": str(path),
        "exists": True,
        "isDirectory": True,
        "fileCount": file_count,
        "directoryCount": directory_count,
        "sizeBytes": size_bytes,
        "scanErrors": errors,
    }


def _empty_stats(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": False,
        "isDirectory": False,
        "fileCount": 0,
        "directoryCount": 0,
        "sizeBytes": 0,
        "scanErrors": [],
    }


def _cache_environment(cache_path: Path) -> dict[str, str]:
    environment = _clean_process_environment()
    environment["UV_CACHE_DIR"] = str(cache_path)
    return environment


def _format_time() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
