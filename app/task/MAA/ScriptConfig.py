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
import shutil
import uuid
from copy import deepcopy
from pathlib import Path

from app.core.ws import Publisher, protocol
from app.models.config import MaaConfig, MaaUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.utils import ProcessManager, get_logger
from app.utils.io import read_file, write_file

from .AutoProxy import (
    _MAA_CONFIG_FILES,
    _repair_maa_task_queue,
    read_maa_config_with_fallback,
)
from .tools.backup_archive import (
    archive_mas_runtime_backup,
    mas_config_dir,
    read_overlay_values,
)

logger = get_logger("MAA 脚本设置")

# 配置会话注入的启动编排项：(文件, 路径, 注入值)。配置会话只让用户调设置，
# 不该自动跑任务、拉模拟器或拉游戏，所以这些项在会话期间强制关闭；会话结束
# 回写时逐项还原成会话前的值，绝不写进 base——它们是会话级的运行编排，
# 不是用户配置。StartGame 关掉后 MAA 打开就是可配置状态，用户不必先终止队列。
_SESSION_STARTUP_OVERRIDES: tuple[tuple[str, tuple[str, ...], object], ...] = (
    (
        "gui.new.json",
        ("Configurations", "Default", "Gui", "RuntimeSettings", "StartGame"),
        False,
    ),
    (
        "gui.new.json",
        ("Configurations", "Default", "Gui", "StartUpSettings", "RunDirectly"),
        False,
    ),
    (
        "gui.new.json",
        ("Configurations", "Default", "Gui", "StartUpSettings", "StartEmulator"),
        False,
    ),
    ("gui.json", ("Configurations", "Default", "Start.StartGame"), "False"),
    ("gui.json", ("Configurations", "Default", "Start.RunDirectly"), "False"),
    (
        "gui.json",
        ("Configurations", "Default", "Start.OpenEmulatorAfterLaunch"),
        "False",
    ),
    # 调起 MAA 的 GUI 必有人要操作界面，启动即最小化恒为关——否则用户自己
    # 设过"启动时最小化"的，配置会话打开就是缩在托盘里。gui.json 的
    # Start.MinimizeDirectly 与 gui.new.json 的 Gui.MinimizeOnStartup 是同一
    # 开关的新旧两通道（均为 MAA 真实键，native 池 3/3 实证），必须同时压住。
    # 会话级覆盖，回写前还原，不进 base。
    (
        "gui.json",
        ("Global", "Start.MinimizeDirectly"),
        "False",
    ),
    (
        "gui.new.json",
        ("Gui", "MinimizeOnStartup"),
        False,
    ),
)


def _dig(doc: dict, path: tuple[str, ...]) -> tuple[dict, str] | None:
    """按路径取出 (父容器, 末键)；中间层不存在时返回 None。"""

    node: object = doc
    for key in path[:-1]:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if not isinstance(node, dict):
        return None
    return node, path[-1]


def _apply_session_startup_overrides(
    docs: dict[str, dict],
) -> dict[str, list[tuple[tuple[str, ...], object | None]]]:
    """把启动编排项强制成配置会话的值，返回各项的会话前原值（供回写还原）。"""

    restore: dict[str, list[tuple[tuple[str, ...], object | None]]] = {}
    for name, path, value in _SESSION_STARTUP_OVERRIDES:
        doc = docs.get(name)
        if doc is None:
            continue
        located = _dig(doc, path)
        if located is None:
            continue
        parent, key = located
        restore.setdefault(name, []).append((path, deepcopy(parent.get(key))))
        parent[key] = value
    return restore


def _restore_session_startup_overrides(
    docs: dict[str, dict],
    restore: dict[str, list[tuple[tuple[str, ...], object | None]]],
) -> None:
    """把配置会话强制过的启动编排项还原为会话前的值。

    用户在 MAA 里改动这些项不会保留（它们是会话级编排，不进 base），
    其余一切用户修改原样写回。
    """

    for name, entries in restore.items():
        doc = docs.get(name)
        if doc is None:
            continue
        for path, original in entries:
            located = _dig(doc, path)
            if located is None:
                continue
            parent, key = located
            if original is None:
                parent.pop(key, None)
            else:
                parent[key] = original


class ScriptConfigTask(TaskExecuteBase):
    """脚本设置模式

    会话包络（下发源 + 回写目标）与运行下发同一套 owner 规则（脚本态共享
    Default、用户态独立目录），见 :meth:`_mas_owner`。view_only=True 时为
    查看会话：只读预览（如「查看历史备份」）——用户级会话下发的 owner 目录
    即刚恢复的备份（所见即备份），脚本级会话跳过下发（原生目录即备份）；
    结束不回写 MAS 配置，安装 config/ 由 manager 的任务前快照还原（临时
    注入，看完还原）。
    """

    _maa_config_baseline: dict[str, dict] | None = None
    """set_maa 写盘快照；final_task 以此甄别用户的 GUI 修改。"""

    _session_startup_restore: (
        dict[str, list[tuple[tuple[str, ...], object | None]]] | None
    ) = None
    """配置会话强制过的启动编排项及其会话前原值，回写时逐项还原。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaConfig,
        user_config: MultipleConfig[MaaUserConfig],
        emulator_manager: DeviceBase,
        view_only: bool = False,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        # 查看会话：只读预览（如「查看历史备份」），结束不回写 MAS 配置
        self.view_only = view_only

    async def prepare(self):

        self.maa_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.maa_root_path = Path(self.script_config.get("Info", "Path"))
        self.maa_set_path = self.maa_root_path / "config"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"

    async def main_task(self):

        await self.prepare()

        await self.set_maa()
        logger.info(f"启动MAA进程: {self.maa_exe_path}")
        self.wait_event.clear()
        await self.maa_process_manager.open_process(self.maa_exe_path)
        await self.wait_event.wait()

    def _mas_owner(self) -> str | None:
        """本会话的 MAS 配置目录 owner；直控/无法解析时返回 ``None``。

        与运行下发（AutoProxy ``set_maa``）同一套来源规则——会话的下发与
        回写此前硬编码用户目录，脚本态用户的会话改动运行时根本不读（改了
        白改），配置备份也因此采不到会话现场；现对齐运行态。直控用户没有
        MAS 托管配置目录（对齐 MaaEnd 的「直控无 mas 池」），返回 ``None``。
        """

        user_id = self.cur_user_item.user_id
        if user_id == "Default":
            return "Default"
        mode = str(
            self.user_config[uuid.UUID(user_id)].get("Info", "Mode") or ""
        ).strip()
        if mode == "直控":
            return None
        return user_id if mode == "用户" else "Default"

    async def set_maa(self):
        """配置MAA运行参数"""

        logger.info(f"开始配置MAA运行参数: 设置脚本 {self.cur_user_item.user_id}")

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)

        # 查看会话的脚本级入口：原生目录即所选备份，跳过下发与注入
        if self.view_only and self.cur_user_item.user_id == "Default":
            logger.info("MAA 查看会话跳过配置下发: 原生目录即所选备份")
            return

        # 直控会话：安装目录原生配置即现场，MAS 零写入（含归档）；MAA GUI
        # 内的编辑由本体落盘并保留
        if self._mas_owner() is None:
            logger.info("MAA 直控会话: 直接使用安装目录原生配置, MAS 零写入")
            return

        # 下发前归档 MAS 配置到用户池（下发源，会话保存会覆盖它；带页面
        # 核心字段侧车，指纹去重，失败不阻断会话）。native 池由
        # manager.prepare 在任务级一次性归档
        target_user_id = self.cur_user_item.user_id
        owner = self._mas_owner()
        mas_dir = mas_config_dir(self.script_info.script_id, owner)
        overlay = (
            read_overlay_values(self.user_config[uuid.UUID(target_user_id)])
            if target_user_id != "Default"
            else None
        )
        archive_mas_runtime_backup(
            self.script_info.script_id,
            target_user_id,
            mas_dir,
            overlay=overlay,
            # 备份标注来源：tri_state 池跨来源恢复靠它切回
            mode="用户" if owner == target_user_id else "脚本",
        )

        if mas_dir.is_dir() and any(mas_dir.iterdir()):
            shutil.copytree(mas_dir, self.maa_set_path, dirs_exist_ok=True)

        # base 缺失/损坏时退回 MAA 自带 .bak 或骨架：骨架不含 TaskQueue，
        # MAA 加载时用内存默认队列填空——默认队列的唯一生成器是 MAA 本体。
        gui_set = read_maa_config_with_fallback(self.maa_set_path, "gui.json")
        gui_new_set = read_maa_config_with_fallback(self.maa_set_path, "gui.new.json")

        # 多配置使用默认配置（gui.new.json 的方案列表可能与 gui.json 不一致，缺失当前方案时保留其自有 Default）
        if gui_set["Current"] != "Default":
            gui_set["Configurations"]["Default"] = gui_set["Configurations"][
                gui_set["Current"]
            ]
            gui_new_configurations = gui_new_set.setdefault("Configurations", {})
            if gui_set["Current"] in gui_new_configurations:
                gui_new_configurations["Default"] = gui_new_configurations[
                    gui_set["Current"]
                ]
            gui_new_configurations.setdefault("Default", {})
            gui_set["Current"] = "Default"

        # 各配置部分的引用
        global_set = gui_set["Global"]

        # GUI 直接展示 base（MAA 自己的日常任务配置）：队列成员与顺序都归 MAA 与
        # 用户所有，MAS 不校对不重建；只修 $type 位置，否则 MAA 读不进整个文件。
        source_queue = gui_new_set["Configurations"]["Default"].get("TaskQueue", [])
        if not isinstance(source_queue, list):
            source_queue = []
        gui_new_set["Configurations"]["Default"]["TaskQueue"] = _repair_maa_task_queue(
            source_queue
        )

        # 配置会话的启动编排：不自动跑任务、不拉模拟器、不拉游戏，让 MAA 打开就是
        # 可配置状态（用户不必先终止队列）。这些是会话级覆盖，回写时还原成原值。
        self._session_startup_restore = _apply_session_startup_overrides(
            {"gui.json": gui_set, "gui.new.json": gui_new_set}
        )

        # 关闭所有定时
        for i in range(1, 9):
            global_set[f"Timer.Timer{i}"] = "False"  # OLD: 即将移除
        # NEW: Timers.List[*].IsEnabled = false
        if "Timers" not in gui_new_set:
            gui_new_set["Timers"] = {}
        if "List" not in gui_new_set["Timers"]:
            gui_new_set["Timers"]["List"] = []
        for timer in gui_new_set["Timers"].get("List", []):
            if isinstance(timer, dict):
                timer["IsEnabled"] = False

        # 更新配置
        global_set["VersionUpdate.ScheduledUpdateCheck"] = "False"  # OLD: 即将移除
        global_set["VersionUpdate.AutoDownloadUpdatePackage"] = "False"  # OLD: 即将移除
        global_set["VersionUpdate.AutoInstallUpdatePackage"] = "False"  # OLD: 即将移除
        # NEW:
        gui_new_set.setdefault("Update", {})["CheckOnSchedule"] = False
        gui_new_set.setdefault("Update", {})["AutoDownloadUpdatePackage"] = False
        gui_new_set.setdefault("Update", {})["AutoInstallUpdatePackage"] = False

        (self.maa_set_path / "gui.json").write_text(  # OLD: 即将移除
            json.dumps(gui_set, ensure_ascii=False, indent=4),
            encoding="utf-8",  # OLD: 即将移除
        )  # OLD: 即将移除
        write_file(self.maa_set_path / "gui.new.json", gui_new_set)
        # 会话基线：final_task 以此甄别用户在 MAA GUI 里的真实修改，
        # 不把 MAA 保存时自带的原生默认任务固化进 MAS 存档
        self._maa_config_baseline = {
            "gui.json": deepcopy(gui_set),
            "gui.new.json": deepcopy(gui_new_set),
        }
        logger.success(f"MAA运行参数配置完成: 设置脚本 {self.cur_user_item.user_id}")

    async def final_task(self):

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)

        # 查看会话：只读预览，不把安装 config/ 回写用户目录（安装现场由
        # manager 的任务前快照还原）；GUI 内的改动一律丢弃
        if self.view_only:
            logger.success("MAA 查看结束（只读，不回写配置）")
            self.cur_user_item.status = "完成"
            return

        # 直控会话：MAS 零写入，安装目录配置由本体保存并保留，不回写 MAS 目录
        if self._mas_owner() is None:
            logger.success("MAA 直控配置已由脚本原生 GUI 保存")
            self.cur_user_item.status = "完成"
            return

        mas_dir = mas_config_dir(self.script_info.script_id, self._mas_owner())

        # GUI 展示的就是 base，用户在 MAA 里改完落盘的文件即新的 base：整份写回
        # 即可，不需要按身份归并（那是"GUI 展示映射层"时代的产物）。队列同样原样
        # 接受——这份文件刚被 MAA 自己写出并读通过，MAS 没有立场替它判定合法。
        saved = False
        for name in _MAA_CONFIG_FILES:
            try:
                current = read_file(self.maa_set_path / name)
            except (OSError, json.JSONDecodeError) as e:
                logger.opt(exception=True).warning(
                    f"读取 MAA 配置以回写失败({name}): {e}"
                )
                continue
            if not current:
                # MAA 未写盘(如被强杀)，GUI 改动无从谈起，存档保持 set_maa 下发态
                continue
            # 先还原会话强制过的启动编排项：它们是会话级覆盖，不能写进 base
            entries = (self._session_startup_restore or {}).get(name)
            if entries:
                _restore_session_startup_overrides({name: current}, {name: entries})
            for configurations in (current.get("Configurations") or {}).values():
                if isinstance(configurations, dict):
                    queue = configurations.get("TaskQueue")
                    if isinstance(queue, list):
                        configurations["TaskQueue"] = _repair_maa_task_queue(queue)
            write_file(mas_dir / name, current)
            saved = True
        if not saved:
            logger.info("MAA 配置回写: 无落盘内容, 存档保持不变")

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"脚本设置任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"脚本设置任务出现异常: {e}"),
        )
