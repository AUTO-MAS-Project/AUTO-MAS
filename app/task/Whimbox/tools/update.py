#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""官方后端 wheel 更新：发行清单、下载器和 pip；不解析上游配置。

安装方式与 whimbox_app 的 PythonManager.installWheelPackage 一致。
安装失败/取消留下安装标记；准备失败且原安装可用时由调度器告警后继续。
"""

import asyncio
import hashlib
import os
import re
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

import httpx
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

from app.core import Config
from app.core.update import download_file
from app.utils import ProcessRunner
from app.utils.common.proxy_env import proxy_environment

from .launcher import find_upstream_pids
from .upstream import APP_EXE_NAME, REL_PYTHON_EXE, WheelAssetsConfigSurface

REPOSITORY = "nikkigallery/Whimbox"
RECOVERY_HINT = (
    "奇想盒后端安装尚未确认完成。请关闭奇想盒 app 和后端，"
    "开启 MAS 的“运行前更新后端”后重新运行，由 MAS 完成安装与校验；"
    "即使已在 app 内修复，仍需完成这一步。"
)


class WhimboxUpdateUnsafeError(RuntimeError):
    """安装状态未确认或仍有写入进程，不能沿用当前安装。"""


async def confirm_usable_installation(root: Path) -> None:
    if pending_marker(root).exists():
        raise WhimboxUpdateUnsafeError(RECOVERY_HINT)
    if await asyncio.to_thread(find_upstream_pids, root):
        raise WhimboxUpdateUnsafeError("奇想盒仍在运行，请先关闭 app 和后端")
    error = WheelAssetsConfigSurface(root).check_install()
    if error:
        raise WhimboxUpdateUnsafeError(error)
    try:
        await installed_version(root)
        await run_python(root, "-m", "pip", "check")
        await run_python(
            root, "-c", "import importlib.util as u; assert u.find_spec('whimbox.main')"
        )
    except Exception as error:
        raise WhimboxUpdateUnsafeError(
            "无法确认奇想盒当前后端可用，请先在 app 内修复"
        ) from error


def pending_marker(root: Path) -> Path:
    return root / "python-embedded" / ".mas-update-pending"


@contextmanager
def installation_access(root: Path):
    """同一安装的更新、运行和设置会话互斥；进程退出由操作系统释放。"""
    key = hashlib.sha256(os.path.normcase(str(root.resolve())).encode()).hexdigest()
    directory = Path(tempfile.gettempdir()) / "auto-mas-whimbox-locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{key}.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("奇想盒安装正在被其他任务使用，请稍后重试") from error
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


async def request_release() -> dict:
    async with httpx.AsyncClient(
        proxy=Config.proxy, timeout=15, follow_redirects=True
    ) as client:
        response = await client.get(
            f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
        )
        response.raise_for_status()
        release = response.json()
    if (
        not isinstance(release, dict)
        or release.get("draft")
        or release.get("prerelease")
    ):
        raise ValueError("奇想盒未返回正式发行版")
    return release


def select_wheel(release: dict) -> tuple[Version, str, str, str]:
    """仅接受官方发布的通用 wheel 和 SHA256，不使用任意下载地址。"""
    tag = release["tag_name"]
    version = Version(tag)
    if version.is_prerelease or version.is_devrelease:
        raise ValueError("奇想盒最新发行版不是正式版")
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if not name.endswith("-py3-none-any.whl") or "/" in name or "\\" in name:
            continue
        package, wheel_version, _, _ = parse_wheel_filename(name)
        digest = asset.get("digest", "")
        if canonicalize_name(package) != "whimbox" or wheel_version != version:
            continue
        if not isinstance(digest, str) or not re.fullmatch(
            r"sha256:[0-9a-fA-F]{64}", digest
        ):
            raise ValueError("奇想盒官方更新包缺少 SHA256 校验信息，请在 app 内更新")
        url = f"https://github.com/{REPOSITORY}/releases/download/{quote(tag, safe='')}/{quote(name, safe='')}"
        return version, name, url, digest[7:].lower()
    raise ValueError("奇想盒正式版没有可安装的后端更新包")


async def run_python(
    root: Path,
    *args: str,
    timeout: float = 30,
    env: Mapping[str, str] | None = None,
) -> str:
    result = await ProcessRunner.run_process(
        root / REL_PYTHON_EXE,
        "-I",
        *args,
        cwd=root,
        timeout=timeout,
        kill_tree_on_cancel=True,
        env=env,
    )
    if result.returncode != 0:
        if pending_marker(root).exists():
            raise WhimboxUpdateUnsafeError(RECOVERY_HINT)
        raise RuntimeError(
            "奇想盒内置 Python 执行失败，请检查目录写入权限或在 app 内修复后端"
        )
    return result.stdout.strip()


async def installed_version(root: Path) -> Version:
    return Version(
        await run_python(
            root, "-c", "import importlib.metadata as m; print(m.version('whimbox'))"
        )
    )


def verify_digest(path: Path, expected: str) -> None:
    with path.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != expected:
        raise ValueError("奇想盒更新包校验失败，请重新运行下载")


async def ensure_backend_updated(root: Path) -> str:
    """调用方持安装锁；每批用户一次，成功返回可展示的版本状态。"""
    if not (root / APP_EXE_NAME).is_file() or not (root / REL_PYTHON_EXE).is_file():
        raise RuntimeError("奇想盒安装不完整，请先在 app 内完成初始化")
    if await asyncio.to_thread(find_upstream_pids, root):
        raise RuntimeError("请先退出奇想盒 app 和后端，再运行更新")
    marker = pending_marker(root)
    target, name, url, digest = select_wheel(await request_release())
    # 上次安装失败时，元数据也可能损坏：强制重装，不按残留版本跳过。
    repairing = marker.exists()
    if not repairing:
        current = await installed_version(root)
        if current >= target:
            return f"奇想盒后端已是最新版本（{current}）"
    key = hashlib.sha256(os.path.normcase(str(root.resolve())).encode()).hexdigest()
    stage = Path.cwd() / "data" / "whimbox_update" / key
    stage.mkdir(parents=True, exist_ok=True)
    wheel = stage / name
    await download_file(
        url,
        wheel,
        timeout=30 * 60,
        proxy=Config.proxy,
        downloader="fluxdown"
        if Config.setting.Update.FluxdownTakeoverAll
        else "builtin",
        source="GitHub",
    )
    await asyncio.to_thread(verify_digest, wheel, digest)
    # 源码依赖在准备阶段隔离构建成 wheel，不往现有后端安装构建工具。
    # 每轮使用独立目录，避免旧缓存的源码包或版本参与离线安装。
    with tempfile.TemporaryDirectory(prefix="packages-", dir=stage) as directory:
        packages = Path(directory)
        await run_python(
            root,
            "-m",
            "pip",
            "--isolated",
            "wheel",
            "--disable-pip-version-check",
            "--no-input",
            "--index-url",
            "https://pypi.org/simple/",
            "--wheel-dir",
            str(packages),
            str(wheel),
            timeout=10 * 60,
            env=proxy_environment(Config.proxy),
        )
        if await asyncio.to_thread(find_upstream_pids, root):
            raise RuntimeError("依赖准备期间奇想盒已启动，请退出后重试")
        # 只有准备完成才进入写盘阶段；安装失败或取消仍保留标记。
        marker.write_text(str(target), encoding="utf-8")
        flags = ("--force-reinstall",) if repairing else ()
        await run_python(
            root,
            "-m",
            "pip",
            "--isolated",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--no-index",
            "--find-links",
            str(packages),
            "--only-binary=:all:",
            "--upgrade",
            *flags,
            str(wheel),
            timeout=10 * 60,
        )
    if await installed_version(root) != target:
        raise WhimboxUpdateUnsafeError(RECOVERY_HINT)
    await run_python(root, "-m", "pip", "check")
    await run_python(
        root, "-c", "import importlib.util as u; assert u.find_spec('whimbox.main')"
    )
    marker.unlink()
    return f"奇想盒后端已更新至 {target}，准备启动任务"
