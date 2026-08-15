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
from typing import Any, Awaitable, Callable

from app.utils import ProcessManager, decode_bytes, get_logger
from app.utils.io import atomic_write, read_file, write_file

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


def _managed_options(user_config: Any, module_key: str) -> dict[str, Any]:
    """读取 ConfigBase JSONValidator 的 Managed.Options（字符串或对象）。"""

    try:
        raw = user_config.get("Managed", "Options")
    except (AttributeError, KeyError, TypeError):
        raw = {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        return {}
    engine = raw.get("SRA")
    if not isinstance(engine, dict):
        return {}
    module = engine.get(module_key)
    return dict(module) if isinstance(module, dict) else {}


def load_sra_native_config(script_config: Any) -> tuple[Path, dict[str, Any]]:
    """Load the selected SRA profile used by forms and runtime overlays."""

    _selected_id, path = resolve_sra_profile(script_config)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise FileNotFoundError(f"SRA 原生配置不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"SRA 原生配置不是有效 JSON：{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"SRA 原生配置顶层必须是对象：{path}")
    return path, payload


def discover_sra_managed_options(
    module_key: str,
    script_config: Any,
) -> tuple[dict[str, Any], str]:
    """Discover native fields for one HSR module without applying overrides."""

    if module_key == "Daily":
        section_name = "trailblazePower"
    elif module_key == "ReceiveRewards":
        section_name = "receiveRewards"
    else:
        section_name = "cosmicStrife"
    _source, payload = load_sra_native_config(script_config)
    if module_key == "Daily":
        predicate = lambda key: key not in {"enabled", "tasklist"}
    elif module_key == "ReceiveRewards":
        predicate = lambda key: key not in {"enabled", "redeemCodes"}
    else:
        if module_key == "DivergentUniverse":
            predicate = (
                lambda key: (
                    key == "pointRewards.enabled"
                    or key.startswith("divergentUniverse.")
                )
                and key != "divergentUniverse.enabled"
            )
        else:
            predicate = (
                lambda key: key.startswith("currencyWars.")
                and key != "currencyWars.enabled"
            )
    section = payload.get(section_name)
    if not isinstance(section, dict):
        return {}, section_name
    options = {str(key): value for key, value in section.items() if predicate(str(key))}
    if module_key == "ReceiveRewards":
        rewards = options.pop("rewards", None)
        if isinstance(rewards, list):
            options.update(
                {f"rewards.{index}": value for index, value in enumerate(rewards)}
            )
    return options, section_name


def _same_value_kind(value: Any, reference: Any) -> bool:
    if isinstance(reference, bool):
        return isinstance(value, bool)
    if isinstance(reference, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(reference, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(reference, list):
        return isinstance(value, list)
    if isinstance(reference, dict):
        return isinstance(value, dict)
    return isinstance(value, str) if isinstance(reference, str) else True


def resolve_sra_managed_options(
    module_key: str,
    script_config: Any,
    user_config: Any,
) -> dict[str, Any]:
    """Return native SRA values overlaid with a user's Managed.Options."""

    native, _section_name = discover_sra_managed_options(module_key, script_config)
    overrides = _managed_options(user_config, module_key)
    unknown = sorted(set(overrides).difference(native))
    if unknown:
        raise ValueError(
            f"SRA {module_key} 包含当前原生配置不支持的字段：{'、'.join(unknown)}"
        )
    effective = dict(native)
    for key, value in overrides.items():
        if not _same_value_kind(value, native[key]):
            raise ValueError(f"SRA {module_key}.{key} 的值类型与原生配置不一致")
        effective[key] = value
    return effective


def _apply_managed_options(
    config: dict[str, Any],
    module_key: str,
    script_config: Any,
    user_config: Any,
) -> None:
    _native, section_name = discover_sra_managed_options(module_key, script_config)
    effective = resolve_sra_managed_options(module_key, script_config, user_config)
    section = config.get(section_name)
    if not isinstance(section, dict):
        raise ValueError(f"SRA 临时配置缺少 {section_name} 对象")
    for key, value in effective.items():
        if key.startswith("rewards."):
            index = int(key.split(".", 1)[1])
            rewards = section.setdefault("rewards", [])
            if not isinstance(rewards, list):
                raise ValueError("SRA receiveRewards.rewards 必须是数组")
            while len(rewards) <= index:
                rewards.append(False)
            rewards[index] = value
        else:
            section[key] = value


def write_sra_temp_config(
    config: dict,
    script_uid: str,
    user_uid: str,
    module_key: str,
) -> Path:
    """写出 SRA 运行 JSON，避免 SRA CLI 按 ANSI 读取时编码炸裂。"""

    target_path = _sra_temp_path(script_uid, user_uid, module_key)
    atomic_write(
        target_path,
        json.dumps(config, ensure_ascii=True, indent=4).encode("utf-8"),
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

    def _cipher(key: str) -> str:
        try:
            item = user_config._config_item_index["Info"][key]
        except (AttributeError, KeyError):
            return ""
        return str(item.getValue(if_decrypt=False) or "")

    username_cipher = _cipher("Id")
    password_cipher = _cipher("Password")
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
    redeem_codes_enabled: bool = True,
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
        # 领取项来自当前 SRA profile；Managed.Options 只覆盖已发现字段。
        native_options = resolve_sra_managed_options(
            module.key, script_config, user_config
        )
        config["receiveRewards"]["rewards"] = [
            bool(native_options.get("rewards.0", True)),
            bool(native_options.get("rewards.1", True)),
            bool(native_options.get("rewards.2", True)),
            bool(native_options.get("rewards.3", True)),
            bool(native_options.get("rewards.4", True)),
            bool(native_options.get("rewards.5", True)),
            bool(native_options.get("rewards.6", True)) and bool(redeem_codes_enabled),
        ]

    elif module.key == "DivergentUniverse":
        native_options = resolve_sra_managed_options(
            module.key, script_config, user_config
        )
        config["cosmicStrife"]["divergentUniverse.enabled"] = True
        config["cosmicStrife"]["divergentUniverse.mode"] = int(
            native_options.get("divergentUniverse.mode", SRA_DIVERGENT_UNIVERSE_MODE)
        )
        config["cosmicStrife"]["divergentUniverse.runtimes"] = int(
            native_options.get(
                "divergentUniverse.runtimes", SRA_DIVERGENT_UNIVERSE_RUNTIMES
            )
        )
        config["cosmicStrife"]["divergentUniverse.useTechnique"] = bool(
            native_options.get(
                "divergentUniverse.useTechnique", SRA_DIVERGENT_UNIVERSE_USE_TECHNIQUE
            )
        )
        config["cosmicStrife"]["pointRewards.enabled"] = bool(
            native_options.get(
                "pointRewards.enabled", SRA_DIVERGENT_UNIVERSE_POINT_REWARDS
            )
        )

    elif module.key == "CurrencyWars":
        native_options = resolve_sra_managed_options(
            module.key, script_config, user_config
        )
        username = str(user_config.get("Info", "Name") or "").strip()
        config["cosmicStrife"]["currencyWars.enabled"] = True
        mode = native_options.get("currencyWars.mode", SRA_CURRENCY_WARS_MODE)
        difficulty = native_options.get(
            "currencyWars.difficulty", SRA_CURRENCY_WARS_DIFFICULTY
        )
        config["cosmicStrife"]["currencyWars.mode"] = {
            "normal": 0,
            "overclock": 1,
            0: 0,
            1: 1,
        }.get(mode, SRA_CURRENCY_WARS_MODE)
        config["cosmicStrife"]["currencyWars.difficulty"] = {
            "lowest": 0,
            "highest": 1,
            0: 0,
            1: 1,
        }.get(difficulty, SRA_CURRENCY_WARS_DIFFICULTY)
        config["cosmicStrife"]["currencyWars.policy"] = 0
        config["cosmicStrife"]["currencyWars.strategy"] = native_options.get(
            "currencyWars.strategy", _resolve_sra_currency_wars_strategy(script_config)
        )
        config["cosmicStrife"]["currencyWars.strategyIndex"] = int(
            native_options.get(
                "currencyWars.strategyIndex", SRA_CURRENCY_WARS_STRATEGY_INDEX
            )
        )
        config["cosmicStrife"]["currencyWars.runtimes"] = int(
            native_options.get("currencyWars.runtimes", SRA_CURRENCY_WARS_RUNTIMES)
        )
        config["cosmicStrife"]["currencyWars.username"] = username

    _apply_managed_options(config, module.key, script_config, user_config)
    if module.key == "Daily":
        trailblaze = config["trailblazePower"]
        trailblaze["enabled"] = True
        if bool(trailblaze.get("useBuildTarget")):
            trailblaze["tasklist"] = []
        else:
            trailblaze["tasklist"] = _build_sra_trailblaze_tasklist(
                user_config,
                eow_enabled=daily_eow_enabled,
            )
    elif module.key == "ReceiveRewards":
        config["receiveRewards"]["enabled"] = True
        rewards = config["receiveRewards"].setdefault("rewards", [])
        while len(rewards) <= 6:
            rewards.append(False)
        rewards[6] = bool(rewards[6]) and bool(redeem_codes_enabled)
        if not rewards[6]:
            config["receiveRewards"]["redeemCodes"] = ""
    elif module.key == "DivergentUniverse":
        config["cosmicStrife"]["enabled"] = True
        config["cosmicStrife"]["divergentUniverse.enabled"] = True
        config["cosmicStrife"]["currencyWars.enabled"] = False
    elif module.key == "CurrencyWars":
        config["cosmicStrife"]["enabled"] = True
        config["cosmicStrife"]["divergentUniverse.enabled"] = False
        config["cosmicStrife"]["currencyWars.enabled"] = True

    return config


def get_sra_app_data_dir() -> Path:
    """定位 SRA 与前端共用的用户配置目录。"""

    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SRA"
    return Path.home() / ".config" / "SRA"


def resolve_sra_profile(
    script_config: Any,
    *,
    config_root: Path | None = None,
) -> tuple[str, Path]:
    """Resolve the one SRA native profile shared by inspect, forms and runtime.

    The conventional ``Default.json`` is preferred when present; otherwise
    the first profile in stable filename order is selected.
    """

    root = (
        Path(config_root)
        if config_root is not None
        else get_sra_app_data_dir() / "configs"
    )
    default_path = root / "Default.json"
    if default_path.is_file():
        return "Default", default_path

    candidates = (
        sorted(
            (item for item in root.glob("*.json") if item.is_file()),
            key=lambda item: item.name.casefold(),
        )
        if root.is_dir()
        else []
    )
    if candidates:
        selected = candidates[0]
        return selected.stem, selected
    return "Default", default_path


def disable_sra_windows_notifications() -> Path:
    """临时关闭 SRA 本体的 Windows 通知。"""

    cache_path = get_sra_app_data_dir() / "cache.json"
    cache: dict = {}
    if cache_path.exists():
        try:
            raw_cache = read_file(cache_path)
        except json.JSONDecodeError:
            raw_cache = {}
        if isinstance(raw_cache, dict):
            cache = raw_cache

    if cache.get(SRA_CACHE_NO_NOTIFY_KEY) is True:
        return cache_path

    cache[SRA_CACHE_NO_NOTIFY_KEY] = True
    write_file(cache_path, cache)
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
        logger.opt(exception=True).warning(f"SRA 单任务 {task_class} 执行失败：{e}")
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


async def run_sra_config(
    sra_exe_path: Path,
    config_path: Path,
    timeout: int = 7200,
    process_registry: SRAProcessRegistry | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> SRACommandResult:
    """运行 SRA 原生配置中的完整任务计划。

    这是旧 dev 对插件版 ``run_sra_config`` 的等价入口；命令仍走 SRA
    ``--inline run``，并复用既有实时日志/进程终止逻辑。
    """

    started_at = datetime.now(timezone.utc)
    module_key = "DirectControl"
    if not sra_exe_path.exists():
        return SRACommandResult(
            task_class="run",
            config_path=str(config_path),
            module_key=module_key,
            success=False,
            error=f"SRA-cli.exe does not exist: {sra_exe_path}",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )

    registry = process_registry or SRAProcessRegistry()
    try:
        proc = await registry.open_process(
            str(sra_exe_path),
            "--inline",
            f'run "{config_path}"',
            "quit",
            cwd=sra_exe_path.parent,
        )
        stdout, stderr = await _communicate_sra_with_live_output(
            proc,
            timeout,
            log_callback,
        )
        success = proc.returncode == 0 and not has_failure_output(stdout, stderr)
        return SRACommandResult(
            task_class="run",
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
        await registry.terminate_current_process()
        return SRACommandResult(
            task_class="run",
            config_path=str(config_path),
            module_key=module_key,
            success=False,
            error=f"command timeout: {timeout}s",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
    except asyncio.CancelledError:
        await registry.terminate_current_process()
        raise
    except Exception as exc:  # noqa: BLE001
        logger.opt(exception=True).warning(f"SRA 原生配置执行失败：{exc}")
        return SRACommandResult(
            task_class="run",
            config_path=str(config_path),
            module_key=module_key,
            success=False,
            error=str(exc),
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
    finally:
        await registry.clear()


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
        read_native_main_stage(user_config, "SRA")
        if field == "ScriptStage"
        else read_native_stage(user_config, field, "SRA")
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
        native_eow = _native_stage_to_sra_tp_item(user_config, "ScriptEchoOfWar", 1)
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
    if not (can_read_stream_live(stdout_stream) or can_read_stream_live(stderr_stream)):
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
