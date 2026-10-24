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

"""魔改 AVD 更新的本机文件操作：解包、拼新版、核对、换上、崩溃恢复。不联网。

根目录里更新器只用自己的 ``.update``（和根目录同一个盘，换上靠改名）::

    .update\\state.json          阶段与换上计划（先写临时文件再替换）
    .update\\download\\          下载的包（``.part`` 续传）
    .update\\pkg\\               包解开后的样子（已剥掉顶层目录）
    .update\\stage\\emulator\\   拼好、核对过的新 ``sdk\\emulator``（``stage\\staged.json`` 记版本与摘要）
    .update\\previous\\          换上中的旧版：``emulator\\`` 与被替换的包内文件（``root\\``），换完就删
    .update\\trash\\             要删的目录先改名到这里、写好状态后再删

根目录里不属于包的东西一律不碰：``avd\\``、``mas-avd.json``（只改 ``components.emulator`` 并记一条
``updateHistory``，读不出时不写）、``sdk\\`` 下 ``emulator`` 以外的目录、``downloads\\``、``logs\\`` 等。

准备新版时先把状态改成「正在准备」（不可安装），核对通过、``stage`` 拼好后才写 ``staged``，并给暂存
记下「路径 + 大小 + 修改时间」摘要；换上前按摘要核对暂存没被动过。

换上只有两次目录改名（``sdk\\emulator`` → ``previous``、``stage`` → ``sdk\\emulator``）。改名前先按
进程的可执行文件路径确认没有程序在用 ``sdk\\emulator``（正在运行的 exe 不挡目录改名，见
:func:`ensure_not_in_use`）；还有文件被不带共享删除地打开着时，第一次改名失败，什么都没动。包里其他
文件（``tools``、``LICENSES``、``components``、两个 bat、``说明.txt``、清单）逐个从 ``pkg`` 替换过去
（``pkg`` 里的就是写好的临时文件），替换前先备份进 ``previous\\root``。每一步之前都把下一步写进
``state.json``，MAS 中途退出时 :func:`recover` 按它补完或退回；``previous`` 留到换上做完、写好状态
之后才挪进 ``trash`` 删掉。不留旧版、不能回退。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import time
import zipfile
from collections.abc import Callable, Iterator
from contextlib import suppress
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import psutil

from app.utils import get_logger
from app.utils.update_files import native_path, replace_file, resolve_within

from .components import (
    MetadataUnreadable,
    emulator_files_present,
    qemu_has_self_built_mark,
    read_metadata_strict,
    read_mod_build_at,
    replace_with_retry,
    sdk_dir,
    write_metadata,
)
from .constants import (
    AVD_DIR,
    GUEST_PATCH_DIR,
    LOGS_DIR,
    METADATA_FILE,
    MODAVD_MANIFEST_FILE,
    MODAVD_PLATFORM,
    SHADER_CACHE_DIR,
    UPDATE_DIR,
    UPDATE_HISTORY_KEEP,
    UPDATE_MAX_ENTRIES,
    UPDATE_MAX_UNPACKED_BYTES,
)
from .update_source import (
    ModAvdVersion,
    display_version,
    local_version,
    parse_version,
    requires_manifest,
)

logger = get_logger("魔改 AVD 更新")

#: ``state.json`` 的 ``phase``：idle 没有待装的 / preparing 正在下载、拼新版（不可安装）/
#: staged 新版已拼好核对过、可以安装 / swapping 换上中
PHASE_IDLE = "idle"
PHASE_PREPARING = "preparing"
PHASE_STAGED = "staged"
PHASE_SWAPPING = "swapping"

_EMULATOR_REL = "sdk/emulator"
#: 包里不许出现、更新器也绝不碰的顶层目录（小写比较）：实例、下载的 Google 组件、日志、MAS 运行期产物。
_PROTECTED_TOP = frozenset(
    name.lower()
    for name in (
        AVD_DIR,
        "downloads",
        LOGS_DIR,
        UPDATE_DIR,
        SHADER_CACHE_DIR,
        GUEST_PATCH_DIR,
    )
)
_BAD_NAME_CHARS = frozenset('<>:"|?*')
_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_COPY_CHUNK = 1024 * 1024


class PackageError(RuntimeError):
    """包本身不能用：路径越界、碰了受保护的目录、清单对不上、不是我们的模拟器……"""


class SwapBlocked(RuntimeError):
    """换上前还有程序在用 ``sdk\\emulator``（或第一次改名失败）。什么都没动。"""


class UpdateCancelled(RuntimeError):
    """用户取消了下载 / 解包。"""


Progress = Callable[[int, int], None]
Cancelled = Callable[[], bool]


# ---- 目录与状态 ------------------------------------------------------------


def update_dir(root: str | Path) -> Path:
    return Path(root) / UPDATE_DIR


def emulator_dir(root: str | Path) -> Path:
    return sdk_dir(root) / "emulator"


def download_dir(root: str | Path) -> Path:
    return update_dir(root) / "download"


def pkg_dir(root: str | Path) -> Path:
    return update_dir(root) / "pkg"


def stage_emulator_dir(root: str | Path) -> Path:
    return update_dir(root) / "stage" / "emulator"


def previous_dir(root: str | Path) -> Path:
    return update_dir(root) / "previous"


def remove_tree(path: str | Path) -> None:
    """删一个目录（只读文件也删）；不在就算了。"""

    def clear_readonly(function, target, _error):
        os.chmod(target, stat.S_IWRITE)
        function(target)

    if os.path.lexists(native_path(path)):
        shutil.rmtree(native_path(path), onexc=clear_readonly)


def _rename(source: Path, target: Path) -> None:
    os.rename(native_path(source), native_path(target))


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """先写临时文件再替换，写到一半断电也不留半个 JSON（同 ``mas-avd.json`` 的写法）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # 界面轮询状态时会读着它，替换撞上了就稍等重试
    replace_with_retry(temp, path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_state(root: str | Path) -> dict[str, Any]:
    """``.update\\state.json``；没有或读不出按空闲处理。"""
    state = _read_json(update_dir(root) / "state.json")
    state.setdefault("phase", PHASE_IDLE)
    return state


def write_state(root: str | Path, state: dict[str, Any]) -> None:
    state["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    write_json_atomic(update_dir(root) / "state.json", state)


# ---- 包内路径 --------------------------------------------------------------


def package_path(name: str, top_dir: str = "") -> str | None:
    """zip 条目名 → 包内相对路径（``/`` 分隔，已剥掉 ``top_dir``）。目录条目返回 ``None``。

    条目必须落在包根以内：``..``、绝对路径、盘符、Windows 不认的名字一律拒收；也不许碰
    根目录里不属于包的东西（实例、``mas-avd.json``、``sdk`` 下 ``emulator`` 以外的组件等）。
    """
    raw = name.replace("\\", "/")
    if top_dir:
        prefix = top_dir.rstrip("/") + "/"
        if raw == prefix:
            return None
        if not raw.startswith(prefix):
            raise PackageError(f"包里的 {name} 不在顶层目录 {top_dir} 下")
        raw = raw[len(prefix) :]
    if raw.startswith("/") or not raw.strip("/"):
        raise PackageError(f"包里有不安全的路径: {name!r}")
    is_dir = raw.endswith("/")
    parts = raw.rstrip("/").split("/")
    for part in parts:
        if (
            not part
            or part in (".", "..")
            or part != part.rstrip(". ")
            or any(char in _BAD_NAME_CHARS or ord(char) < 32 for char in part)
            or part.split(".")[0].lower() in _RESERVED_NAMES
        ):
            raise PackageError(f"包里有不安全的路径: {name!r}")
    rel = "/".join(parts)
    lowered = [part.lower() for part in parts]
    if (
        lowered[0] in _PROTECTED_TOP
        or rel.lower() == METADATA_FILE.lower()
        or (lowered[0] == "sdk" and (len(lowered) < 2 or lowered[1] != "emulator"))
    ):
        if is_dir and len(parts) == 1 and lowered[0] == "sdk":
            return None
        raise PackageError(f"包里有不该由更新覆盖的文件: {rel}")
    return None if is_dir else rel


def is_emulator_file(rel: str) -> bool:
    return rel.lower().startswith(_EMULATOR_REL + "/")


def walk_files(tree: Path) -> Iterator[str]:
    """``tree`` 下全部文件的相对路径（``/`` 分隔）。"""
    base = native_path(tree)
    for current, _dirs, files in os.walk(base):
        rel_dir = os.path.relpath(current, base)
        for name in files:
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            yield PurePosixPath(*Path(rel).parts).as_posix()


# ---- 解包与核对 ------------------------------------------------------------


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def package_entries(
    archive: zipfile.ZipFile, top_dir: str
) -> list[tuple[str, zipfile.ZipInfo]]:
    """校验整个包的条目表，返回 ``[(包内路径, 条目)]``（不含目录）。坏包抛 :class:`PackageError`。"""
    infos = archive.infolist()
    if len(infos) > UPDATE_MAX_ENTRIES:
        raise PackageError(f"包里的条目太多（{len(infos)} 个）")
    if sum(info.file_size for info in infos) > UPDATE_MAX_UNPACKED_BYTES:
        raise PackageError("包解开后太大")
    entries: list[tuple[str, zipfile.ZipInfo]] = []
    seen: set[str] = set()
    for info in infos:
        if _is_symlink(info):
            raise PackageError(f"包里有符号链接: {info.orig_filename}")
        rel = package_path(info.orig_filename, top_dir)
        if rel is None:
            continue
        key = rel.lower()
        if key in seen:
            raise PackageError(f"包里有重名的文件: {rel}")
        seen.add(key)
        entries.append((rel, info))
    if not any(is_emulator_file(rel) for rel, _ in entries):
        raise PackageError("包里没有 sdk\\emulator")
    return entries


def extract_package(
    archive_path: Path,
    dest: Path,
    *,
    top_dir: str,
    progress: Progress | None = None,
    cancelled: Cancelled | None = None,
) -> int:
    """把整个包解到 ``dest``（先清空），返回文件数。zip 的 CRC 在读完每个条目时由标准库核对。"""
    remove_tree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(native_path(archive_path)) as archive:
        entries = package_entries(archive, top_dir)
        total = sum(info.file_size for _, info in entries)
        done = 0
        for rel, info in entries:
            target = resolve_within(dest, rel, resolve_links=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, open(native_path(target), "wb") as sink:
                while block := source.read(_COPY_CHUNK):
                    if cancelled is not None and cancelled():
                        raise UpdateCancelled("已取消")
                    sink.write(block)
                    done += len(block)
                    if progress is not None:
                        progress(done, total)
    return len(entries)


def file_sha256(path: Path, on_bytes: Callable[[int], None] | None = None) -> str:
    digest = hashlib.sha256()
    with open(native_path(path), "rb") as handle:
        while block := handle.read(_COPY_CHUNK):
            digest.update(block)
            if on_bytes is not None:
                on_bytes(len(block))
    return digest.hexdigest()


def manifest_files(manifest: dict[str, Any]) -> dict[str, tuple[int, str]]:
    """清单的 ``files`` → ``{包内路径: (大小, sha256)}``；形状不对抛 :class:`PackageError`。"""
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise PackageError("清单里没有文件列表")
    result: dict[str, tuple[int, str]] = {}
    for rel, meta in files.items():
        if not isinstance(rel, str) or not isinstance(meta, dict):
            raise PackageError(f"清单里有写错的条目: {rel!r}")
        size, digest = meta.get("size"), str(meta.get("sha256") or "").lower()
        if (
            package_path(rel) != rel
            or not isinstance(size, int)
            or size < 0
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise PackageError(f"清单里有写错的条目: {rel!r}")
        result[rel] = (size, digest)
    return result


def verify_tree(
    tree: Path,
    manifest: dict[str, Any],
    *,
    progress: Progress | None = None,
    cancelled: Cancelled | None = None,
) -> list[str]:
    """拿清单逐文件比 ``tree``（大小 + SHA-256）。返回对不上的项，全对返回空列表。"""
    expected = manifest_files(manifest)
    actual = {
        rel.lower(): rel
        for rel in walk_files(tree)
        if rel.lower() != MODAVD_MANIFEST_FILE.lower()
    }
    wanted = {rel.lower(): rel for rel in expected}
    problems = [f"缺 {wanted[key]}" for key in sorted(wanted.keys() - actual.keys())]
    problems += [
        f"清单里没有 {actual[key]}" for key in sorted(actual.keys() - wanted.keys())
    ]
    total = sum(expected[wanted[key]][0] for key in wanted.keys() & actual.keys())
    done = 0

    def advance(count: int) -> None:
        nonlocal done
        done += count
        if cancelled is not None and cancelled():
            raise UpdateCancelled("已取消")
        if progress is not None:
            progress(done, total)

    for key in sorted(wanted.keys() & actual.keys()):
        rel = wanted[key]
        size, digest = expected[rel]
        path = tree / actual[key]
        if os.stat(native_path(path)).st_size != size:
            problems.append(f"{rel} 大小不对")
            advance(size)
            continue
        if file_sha256(path, advance) != digest:
            problems.append(f"{rel} 内容与清单不符")
    return problems


def check_package_manifest(manifest: dict[str, Any], target: ModAvdVersion) -> None:
    """包里清单的版本号要和要装的版本一致，写了 ``build`` 时要等于版本的第二段（构建号），
    ``platform`` 要和本机一致（``win-x64``）。

    带清单的都是新写法的版本，清单必须写 ``platform``：缺了、写的是别的平台都拒装。
    """
    declared = parse_version(manifest.get("version"))
    if declared != target:
        raise PackageError(
            f"包里清单的版本（{display_version(manifest.get('version'))}）和要装的版本"
            f"（{target.display}）不一致"
        )
    build = manifest.get("build")
    if build is not None and build != target.build:
        raise PackageError(
            f"包里清单的构建号（{build}）和版本 {target.display} 的构建号（{target.build}）不一致"
        )
    platform = manifest.get("platform")
    if not isinstance(platform, str) or not platform.strip():
        raise PackageError(
            f"包里清单没写 platform，确认不了是 {MODAVD_PLATFORM} 的包，不装"
        )
    if platform.strip().lower() != MODAVD_PLATFORM:
        raise PackageError(
            f"这是 {platform} 平台的包，本机要的是 {MODAVD_PLATFORM}，不装"
        )


def check_emulator(source: Path, target: ModAvdVersion) -> None:
    """``source`` 确是要装的那一版魔改 AVD 自编模拟器：关键文件齐、构建号对、有自编版标志。"""
    if not emulator_files_present(source):
        raise PackageError("包里的 sdk\\emulator 不完整（缺 emulator.exe 或 qemu）")
    build = read_mod_build_at(source)
    if build != target.build:
        raise PackageError(
            f"包里模拟器的构建号（{build if build is not None else '读不到'}）"
            f"和要装的 {target.display}（构建号 {target.build}）不一致"
        )
    if not qemu_has_self_built_mark(
        source / "qemu" / "windows-x86_64" / "qemu-system-x86_64-headless.exe"
    ):
        raise PackageError("包里的模拟器不是魔改 AVD 的自编版")


def verify_package(
    pkg: Path,
    target: ModAvdVersion,
    *,
    tag: str,
    progress: Progress | None = None,
    cancelled: Cancelled | None = None,
) -> str:
    """核对解开（或按区间拼好）的包：返回 ``manifest``（按清单逐文件核对）或 ``zip``（旧版包没有清单）。

    tag 是新写法（``vX.Y.Z``）的版本必须带清单，缺了就是包不对；只有旧 tag ``v37.2.10-masN`` 的包
    允许没有清单（那时只靠包的 SHA-256 与 zip CRC）。模拟器本身另核对构建号与自编版标志。
    """
    manifest = _read_json(pkg / MODAVD_MANIFEST_FILE) or None
    if manifest is None and requires_manifest(tag):
        raise PackageError(f"{tag} 的包里没有 {MODAVD_MANIFEST_FILE}，不装")
    if manifest is not None:
        check_package_manifest(manifest, target)
        problems = verify_tree(pkg, manifest, progress=progress, cancelled=cancelled)
        if problems:
            shown = "；".join(problems[:5])
            more = f" 等 {len(problems)} 项" if len(problems) > 5 else ""
            raise PackageError(f"包里的文件和清单对不上：{shown}{more}")
    check_emulator(pkg / "sdk" / "emulator", target)
    return "manifest" if manifest is not None else "zip"


def build_stage(root: str | Path, target: ModAvdVersion) -> Path:
    """把 ``pkg\\sdk\\emulator`` 改名成 ``stage\\emulator``（先再核对一遍它确是要装的那一版）。"""
    source = pkg_dir(root) / "sdk" / "emulator"
    check_emulator(source, target)
    stage = stage_emulator_dir(root)
    remove_tree(stage.parent)
    stage.parent.mkdir(parents=True)
    _rename(source, stage)
    return stage


# ---- 暂存的记录 --------------------------------------------------------------


def tree_fingerprint(*trees: tuple[Path, str]) -> str:
    """几个目录里全部文件的「路径 + 大小 + 修改时间」摘要。改名不改这些，删掉、换掉、半截都会变。"""
    lines: list[str] = []
    for base, prefix in trees:
        if not os.path.isdir(native_path(base)):
            continue
        for rel in walk_files(base):
            info = os.stat(native_path(base / rel))
            lines.append(f"{prefix}{rel}\0{info.st_size}\0{info.st_mtime_ns}")
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def staged_fingerprint(root: str | Path) -> str:
    """暂存的新版：``stage\\emulator`` 加上 ``pkg`` 里剩下的包内文件。"""
    return tree_fingerprint(
        (stage_emulator_dir(root), "sdk/emulator/"), (pkg_dir(root), "")
    )


def _staged_marker(root: str | Path) -> Path:
    return stage_emulator_dir(root).parent / "staged.json"


def begin_staging(root: str | Path, target: dict[str, Any]) -> None:
    """开始准备 ``target``：先把状态改成「正在准备」（不可安装），再动 ``pkg`` / ``stage``。

    之前拼好、还没装的那一版就此作废：准备到一半取消、失败、崩溃，都不会留下一个「可以安装」的
    半成品。
    """
    state = read_state(root)
    write_state(
        root,
        {
            "phase": PHASE_PREPARING,
            "target": target,
            "lastResult": state.get("lastResult"),
        },
    )
    _to_trash(root, pkg_dir(root), stage_emulator_dir(root).parent)
    purge_trash(root)


def finish_staging(
    root: str | Path, target: dict[str, Any], staged: dict[str, Any]
) -> dict[str, Any]:
    """核对通过、``stage`` 也拼好了：给暂存记下「路径 + 大小 + 修改时间」摘要（``stage`` 里的标记和
    ``state.json`` 各一份），这时才写 ``staged``。返回写进状态的 ``staged``。"""
    staged = {
        **staged,
        "version": target["version"],
        "fingerprint": staged_fingerprint(root),
    }
    write_json_atomic(
        _staged_marker(root),
        {"version": target["version"], "fingerprint": staged["fingerprint"]},
    )
    state = read_state(root)
    write_state(
        root,
        {
            "phase": PHASE_STAGED,
            "target": target,
            "staged": staged,
            "lastResult": state.get("lastResult"),
        },
    )
    return staged


def abort_staging(root: str | Path, reason: str) -> None:
    """准备没成（取消、失败）：丢掉暂存，状态回到空闲（下载的包留着，下次接着用）。"""
    state = read_state(root)
    if state.get("phase") not in (PHASE_PREPARING, PHASE_STAGED):
        return
    _to_trash(root, pkg_dir(root), stage_emulator_dir(root).parent)
    write_state(
        root,
        {
            "phase": PHASE_IDLE,
            "lastResult": {"action": "prepare", "ok": False, "error": reason},
        },
    )
    purge_trash(root)


def _check_staged(root: Path, state: dict[str, Any]) -> None:
    """换上前核对暂存确实是 ``state.json`` 记的那一版、核对过之后没被动过；对不上就丢掉暂存、拒装。"""
    target = (state.get("target") or {}).get("version")
    staged = state.get("staged") or {}
    marker = _read_json(_staged_marker(root))
    problem = ""
    if state.get("phase") != PHASE_STAGED or not target:
        problem = "还没有准备好的新版，请先下载"
    elif not os.path.isdir(native_path(stage_emulator_dir(root))):
        problem = "暂存的新版不见了，请重新下载"
    elif not (
        staged.get("version") == marker.get("version") == target
        and staged.get("fingerprint")
        and staged.get("fingerprint")
        == marker.get("fingerprint")
        == staged_fingerprint(root)
    ):
        problem = "暂存的新版和记录对不上（准备时可能被打断过），已丢掉，请重新下载"
    if not problem:
        return
    if state.get("phase") == PHASE_STAGED:
        abort_staging(root, problem)
    raise PackageError(problem)


# ---- 换上 ------------------------------------------------------------------

#: 读不到可执行文件路径时，按名字看可能在用模拟器文件的进程（小写前缀）。
_SUSPECT_PROCESS_PREFIXES = ("qemu-system", "emulator", "netsimd", "crashpad_handler")


def _real_path(path: str | Path, cache: dict[str, str] | None = None) -> str:
    """规范化成真实路径（解开目录链接、符号链接），用来比较；解不开就用绝对路径。"""
    key = str(path)
    if cache is not None and key in cache:
        return cache[key]
    try:
        value = os.path.normcase(os.path.realpath(key))
    except (OSError, ValueError):
        value = os.path.normcase(os.path.abspath(key))
    if cache is not None:
        cache[key] = value
    return value


def processes_using(root: str | Path) -> list[dict[str, Any]]:
    """可能在用 ``<根>\\sdk\\emulator`` 的进程。

    - 可执行文件在 ``sdk\\emulator`` 下的（emulator.exe、qemu、netsimd、crashpad_handler 都算）。两边都按
      真实路径比：根目录可能是经目录链接（junction）登记的，进程报的却是链接指向的真实路径；
    - 读不到可执行文件路径、名字又像模拟器的（``qemu-system*``、``emulator*``、``netsimd``、
      ``crashpad_handler``）也算上（``unknownPath``），宁可拒绝换上也不在它运行时换目录。
    """
    prefixes = {
        _real_path(emulator_dir(root)) + os.sep,
        os.path.normcase(os.path.abspath(emulator_dir(root))) + os.sep,
    }
    cache: dict[str, str] = {}
    found: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            info = dict(process.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        name = info.get("name") or ""
        exe = info.get("exe") or ""
        if exe:
            if any(_real_path(exe, cache).startswith(prefix) for prefix in prefixes):
                found.append({"pid": info["pid"], "name": name, "unknownPath": False})
        elif name.lower().startswith(_SUSPECT_PROCESS_PREFIXES):
            found.append({"pid": info["pid"], "name": name, "unknownPath": True})
    return found


def describe_processes(items: list[dict[str, Any]]) -> str:
    return "、".join(
        f"{item['name']}（pid {item['pid']}{'，读不到路径' if item.get('unknownPath') else ''}）"
        for item in items
    )


def ensure_not_in_use(root: str | Path, verb: str) -> None:
    """有进程可能在用 ``sdk\\emulator`` 就抛 :class:`SwapBlocked`。

    不能只靠改名失败来挡：10-23 实测，``sdk\\emulator`` 里有 exe 正在运行时目录照样改得了名
    （映像映射不挡改名），只有不带 FILE_SHARE_DELETE 打开的文件才会让改名失败。
    """
    busy = processes_using(root)
    if busy:
        raise SwapBlocked(
            f"还有程序在用模拟器文件：{describe_processes(busy)}。什么都没动，请先关掉所有实例和"
            f"这些程序再{verb}"
        )


def ensure_metadata_readable(root: str | Path) -> None:
    """``mas-avd.json`` 在却读不出时不动手：换上最后要改它，读不出就会拿空内容盖掉原文件。"""
    try:
        read_metadata_strict(root)
    except MetadataUnreadable as e:
        raise PackageError(f"{e}。先修好或删掉它再更新，什么都没动") from e


def plan_root_files(root: str | Path) -> dict[str, list[str]]:
    """包里 ``sdk\\emulator`` 以外的文件怎么换：``replace`` 覆盖、``delete`` 删（旧清单里有、新包里没有的；
    没有旧清单就不删）、``created`` 是原来没有、这次新建的（换上中途退回旧版时删掉）。"""
    root = Path(root)
    new = sorted(walk_files(pkg_dir(root)))
    new_keys = {rel.lower() for rel in new}
    old: list[str] = []
    old_manifest = _read_json(root / MODAVD_MANIFEST_FILE)
    if old_manifest:
        with suppress(PackageError):
            old = [
                rel for rel in manifest_files(old_manifest) if not is_emulator_file(rel)
            ] + [MODAVD_MANIFEST_FILE]
    delete = sorted(
        rel
        for rel in old
        if rel.lower() not in new_keys and os.path.isfile(native_path(root / rel))
    )
    created = [rel for rel in new if not os.path.lexists(native_path(root / rel))]
    return {"replace": new, "delete": delete, "created": created}


def _backup_root_files(root: Path, plan: dict[str, list[str]]) -> None:
    """换上前把要被覆盖 / 删掉的包内文件抄进 ``previous\\root``（已经抄过的不再抄）。"""
    backup = previous_dir(root) / "root"
    created = {rel.lower() for rel in plan["created"]}
    for rel in [*plan["replace"], *plan["delete"]]:
        if rel.lower() in created:
            continue
        source = root / rel
        target = backup / rel
        if os.path.isfile(native_path(source)) and not os.path.exists(
            native_path(target)
        ):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(native_path(source), native_path(target))


def _apply_root_files(root: Path, plan: dict[str, list[str]]) -> None:
    """``pkg`` 里写好的文件逐个替换过去，再删掉新包不要的。可以重跑（已经挪走的跳过）。"""
    source_root = pkg_dir(root)
    for rel in plan["replace"]:
        source = resolve_within(source_root, rel, resolve_links=False)
        if os.path.isfile(native_path(source)):
            replace_file(
                source,
                resolve_within(root, rel, resolve_links=False),
                clear_readonly=True,
            )
    for rel in plan["delete"]:
        target = resolve_within(root, rel, resolve_links=False)
        with suppress(FileNotFoundError):
            os.chmod(native_path(target), stat.S_IWRITE)
            os.unlink(native_path(target))


def _record_history(root: Path, entry: dict[str, Any]) -> None:
    """``mas-avd.json``：``components.emulator`` 写成现在的版本，``updateHistory`` 追加一条。

    读不出原文件时不写（换上前已核对过能读，这里只防中途被改坏），免得拿空内容盖掉。
    """
    try:
        data = read_metadata_strict(root)
    except MetadataUnreadable as e:
        logger.warning(f"{e}，这次不记更新记录")
        return
    history = data.get("updateHistory")
    history = (
        [item for item in history if isinstance(item, dict)]
        if isinstance(history, list)
        else []
    )
    if history and all(
        history[-1].get(key) == entry.get(key) for key in ("action", "from", "to")
    ):
        # 崩溃恢复把同一次换上补完时不重复记
        return
    history.append(entry)
    components = data.get("components")
    components = dict(components) if isinstance(components, dict) else {}
    components["emulator"] = entry["to"]
    data["components"] = components
    data["updateHistory"] = history[-UPDATE_HISTORY_KEEP:]
    write_metadata(root, data)


# ---- 丢弃：先改名、写好状态、再删 ----------------------------------------------


def _trash_dir(root: str | Path) -> Path:
    return update_dir(root) / "trash"


def _to_trash(root: str | Path, *paths: Path) -> None:
    """把要删的目录先改名进 ``trash``（一步完成，不会删到一半）。真正删在写好状态之后（:func:`purge_trash`）。"""
    trash = _trash_dir(root)
    for path in paths:
        if os.path.lexists(native_path(path)):
            trash.mkdir(parents=True, exist_ok=True)
            _rename(path, trash / f"{time.time_ns()}-{path.name}")


def _tidy_up(root: str | Path, *paths: Path) -> None:
    """收尾时顺手丢掉不再要的目录：逐个改名进 ``trash``，改不动的（被不带共享删除地打开着，比如杀软
    在扫）只记日志、留到下次清理，不影响这次的结果和状态。"""
    for path in paths:
        try:
            _to_trash(root, path)
        except OSError as e:
            logger.warning(f"{path} 这次挪不走（{e.strerror or e}），留着下次再清理")


_MOUNT_POINT_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def _remove_best_effort(path: Path, failed: list[str]) -> None:
    """删 ``path``（文件或目录）：删不掉的项记进 ``failed`` 后跳过，其余照删。

    不跟随目录链接（符号链接、junction 只删链接本身）。只读文件先去掉只读再删。
    """
    native = native_path(path)
    try:
        info = os.lstat(native)
    except FileNotFoundError:
        return
    except OSError as e:
        failed.append(f"{path}（{e.strerror or e}）")
        return
    is_link = stat.S_ISLNK(info.st_mode) or (
        getattr(info, "st_reparse_tag", 0) == _MOUNT_POINT_TAG
    )
    if stat.S_ISDIR(info.st_mode) and not is_link:
        try:
            names = os.listdir(native)
        except OSError as e:
            failed.append(f"{path}（{e.strerror or e}）")
            return
        before = len(failed)
        for name in names:
            _remove_best_effort(path / name, failed)
        if len(failed) > before:
            return  # 里面有删不掉的，目录本身肯定删不掉，不重复记
        removers = [os.rmdir]
    elif is_link:
        # 目录链接要 rmdir，文件链接要 unlink；不分辨，两种都试
        removers = [os.unlink, os.rmdir]
    else:
        removers = [os.unlink]
    error: OSError | None = None
    for remove in removers:
        for attempt in range(2):
            try:
                remove(native)
                return
            except FileNotFoundError:
                return
            except PermissionError as e:
                error = e
                if attempt == 0:
                    with suppress(OSError):
                        os.chmod(native, stat.S_IWRITE)
            except OSError as e:
                error = e
                break
    failed.append(f"{path}（{getattr(error, 'strerror', None) or error}）")


def purge_trash(root: str | Path) -> None:
    """删 ``trash``：逐项尽力删，删不掉的（文件被占用、杀软在扫）跳过并记日志，其余照删；剩下的下次再删。"""
    trash = _trash_dir(root)
    failed: list[str] = []
    _remove_best_effort(trash, failed)
    if failed:
        shown = "；".join(failed[:5]) + (
            f" 等 {len(failed)} 项" if len(failed) > 5 else ""
        )
        logger.warning(f"清理 {trash} 有删不掉的，先跳过、下次再删：{shown}")


def trash_bytes(root: str | Path) -> int:
    """``trash`` 里还占着多少字节（读不到的不算）。"""
    total = 0
    for folder, _dirs, files in os.walk(native_path(_trash_dir(root))):
        for name in files:
            with suppress(OSError):
                total += os.lstat(os.path.join(folder, name)).st_size
    return total


def _finish_install(root: Path, state: dict[str, Any]) -> None:
    """换上的收尾：记 ``mas-avd.json``，写状态（空闲），再把旧版（``previous``：换下来的 ``sdk\\emulator``
    与被替换的包内文件备份）、暂存与下载改名进 ``trash``，最后才真删。

    旧版留到写完状态才挪走：在那之前 MAS 退出，:func:`recover` 还能按 ``previous`` 补完或退回。这些
    挪不走（比如杀软正开着下载的包）不算失败：新版已经换上，只记日志、留到下次清理（:func:`_tidy_up`）。
    """
    target = state["target"]
    _record_history(
        root,
        {
            "action": "update",
            "at": datetime.now().isoformat(timespec="seconds"),
            "from": state.get("from") or "",
            "to": target["version"],
            "source": target.get("source", ""),
            "asset": target.get("asset", {}).get("name", ""),
        },
    )
    write_state(
        root,
        {
            "phase": PHASE_IDLE,
            "lastResult": {
                "action": "update",
                "ok": True,
                "version": target["version"],
            },
        },
    )
    # 装好了，下载的包也不再要
    _tidy_up(
        root,
        previous_dir(root),
        pkg_dir(root),
        stage_emulator_dir(root).parent,
        download_dir(root),
    )
    purge_trash(root)


def _back_to_staged(root: Path, state: dict[str, Any]) -> None:
    """第一次改名没成或已复原（``sdk\\emulator`` 还是旧版）：写回「待安装」，再丢掉这次做的包内文件备份。"""
    state.update(phase=PHASE_STAGED, swap=None, plan=None)
    write_state(root, state)
    _tidy_up(root, previous_dir(root))
    purge_trash(root)


def swap_in(root: str | Path) -> str:
    """把 ``staged`` 的新版换上。返回换上的版本号。

    换上前核对暂存确是 ``state.json`` 记的那一版（不对就丢掉暂存、拒装）、``mas-avd.json`` 读得出、
    没有程序在用 ``sdk\\emulator``；第一次改名失败抛 :class:`SwapBlocked`，什么都没动、还是「待安装」。
    调用方要先确认没有实例在跑、在开机（只走 MAS 的 close 关实例，不硬杀）。
    """
    root = Path(root)
    state = read_state(root)
    _check_staged(root, state)
    ensure_metadata_readable(root)
    ensure_not_in_use(root, "装")
    current = local_version(root)
    # 上次收尾没挪走的旧版（不在换上中，留着没用）先丢掉，免得和这次的备份混在一起
    try:
        _to_trash(root, previous_dir(root))
    except OSError as e:
        raise SwapBlocked(
            f"上次留下、要删的旧版文件还被占用（{e.strerror or e}），什么都没动，稍后再试"
        ) from e
    purge_trash(root)
    plan = plan_root_files(root)
    _backup_root_files(root, plan)
    state.update(
        phase=PHASE_SWAPPING,
        plan=plan,
        swap={"step": "begin"},
        **{"from": str(current) if current else ""},
    )
    write_state(root, state)

    old_target = previous_dir(root) / "emulator"
    old_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _rename(emulator_dir(root), old_target)
    except OSError as e:
        _back_to_staged(root, state)
        raise SwapBlocked(
            f"模拟器文件还在被占用（{e.strerror or e}），什么都没动。请先关掉所有实例和用到"
            "模拟器的程序再装"
        ) from e
    try:
        state["swap"] = {"step": "old_moved"}
        write_state(root, state)
        try:
            _rename(stage_emulator_dir(root), emulator_dir(root))
        except OSError as e:
            _rename(old_target, emulator_dir(root))
            _back_to_staged(root, state)
            raise SwapBlocked(f"换上新版失败，已恢复原样: {e}") from e
        state["swap"] = {"step": "new_moved"}
        write_state(root, state)
        _apply_root_files(root, plan)
        _finish_install(root, state)
    except SwapBlocked:
        raise
    except Exception as e:
        # 改过名之后出错（写 state.json、换包内文件……）：当场按崩溃恢复的规则补完或退回，不留半套
        raise PackageError(f"换上中途出错（{e}）；{_recover_now(root)}") from e
    logger.info(
        f"{root} 的魔改 AVD 已从 {display_version(state.get('from')) or '旧版'} 换成 "
        f"{display_version(state['target']['version'])}"
    )
    return state["target"]["version"]


def _recover_now(root: Path) -> str:
    try:
        return recover(root) or "状态已经完整"
    except Exception as error:  # noqa: BLE001 - 恢复也失败时交给下次启动再试
        logger.opt(exception=True).error(f"{root} 更新出错后当场恢复也失败: {error}")
        return f"当场恢复也失败了（{error}），重启 MAS 时会再按记录恢复"


def _restore_root_files(root: Path, plan: dict[str, list[str]]) -> None:
    """换上到一半退回旧版：删掉这次新建的包内文件，被覆盖 / 删掉的从 ``previous\\root`` 还原。"""
    backup = previous_dir(root) / "root"
    for rel in plan.get("created", []):
        target = resolve_within(root, rel, resolve_links=False)
        with suppress(FileNotFoundError):
            os.chmod(native_path(target), stat.S_IWRITE)
            os.unlink(native_path(target))
    for rel in [*plan.get("replace", []), *plan.get("delete", [])]:
        source = backup / rel
        if os.path.isfile(native_path(source)):
            replace_file(
                source,
                resolve_within(root, rel, resolve_links=False),
                clear_readonly=True,
            )


# ---- 崩溃恢复 --------------------------------------------------------------


def recover(root: str | Path) -> str | None:
    """MAS 启动时收拾上次没做完的事。返回做了什么（给日志），没事返回 ``None``。

    - 准备新版到一半（``preparing``）：丢掉暂存，回到空闲（下载的包还在）。
    - 换上中、``sdk\\emulator`` 不在了：``stage`` 已核对过 → 把 ``stage`` 改名过去、补完；否则把
      ``previous\\emulator`` 改回去、包内文件从 ``previous\\root`` 还原，回到空闲。两次改名都做完了只差
      包内文件 → 补完。第一次改名都没成 → 回到「待安装」。
    - 不在换上中却还有 ``previous``（换上收尾写完状态、还没挪走旧版就退出了，或当时挪不走）：丢掉。
    - 上次没删完的 ``trash`` 再删一次。
    """
    root = Path(root)
    state = read_state(root)
    phase = state.get("phase")
    current = emulator_dir(root)
    old = previous_dir(root) / "emulator"
    stage = stage_emulator_dir(root)
    present = os.path.isdir(native_path(current))
    done: str | None = None
    if phase == PHASE_PREPARING:
        abort_staging(root, "上次准备新版没做完")
        done = "上次准备新版没做完，已丢掉暂存（下载的包还在）"
    elif phase == PHASE_SWAPPING:
        step = (state.get("swap") or {}).get("step")
        verified = bool((state.get("staged") or {}).get("verified"))
        if not present:
            if verified and os.path.isdir(native_path(stage)):
                _rename(stage, current)
                _apply_root_files(root, state["plan"])
                _finish_install(root, state)
                return f"补完了上次没装完的更新（{display_version(state['target']['version'])}）"
            if os.path.isdir(native_path(old)):
                _rename(old, current)
                _restore_root_files(root, state.get("plan") or {})
                write_state(
                    root,
                    {
                        "phase": PHASE_IDLE,
                        "lastResult": {
                            "action": "update",
                            "ok": False,
                            "error": "上次更新没装完，已退回旧版",
                        },
                    },
                )
                _tidy_up(root, previous_dir(root), pkg_dir(root), stage.parent)
                purge_trash(root)
                return "上次更新没装完，已退回旧版"
            return "sdk\\emulator 不见了，也没有可用的新版或旧版"
        if step == "new_moved" or (
            not os.path.isdir(native_path(stage)) and os.path.isdir(native_path(old))
        ):
            _apply_root_files(root, state["plan"])
            _finish_install(root, state)
            return f"补完了上次没装完的更新（{display_version(state['target']['version'])}）"
        _back_to_staged(root, state)
        return "上次更新还没开始换，已回到「待安装」"
    if os.path.lexists(native_path(previous_dir(root))):
        _tidy_up(root, previous_dir(root))
        done = f"{done}；丢掉了上次没删掉的旧版" if done else "丢掉了上次没删掉的旧版"
    if os.path.lexists(native_path(_trash_dir(root))):
        purge_trash(root)
    return done


__all__ = [
    "PHASE_IDLE",
    "PHASE_PREPARING",
    "PHASE_STAGED",
    "PHASE_SWAPPING",
    "PackageError",
    "SwapBlocked",
    "UpdateCancelled",
    "abort_staging",
    "begin_staging",
    "build_stage",
    "check_emulator",
    "check_package_manifest",
    "describe_processes",
    "download_dir",
    "emulator_dir",
    "ensure_metadata_readable",
    "extract_package",
    "file_sha256",
    "finish_staging",
    "is_emulator_file",
    "manifest_files",
    "package_entries",
    "package_path",
    "pkg_dir",
    "plan_root_files",
    "previous_dir",
    "processes_using",
    "purge_trash",
    "read_state",
    "recover",
    "remove_tree",
    "stage_emulator_dir",
    "staged_fingerprint",
    "swap_in",
    "trash_bytes",
    "tree_fingerprint",
    "update_dir",
    "verify_package",
    "verify_tree",
    "walk_files",
    "write_json_atomic",
    "write_state",
]
