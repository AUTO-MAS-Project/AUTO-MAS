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

"""模拟器版本探测。

Emulator 2.0 只接受特定大版本，添加路径时必须先探测。探测结果要缓存在配置里——
``get_status()`` 每次轮询都会重建管理器，把探测放进构造函数会变成每轮一次子进程。

探测方式（均为本机实测）：

- 雷电：裸跑 ``ldconsole.exe``，首行形如
  ``dnplayer v14.0.25.1 Command Line Management Interface``
- MuMu：``MuMuManager.exe version`` 输出 ``{"version": "6.5.9.0"}``

解析与判定是纯函数，可以脱离模拟器测试；只有 :func:`probe_install_path` 会起子进程。
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.utils import ProcessRunner, get_logger
from app.utils.constants import EMULATOR_PATH_BOOK

logger = get_logger("Emulator2 版本探测")

#: 接受的大版本。两家都已实现后端。
SUPPORTED_MAJOR = {"ldplayer": 14, "mumu": 6}
#: 还没接、但界面要如实说「后续接入」而不是「不支持」的。
PLANNED_MAJOR: dict[str, int] = {}

#: 探测超时。裸跑 ``ldconsole.exe`` 只打印用法，正常在一秒内返回。
PROBE_TIMEOUT_SECONDS = 15

_LDPLAYER_VERSION = re.compile(r"dnplayer\s+v?(\d+(?:\.\d+)*)", re.IGNORECASE)
_LOOSE_VERSION = re.compile(r"(\d+(?:\.\d+)+)")


@dataclass(frozen=True)
class DetectResult:
    """一次探测的结果。

    ``reason`` 是给界面用的枚举，不是给用户直接看的文案——文案在前端按枚举取，
    这样后端不用管翻译，也不会把内部细节漏进界面。
    """

    supported: bool
    reason: str
    type: str = ""
    version: str = ""
    manager_exe: str = ""
    install_path: str = ""

    #: reason 取值
    #: - ``ok``              可添加
    #: - ``version_too_old`` 版本太旧（雷电 9 等）
    #: - ``planned``         后续版本接入（当前没有类型命中，留给以后加第三家）
    #: - ``unsupported``     暂不支持（MuMu 12、其他品牌）
    #: - ``not_found``       路径下没找到管理器程序
    #: - ``probe_failed``    管理器程序跑不起来或输出认不出


def parse_ldplayer_version(output: str) -> str | None:
    """从 ``ldconsole.exe`` 的裸跑输出里取版本号。

    实测首行：``dnplayer v14.0.25.1 Command Line Management Interface``
    """
    if not output:
        return None
    match = _LDPLAYER_VERSION.search(output)
    if match:
        return match.group(1)
    # 首行格式换了也别直接放弃，退而求其次找第一个点分数字
    head = output.strip().splitlines()[0] if output.strip() else ""
    loose = _LOOSE_VERSION.search(head)
    return loose.group(1) if loose else None


def parse_mumu_version(output: str) -> str | None:
    """从 ``MuMuManager.exe version`` 的输出里取版本号。

    实测输出是 JSON：``{"version": "6.5.9.0"}``
    """
    if not output:
        return None
    try:
        data = json.loads(output)
    except (TypeError, ValueError):
        data = None
    if isinstance(data, dict):
        version = data.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    loose = _LOOSE_VERSION.search(output)
    return loose.group(1) if loose else None


def major_of(version: str) -> int | None:
    """取大版本号。认不出返回 ``None``，调用方按探测失败处理。"""
    if not version:
        return None
    head = version.strip().split(".")[0]
    return int(head) if head.isdecimal() else None


def judge(emulator_type: str, version: str) -> tuple[bool, str]:
    """按类型与版本判定是否可加入 Emulator 2.0。

    三种「不可加」要分开，界面上的措辞完全不同：版本太旧是用户可行动的，
    后续接入是路线上的，暂不支持是没计划的。
    """
    major = major_of(version)
    if major is None:
        return False, "probe_failed"

    expected = SUPPORTED_MAJOR.get(emulator_type)
    if expected is not None:
        if major == expected:
            return True, "ok"
        return False, "version_too_old" if major < expected else "unsupported"

    planned = PLANNED_MAJOR.get(emulator_type)
    if planned is not None and major == planned:
        return False, "planned"

    return False, "unsupported"


def resolve_manager_exe(install_path: str, emulator_type: str) -> Path | None:
    """把安装目录或旁路 exe 解析成主管理器程序。

    复用发现链里那套定位逻辑，保证与自动搜索的口径一致。
    """
    if not install_path:
        return None
    from app.utils.emulator.tools import find_emulator_manager_path

    resolved = Path(find_emulator_manager_path(install_path, emulator_type))
    if not resolved.is_file():
        return None
    executables = EMULATOR_PATH_BOOK.get(emulator_type, {}).get("executables") or []
    if executables and resolved.name.lower() != executables[0].lower():
        return None
    return resolved


def guess_type(install_path: str) -> str | None:
    """在不知道类型时，按各家的主管理器程序名猜一把。

    手动指定路径时用户只给目录，得先猜出是哪一家才知道用哪种方式问版本。
    """
    base = Path(install_path)
    candidates = [base] if base.is_dir() else [base.parent, base.parent.parent]
    for emulator_type, config in EMULATOR_PATH_BOOK.items():
        executables = config.get("executables") or []
        if not executables:
            continue
        primary = executables[0]
        for directory in candidates:
            try:
                if (directory / primary).is_file():
                    return emulator_type
            except OSError:
                continue
        # MuMu 的管理器在 nx_main / shell 子目录里
        if emulator_type == "mumu":
            for directory in candidates:
                for sub in ("nx_main", "shell"):
                    try:
                        if (directory / sub / primary).is_file():
                            return emulator_type
                    except OSError:
                        continue
    return None


async def read_version(manager_exe: Path, emulator_type: str) -> str | None:
    """起子进程问版本。认不出返回 ``None``。"""
    args: tuple[str, ...] = () if emulator_type == "ldplayer" else ("version",)
    try:
        result = await ProcessRunner.run_process(
            manager_exe,
            *args,
            timeout=PROBE_TIMEOUT_SECONDS,
            if_merge_std=True,
            breakaway=True,
        )
    except Exception as e:  # noqa: BLE001 - 探测失败不该让调用方炸
        logger.warning(f"探测 {manager_exe} 版本失败: {e}")
        return None

    # 雷电裸跑只是打印用法, 返回码不为 0 也属正常; 而且实测 `add` 成功时都会返回 4,
    # 所以这里一律不看返回码, 只看输出认不认得出版本。
    output = result.stdout or ""
    if emulator_type == "ldplayer":
        return parse_ldplayer_version(output)
    return parse_mumu_version(output)


async def probe_install_path(
    install_path: str, emulator_type: str | None = None
) -> DetectResult:
    """探测一条安装路径：定位管理器 → 问版本 → 判定。

    唯一会起子进程的入口。结果应由调用方持久化，不要在每次轮询时重复调用。
    """
    if not install_path:
        return DetectResult(supported=False, reason="not_found")

    resolved_type = emulator_type or guess_type(install_path)
    if resolved_type is None:
        return DetectResult(
            supported=False, reason="not_found", install_path=install_path
        )

    manager_exe = resolve_manager_exe(install_path, resolved_type)
    if manager_exe is None:
        return DetectResult(
            supported=False,
            reason="not_found",
            type=resolved_type,
            install_path=install_path,
        )

    version = await read_version(manager_exe, resolved_type)
    if version is None:
        return DetectResult(
            supported=False,
            reason="probe_failed",
            type=resolved_type,
            manager_exe=manager_exe.as_posix(),
            install_path=manager_exe.parent.as_posix(),
        )

    supported, reason = judge(resolved_type, version)
    return DetectResult(
        supported=supported,
        reason=reason,
        type=resolved_type,
        version=version,
        manager_exe=manager_exe.as_posix(),
        install_path=manager_exe.parent.as_posix(),
    )
