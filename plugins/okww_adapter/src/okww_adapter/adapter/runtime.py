from __future__ import annotations

import asyncio
import shutil
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.ConfigBase import ConfigBase, MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import TaskExecuteBase, UserItem
from app.plugins import ScriptAdapterHooks, ScriptAdapterRuntime
from app.services import System
from app.utils import ProcessManager, get_logger

from .autoproxy import AutoProxyTask, _OKWW_REL_CONFIG_DIR

logger = get_logger("OK-WW 插件适配")


def _cfg_get(config: ConfigBase | None, group: str, name: str, default: Any = None) -> Any:
    if config is None:
        return default
    try:
        value = config.get(group, name)
    except Exception:
        return default
    return default if value is None else value


def _user_name(config: ConfigBase | None, fallback: str) -> str:
    value = _cfg_get(config, "Info", "Name", fallback)
    return str(value or fallback)


def _user_enabled(config: ConfigBase | None) -> bool:
    return bool(_cfg_get(config, "Info", "Status", True))


class _CheckedAutoProxyTask(TaskExecuteBase):
    def __init__(self, inner: AutoProxyTask) -> None:
        super().__init__()
        self.inner = inner

    async def main_task(self) -> None:
        try:
            result = await self.inner.check()
            if result != "Pass":
                current_user = self.inner.cur_user_item
                if current_user.status == "等待":
                    current_user.status = "异常"
                await Publisher.send(
                    id=self.inner.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=result),
                )
                return
            await self.inner.main_task()
        except asyncio.CancelledError:
            self.inner.manual_stop_requested = True
            raise

    async def final_task(self) -> None:
        await self.inner.final_task()

    async def on_crash(self, error: Exception) -> None:
        await self.inner.on_crash(error)


class OkwwAdapterHooks(ScriptAdapterHooks):
    async def check(self, runtime: ScriptAdapterRuntime) -> str:
        if runtime.mode != "AutoProxy":
            return "OK-WW 插件仅支持 AutoProxy 模式"
        return "Pass"

    async def prepare(self, runtime: ScriptAdapterRuntime) -> None:
        storage_script_config = runtime.get_storage_script_config()
        await storage_script_config.lock()
        runtime.storage_script_config = storage_script_config
        runtime.script_config = await runtime.build_script_model()
        user_pairs = await runtime.build_user_models()
        provider = runtime._resolve_provider()
        user_config = MultipleConfig([provider.user_config_class])
        await user_config.load(
            {
                "instances": [
                    {"uid": user_id, "type": provider.user_config_class.__name__}
                    for user_id, _ in user_pairs
                ],
                **{
                    user_id: await model.toDict(if_decrypt=False)
                    for user_id, model in user_pairs
                    if isinstance(model, ConfigBase)
                },
            }
        )

        runtime.extra["user_config"] = user_config
        runtime.script_info.user_list = [
            UserItem(
                user_id=user_id,
                name=_user_name(model if isinstance(model, ConfigBase) else None, user_id),
                status="等待",
            )
            for user_id, model in user_pairs
            if isinstance(model, ConfigBase) and _user_enabled(model)
        ]

        game_enabled = bool(_cfg_get(runtime.script_config, "Game", "Enabled", False))
        runtime.extra["game_manager"] = ProcessManager() if game_enabled else None
        runtime.extra["temp_path"] = None
        runtime.extra["script_config_path"] = None
        runtime.extra["had_original_script_config"] = False

        root_path = str(_cfg_get(runtime.script_config, "Info", "RootPath", "") or "").strip()
        if root_path:
            script_config_path = Path(root_path) / _OKWW_REL_CONFIG_DIR
            temp_path = Path.cwd() / f"data/{runtime.script_info.script_id}/Temp"
            temp_path.mkdir(parents=True, exist_ok=True)
            runtime.extra["script_config_path"] = script_config_path
            runtime.extra["temp_path"] = temp_path
            if script_config_path.exists():
                runtime.extra["had_original_script_config"] = True
                shutil.copytree(script_config_path, temp_path, dirs_exist_ok=True)

    async def finalize(self, runtime: ScriptAdapterRuntime) -> None:
        await self._restore_script_config_from_temp(runtime)
        await self._write_back_user_config(runtime)
        if any(user.status == "异常" for user in runtime.script_info.user_list):
            runtime.script_info.status = "异常"
            return
        runtime.script_info.status = "完成"

    async def on_crash(self, runtime: ScriptAdapterRuntime, error: Exception) -> None:
        runtime.script_info.status = "异常"
        logger.exception(f"OK-WW 插件任务出现异常: {error}")
        await self._restore_script_config_from_temp(runtime)
        with suppress(Exception):
            await self._write_back_user_config(runtime)
        await Publisher.send(
            id=runtime.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error", message=f"OK-WW 插件任务出现异常: {error}"
            ),
        )

    def run_auto_proxy(self, runtime: ScriptAdapterRuntime) -> TaskExecuteBase:
        user_config = runtime.extra.get("user_config")
        if not isinstance(user_config, MultipleConfig):
            raise RuntimeError("OK-WW 用户配置未准备完成")
        inner = AutoProxyTask(
            script_info=runtime.script_info,
            script_config=runtime.script_config,
            user_config=user_config,
            game_manager=runtime.extra.get("game_manager"),
        )
        return _CheckedAutoProxyTask(inner)

    async def _write_back_user_config(self, runtime: ScriptAdapterRuntime) -> None:
        script_uid = uuid.UUID(runtime.script_info.script_id)
        script_cfg = Config.ScriptConfig[script_uid]
        if script_cfg.is_locked:
            await script_cfg.unlock()
        user_config = runtime.extra.get("user_config")
        if not isinstance(user_config, MultipleConfig):
            return
        await script_cfg.UserData.load(await user_config.toDict(if_decrypt=False))

    async def _restore_script_config_from_temp(self, runtime: ScriptAdapterRuntime) -> None:
        temp_path = runtime.extra.get("temp_path")
        script_config_path = runtime.extra.get("script_config_path")
        had_original = bool(runtime.extra.get("had_original_script_config"))
        if not (
            isinstance(temp_path, Path)
            and temp_path.exists()
            and isinstance(script_config_path, Path)
        ):
            return
        if not had_original:
            logger.info(f"清理任务期写入的 OK-WW 脚本配置目录: {script_config_path}")
            shutil.rmtree(script_config_path, ignore_errors=True)
        else:
            logger.info(f"复原 OK-WW 脚本配置文件: {temp_path}")
            tmp_dst = script_config_path.with_name(script_config_path.name + ".tmp")
            shutil.rmtree(tmp_dst, ignore_errors=True)
            shutil.copytree(temp_path, tmp_dst, dirs_exist_ok=True)
            shutil.rmtree(script_config_path, ignore_errors=True)
            tmp_dst.rename(script_config_path)
        shutil.rmtree(temp_path, ignore_errors=True)
        with suppress(Exception):
            await System.kill_process(Path(_cfg_get(runtime.script_config, "Info", "RootPath", "")) / "ok-ww.exe")
