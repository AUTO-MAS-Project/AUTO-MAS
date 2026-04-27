#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from app.utils import get_logger

logger = get_logger("uv后端")

_uv_path: str | None = None

DEFAULT_INDEX_URLS: list[str] = [
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "https://pypi.mirrors.ustc.edu.cn/simple/",
]


def _find_uv() -> str | None:
    """查找 uv 可执行文件路径。"""
    return shutil.which("uv")


def get_uv_executable() -> str:
    """返回 uv 可执行文件路径（带缓存）。

    Returns:
        str: uv 可执行文件的绝对路径。

    Raises:
        RuntimeError: 未找到 uv 时抛出。
    """
    global _uv_path
    if _uv_path is not None:
        return _uv_path

    found = _find_uv()
    if found is None:
        raise RuntimeError(
            "未找到 uv 可执行文件，请先安装: https://docs.astral.sh/uv/getting-started/installation/"
        )
    _uv_path = found
    return _uv_path


def check_uv_available() -> bool:
    """检查 uv 是否可用。"""
    return _find_uv() is not None


async def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """在线程池中执行子进程命令，避免阻塞事件循环。"""
    return await asyncio.to_thread(
        subprocess.run,
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def _error_detail(completed: subprocess.CompletedProcess[str]) -> str:
    """从 subprocess 结果中提取错误摘要。"""
    stderr = (completed.stderr or "").strip()
    stdout = (completed.stdout or "").strip()
    return stderr or stdout or "未知错误"


def _append_index_args(command: list[str], index_url: Optional[str]) -> None:
    """将 PyPI 镜像源参数追加到命令列表。"""
    if index_url:
        command.extend(["--index-url", index_url])


async def uv_pip_install(
    packages: list[str],
    *,
    target: Path,
    editable: bool = False,
    upgrade: bool = True,
    index_url: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    """使用 uv pip install 安装包到指定目录。

    Args:
        packages: 包名列表或本地路径列表。
        target: 安装目标目录（对应 --target）。
        editable: 是否以 editable 模式安装。
        upgrade: 是否使用 --upgrade。
        index_url: PyPI 镜像源 URL，为 None 时使用 uv 默认源。

    Returns:
        subprocess.CompletedProcess: 命令执行结果。

    Raises:
        RuntimeError: uv 不可用或安装失败时抛出。
    """
    uv = get_uv_executable()
    target.mkdir(parents=True, exist_ok=True)

    command = [uv, "pip", "install"]
    if editable:
        for pkg in packages:
            command.extend(["-e", pkg])
    else:
        command.extend(packages)
    command.extend(["--target", str(target)])
    if upgrade:
        command.append("--upgrade")
    _append_index_args(command, index_url)

    completed = await _run(command)
    if completed.returncode != 0:
        detail = _error_detail(completed)
        raise RuntimeError(
            f"uv pip install 失败: packages={packages}, detail={detail}"
        )

    return completed


async def uv_pip_install_with_mirror_fallback(
    packages: list[str],
    *,
    target: Path,
    editable: bool = False,
    upgrade: bool = True,
    index_urls: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """使用 uv pip install 安装包，自动轮替镜像源。

    依次尝试指定的镜像源列表，任一成功即返回。
    全部失败后使用 uv 默认源做最后尝试。

    Args:
        packages: 包名列表。
        target: 安装目标目录。
        editable: 是否 editable 安装。
        upgrade: 是否 --upgrade。
        index_urls: 镜像源 URL 列表，为 None 时使用内置默认镜像列表。

    Returns:
        subprocess.CompletedProcess: 成功的命令执行结果。

    Raises:
        RuntimeError: 所有镜像源均失败时抛出。
    """
    urls = index_urls if index_urls is not None else DEFAULT_INDEX_URLS
    last_error = ""

    for url in urls:
        try:
            return await uv_pip_install(
                packages,
                target=target,
                editable=editable,
                upgrade=upgrade,
                index_url=url,
            )
        except RuntimeError as e:
            last_error = str(e)
            logger.warning(f"镜像源 {url} 安装失败，尝试下一个: {e}")

    try:
        return await uv_pip_install(
            packages,
            target=target,
            editable=editable,
            upgrade=upgrade,
            index_url=None,
        )
    except RuntimeError as e:
        raise RuntimeError(
            f"所有镜像源均失败 (packages={packages}): {last_error}"
        ) from e


async def uv_pip_uninstall(
    package: str,
    *,
    target: Path,
) -> subprocess.CompletedProcess[str]:
    """使用 uv pip uninstall 从指定目录卸载包。

    Args:
        package: 包名。
        target: 目标目录（对应 --target）。

    Returns:
        subprocess.CompletedProcess: 命令执行结果。
    """
    uv = get_uv_executable()

    command = [uv, "pip", "uninstall", package, "--target", str(target)]
    return await _run(command)
