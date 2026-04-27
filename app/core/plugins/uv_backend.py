#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
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

UV_INSTALL_SCRIPT_URL = "https://astral.sh/uv/install.ps1"


def _embedded_uv_path(app_root: Path | None = None) -> Path:
    root = app_root or Path.cwd()
    return root / "environment" / "python" / "Scripts" / "uv.exe"


def _is_executable_file(path: Path) -> bool:
    return path.is_file()


def _candidate_uv_paths() -> list[Path]:
    """返回 uv 的候选路径，AUTO-MAS 管理路径优先。"""
    candidates: list[Path] = []

    env_path = os.getenv("AUTO_MAS_UV_EXE")
    if env_path:
        candidates.append(Path(env_path))

    app_root = Path.cwd()
    candidates.extend(
        [
            _embedded_uv_path(app_root),
            app_root / ".venv" / "Scripts" / "uv.exe",
            Path(sys.executable).resolve().parent / "uv.exe",
        ]
    )

    path_uv = shutil.which("uv")
    if path_uv:
        candidates.append(Path(path_uv))

    return candidates


def _find_uv() -> str | None:
    """查找 uv 可执行文件路径。

    查找顺序：
    1. Electron 安装位置 (environment/python/Scripts/uv.exe)
    2. 系统 PATH
    """
    local_uv = Path.cwd() / "environment" / "python" / "Scripts" / "uv.exe"
    if local_uv.is_file():
        return str(local_uv)
    return shutil.which("uv")


def _set_cached_uv(path: str) -> str:
    global _uv_path
    _uv_path = path
    os.environ["AUTO_MAS_UV_EXE"] = path
    return path


def get_uv_executable() -> str:
    """返回 uv 可执行文件路径（带缓存）。"""
    if _uv_path is not None:
        return _uv_path

    found = _find_uv()
    if found is None:
        raise RuntimeError(
            "未找到 uv 可执行文件，请确认 environment/python/Scripts/uv.exe 已存在，"
            "或通过 AUTO_MAS_UV_EXE 指定 uv.exe 路径。"
        )
    return _set_cached_uv(found)


def check_uv_available() -> bool:
    """检查 uv 是否可用。"""
    found = _find_uv()
    if found is None:
        return False
    _set_cached_uv(found)
    return True


def _quote_powershell_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _find_powershell() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")


def install_uv(install_dir: Path | None = None) -> bool:
    """通过官方安装脚本把 uv 安装到 AUTO-MAS 管理目录。"""
    target_dir = install_dir or _embedded_uv_path().parent
    target_dir.mkdir(parents=True, exist_ok=True)

    powershell = _find_powershell()
    if powershell is None:
        logger.error("未找到 PowerShell，无法自动安装 uv")
        return False

    script = "; ".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$env:UV_INSTALL_DIR = {_quote_powershell_string(str(target_dir))}",
            f"irm {UV_INSTALL_SCRIPT_URL} | iex",
        ]
    )
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip() or (completed.stdout or "").strip() or "未知错误"
        logger.error(f"uv 自动安装失败: {detail}")
        return False

    found = _find_uv()
    if found is None:
        logger.error(f"uv 安装脚本执行完成，但未找到 uv.exe: target={target_dir}")
        return False

    _set_cached_uv(found)
    logger.info(f"uv 已就绪: {found}")
    return True


def ensure_uv() -> bool:
    """确保 uv 可用；缺失时安装到 environment/python/Scripts。"""
    if check_uv_available():
        return True
    return install_uv()


def install_uv() -> bool:
    """通过官方安装脚本自动安装 uv。

    Returns:
        bool: 安装成功返回 True。
    """
    global _uv_path
    logger.info("正在自动安装 uv ...")

    completed = subprocess.run(
        ["powershell", "-ExecutionPolicy", "ByPass", "-c", "irm https://astral.sh/uv/install.ps1 | iex"],
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        logger.error(f"uv 安装失败: {detail}")
        return False

    _uv_path = None
    found = _find_uv()
    if found is None:
        logger.error("uv 安装脚本执行成功，但仍未在 PATH 中找到 uv")
        return False

    _uv_path = found
    logger.info(f"uv 安装成功: {found}")
    return True


def ensure_uv() -> bool:
    """确保 uv 可用，不可用时自动安装。

    Returns:
        bool: uv 最终可用返回 True。
    """
    if check_uv_available():
        return True
    return install_uv()


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
    """使用 uv pip install 安装包到指定目录。"""
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
        raise RuntimeError(f"uv pip install 失败: packages={packages}, detail={detail}")

    return completed


async def uv_pip_install_with_mirror_fallback(
    packages: list[str],
    *,
    target: Path,
    editable: bool = False,
    upgrade: bool = True,
    index_urls: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """使用 uv pip install 安装包，自动轮替镜像源。"""
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
        raise RuntimeError(f"所有镜像源均失败 (packages={packages}): {last_error}") from e


async def uv_pip_uninstall(
    package: str,
    *,
    target: Path,
) -> subprocess.CompletedProcess[str]:
    """使用 uv pip uninstall 从指定目录卸载包。"""
    uv = get_uv_executable()
    command = [uv, "pip", "uninstall", package, "--target", str(target)]
    return await _run(command)
