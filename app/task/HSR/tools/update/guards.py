"""更新前置门：进程占用、目录可写、磁盘余量。

三个门都在**动目录之前**求值，命中任何一个都只是跳过本轮更新、按现有版本
继续跑任务，绝不让安装目录处于中间状态。
"""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.utils.logger import get_logger

logger = get_logger("HSR 更新守卫")

#: 除下载包/解压体积外额外要求的余量。外部工具运行时还要写截图和日志，
#: 把盘刚好占满会把问题转移到下一次运行。
_RESERVE_BYTES = 256 * 1024 * 1024

#: 下载前拿不到解压后体积，用压缩包大小的倍数粗估。实测比值：
#: M7A 169.5MB → 565MB（3.3×），SRA 171.5MB → 约 400MB（2.4×）。
_EXPAND_RATIO_GUESS = 3


@dataclass(frozen=True)
class GuardFailure:
    """某个前置门未通过。``reason`` 直接面向用户。"""

    reason: str


def check_no_process_running(root: Path) -> GuardFailure | None:
    """确认没有进程正跑在安装目录里。

    按**镜像路径**判断而不是进程名：既天然覆盖 SRA 的 ``SRA.exe`` /
    ``SRA-server.exe`` 和 M7A 的一串子进程，又不会误伤别家同名的
    ``chromedriver.exe``。命中不杀进程——那是用户自己开的窗口，定时触发的
    更新没有当场授权去关它。
    """

    try:
        anchor = root.resolve()
    except OSError:
        return None

    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            executable = process.info.get("exe")
            if not executable:
                continue
            if not _is_within(Path(executable), anchor):
                continue
            name = process.info.get("name") or Path(executable).name
            return GuardFailure(
                f"{name}（PID {process.info.get('pid')}）正在使用该目录，本轮跳过更新"
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return None


def check_writable(root: Path) -> GuardFailure | None:
    """建删一个探针文件确认可写。

    不按路径猜是不是 Program Files，也不查注册表、不提权：无人值守时 UAC
    弹窗会把调度卡死，而后端在正式环境本来就会自我提权，按路径猜只会误拒。
    """

    probe = root / f".automas-write-probe-{uuid.uuid4().hex}"
    try:
        probe.touch()
    except PermissionError:
        return GuardFailure(
            f"没有 {root} 的写入权限，无法自动更新；"
            "请以管理员身份运行 AUTO-MAS，或手动更新该脚本"
        )
    except OSError as exc:
        return GuardFailure(f"无法写入 {root}：{exc}")
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    return None


def check_disk_space(
    *,
    install_root: Path,
    download_dir: Path,
    package_bytes: int,
    expanded_bytes: int | None = None,
) -> GuardFailure | None:
    """分别核对下载卷和安装卷的余量。

    两者常常不在一个盘：下载包落 MAS 数据目录，解压和备份落安装卷。
    ``expanded_bytes`` 为空表示还没下载、拿不到精确值，用倍数粗估。
    备份走的是同卷改名，不额外占空间，不计入。
    """

    need_download = package_bytes + _RESERVE_BYTES
    failure = _require_free(download_dir, need_download, "下载目录")
    if failure:
        return failure

    need_install = (
        expanded_bytes
        if expanded_bytes is not None
        else package_bytes * _EXPAND_RATIO_GUESS
    ) + _RESERVE_BYTES
    return _require_free(install_root, need_install, "安装目录")


def _require_free(target: Path, need: int, label: str) -> GuardFailure | None:
    probe = target
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError as exc:
        logger.warning(f"HSR 更新：无法读取 {probe} 的磁盘余量：{exc}")
        return None
    if free >= need:
        return None
    return GuardFailure(
        f"{label}所在磁盘余量不足：需要约 {_mib(need)}，当前可用 {_mib(free)}"
    )


def _is_within(candidate: Path, anchor: Path) -> bool:
    try:
        candidate.resolve().relative_to(anchor)
    except (ValueError, OSError):
        return False
    return True


def _mib(value: int) -> str:
    return f"{value / (1024 * 1024):.0f} MB"


def expanded_size_of_zip(package: Path) -> int:
    """读 zip 目录得到解压后体积，不实际解压。"""

    import zipfile

    with zipfile.ZipFile(package) as archive:
        return sum(item.file_size for item in archive.infolist())


def free_bytes(path: Path) -> int:
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return 0


def same_volume(left: Path, right: Path) -> bool:
    """两个路径是否在同一个卷上——决定备份能不能靠改名完成。"""

    try:
        return os.path.splitdrive(left.resolve())[0].casefold() == (
            os.path.splitdrive(right.resolve())[0].casefold()
        )
    except OSError:
        return False


__all__ = [
    "GuardFailure",
    "check_disk_space",
    "check_no_process_running",
    "check_writable",
    "expanded_size_of_zip",
    "free_bytes",
    "same_volume",
]
