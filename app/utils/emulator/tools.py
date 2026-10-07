#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 MoeSnowyFox
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


import asyncio
import os
import re
import time
from dataclasses import dataclass, field

from app.utils.platform import IS_WINDOWS
from app.utils.platform import window as platform_window

if IS_WINDOWS:
    import winreg
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.utils import get_logger
from app.utils.constants import EMULATOR_PATH_BOOK

logger = get_logger("模拟器管理工具")


def _normalize_fs_path_candidate(raw: str) -> str:
    """规整注册表/服务 ImagePath（如 \\??\\、\\?\\、\\SystemRoot）为本地路径。"""
    s = str(raw).strip().strip('"').strip("'")
    if not s:
        return ""
    # \??\C:\... ；\??\UNC\server\share\... 去掉前缀后 UNC 仍缺前导 \\，需补全
    if len(s) >= 4 and s.startswith("\\??\\"):
        rest = s[4:]
        ul = rest.upper()
        if ul.startswith("UNC\\"):
            rest = "\\\\" + rest[4:].lstrip("\\")
        s = rest
    # \\?\C:\... 扩展路径前缀（去掉 \\?\ 保留盘符路径）
    if s.startswith("\\\\?\\") and len(s) >= 7 and s[5] == ":":
        s = s[4:]
    # \SystemRoot\...（服务镜像偶见）
    sr = "\\SystemRoot"
    if s[: len(sr)].lower() == sr.lower() and (
        len(s) == len(sr) or s[len(sr) : len(sr) + 1] in ("\\", "/")
    ):
        root = os.environ.get("SystemRoot", r"C:\Windows").rstrip("\\/")
        s = root + s[len(sr) :]
    return s.strip()


def _emulator_brand_keyword_rows() -> List[Tuple[str, List[str]]]:
    return [
        (emulator_type, cfg.get("registry_display_keywords") or [])
        for emulator_type, cfg in EMULATOR_PATH_BOOK.items()
    ]


def _find_manager_exe_in_dir(
    directory: Path, executable_names: List[str]
) -> Optional[Path]:
    for name in executable_names:
        if not name:
            continue
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _primary_executable_name(executable_names: List[str]) -> str:
    return executable_names[0] if executable_names else ""


def _find_manager_exe_near_side_exe(
    path_obj: Path,
    executable_names: List[str],
    *,
    max_parent_levels: int = 2,
) -> Optional[Path]:
    """自旁路 exe 所在目录向上有限层查找主管理器（executables[0]，仅 is_file，不 iterdir）。"""
    if path_obj.suffix.lower() != ".exe" or not executable_names:
        return None

    primary = _primary_executable_name(executable_names).lower()
    if path_obj.name.lower() == primary and path_obj.is_file():
        return path_obj

    current = path_obj.parent
    for _ in range(max_parent_levels + 1):
        hit = _find_manager_exe_in_dir(current, executable_names)
        if hit and hit.name.lower() == primary:
            return hit
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# MuMu 卸载表旁路：自 uninstall.exe 所在目录向上最多 2 层，按序尝试相对路径
MUMU_RELATIVE_EXECUTABLE_PATTERNS = (
    ("MuMuManager.exe",),
    ("nx_main", "MuMuManager.exe"),
    ("shell", "MuMuManager.exe"),
)


def _iter_registry_path_variants(path: str):
    """SOFTWARE 路径同时尝试 WOW6432Node 镜像，与原先 _search_from_registry 行为一致。"""
    yielded = set()
    candidates = [path]
    software_prefix = "SOFTWARE\\"
    wow_prefix = "SOFTWARE\\WOW6432Node\\"
    p_upper = path.upper()
    if p_upper.startswith(software_prefix) and not p_upper.startswith(wow_prefix):
        candidates.append(path.replace(software_prefix, wow_prefix, 1))
    if p_upper.startswith(wow_prefix):
        candidates.append(path.replace(wow_prefix, software_prefix, 1))
    for candidate in candidates:
        key = candidate.upper()
        if key in yielded:
            continue
        yielded.add(key)
        yield candidate


def _is_uninstall_registry_root(path: str) -> bool:
    u = path.upper().rstrip("\\")
    return u.endswith(r"MICROSOFT\WINDOWS\CURRENTVERSION\UNINSTALL")


def _match_registry_display_keywords(display_name: str, keywords: List[str]) -> bool:
    if not keywords:
        return True
    n = display_name.lower()
    return any(k.lower() in n for k in keywords if k)


def _read_registry_uninstall_string(subkey) -> str:
    with suppress(FileNotFoundError, OSError):
        value, _ = winreg.QueryValueEx(subkey, "UninstallString")
        if isinstance(value, str) and value.strip():
            s = value.strip()
            return _extract_path_from_command(s) or s
    return ""


def _unique_uninstall_roots_from_book() -> List[str]:
    """从 EMULATOR_PATH_BOOK 去重收集卸载表根路径（保持首次出现顺序）。"""
    seen: Set[str] = set()
    out: List[str] = []
    for cfg in EMULATOR_PATH_BOOK.values():
        for p in cfg.get("registry_paths") or []:
            if "MICROSOFT\\WINDOWS\\CURRENTVERSION\\UNINSTALL" not in p.upper():
                continue
            u = p.upper()
            if u in seen:
                continue
            seen.add(u)
            out.append(p)
    return out


def _collect_uninstall_paths_by_emulator_type() -> Dict[str, List[str]]:
    """单遍枚举卸载表：每个子键只读一次 DisplayName / UninstallString，再按品牌关键词分发。"""

    if not IS_WINDOWS:
        return {}

    acc: Dict[str, List[str]] = defaultdict(list)
    roots = _unique_uninstall_roots_from_book()
    if not roots:
        return {}

    for reg_path in roots:
        for candidate_path in _iter_registry_path_variants(reg_path):
            if not _is_uninstall_registry_root(candidate_path):
                continue
            # 已安装模拟器卸载项均在 HKLM；跳过 HKCU 以减少整树枚举
            for hive in (winreg.HKEY_LOCAL_MACHINE,):
                with suppress(FileNotFoundError, OSError):
                    with winreg.OpenKey(hive, candidate_path) as key:
                        i = 0
                        while True:
                            try:
                                sub = winreg.EnumKey(key, i)
                                i += 1
                            except OSError:
                                break
                            with suppress(FileNotFoundError, OSError):
                                with winreg.OpenKey(key, sub) as subkey:
                                    try:
                                        dn, _ = winreg.QueryValueEx(
                                            subkey, "DisplayName"
                                        )
                                    except OSError:
                                        continue
                                    if not isinstance(dn, str):
                                        continue
                                    matched: List[str] = []
                                    for (
                                        emulator_type,
                                        kw,
                                    ) in _emulator_brand_keyword_rows():
                                        if _match_registry_display_keywords(dn, kw):
                                            matched.append(emulator_type)
                                    if not matched:
                                        continue
                                    raw = _read_registry_uninstall_string(subkey)
                                    if not raw:
                                        continue
                                    for emulator_type in matched:
                                        acc[emulator_type].append(raw)

    return {et: _dedupe_path_strings(paths) for et, paths in acc.items()}


def search_all_emulators() -> List[Dict[str, str]]:
    """搜索所有支持的模拟器：仅卸载表 UninstallString 路径（全同步实现）。"""

    logger.info("开始搜索所有模拟器, mode=registry_uninstall")
    found_emulators = []
    found_emulator_paths = set()

    paths_by_type = _collect_uninstall_paths_by_emulator_type()

    for emulator_type, config in EMULATOR_PATH_BOOK.items():
        try:
            for raw_path in paths_by_type.get(emulator_type, []):
                manager_key = _resolve_uninstall_exe_to_manager(
                    raw_path,
                    config,
                    emulator_type,
                    source="registry_uninstall",
                )
                if not manager_key:
                    continue
                dedupe_key = manager_key.lower()
                if dedupe_key in found_emulator_paths:
                    continue
                found_emulator_paths.add(dedupe_key)
                found_emulators.append(
                    {
                        "type": emulator_type,
                        "path": manager_key,
                        "name": f"{config['name']} ({manager_key})",
                    }
                )
                logger.info(f"找到{config['name']}: {manager_key}")
        except Exception as e:
            logger.warning(f"搜索{config['name']}时出错: {e}")

    logger.info(f"搜索完成，共找到 {len(found_emulators)} 个模拟器")
    return found_emulators


def _resolve_uninstall_exe_to_manager(
    candidate_path: str,
    config: Dict,
    emulator_type: str,
    source: str,
) -> Optional[str]:
    """卸载表 UninstallString 一次解析到主管理器 exe（避免目录校验与二次全盘查找）。"""

    candidate_path = _normalize_fs_path_candidate(candidate_path)
    if not candidate_path:
        return None

    path_obj = Path(candidate_path)
    if not path_obj.is_file():
        return None

    executable_names = config.get("executables") or []
    primary = _primary_executable_name(executable_names)
    if primary and path_obj.name.lower() == primary.lower():
        logger.info(f"{config['name']} 通过{source}命中主管理器: {path_obj}")
        return path_obj.as_posix()

    manager: Optional[Path] = None
    if emulator_type == "mumu":
        manager = _find_mumu_manager_from_base(path_obj.parent)
    elif emulator_type in ("ldplayer", "nox", "bluestacks", "memu"):
        parent_levels = 3 if emulator_type == "memu" else 2
        manager = _find_manager_exe_near_side_exe(
            path_obj,
            executable_names,
            max_parent_levels=parent_levels,
        )

    if manager:
        logger.info(f"{config['name']} 通过{source}由旁路 exe 推断主管理器: {manager}")
        return manager.as_posix()

    logger.debug(f"{config['name']} 通过{source}未解析到主管理器: {candidate_path}")
    return None


def _dedupe_path_strings(paths: List[str]) -> List[str]:
    """路径去重（大小写不敏感），保留首次出现的大小写"""
    dedup: List[str] = []
    seen: Set[str] = set()
    for path in paths:
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(path)
    return dedup


def _find_mumu_manager_from_base(base_path: Path) -> Optional[Path]:
    """自基准目录及最多 2 层父目录，按 MUMU_RELATIVE_EXECUTABLE_PATTERNS 找首个存在的 MuMuManager。"""
    candidate_bases: List[Path] = [base_path]
    current = base_path
    for _ in range(2):
        parent = current.parent
        if parent == current:
            break
        candidate_bases.append(parent)
        current = parent

    seen: Set[str] = set()
    for candidate_base in candidate_bases:
        for pattern in MUMU_RELATIVE_EXECUTABLE_PATTERNS:
            candidate = candidate_base.joinpath(*pattern)
            key = candidate.as_posix().lower()
            if key in seen:
                continue
            seen.add(key)
            if candidate.is_file():
                return candidate
    return None


# 未加引号时，从命令行中提取「盘符:\...\文件名.扩展名」（贪婪，支持空格与 / 或 \）
_CMDLINE_PATH_WITH_EXT = re.compile(
    r"([A-Za-z]:[/\\](?:[^/\\:*?\"<>|\r\n]+[/\\])*[^/\\:*?\"<>|\r\n]+"
    r"\.(?:exe|cmd|bat|lnk|msi))(?:,\d+)?",
    re.IGNORECASE,
)


def _strip_icon_index_suffix(path: str) -> str:
    return re.sub(r",\d+\s*$", "", path).strip()


def _merge_unquoted_path_tokens(s: str) -> str:
    """无引号且路径含空格时，合并 token 直至拼成存在的文件路径。"""
    parts = s.split()
    if not parts:
        return ""
    if not re.match(r"^[A-Za-z]:[/\\]", parts[0]):
        return ""
    candidate = _strip_icon_index_suffix(parts[0])
    if Path(candidate).is_file():
        return candidate
    for extra in parts[1:]:
        if extra.startswith("/") or extra.startswith("-"):
            break
        trial = _strip_icon_index_suffix(f"{candidate} {extra}")
        if Path(trial).is_file():
            return trial
        candidate = f"{candidate} {extra}"
    final = _strip_icon_index_suffix(candidate)
    return final if Path(final).is_file() else ""


def _extract_path_from_command(value: str) -> str:
    """从注册表命令行字段抽取 exe/目录路径，并去掉图标索引尾缀（如 ,0）。"""

    if not value:
        return ""
    s = str(value).strip()
    if not s:
        return ""

    # 优先取第一个引号内片段
    m = re.match(r'^\s*"([^"]+)"', s)
    if m:
        extracted = _strip_icon_index_suffix(m.group(1).strip())
        return extracted

    # 未加引号：贪婪匹配带扩展名的 Windows 路径（含空格、正斜杠/反斜杠、.msi）
    m = _CMDLINE_PATH_WITH_EXT.search(s)
    if m:
        return _strip_icon_index_suffix(m.group(1).strip())

    merged = _merge_unquoted_path_tokens(s)
    if merged:
        return merged

    # 兜底：取第一个 token（到空格为止）
    token = _strip_icon_index_suffix(s.split(" ", 1)[0].strip())
    return token


def find_emulator_manager_path(
    input_path: str, emulator_type: str, max_levels: int = 3
) -> str:
    """从给定路径搜索主管理器 exe 完整路径，未找到则返回原路径（配置校正等场景）。"""

    if not input_path:
        logger.warning(f"输入路径无效: {input_path}")
        return input_path
    input_path_obj = Path(input_path)
    if not input_path_obj.exists():
        logger.warning(f"输入路径无效: {input_path}")
        return input_path

    if emulator_type not in EMULATOR_PATH_BOOK:
        logger.warning(f"不支持的模拟器类型: {emulator_type}")
        return input_path

    config = EMULATOR_PATH_BOOK[emulator_type]
    executables = config["executables"]

    if input_path_obj.is_file():
        if emulator_type == "mumu":
            manager = _find_mumu_manager_from_base(input_path_obj.parent)
            if manager:
                return str(manager)
        else:
            parent_levels = 3 if emulator_type == "memu" else max_levels
            manager = _find_manager_exe_near_side_exe(
                input_path_obj,
                executables,
                max_parent_levels=parent_levels,
            )
            if manager:
                return str(manager)

    path_obj = input_path_obj if input_path_obj.is_dir() else input_path_obj.parent

    hit = _find_manager_exe_in_dir(path_obj, executables)
    if hit:
        return str(hit)

    current = path_obj
    for level in range(max_levels):
        parent = current.parent
        if parent == current:
            break
        parent_hit = _find_manager_exe_in_dir(parent, executables)
        if parent_hit:
            logger.debug(f"父目录(第{level + 1}层)直接包含主程序: {parent_hit}")
            return str(parent_hit)
        current = parent

    with suppress(PermissionError):
        for subdir in path_obj.iterdir():
            if subdir.is_dir():
                sub_hit = _find_manager_exe_in_dir(subdir, executables)
                if sub_hit:
                    return str(sub_hit)

    logger.warning(f"未能找到{config['name']}主程序，返回原路径: {input_path}")
    return input_path


@dataclass
class AudioMuteRecord:
    """一次启动的模拟器音频静音记录。

    ``states`` 只含已找到音频会话的 pid（记录到它们静音前的状态）；音频会话是
    进程首次发声时才建立的，尚未出现的 pid 由 ``task`` 指向的后台任务继续等待。
    """

    pids: Set[int]
    states: Dict[int, bool] = field(default_factory=dict)
    task: Optional[asyncio.Task] = None
    timeout: float = 600.0
    poll_interval: float = 5.0

    def pending(self) -> Set[int]:
        return self.pids - self.states.keys()


async def _watch_and_mute(record: AudioMuteRecord) -> None:
    """轮询等待目标进程的音频会话出现，出现即静音并记录先前状态。

    游戏引擎往往在启动完成后数分钟才首次发声，音频会话届时才建立；按
    ``poll_interval`` 重试到 ``timeout`` 为止，超时放弃（说明那条进程没在出声）。
    被取消时先让进行中的一轮把结果落进记录再退出，保证这一轮刚静音上的会话不漏还原。
    """
    try:
        from app.utils.platform.windows import audio
    except ImportError:
        logger.warning("音频静音组件不可用（缺少 pycaw），跳过静音")
        return

    deadline = time.monotonic() + record.timeout
    while time.monotonic() < deadline:
        mute_task = asyncio.create_task(audio.mute_once(record.pending()))
        try:
            states = await asyncio.shield(mute_task)
        except asyncio.CancelledError:
            # 取消落在枚举进行中：线程无法中断，等这一轮跑完并把结果落进记录再传播，
            # 否则它刚静音上的会话会因结果被丢弃而漏还原
            with suppress(Exception):
                record.states.update(await mute_task)
            raise
        if states:
            record.states.update(states)
            logger.info(f"已静音音频会话: {sorted(states)}")
            if not record.pending():
                return
        await asyncio.sleep(record.poll_interval)
    logger.warning(f"等待音频会话超时，未能静音: {sorted(record.pending())}")


async def apply_launch_audio_mute(
    states_store: Dict[str, AudioMuteRecord],
    idx: str,
    resolve_pids: Callable[[], Awaitable[List[int]]],
) -> None:
    """静默模式下静音全新启动实例的声音，把记录存入 ``states_store``。

    只对实例由本次 ``open()`` 全新拉起的情况调用——已在线早退的实例可能是用户手动
    开着的，不能动。PID 查询完成后，音频会话由后台任务跟随（见
    :class:`AudioMuteRecord`），启动流程不等待会话建立。PID 查询只在开启静默时
    执行，查询与静音准备的任何失败只记日志，不影响启动。
    """
    if not IS_WINDOWS:
        return
    try:
        from app.core import Config

        if not Config.get("Function", "IfSilence"):
            return
        pids = await resolve_pids()
        if not pids:
            return
        old = states_store.get(idx)
        if old is not None and old.task is not None and not old.task.done():
            old.task.cancel()
        record = AudioMuteRecord(pids=set(pids))
        record.task = asyncio.create_task(_watch_and_mute(record))
        states_store[idx] = record
        logger.debug(f"开始跟随静音模拟器 {idx} 的音频进程: {sorted(record.pids)}")
    except Exception:  # noqa: BLE001 - 音频辅助步骤失败不应阻断模拟器启动
        logger.opt(exception=True).warning(f"模拟器 {idx} 音频静音失败，将继续运行")


async def restore_audio_before_close(
    states_store: Dict[str, AudioMuteRecord], idx: str
) -> None:
    """关闭实例前还原 ``apply_launch_audio_mute`` 的静音状态并停掉跟随任务。

    实例已被外部关掉时音频会话随之销毁，等价跳过；极端时序下飞行中的一轮静音可能
    落在还原之后，此时实例已在关闭流程里，会话随进程销毁。失败只记日志，不阻断
    关闭流程。
    """
    if not IS_WINDOWS:
        return
    record = states_store.pop(idx, None)
    if record is None:
        return
    if record.task is not None and not record.task.done():
        record.task.cancel()
        try:
            await record.task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - 跟随任务的意外异常不应阻断关闭流程
            logger.opt(exception=True).warning("音频静音跟随任务异常退出")
    if not record.states:
        return
    try:
        from app.utils.platform.windows import audio
    except ImportError:
        logger.warning("音频静音组件不可用（缺少 pycaw），跳过还原")
        return
    restored = await audio.restore_processes(record.states)
    if restored:
        logger.info(f"已还原模拟器 {idx} 的音频静音状态: {sorted(restored)}")
    else:
        logger.debug(f"模拟器 {idx} 的音频进程已退出，无需还原静音状态")


_WINDOW_RESOLVE_TIMEOUT = 1.0
"""解析实例主窗口句柄的上限（秒）：实例刚启动时窗口可能还没建出来"""

_WINDOW_POLL_INTERVAL = 0.5
"""窗口句柄重读与可见性轮询的间隔（秒）"""


async def resolve_main_window(
    idx: str, resolve: Callable[[], Awaitable[int | None]]
) -> int:
    """在 :data:`_WINDOW_RESOLVE_TIMEOUT` 内反复取该实例的主窗口句柄，取不到报错。

    ``resolve`` 每次给出一个候选句柄（拿不到返回 None），窗口可能等实例起来才
    建出来，所以按 :data:`_WINDOW_POLL_INTERVAL` 重试到超时为止；解析不到就明确
    报错，不空转到 ``MaxWaitTime``（#948：把 PID 当句柄传的判据恒为假，只会白等到超时）。
    """

    deadline = time.monotonic() + _WINDOW_RESOLVE_TIMEOUT
    while True:
        hwnd = await resolve()
        if hwnd:
            return hwnd
        if time.monotonic() >= deadline:
            raise RuntimeError(f"未找到设备{idx}的主窗口，无法切换窗口可见性")
        await asyncio.sleep(_WINDOW_POLL_INTERVAL)


async def apply_window_visibility(
    hwnd: int, idx: str, is_visible: bool, max_wait: float
) -> None:
    """按 ``max_wait`` 轮询切换 ``hwnd`` 的可见性，超时抛 ``RuntimeError``。

    老板键不带实例信息，多开时会把别的实例一起翻过去，所以直接对该实例自己的窗口
    句柄调 ``ShowWindow``；单次切换失败只记日志，接着重试。
    """

    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        if platform_window.is_visible(hwnd) == is_visible:
            return
        try:
            if is_visible:
                platform_window.show_window(hwnd)
            else:
                platform_window.hide_window(hwnd)
        except Exception as e:
            logger.error(f"切换设备{idx}窗口可见性失败: {e}")
        await asyncio.sleep(_WINDOW_POLL_INTERVAL)

    raise RuntimeError(f"{'显示' if is_visible else '隐藏'}设备{idx}窗口超时")
