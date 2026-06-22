#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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
import json
import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import isawaitable
from pathlib import Path
from typing import Awaitable, Callable

from app.utils import ProcessManager, decode_bytes, get_logger

from .log_detect import (
    can_read_stream_live,
    emit_process_output,
    has_failure_output,
)
from .stage_runtime import (
    get_sra_native_stage,
    read_native_main_stage,
    read_native_stage,
)


logger = get_logger("HSR SRA 运行器")

SRA_GAME_CHANNEL_CLIENT = 0
SRA_TRAILBLAZE_POWER_AUTO_DETECT = True

SRA_DIVERGENT_UNIVERSE_MODE = 0
SRA_DIVERGENT_UNIVERSE_RUNTIMES = 20
SRA_DIVERGENT_UNIVERSE_USE_TECHNIQUE = False
SRA_DIVERGENT_UNIVERSE_POINT_REWARDS = True

SRA_CURRENCY_WARS_MODE = 0
SRA_CURRENCY_WARS_DIFFICULTY = 0
SRA_CURRENCY_WARS_STRATEGY = "template"
SRA_CURRENCY_WARS_STRATEGY_INDEX = 0
SRA_CURRENCY_WARS_RUNTIMES = 2
SRA_CURRENCY_WARS_STRATEGY_KEYWORDS = ("阿格莱雅", "aglaea")
SRA_CACHE_NO_NOTIFY_KEY = "NoNotifyForShortcut"


def write_sra_temp_config(
    config: dict,
    script_uid: str,
    user_uid: str,
    module_key: str,
) -> Path:
    """写出 SRA 运行 JSON，避免 SRA CLI 按 ANSI 读取时编码炸裂。"""

    target_path = _sra_temp_path(script_uid, user_uid, module_key)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(config, ensure_ascii=True, indent=4),
        encoding="utf-8",
    )
    logger.debug(f"SRA temp config written: {target_path}")
    return target_path


def cleanup_sra_temp_config(path: Path, keep_on_error: bool = False) -> None:
    if keep_on_error:
        return

    if path.exists():
        try:
            path.unlink()
            logger.debug(f"SRA temp config cleaned: {path}")
        except OSError as e:
            logger.warning(f"Failed to clean SRA temp config: {path} - {e}")

    parent = path.parent
    try:
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            grand = parent.parent
            if grand.exists() and not any(grand.iterdir()):
                grand.rmdir()
    except OSError:
        pass


def build_sra_tasklist_description(tasklist: list[dict]) -> str:
    if not tasklist:
        return "no trailblaze power task"
    return "; ".join(
        (
            f"{item.get('levelName') or item.get('name') or item.get('id')} 自动检测"
            if item.get("autoDetect")
            else (
                f"{item.get('levelName') or item.get('name') or item.get('id')} "
                f"x{item.get('runtimes')}"
            )
        )
        for item in tasklist
    )


def build_sra_start_game_config(
    script_config,
    user_config,
    name: str = "_mas_temp_start",
    mode: str = "switch",
) -> dict:
    """构造只启用 SRA StartGameTask 的配置。"""

    if mode not in ("switch", "remembered"):
        raise ValueError(
            f"不支持的 SRA StartGame 模式：{mode!r}，仅支持 switch / remembered"
        )

    config = _build_sra_base_config(name)
    config["startGame"]["enabled"] = True
    config["startGame"]["game.channel"] = SRA_GAME_CHANNEL_CLIENT
    config["startGame"]["game.path"] = str(script_config.get("Game", "Path"))
    config["startGame"]["game.useGlobalPath"] = False

    if mode == "remembered":
        config["startGame"]["relogin"] = False
        config["startGame"]["autologin"] = False
        return config

    username_cipher = user_config._config_item_index["Info"]["Id"].getValue(
        if_decrypt=False
    )
    password_cipher = user_config._config_item_index["Info"]["Password"].getValue(
        if_decrypt=False
    )
    config["startGame"]["relogin"] = True
    config["startGame"]["autologin"] = True
    config["startGame"]["username"] = str(username_cipher)
    config["startGame"]["password"] = str(password_cipher)
    return config


def build_sra_module_config(
    module,
    script_config,
    user_config,
    name: str = "",
    daily_eow_enabled: bool = False,
) -> dict:
    """构造只启用一个目标模块的 SRA TasksConfig。"""

    config = _build_sra_base_config(name or f"_mas_temp_{module.key}")
    if module.sra_task is None:
        return config

    if module.sra_overrides:
        for top_key, overrides in module.sra_overrides.items():
            section = config.get(top_key)
            if not isinstance(section, dict):
                continue
            for key, value in overrides.items():
                if key in section:
                    section[key] = value
                    continue
                keys = str(key).split(".")
                target = section
                for nested_key in keys[:-1]:
                    child = target.get(nested_key)
                    if not isinstance(child, dict):
                        child = {}
                        target[nested_key] = child
                    target = child
                target[keys[-1]] = value

    if module.key == "Daily":
        config["trailblazePower"]["tasklist"] = _build_sra_trailblaze_tasklist(
            user_config, eow_enabled=daily_eow_enabled
        )
        config["trailblazePower"]["replenish.enabled"] = False
        config["trailblazePower"]["replenish.way"] = 0
        config["trailblazePower"]["replenish.times"] = 0

    elif module.key == "ReceiveRewards":
        # 不接管 SRA 自己维护的兑换码内容，只打开领取开关。
        config["receiveRewards"]["rewards"] = [
            True,
            True,
            True,
            True,
            True,
            True,
            True,
        ]

    elif module.key == "DivergentUniverse":
        config["cosmicStrife"]["divergentUniverse.enabled"] = True
        config["cosmicStrife"]["divergentUniverse.mode"] = SRA_DIVERGENT_UNIVERSE_MODE
        config["cosmicStrife"]["divergentUniverse.runtimes"] = (
            SRA_DIVERGENT_UNIVERSE_RUNTIMES
        )
        config["cosmicStrife"]["divergentUniverse.useTechnique"] = (
            SRA_DIVERGENT_UNIVERSE_USE_TECHNIQUE
        )
        config["cosmicStrife"]["pointRewards.enabled"] = (
            SRA_DIVERGENT_UNIVERSE_POINT_REWARDS
        )

    elif module.key == "CurrencyWars":
        username = str(user_config.get("Info", "Name") or "").strip()
        config["cosmicStrife"]["currencyWars.enabled"] = True
        config["cosmicStrife"]["currencyWars.mode"] = SRA_CURRENCY_WARS_MODE
        config["cosmicStrife"]["currencyWars.difficulty"] = (
            SRA_CURRENCY_WARS_DIFFICULTY
        )
        config["cosmicStrife"]["currencyWars.policy"] = 0
        config["cosmicStrife"]["currencyWars.strategy"] = (
            _resolve_sra_currency_wars_strategy(script_config)
        )
        config["cosmicStrife"]["currencyWars.strategyIndex"] = (
            SRA_CURRENCY_WARS_STRATEGY_INDEX
        )
        config["cosmicStrife"]["currencyWars.runtimes"] = SRA_CURRENCY_WARS_RUNTIMES
        config["cosmicStrife"]["currencyWars.username"] = username

    return config


def get_sra_app_data_dir() -> Path:
    """定位 SRA 与前端共用的用户配置目录。"""

    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SRA"
    return Path.home() / ".config" / "SRA"


def disable_sra_windows_notifications() -> Path:
    """临时关闭 SRA 本体的 Windows 通知。"""

    cache_path = get_sra_app_data_dir() / "cache.json"
    cache: dict = {}
    if cache_path.exists():
        try:
            raw_cache = json.loads(cache_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            raw_cache = {}
        if isinstance(raw_cache, dict):
            cache = raw_cache

    if cache.get(SRA_CACHE_NO_NOTIFY_KEY) is True:
        return cache_path

    cache[SRA_CACHE_NO_NOTIFY_KEY] = True
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    logger.info(f"SRA cache.json 已关闭 Windows 通知：{cache_path}")
    return cache_path


@dataclass
class SRACommandResult:
    task_class: str
    config_path: str
    module_key: str = ""
    success: bool = False
    output: str = ""
    error: str = ""
    returncode: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SRAProcessRegistry:
    """记录 SRA 当前子进程，供任务停止时终止。"""

    def __init__(self):
        self._process_manager = ProcessManager()

    async def open_process(
        self,
        program: str,
        *args: str,
        cwd: Path,
    ) -> asyncio.subprocess.Process:
        await self._process_manager.open_process(
            program,
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        proc = self._process_manager.main_process
        if not isinstance(proc, asyncio.subprocess.Process):
            raise RuntimeError("SRA 子进程启动后未能被 ProcessManager 跟踪")
        return proc

    async def clear(self) -> None:
        await self._process_manager.clear()

    async def terminate_current_process(self) -> bool:
        if not await self._process_manager.is_running():
            return False

        logger.warning("正在终止 SRA 当前子进程")
        await self._process_manager.kill()
        return True


async def run_sra_single_task(
    sra_exe_path: Path,
    task_class: str,
    config_path: Path,
    timeout: int = 600,
    process_registry: SRAProcessRegistry | None = None,
    log_callback: Callable[[str], None] | None = None,
    output_line_callback: Callable[[str], Awaitable[None] | None] | None = None,
    module_key: str = "",
) -> SRACommandResult:
    """通过 SRA inline 模式运行单个任务并退出。"""

    command_text = f'single {task_class} --config "{config_path}"'
    started_at = datetime.now(timezone.utc)

    if not sra_exe_path.exists():
        return SRACommandResult(
            task_class=task_class,
            config_path=str(config_path),
            module_key=module_key,
            success=False,
            error=f"SRA-cli.exe does not exist: {sra_exe_path}",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )

    try:
        process_registry = process_registry or SRAProcessRegistry()
        proc = await process_registry.open_process(
            str(sra_exe_path),
            "--inline",
            command_text,
            "quit",
            cwd=sra_exe_path.parent,
        )
        stdout, stderr = await _communicate_sra_with_live_output(
            proc,
            timeout,
            log_callback,
            output_line_callback=output_line_callback,
        )
        success = proc.returncode == 0 and not has_failure_output(stdout, stderr)

        return SRACommandResult(
            task_class=task_class,
            config_path=str(config_path),
            module_key=module_key,
            success=success,
            output=stdout,
            error=stderr,
            returncode=proc.returncode or 0,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )

    except asyncio.TimeoutError:
        if process_registry is not None:
            await process_registry.terminate_current_process()
        return SRACommandResult(
            task_class=task_class,
            config_path=str(config_path),
            module_key=module_key,
            success=False,
            error=f"command timeout: {timeout}s",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )

    except asyncio.CancelledError:
        logger.warning(f"SRA 单任务 {task_class} 收到取消请求，准备终止子进程")
        if process_registry is not None:
            await process_registry.terminate_current_process()
        raise

    except Exception as e:
        logger.exception(f"SRA 单任务 {task_class} 执行失败：{e}")
        return SRACommandResult(
            task_class=task_class,
            config_path=str(config_path),
            module_key=module_key,
            success=False,
            error=str(e),
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
    finally:
        if process_registry is not None:
            await process_registry.clear()


def _sra_temp_path(script_uid: str, user_uid: str, module_key: str) -> Path:
    from app.core import Config

    return (
        Config.config_path.parent
        / "runtime"
        / "hsr"
        / "sra-config"
        / script_uid
        / user_uid
        / f"{module_key}.json"
    )


def _build_sra_base_config(name: str) -> dict:
    """构造一个默认关闭所有任务的 SRA TasksConfig。"""

    return {
        "name": name,
        "version": 0,
        "general": {
            "cloudGame.enabled": False,
        },
        "startGame": {
            "enabled": False,
            "game.channel": SRA_GAME_CHANNEL_CLIENT,
            "game.path": "",
            "game.useGlobalPath": False,
            "autologin": True,
            "relogin": True,
            "username": "",
            "password": "",
        },
        "trailblazePower": {
            "enabled": False,
            "replenish.enabled": False,
            "replenish.times": 0,
            "replenish.way": 0,
            "useAssistant": False,
            "useBuildTarget": False,
            "tasklist": [],
            "activity.enabled": False,
        },
        "receiveRewards": {
            "enabled": False,
            "redeemCodes": "",
            "rewards": [],
        },
        "cosmicStrife": {
            "enabled": False,
            "pointRewards.enabled": False,
            "divergentUniverse.enabled": False,
            "divergentUniverse.mode": 0,
            "divergentUniverse.runtimes": 0,
            "divergentUniverse.useTechnique": False,
            "currencyWars.enabled": False,
            "currencyWars.mode": 0,
            "currencyWars.difficulty": 0,
            "currencyWars.policy": 0,
            "currencyWars.runtimes": 0,
            "currencyWars.strategy": "template",
            "currencyWars.strategyIndex": 0,
            "currencyWars.username": "",
        },
        "missionAccomplished": {
            "enabled": False,
            "logout": False,
            "exitGame": False,
            "shutdown": False,
            "sleep": False,
            "exitApp": False,
        },
    }


def _native_stage_to_sra_tp_item(
    user_config,
    field: str,
    run_times: int,
    count: int = 1,
) -> dict | None:
    """把 Stage.ScriptStage / ScriptEchoOfWar 转成 SRA tasklist item。"""

    stage_data = (
        read_native_main_stage(user_config)
        if field == "ScriptStage"
        else read_native_stage(user_config, field)
    )
    native = get_sra_native_stage(stage_data)
    if native is None:
        return None

    label = native["label"] or f"{native['id']}#{native['level']}"
    category_label = native["categoryLabel"] or label
    return {
        "name": category_label,
        "id": native["id"],
        "level": native["level"],
        "levelName": label,
        "count": count,
        "runtimes": run_times,
        "autoDetect": SRA_TRAILBLAZE_POWER_AUTO_DETECT,
    }


def _build_sra_trailblaze_tasklist(
    user_config,
    eow_enabled: bool = False,
) -> list[dict]:
    """按 HSR 用户配置构造 SRA trailblazePower.tasklist。"""

    tasklist: list[dict] = []
    main_item: dict | None = None
    eow_item: dict | None = None

    native_item = _native_stage_to_sra_tp_item(user_config, "ScriptStage", 1)
    if native_item is not None:
        main_item = native_item

    if eow_enabled:
        # SRA autoDetect 路径不读取 RunTimes，这里只保留结构占位。
        native_eow = _native_stage_to_sra_tp_item(
            user_config, "ScriptEchoOfWar", 1
        )
        if native_eow is None:
            raise RuntimeError(
                "本周需要执行历战余响，但 Stage.ScriptEchoOfWar 缺少 SRA 原生"
                "历战余响字段；请在体力配置中重新选择历战余响"
            )
        eow_item = native_eow

    if eow_item is not None:
        tasklist.append(eow_item)
    if main_item is not None:
        tasklist.append(main_item)
    return tasklist


def _resolve_sra_currency_wars_strategy(script_config) -> str:
    """优先使用 SRA 本地货币战争攻略 json。"""

    raw_path = str(script_config.get("Info", "SRAPath") or "").strip()
    if not raw_path:
        return SRA_CURRENCY_WARS_STRATEGY
    path = Path(raw_path)
    root = path.parent if path.suffix.lower() == ".exe" else path
    strategy_dirs = [
        root / "tasks" / "currency_wars" / "strategies",
        root / "tasks" / "currency_wars",
        root.parent / "tasks" / "currency_wars" / "strategies",
        root.parent / "tasks" / "currency_wars",
    ]

    strategy_files: list[Path] = []
    seen: set[Path] = set()
    for strategy_dir in strategy_dirs:
        if not strategy_dir.is_dir():
            continue
        for file in strategy_dir.glob("*.json"):
            resolved = file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            strategy_files.append(resolved)

    if not strategy_files:
        return SRA_CURRENCY_WARS_STRATEGY

    strategy_files.sort(key=lambda p: p.name.lower())
    for keyword in SRA_CURRENCY_WARS_STRATEGY_KEYWORDS:
        keyword_lower = keyword.lower()
        for file in strategy_files:
            if keyword_lower in file.name.lower():
                return str(file)
    return str(strategy_files[0])


async def _read_sra_stream_live(
    stream,
    title: str,
    lines: list[str],
    log_callback: Callable[[str], None] | None,
    output_line_callback: Callable[[str], Awaitable[None] | None] | None,
) -> None:
    """逐行读取 SRA 输出并立即转发到调度台。"""

    while True:
        raw = await stream.readline()
        if not raw:
            break
        if isinstance(raw, str):
            text = raw
        else:
            text = decode_bytes(bytes(raw))
        for line in text.rstrip("\r\n").splitlines():
            line = line.strip()
            if line:
                lines.append(line)
                emit_process_output(log_callback, title, line)
                if output_line_callback is not None:
                    result = output_line_callback(line)
                    if isawaitable(result):
                        await result


async def _communicate_sra_with_live_output(
    proc: asyncio.subprocess.Process,
    timeout: int,
    log_callback: Callable[[str], None] | None,
    *,
    output_line_callback: Callable[[str], Awaitable[None] | None] | None = None,
) -> tuple[str, str]:
    """读取 SRA 输出；可实时读取时逐行转发到调度台。"""

    stdout_stream = getattr(proc, "stdout", None)
    stderr_stream = getattr(proc, "stderr", None)
    if not (
        can_read_stream_live(stdout_stream)
        or can_read_stream_live(stderr_stream)
    ):
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        stdout = decode_bytes(stdout_bytes).strip()
        stderr = decode_bytes(stderr_bytes).strip()
        emit_process_output(log_callback, "SRA", stdout)
        emit_process_output(log_callback, "SRA stderr", stderr)
        if output_line_callback is not None:
            for text in (stdout, stderr):
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    result = output_line_callback(line)
                    if isawaitable(result):
                        await result
        return stdout, stderr

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    read_tasks: list[asyncio.Task] = []
    if can_read_stream_live(stdout_stream):
        read_tasks.append(
            asyncio.create_task(
                _read_sra_stream_live(
                    stdout_stream,
                    "SRA",
                    stdout_lines,
                    log_callback,
                    output_line_callback,
                )
            )
        )
    if can_read_stream_live(stderr_stream):
        read_tasks.append(
            asyncio.create_task(
                _read_sra_stream_live(
                    stderr_stream,
                    "SRA stderr",
                    stderr_lines,
                    log_callback,
                    output_line_callback,
                )
            )
        )

    wait_group = asyncio.gather(proc.wait(), *read_tasks)
    try:
        await asyncio.wait_for(wait_group, timeout=timeout)
    except Exception:
        wait_group.cancel()
        for task in read_tasks:
            task.cancel()
        with suppress(Exception):
            await asyncio.gather(wait_group, *read_tasks, return_exceptions=True)
        raise

    return "\n".join(stdout_lines).strip(), "\n".join(stderr_lines).strip()
