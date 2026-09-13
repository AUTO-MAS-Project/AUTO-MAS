#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ZZZ-OD 原生 GUI 配置会话（「在一条龙内配置」入口，与 MAS 字段双向联动）。

用户配置界面只覆盖高频字段，配队等复杂配置由用户在 zzz-od 原生界面完成。
会话以 MAS 用户字段为基线：打开前把字段注入绑定槽（GUI 所见即本页配置），
关闭时把 GUI 内的任务编排与账号改动回读到 MAS 字段——两侧始终一致；
配队等 MAS 不管的内容持久留在槽里。目标为 Default（脚本级）时直接无参数
拉起 GUI 编辑当前原生配置。
"""

import asyncio
import json
import uuid
from contextlib import suppress
from pathlib import Path

from app.core.ws import Publisher, protocol
from app.models.config import ZzzOdConfig, ZzzOdUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.utils import ProcessInfo, ProcessManager, get_logger

from .AutoProxy import (
    collect_used_slot_idxs,
    ensure_user_slot,
    find_launcher_exe,
    inject_user_fields,
    parse_user_apps,
)
from .tools import (
    archive_mas_config_backup,
    archive_onedragon_backup,
    collect_mas_user_info,
    find_active_instance,
    instance_dir,
    normalize_app_group_entries,
    read_app_group,
    read_game_account,
    restore_instance_view,
    set_active_instance,
    write_instance_view,
)

logger = get_logger("ZZZ-OD 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """拉起 zzz-od 原生 GUI；用户会话以 MAS 字段为基线，关闭后回读改动。

    view_only=True 时为查看会话：只读预览（槽内即恢复的历史备份），
    不注入基线、不回读字段，用于「查看配置」等预览场景。

    instance_idx 仅脚本级会话（直控）生效：会话窗口把原生注册表的活跃
    实例临时切到正在编辑的实例（GUI 打开即所见实例），结束还原原活跃，
    全程只动 one_dragon.yml 的 active 标志（纯配置操作）。
    """

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: ZzzOdConfig,
        user_config: MultipleConfig[ZzzOdUserConfig],
        view_only: bool = False,
        instance_idx: int | None = None,
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")
        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        # 查看会话：只读预览（如「查看历史备份」），不注入基线也不回读字段
        self.view_only = view_only
        # 直控指定的会话实例（用户会话忽略；脚本级会话临时切活跃）
        self._session_native_idx = instance_idx
        # 会话前的原生活跃实例（有临时切换时结束后还原）
        self._original_active_idx: int | None = None
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        # 目标用户（user_id 可解析且在 UserData 中）；Default 等伪用户为 None
        self._target_uid: uuid.UUID | None = None
        self.cur_user_config: ZzzOdUserConfig | None = None
        with suppress(ValueError):
            uid = uuid.UUID(self.cur_user_item.user_id)
            if uid in self.user_config:
                self._target_uid = uid
                self.cur_user_config = self.user_config[uid]
        self.process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.crashed = False
        self.root_path = Path(self.script_config.get("Info", "RootPath"))
        self.exe_path = find_launcher_exe(self.root_path)
        # 用户会话使用的绑定槽（回读用；脚本级会话为 None）
        self._session_slot: int | None = None

    async def main_task(self) -> None:
        # 用户会话：合成注册表视图（仅本槽，active=本槽）+ 以 MAS 字段为基线
        # 注入绑定槽（GUI 所见即本页配置，不清运行记录）；关闭时回读 GUI 改动。
        # 查看会话（view_only）跳过基线注入——槽里是刚恢复的历史备份，所见即备份；
        # 也跳过 MAS 槽归档（恢复动作自身已归档恢复前内容）
        if self.cur_user_config is not None:
            restore_instance_view(self.root_path)  # 闪退自愈
            # 归档点：一条龙原生配置快照——必须在 ensure_user_slot（可能注册
            # 新槽）与合成视图写入之前，捕获未被本次会话触碰的原生状态
            try:
                archive_onedragon_backup(self.root_path)
            except Exception as e:
                logger.opt(exception=True).warning(f"归档 zzz-od 原生配置快照失败: {e}")
            used = collect_used_slot_idxs(exclude_uids={self._target_uid})
            slot = await ensure_user_slot(self.root_path, self.cur_user_config, used)
            self._session_slot = slot
            write_instance_view(
                self.root_path,
                [(slot, f"MAS-{self.cur_user_config.get('Info', 'Name')}")],
                active_idx=slot,
            )
            if self.view_only:
                logger.info(
                    f"启动 zzz-od 原生查看: {self.exe_path} (用户绑定槽 {slot:02d}, "
                    f"只读预览，不注入不回读)"
                )
            else:
                # MAS 用户槽快照（含配队等全部内容），供配置恢复——统一入口
                # 会先物化本页账号+编排进槽（它们只存在 UserData，槽要会话
                # 注入才带上；直接快照会漏掉，恢复会把本页字段清空）
                if instance_dir(self.root_path, slot).is_dir():
                    archive_mas_config_backup(
                        self.script_info.script_id,
                        slot,
                        instance_dir(self.root_path, slot),
                        self.cur_user_config,
                        meta=collect_mas_user_info(self.cur_user_config),
                    )
                inject_user_fields(
                    self.root_path,
                    slot,
                    self.cur_user_config,
                    parse_user_apps(self.cur_user_config),
                )
                logger.info(
                    f"启动 zzz-od 原生设置: {self.exe_path} (用户绑定槽 {slot:02d}, "
                    f"以 MAS 配置为基线)"
                )
        else:
            # 脚本级会话（直控「在一条龙内配置」入口）：先自愈崩溃残留的
            # 合成视图，保证拉起的是完整原生实例列表，不做隔离与注入。
            # 指定了会话实例时把原生活跃临时切过去（GUI 打开即正在编辑的
            # 实例），原活跃在会话结束还原；目标不存在则跳过不切换
            restore_instance_view(self.root_path)
            if self._session_native_idx is not None:
                active = find_active_instance(self.root_path)
                self._original_active_idx = (
                    int(active["idx"]) if active is not None else None
                )
                if self._original_active_idx != self._session_native_idx:
                    with suppress(Exception):
                        set_active_instance(self.root_path, self._session_native_idx)
                        logger.info(
                            f"会话窗口临时切换活跃实例: "
                            f"{self._original_active_idx} → {self._session_native_idx}"
                        )
            logger.info(f"启动 zzz-od 原生设置: {self.exe_path}")
        self.cur_user_item.status = "运行"
        # 无参数启动 = GUI 模式；启动器要求管理员权限，elevated 避免二次 UAC
        await self.process_manager.open_process(
            self.exe_path,
            target_process=ProcessInfo(
                name=self.exe_path.name,
                exe=str(self.exe_path),
                cmdline=None,
            ),
            elevated=True,
        )
        await self.wait_event.wait()

    async def _readback_user_fields(self, slot: int) -> None:
        """把 GUI 会话落盘的账号字段与任务编排回读到 MAS 用户字段。

        - 区服/路径/语言/B服名：无条件回读（客观字段，槽值即真相）；
        - 账号/密码：槽值非空才回读（留空=沿用登录态语义，避免清空被读回）；
        - 任务编排：取 ``_group.yml`` 全量条目顺序（含未启用项）整表进 AppList
          （运行侧 parse_user_apps 只消费启用项，未启用项原位保留顺序）。
        """

        cfg = self.cur_user_config
        if cfg is None:
            return
        slot_dir = instance_dir(self.root_path, slot)
        account = read_game_account(slot_dir)
        await cfg.set("Game", "GameRegion", str(account.get("game_region") or "cn"))
        await cfg.set("Game", "GamePath", str(account.get("game_path") or ""))
        await cfg.set("Game", "GameLanguage", str(account.get("game_language") or "cn"))
        await cfg.set(
            "Game",
            "BilibiliAccountName",
            str(account.get("bilibili_account_name") or ""),
        )
        if str(account.get("account") or "").strip():
            await cfg.set("Game", "Account", str(account.get("account")))
        if str(account.get("password") or "").strip():
            await cfg.set("Game", "Password", str(account.get("password")))
        all_apps = normalize_app_group_entries(read_app_group(slot_dir))
        await cfg.set("OneDragon", "AppList", json.dumps(all_apps, ensure_ascii=False))
        logger.info(
            f"绑定槽 {slot:02d} 会话改动已回读用户配置 (任务 {len(all_apps)} 项)"
        )

    def _restore_native_active(self) -> None:
        """会话结束还原会话前的原生活跃实例（仅做过临时切换时）。"""

        if self._original_active_idx is None:
            return
        with suppress(Exception):
            set_active_instance(self.root_path, self._original_active_idx)
            logger.info(
                f"会话结束还原活跃实例: {self._session_native_idx} → "
                f"{self._original_active_idx}"
            )
        self._original_active_idx = None

    async def final_task(self) -> None:
        self.wait_event.set()
        # 进程清掉前先回读：GUI 内的任务编排/账号改动写回 MAS 字段（查看会话跳过）
        readback_failed = False
        if self._session_slot is not None and not self.view_only:
            try:
                await self._readback_user_fields(self._session_slot)
            except Exception as e:
                readback_failed = True
                logger.opt(exception=True).warning(f"回读 zzz-od 会话改动失败: {e}")
        await self._kill_processes()
        # GUI 已退出，恢复原生注册表与会话前的原生活跃实例
        try:
            restore_instance_view(self.root_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"恢复 zzz-od 原生注册表失败: {e}")
        self._restore_native_active()
        if self.crashed:
            return
        if readback_failed:
            # GUI 改动没能写回 MAS 字段：两侧已不一致，不能报成功
            self.cur_user_item.status = "异常"
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error",
                    message="zzz-od 会话改动回读失败，MAS 用户字段未更新，请重新打开配置检查",
                ),
            )
            return
        if self.view_only:
            logger.success("zzz-od 原生查看结束（只读，不回读字段）")
        else:
            logger.success("zzz-od 原生配置已由 GUI 保存")
        self.cur_user_item.status = "完成"

    async def on_crash(self, e: Exception) -> None:
        self.crashed = True
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"zzz-od 设置任务出现异常: {e}")
        with suppress(Exception):
            await self._kill_processes()
        with suppress(Exception):
            restore_instance_view(self.root_path)
        self._restore_native_active()
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error", message=f"zzz-od 设置任务出现异常: {e}"
            ),
        )

    async def _kill_processes(self) -> None:
        try:
            await self.process_manager.kill()
        except Exception as e:
            logger.opt(exception=True).warning(f"通过进程管理器中止 zzz-od 失败: {e}")

        try:
            await System.kill_process(self.exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止 zzz-od 进程失败: {e}")
