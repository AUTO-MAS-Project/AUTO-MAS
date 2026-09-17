#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MFW 运行环境准备结果的指纹缓存。

编辑页每打开一次就调一次 ``/maafw/agent-env/prepare``。底层准备本身是幂等的
（隔离 venv 靠自己的 manifest 三段哈希决定重不重建，不会重下 MaaFramework），
但「确认」这件事要取项目锁、起解释器核一次 ABI、再对每个 agent 跑 pip 健康
检查，项目没动过时这几秒全是空转。

这里把成功准备过的结果连同**项目输入指纹**落盘，下次先比指纹：一致、且结果里
记的那些路径都还在，就直接把上次的结果还回去。指纹用的就是 runner 包的
``project_environment_fingerprint()``——它哈希的正是 interface / requirements /
uv.lock 这些「脚本更新了没」的输入，项目一更新缓存自然失效。

项目文件不是唯一的输入：运行池里那份 runtime 的身份还包含**宿主引导解释器**
（``pool.resolve()`` 的 ``python_identity``，源头是本进程的 ``sys.executable``）。
AUTO-MAS 自己换了随包 Python 之后，旧 runtime 目录仍在盘上、项目也没动过，光比
项目指纹会命中，而真正运行时会解析到另一个 runtime 并现建——正好是这层缓存想
避免的事。所以宿主解释器身份也是命中判据的一部分。

**存在性检查不验内容**：文件还在、但 venv 内部已经坏了这种情况这里会放行。
兜底仍在：运行前 ``embedded_manager.describe_unusable_runtime()`` 会起解释器
核一次 ABI，编辑页的重试按钮也带 ``force`` 直接绕过缓存。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils import get_logger

from .project_path import normalize_project_path

logger = get_logger("MFW 运行环境缓存")

# 缓存结构变更时递增：读到不认识的版本一律当没有缓存。
CACHE_FORMAT_VERSION = 2


def _host_python_identity() -> dict[str, str]:
    """本进程解释器的身份，用来判断运行池那份 runtime 该不该换。

    只读内存里的常量，不起子进程——运行池真正算 identity 时会去探测解释器，
    但那份探测的输入就是这里这两个值，同路径同版本探不出不同结果。
    """

    return {"executable": sys.executable, "version": sys.version}


def _cache_root() -> Path:
    """与运行池同级放在 ``config/`` 下，用户清运行池时顺手也能看到它。"""

    return Path.cwd() / "config" / "maafw_env_cache"


def _cache_path(project_path: str | Path) -> Path:
    key = normalize_project_path(project_path)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return _cache_root() / f"{digest}.json"


def _paths_still_present(result: Mapping[str, Any]) -> bool:
    """只做 stat，不起进程：缓存的那套环境在盘上还完整吗？"""

    runtime = result.get("runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}

    python_executable = str(runtime.get("pythonExecutable") or "")
    if not python_executable or not Path(python_executable).is_file():
        return False

    venv_path = str(runtime.get("venvPath") or "")
    if venv_path and not Path(venv_path).is_dir():
        return False

    agents = result.get("agents")
    agents = agents if isinstance(agents, Mapping) else {}
    plans = agents.get("plans")
    plans = plans if isinstance(plans, list) else []
    for plan in plans:
        if not isinstance(plan, Mapping):
            return False
        isolated_venv = str(plan.get("isolatedVenvPath") or "")
        if isolated_venv and not Path(isolated_venv).is_dir():
            return False
        executable = str(plan.get("executable") or "")
        # external agent 的 executable 可能只是个命令名，交给 PATH 解析；
        # 只有写死绝对路径的（project_binary / 各种 venv）才检查。
        if executable and Path(executable).is_absolute():
            if not Path(executable).is_file():
                return False
    return True


def load_prepared_environment(
    project_path: str | Path, fingerprint: str | None
) -> dict[str, Any] | None:
    """指纹命中且环境路径都还在时返回上次的准备结果，否则返回 ``None``。

    ``fingerprint`` 为 ``None`` 表示项目里连 interface 都读不到，这种项目不该
    有缓存可用。
    """

    if not fingerprint:
        return None

    path = _cache_path(project_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001 - 缓存坏了不该挡住准备
        logger.debug(f"MFW 运行环境缓存读取失败，按未缓存处理：{exc}")
        return None

    if not isinstance(payload, Mapping):
        return None
    if payload.get("version") != CACHE_FORMAT_VERSION:
        return None
    if payload.get("projectPath") != normalize_project_path(project_path):
        return None
    if payload.get("fingerprint") != fingerprint:
        return None
    if payload.get("host") != _host_python_identity():
        logger.debug("MFW 运行环境缓存来自另一个宿主解释器，将重新准备")
        return None

    result = payload.get("result")
    if not isinstance(result, Mapping):
        return None
    if not _paths_still_present(result):
        logger.debug("MFW 运行环境缓存指向的路径已不完整，将重新准备")
        return None

    prepared = dict(result)
    prepared["preparedAt"] = payload.get("preparedAt")
    return prepared


def store_prepared_environment(
    project_path: str | Path, fingerprint: str | None, result: Mapping[str, Any]
) -> None:
    """记下这次成功的准备结果。写失败只记日志——缓存不是正确性的一部分。"""

    if not fingerprint:
        return

    payload = {
        "version": CACHE_FORMAT_VERSION,
        "projectPath": normalize_project_path(project_path),
        "fingerprint": fingerprint,
        "host": _host_python_identity(),
        "preparedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        # 只留下次要用的两段，日志不留：命中时那是上一次的日志，不是这次的。
        "result": {
            "runtime": result.get("runtime"),
            "agents": result.get("agents"),
        },
    }

    path = _cache_path(project_path)
    temp_path = path.with_name(f"{path.stem}.{uuid.uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temp_path, path)
    except Exception as exc:  # noqa: BLE001 - 写不进去也不影响本次准备
        logger.debug(f"MFW 运行环境缓存写入失败：{exc}")
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def has_prepared_environment(project_path: str | Path) -> bool:
    """这个项目此前有没有准备过（不看指纹是否还匹配）。

    只用来给界面分「首次准备完成」与「运行环境更新完成」两句话，所以缓存文件
    在就算有过，坏了、过期了都不深究——那些交给 ``load_prepared_environment``。
    """

    return _cache_path(project_path).is_file()


def discard_prepared_environment(project_path: str | Path) -> None:
    """丢掉缓存，让下次调用走完整准备。"""

    try:
        _cache_path(project_path).unlink(missing_ok=True)
    except OSError as exc:
        logger.debug(f"MFW 运行环境缓存清理失败：{exc}")


__all__ = [
    "CACHE_FORMAT_VERSION",
    "discard_prepared_environment",
    "has_prepared_environment",
    "load_prepared_environment",
    "store_prepared_environment",
]
