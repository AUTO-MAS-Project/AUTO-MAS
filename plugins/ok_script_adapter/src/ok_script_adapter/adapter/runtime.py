from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Mapping

from app.core.ws import Publisher, protocol
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.plugins import ScriptAdapterHooks, ScriptAdapterRuntime
from app.services import Notify
from app.utils import ProcessManager, get_logger

from .autoproxy import OkScriptAutoProxyTask


logger = get_logger("ok-script 插件适配")


def _config_value(config: Any, group: str, name: str, default: object = None) -> object:
    try:
        value = config.get(group, name)
    except Exception:
        return default
    return default if value is None else value


class _CheckedAutoProxyTask(TaskExecuteBase):
    """在插件通用编排器中补齐原 ok-script 用户级前置检查。"""

    def __init__(self, inner: OkScriptAutoProxyTask) -> None:
        super().__init__()
        self.inner = inner

    async def main_task(self) -> None:
        try:
            result = await self.inner.check()
            if result != "Pass":
                if self.inner.cur_user_item.status == "等待":
                    self.inner.cur_user_item.status = "异常"
                await Publisher.send(
                    id=self.inner.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=result),
                )
                return
            await self.inner.main_task()
        except asyncio.CancelledError:
            raise

    async def final_task(self) -> None:
        await self.inner.final_task()

    async def on_crash(self, error: Exception) -> None:
        await self.inner.on_crash(error)


class OkScriptAdapterHooks(ScriptAdapterHooks):
    """将插件表单配置转换为 ok-script 任务本地配置会话。"""

    async def check(self, runtime: ScriptAdapterRuntime) -> str:
        if runtime.mode != "AutoProxy":
            return "ok-script 插件仅支持 AutoProxy 模式"
        return "Pass"

    async def prepare(self, runtime: ScriptAdapterRuntime) -> None:
        await runtime.storage.lock()
        runtime.script_config = await runtime.build_script_model()

        user_config = await runtime.storage.load_user_collection()
        runtime.extra["user_config"] = user_config
        runtime.extra["game_manager"] = ProcessManager()
        runtime.script_info.user_list = [
            UserItem(
                user_id=user_id,
                name=str(_config_value(model, "Info", "Name", user_id)),
                status="等待",
            )
            for user_uid, model in user_config.items()
            for user_id in (str(user_uid),)
            if bool(_config_value(model, "Info", "Status", True))
            and int(_config_value(model, "Info", "RemainedDay", -1)) != 0
        ]

    async def finalize(self, runtime: ScriptAdapterRuntime) -> None:
        await self._write_back_user_config(runtime)
        runtime.script_info.status = (
            "异常" if any(user.status == "异常" for user in runtime.script_info.user_list) else "完成"
        )

    async def on_crash(self, runtime: ScriptAdapterRuntime, error: Exception) -> None:
        runtime.script_info.status = "异常"
        logger.exception(f"ok-script 插件任务出现异常: {error}")
        with suppress(Exception):
            await self._write_back_user_config(runtime)
        with suppress(Exception):
            await Notify.push_plyer(
                "ok-script 自动代理出现异常",
                str(error),
                "ok-script 自动代理异常",
                3,
            )

    def run_auto_proxy(self, runtime: ScriptAdapterRuntime) -> TaskExecuteBase:
        user_config = runtime.extra.get("user_config")
        if not isinstance(user_config, Mapping):
            raise RuntimeError("ok-script 用户配置未准备完成")
        if runtime.script_config is None:
            raise RuntimeError("ok-script 脚本配置未准备完成")
        return _CheckedAutoProxyTask(
            OkScriptAutoProxyTask(
                script_info=runtime.script_info,
                script_config=runtime.script_config,
                user_config=user_config,
                game_manager=runtime.extra.get("game_manager"),
            )
        )

    async def _write_back_user_config(self, runtime: ScriptAdapterRuntime) -> None:
        user_config = runtime.extra.get("user_config")
        await runtime.storage.unlock()
        if isinstance(user_config, Mapping):
            await runtime.storage.save_user_models(user_config)
