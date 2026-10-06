"""MAA 用户展开：校验安装目录与原生配置，备份/还原安装 config/。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from auto_mas_core import Config, TaskMode, UserExpander
from auto_mas_core.utils import (
    clear_native_config_snapshot,
    commit_native_config_snapshot,
    get_logger,
    recover_native_config,
    swap_in_dir,
)

from ..schema import MaaScript, MaaUser
from .auto_proxy import MaaAutoProxy
from .runtime import MaaRuntime
from .script_config import MaaScriptConfig

logger = get_logger("MAA 调度")


class MaaExpander(UserExpander):
    """不锁脚本、不拷用户：L2/L3 已做。prepare 只碰 MAA 安装目录快照。"""

    supported_modes = (TaskMode.AUTO_PROXY, TaskMode.SCRIPT_CONFIG)
    mode_workers = {
        TaskMode.AUTO_PROXY: MaaAutoProxy,
        TaskMode.SCRIPT_CONFIG: MaaScriptConfig,
    }

    runtime: MaaRuntime | None = None
    # 各用户失败画面（标签+图片）按序累积，供汇总「代理结果」带图；prepare 时重置
    report_image_pairs: list

    async def check(self) -> str:
        entry = self.script_entry
        if not isinstance(entry, MaaScript):
            return "脚本配置类型错误, 不是MAA脚本类型"
        ctx = self.task_context
        mode = ctx.mode if ctx is not None else TaskMode.AUTO_PROXY
        if mode not in self.supported_modes:
            return "不支持的任务模式，请检查任务配置！"
        if not isinstance(entry.info.game_id, UUID):
            return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
        if not isinstance(entry.info.game_device_id, UUID):
            return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
        root = entry.info.path
        if root is None or not (Path(root) / "MAA.exe").exists():
            return "MAA.exe文件不存在, 请检查MAA路径设置！"
        cfg = Path(root) / "config"
        if not (cfg / "gui.json").exists() or not (cfg / "gui.new.json").exists():
            return "MAA配置文件不存在, 请检查MAA路径设置或先启动MAA完成配置文件生成！"
        if mode != TaskMode.SCRIPT_CONFIG and self._has_script_config_user():
            sid = str(entry.uid)
            if not (Path.cwd() / f"data/{sid}/Default/ConfigFile").exists():
                return "未完成 MAA 全局设置, 请先设置 MAA！"
        return "Pass"

    def _has_script_config_user(self) -> bool:
        entry = self.script_entry
        if not isinstance(entry, MaaScript) or self.task_item is None:
            return False
        want = self.task_item.info.user_id
        for uid, user in entry.users.items():
            if not isinstance(user, MaaUser):
                continue
            if not user.info.enabled or user.info.remained_day == 0:
                continue
            if want not in (None, "", "-") and str(uid) != want:
                continue
            if user.info.mode == "脚本":
                return True
        return False

    async def prepare(self) -> None:
        entry = self.script_entry
        if not isinstance(entry, MaaScript):
            return
        root = Path(entry.info.path or "")
        maa_set_path = root / "config"
        temp_path = Path.cwd() / f"data/{entry.uid}/Temp"
        handle = self.game[2] if self.game is not None else None
        recover_native_config(
            temp_path, maa_set_path, expected_script_id=str(entry.uid)
        )
        commit_native_config_snapshot(
            temp_path, maa_set_path, script_id=str(entry.uid)
        )
        try:
            from ..features.backup.archive import archive_native_backup

            archive_native_backup(maa_set_path)
        except Exception as e:
            logger.warning(f"归档 MAA 原生配置失败（不阻断）: {e}")
        if self.task_context is not None and self.task_context.mode == TaskMode.AUTO_PROXY:
            try:
                await Config.get_stage()
            except Exception as e:
                logger.warning(f"刷新活动关卡信息失败: {e}")
        self.runtime = MaaRuntime(
            maa_set_path=maa_set_path,
            temp_path=temp_path,
            device=handle,
            begin_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.report_image_pairs = []

    async def spawn(self, child) -> None:
        if self.runtime is not None and hasattr(child, "runtime"):
            child.runtime = self.runtime
        try:
            await super().spawn(child)
        finally:
            self.report_image_pairs.extend(getattr(child, "report_image_pairs", ()))

    def expand_users(self, *, mode: TaskMode, enabled_user_ids: list[str]) -> list[str]:
        ids = super().expand_users(mode=mode, enabled_user_ids=enabled_user_ids)
        entry = self.script_entry
        if not isinstance(entry, MaaScript):
            return ids
        out: list[str] = []
        for uid_s in ids:
            user = entry.users.get(UUID(uid_s))
            if isinstance(user, MaaUser) and user.info.remained_day == 0:
                continue
            out.append(uid_s)
        return out

    async def final_task(self) -> None:
        await super().final_task()
        entry = self.script_entry
        if not isinstance(entry, MaaScript):
            return
        runtime = self.runtime
        if runtime is None:
            return
        temp_path = runtime.temp_path
        maa_set_path = runtime.maa_set_path
        if self.task_context is not None and self.task_context.mode == TaskMode.AUTO_PROXY:
            if runtime.device is not None:
                try:
                    await runtime.device.close()
                except Exception as e:
                    logger.warning(f"关闭模拟器失败: {e}")
            await self._push_proxy_result(entry, runtime.begin_time)
        keep = False
        if (
            self.task_context is not None
            and self.task_context.mode == TaskMode.SCRIPT_CONFIG
            and self.script_item is not None
        ):
            users = list(self.script_item.users.values())
            if users and users[0].info.status == "完成":
                live = entry.users.get(users[0].uid)
                if isinstance(live, MaaUser) and live.info.mode == "直控":
                    keep = True
        if temp_path.exists() and not keep:
            swap_in_dir(temp_path, maa_set_path)
        clear_native_config_snapshot(temp_path)
        self.runtime = None
        if self.script_item is not None and self.script_item.info.status != "异常":
            self.script_item.info.status = "完成"
            await self.script_item.commit()

    async def on_crash(self, exc: BaseException) -> None:
        await super().on_crash(exc)
        if self.script_item is not None:
            self.script_item.info.status = "异常"
            await self.script_item.commit()

    async def _push_proxy_result(self, entry: MaaScript, begin_time: str) -> None:
        from ..features.notify import (
            NOTIFY_SCREENSHOT_LIMIT,
            push_notification,
            screenshot_entries,
        )

        users = list(self.script_item.users.values()) if self.script_item else []
        over = sum(1 for u in users if u.info.status == "完成")
        name = entry.info.name or "空白"
        result = {
            "title": "自动代理任务报告",
            "script_name": name,
            "start_time": begin_time,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": over,
            "uncompleted_count": len(users) - over,
            "result": "\n".join(f"{u.info.name}: {u.info.result}" for u in users)
            or "用户未加载",
        }
        # 失败用户多了只取最后几张
        pairs = self.report_image_pairs[-NOTIFY_SCREENSHOT_LIMIT:]
        if pairs:
            result["screenshots"] = screenshot_entries(pairs)
        try:
            await push_notification(
                mode="代理结果",
                title=f"{datetime.now().strftime('%m-%d')} | {name}的自动代理任务报告",
                message=result,
                user_config=None,
                task_info=self.task_item,
                images=[image for _, image in pairs],
            )
        except Exception as e:
            logger.warning(f"推送代理结果时出现异常: {e}")
