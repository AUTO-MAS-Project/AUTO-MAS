#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

#   Patch landing order and per-file replacement adapted from:
#       Hi3Helper.Plugin.Hypergryph Copyright (c) 2025 Collapse Launcher (MIT License)
#       https://github.com/misaka10843/Hi3Helper.Plugin.Hypergryph

"""终末地差量包读取与落地：校验后逐文件替换，最后提交版本配置。"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import subprocess
import threading
import time
import zipfile
from collections.abc import Callable, Coroutine, Sequence
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any

import pyzipper

from app.services import System
from app.utils.update_files import (
    file_md5,
    file_size,
    native_path,
    replace_file,
)

from .checks import _resolve_within
from .common import (
    _APPLY_STEP,
    _CONFIG_MEMBER,
    _DOWNLOAD_CHUNK,
    _MANIFEST_MAX_BYTES,
    _TEMP_SUFFIX,
    _VERIFY_MANIFEST_MEMBER,
    DeltaPlan,
    EndfieldUpdateError,
    MoveJob,
    PatchJob,
    ProgressFn,
    logger,
)
from .protocol import _canonical_relative, _move_entries

_PENDING_CONFIG_NAME = "config.ini.pending"
_DELETE_LIST_MEMBER = "delete_files.txt"
_WHOLE_MEMBER_PREFIX = "vfs_files/files/"
"""差量包内的成员摆法：差量成员是 `vfs_files/vfs_patch/` 加上清单里给出的名字；
VFS 整文件挂在 `vfs_files/files/<安装目录相对路径>`；非 VFS 的整文件直接用安装目录
相对路径躺在根上。"""
_APPLY_BUSY_RECHECK_SECONDS = 60.0
"""落地期间隔多久复查一次游戏占用：取一次进程表要百毫秒级，逐条问会把几千条拖成明显
更久的一轮，而用户在落地中途把客户端开回来的窗口不需要更细的粒度。"""
_DRAIN_SECONDS = 5.0
"""中止后等设备自己停下的上限：解包线程与 hpatchz 子进程都只等它松手（放掉文件句柄），
不等它把这一条做完。"""
_HPATCHZ_POLL_SECONDS = 0.5
"""打差量期间问一次「要不要中止」的间隔：单条能打到几分钟，取消若只落在等待上，子进程
还在往输出文件里写。"""


class _SplicedStream(io.RawIOBase):
    """把已下载分卷拼成可 seek 的连续流，避免物理合包再占一份体积。

    任意时刻只开一个卷句柄；所有分卷留到收尾，磁盘预估也按全程占盘计算。"""

    def __init__(self, files: Sequence[Path], sizes: Sequence[int]) -> None:
        self._files = list(files)
        self.sizes = list(sizes)
        self._starts: list[int] = []
        cursor = 0
        for size in self.sizes:
            self._starts.append(cursor)
            cursor += size
        self.size = cursor
        self.pos = 0
        self._handle: io.BufferedReader | None = None
        self._handle_index = -1

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        base = {os.SEEK_SET: 0, os.SEEK_CUR: self.pos, os.SEEK_END: self.size}[whence]
        self.pos = max(0, base + offset)
        return self.pos

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self.size - self.pos
        size = min(size, self.size - self.pos)
        if size <= 0:
            return b""
        data = self._span(self.pos, size)
        self.pos += len(data)
        return data

    def readinto(self, buffer):  # type: ignore[no-untyped-def]
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def close(self) -> None:
        self._close_handle()
        super().close()

    def _locate(self, offset: int) -> int:
        for index in range(len(self._starts) - 1, -1, -1):
            if offset >= self._starts[index]:
                return index
        return 0

    def _span(self, offset: int, length: int) -> bytes:
        out = bytearray()
        cursor = offset
        remaining = length
        while remaining > 0:
            index = self._locate(cursor)
            local = cursor - self._starts[index]
            take = min(remaining, self.sizes[index] - local)
            out += self._read_volume(index, local, take)
            cursor += take
            remaining -= take
        return bytes(out)

    def _read_volume(self, index: int, local: int, length: int) -> bytes:
        if self._handle is None or self._handle_index != index:
            self._close_handle()
            self._handle = open(native_path(self._files[index]), "rb")
            self._handle_index = index
        self._handle.seek(local)
        data = self._handle.read(length)
        if len(data) != length:
            raise EndfieldUpdateError(
                f"分卷 {self._files[index].name} 比服务端声明的短：读到 "
                f"{len(data)}，期望 {length}"
            )
        return data

    def _close_handle(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
            self._handle_index = -1


def _read_package_manifests(
    archive: pyzipper.AESZipFile, members: set[str]
) -> tuple[tuple[MoveJob, ...], tuple[str, ...]]:
    """读包内落地核对表与删除表，限制正文体积并核对每个整文件成员。

    verify_files.json 的 move 段给出路径、MD5 与体积；VFS 成员在 vfs_files/files/
    下，其余在包根。缺少成员就停止，避免漏写文件后仍提交新版配置。"""

    # 整块读进内存之前先卡一次体积，与 CDN 上那份差量清单同一条上限
    for name in (_VERIFY_MANIFEST_MEMBER, _DELETE_LIST_MEMBER):
        if name not in members:
            raise EndfieldUpdateError(
                f"差量包里没有 {name}，MAS 无法确认落地文件，已停止自动更新，请手动更新一次"
            )
        info = archive.getinfo(name)
        if info.file_size > _MANIFEST_MAX_BYTES:
            raise EndfieldUpdateError(
                f"包内清单 {name} 体积 {info.file_size} 字节"
                f"超过上限 {_MANIFEST_MAX_BYTES}，判为异常"
            )
    with archive.open(_VERIFY_MANIFEST_MEMBER) as handle:
        doc = json.loads(handle.read().decode("utf-8"))
    if not isinstance(doc, dict):
        raise EndfieldUpdateError("包内落地核对表顶层不是 JSON 对象")
    moves: list[MoveJob] = []
    for entry in _move_entries(doc):
        member = (
            entry.path if entry.path in members else _WHOLE_MEMBER_PREFIX + entry.path
        )
        if member not in members:
            raise EndfieldUpdateError(f"清单要的整文件在包里找不到: {entry.path}")
        moves.append(replace(entry, member=member))
    with archive.open(_DELETE_LIST_MEMBER) as handle:
        text = handle.read().decode("utf-8", "replace")
    deletes = tuple(
        _canonical_relative(line.strip()) for line in text.splitlines() if line.strip()
    )
    return tuple(moves), deletes


def _build_delta_plan(
    specs: Sequence[PatchJob],
    members: set[str],
    moves: Sequence[MoveJob],
    deletes: Sequence[str],
) -> DeltaPlan:
    """把两份清单并成一次落地计划；成员对不上就判废。"""

    for spec in specs:
        if spec.member not in members:
            raise EndfieldUpdateError(f"清单要的差量成员在包里找不到: {spec.member}")
    for job in moves:
        if not job.member or job.member not in members:
            raise EndfieldUpdateError(f"清单要的整文件在包里找不到: {job.path}")
    if _CONFIG_MEMBER not in members:
        # 缺了它 MAS 无法确认更新是否生效，只会每轮静默重下差量，宁可拒绝接管
        raise EndfieldUpdateError(
            "差量包里没有 config.ini，MAS 无法确认更新结果，已停止自动更新，请手动更新一次"
        )
    # 先写后删：与本轮要写的文件同名的删除项跳过，否则刚写好就自我删除；
    # 大小写按文件系统口径忽略。
    written = {os.path.normcase(job.path) for job in (*specs, *moves)}
    kept = [path for path in deletes if os.path.normcase(path) not in written]
    if len(kept) != len(deletes):
        logger.info(
            f"删除表有 {len(deletes) - len(kept)} 项与本轮要写的文件同名，跳过这些删除"
        )
    return DeltaPlan(
        patches=tuple(specs),
        moves=tuple(moves),
        deletes=tuple(kept),
    )


def _write_member(
    archive: pyzipper.AESZipFile,
    info: zipfile.ZipInfo,
    temp: Path,
    abort: threading.Event,
) -> None:
    """逐块解包到临时文件并检查 abort，由调用方放在线程中执行。

    pyzipper 读满时验证 AES HMAC，这里另核对长度；逐块检查防止中止后继续长时间写盘。"""

    written = 0
    try:
        # 包里的目录条目不进成员表，父目录得自己建出来
        temp.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, open(native_path(temp), "wb") as sink:
            while chunk := source.read(4 * _DOWNLOAD_CHUNK):
                if abort.is_set():
                    raise EndfieldUpdateError(
                        f"本轮更新已中止（正在读 {info.filename}），游戏目录处于未完成状态"
                    )
                sink.write(chunk)
                written += len(chunk)
    except OSError as error:
        raise EndfieldUpdateError(_describe_os_error(error, info.filename)) from error
    if written != info.file_size:
        raise EndfieldUpdateError(
            f"{info.filename} 读出 {written} 字节，与包内声明的 {info.file_size} 不符"
        )


def _describe_os_error(error: OSError, name: str) -> str:
    if getattr(error, "winerror", None) == 5:
        return f"{name} 被占用或无权限写入，请确认终末地已完全退出后重试（{error}）"
    if getattr(error, "winerror", None) == 206:
        return (
            f"{name} 的路径超过 Windows 长度限制，"
            "请缩短安装目录或开启系统长路径支持后重试"
        )
    return f"写入 {name} 失败: {error}"


def _run_hpatchz(
    exe: Path,
    base: Path,
    diff: Path,
    out: Path,
    new_size: int,
    abort: threading.Event,
) -> None:
    """单文件模式打差量：`hpatchz <基线> <差量> <输出>`，非 0 退出即失败。

    `new_size` 是这一条声明的新文件体积，用来把「盘写不下」从其它失败里分出来。
    子进程按 `_HPATCHZ_POLL_SECONDS` 问一次 `abort`：大成员能打几十秒到几分钟，取消只
    取消等待的话，它还攥着输出文件，本次收尾和下一轮都要跟它抢同一个名字。
    """

    child = subprocess.Popen(
        [str(exe), str(base), str(diff), str(out)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = stderr = b""
    while True:
        try:
            stdout, stderr = child.communicate(timeout=_HPATCHZ_POLL_SECONDS)
            break
        except subprocess.TimeoutExpired:
            if not abort.is_set():
                continue
            child.kill()
            with suppress(OSError, subprocess.SubprocessError):
                child.communicate(timeout=_DRAIN_SECONDS)
            raise EndfieldUpdateError(f"本轮更新已中止（正在打 {base.name}）") from None
    if child.returncode == 0:
        return
    free = shutil.disk_usage(out.parent).free
    if free < new_size:
        raise EndfieldUpdateError(
            f"磁盘余量不足：写 {out.name} 还差约 "
            f"{(new_size - free) / 1024**3:.1f} GB，当前只剩 "
            f"{free / 1024**3:.1f} GB，请清理磁盘后重试"
        )
    lines = (stdout + stderr).decode("utf-8", "replace").strip().splitlines()
    raise EndfieldUpdateError(
        f"差量应用失败（{base.name} → {out.name}）："
        f"hpatchz 退出码 {child.returncode}，"
        f"{lines[-1] if lines else '没有输出'}"
    )


async def _commit(temp: Path, target: Path, md5: str, size: int) -> None:
    """比过体积与 MD5 才把临时文件改名就位。

    先校验再移动：宁可这次更新停住，也不能把坏文件写进游戏目录。同卷下 `os.replace`
    是原子改名，不存在写一半的中间态。
    """

    actual = file_size(temp)
    if actual != size:
        with suppress(OSError):
            temp.unlink(missing_ok=True)
        logger.warning(f"{target} 落地体积不符：期望 {size} 实际 {actual}")
        raise EndfieldUpdateError(f"{target.name} 落地后的体积不对，已停止覆盖")
    digest = await asyncio.to_thread(file_md5, temp)
    if digest != md5:
        with suppress(OSError):
            temp.unlink(missing_ok=True)
        logger.warning(f"{target} 落地校验未通过：期望 {md5} 实际 {digest}")
        raise EndfieldUpdateError(f"{target.name} 落地校验未通过，已停止覆盖")
    # 改名是单次系统调用，不走线程池：进了线程池，被判定「已中止」之后仍可能在后台
    # 把游戏文件换掉，回报的状态就和磁盘上的实情不一致
    replace_file(temp, target, clear_readonly=True)


async def _commit_verified(temp: Path, target: Path, size: int) -> None:
    """提交一个**已经**比过指纹的临时文件：只复核体积，不再读一遍内容。

    复用上一轮打好的临时文件时走这里。`_reusable_output` 刚把整份内容读过一次算 MD5，
    紧接着再让 `_commit` 读第二遍，等于为一个 GB 级的整文件成员白扫一遍盘。体积仍要
    复核：从校验到改名之间窗口很短，但把这一步省掉就等于「校验过的东西」不再有下限。
    """

    actual = file_size(temp)
    if actual != size:
        with suppress(OSError):
            temp.unlink(missing_ok=True)
        logger.warning(f"{target} 落地体积不符：期望 {size} 实际 {actual}")
        raise EndfieldUpdateError(f"{target.name} 落地后的体积不对，已停止覆盖")
    replace_file(temp, target, clear_readonly=True)


async def _reusable_output(temp: Path, md5: str, size: int) -> bool:
    """`temp` 是不是上一轮已经做好、只差改名的那一条：体积与 MD5 都对得上才算。

    认出来就能省掉一次解包加一次 `hpatchz`——整文件成员可以到 GB 级，重做一遍的代价
    是实打实的。对不上的一律删掉：留着它，下一轮的 `hpatchz` 或解包会从残骸上接着写。

    `md5` 缺失时一律返回 False，退回重做：改动后的提交入口（`_commit_verified`）不再复核
    内容，只靠体积就放行等于把一个没验过内容的文件写进游戏目录；而改动前那条路是
    `_commit`，它对空 `md5` 必然判失败——这里保持同样的保守口径。
    """

    if not md5:
        return False
    if file_size(temp) != size:
        return False
    try:
        if await asyncio.to_thread(file_md5, temp) != md5:
            return False
    except OSError:
        return False
    return True


def _collect_temp_files(root: Path) -> list[Path]:
    """在工作线程里收一遍残留的临时文件：遍历十万级目录是秒级的活，别压在事件循环上。"""

    return list(root.rglob("*" + _TEMP_SUFFIX))


async def _apply_delta(
    archive: pyzipper.AESZipFile,
    plan: DeltaPlan,
    game_exe: Path,
    install_dir: Path,
    staging: Path,
    hpatchz: Path,
    progress: ProgressFn | None,
    abort: threading.Event,
    mark_landing_started: Callable[[], None] | None = None,
) -> int:
    """按差量计划落地：打差量 → 搬整文件 → 清理删除表 → 最后提交 `config.ini`。

    每条都先写进目标旁边的临时文件，比过 MD5 才改名；`config.ini` 单独暂存到收尾才
    提交，于是「安装目录里的版本号已是新版」等价于「本次其余文件都已落盘」。上一轮
    落到一半的那些条目由调用方先按新指纹挑走，剩下的在这里做；已经做好的临时文件也
    认指纹直接改名，不重打一遍。清单里没有而本地多出来的文件不删——删错了不可逆，
    而留着只是占地方。"""

    total = len(plan.patches) + len(plan.moves)
    done = 0
    planned_temps: set[str] = set()
    for job in (*plan.patches, *plan.moves):
        target = _resolve_within(install_dir, job.path)
        planned_temps.add(target.with_name(target.name + _TEMP_SUFFIX).name)
    # 只回收与本轮计划无关的孤儿：计划内那些临时文件正是续传要接着用的东西，一并扫掉
    # 就等于每轮都从零开始。同名目标会被本轮截断覆盖，但文件名一旦变了，旧孤儿就永久
    # 留在游戏目录里，所以仍要收。只认我们自己独占的那个后缀。
    for stray in await asyncio.to_thread(_collect_temp_files, install_dir):
        if stray.name in planned_temps:
            continue
        try:
            stray.unlink(missing_ok=True)
        except OSError as error:
            logger.warning(f"未能清理残留的临时文件 {stray.name}: {error}")

    async def _report(line: str) -> None:
        if progress is not None and (done % _APPLY_STEP == 0 or done == total):
            await progress(line)

    next_busy_check = time.monotonic() + _APPLY_BUSY_RECHECK_SECONDS

    async def recheck() -> None:
        """定期检查游戏是否重新启动，在下一条覆盖前停止，避免客户端占用资源文件。"""

        nonlocal next_busy_check
        now = time.monotonic()
        if now < next_busy_check:
            return
        next_busy_check = now + _APPLY_BUSY_RECHECK_SECONDS
        if await System.is_process_running(game_exe):
            raise EndfieldUpdateError(
                "落地期间游戏被重新启动，本轮不再覆盖，请退出游戏后重试"
            )

    async def run_worker(work: Coroutine[Any, Any, None]) -> None:
        """取消时通知写盘线程停下，并限时等待它释放句柄。"""

        task = asyncio.create_task(work)
        # 取消后线程仍可能报错，取回异常以免留下未处理的任务异常。
        task.add_done_callback(lambda done: done.cancelled() or done.exception())
        try:
            await asyncio.shield(task)
        except (TimeoutError, asyncio.CancelledError):
            abort.set()
            with suppress(BaseException):
                await asyncio.wait({task}, timeout=_DRAIN_SECONDS)
            raise

    async def _unpack(info: zipfile.ZipInfo, temp: Path) -> None:
        # 大成员解包放在线程里，保持事件循环响应；中止由逐块检查 abort 实现。
        await run_worker(asyncio.to_thread(_write_member, archive, info, temp, abort))

    if mark_landing_started is not None:
        # 置位必须早于第一次写入：此后崩溃留下的就是「可能半新半旧」的现场，而在这之前
        # 一个字都没写进游戏目录，不该让下一轮误判
        mark_landing_started()

    for index, job in enumerate(plan.patches, start=1):
        await recheck()
        target = _resolve_within(install_dir, job.path)
        temp = target.with_name(target.name + _TEMP_SUFFIX)
        try:
            temp.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise EndfieldUpdateError(
                f"无法创建游戏目录 {temp.parent}：{error}"
            ) from error
        if await _reusable_output(temp, job.md5, job.size):
            # 上一轮已经打好了，只差改名；省掉解包与 hpatchz 两道重活。指纹刚在上面
            # 比过，这里不再读第二遍
            logger.info(f"复用上轮已打好的临时文件: {temp.name}")
            await _commit_verified(temp, target, job.size)
            done += 1
            await _report(f"正在打补丁并覆盖游戏文件 {done}/{total}")
            continue
        with suppress(OSError):
            temp.unlink(missing_ok=True)
        diff_file = staging / f"diff-{index:04d}{_TEMP_SUFFIX}"
        await _unpack(archive.getinfo(job.member), diff_file)
        try:
            await run_worker(
                asyncio.to_thread(
                    _run_hpatchz,
                    hpatchz,
                    _resolve_within(install_dir, job.base_path),
                    diff_file,
                    temp,
                    job.size,
                    abort,
                )
            )
        finally:
            # 清残骸不能顶掉真正的失败原因（或取消）：限时到点与用户手停时，hpatchz
            # 还攥着这个差量文件，Windows 上删不动，删失败必须咽在这里
            with suppress(OSError):
                diff_file.unlink(missing_ok=True)
        await _commit(temp, target, job.md5, job.size)
        done += 1
        await _report(f"正在打补丁并覆盖游戏文件 {done}/{total}")

    for job in plan.moves:
        await recheck()
        target = _resolve_within(install_dir, job.path)
        temp = target.with_name(target.name + _TEMP_SUFFIX)
        if await _reusable_output(temp, job.md5, job.size):
            logger.info(f"复用上轮已解好的临时文件: {temp.name}")
            await _commit_verified(temp, target, job.size)
            done += 1
            await _report(f"正在打补丁并覆盖游戏文件 {done}/{total}")
            continue
        with suppress(OSError):
            temp.unlink(missing_ok=True)
        await _unpack(archive.getinfo(job.member), temp)
        await _commit(temp, target, job.md5, job.size)
        done += 1
        await _report(f"正在打补丁并覆盖游戏文件 {done}/{total}")

    for path in plan.deletes:
        try:
            _resolve_within(install_dir, path).unlink(missing_ok=True)
        except OSError as error:
            # 删除失败只是留个没用的文件，不该让整轮更新停在这里
            logger.warning(f"未能按删除表清理 {path}: {error}")

    pending = staging / _PENDING_CONFIG_NAME
    await _unpack(archive.getinfo(_CONFIG_MEMBER), pending)
    # 携带新版本号的这份配置是本轮最后一次写入：单次原子改名，不进线程池
    replace_file(pending, install_dir / _CONFIG_MEMBER, clear_readonly=True)
    return done
