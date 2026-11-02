#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
import asyncio
import json
import time
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.config import ConfigCollection
from app.core import Notify, Publisher
from app.core.history import aggregate_data
from app.core.notify.task_content import (
    build_user_statistics_payload as build_user_statistics_payload,
)
from app.core.ws import protocol
from app.models.config import OkwwConfig, OkwwUserConfig
from app.models.notification import LocalNotice
from app.models.schema import HistoryAggregationItem, HistoryWrite, WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, UserItem
from app.services import System
from app.services import wuthering_waves as _service_wuthering_waves
from app.services.common.wuthering_waves import (
    updater as _service_wuthering_waves_updater,
)
from app.task.base import ScriptAutoProxyBase
from app.task.proxy_helpers import (
    kill_pids,
    push_dispatch_log,
    split_args,
)
from app.utils import (
    LOG_TYPE_NORMAL,
    LogMonitor,
    ProcessInfo,
    ProcessManager,
    get_logger,
    is_process_alive,
    is_process_running,
    log_box,
)
from app.utils import constants as _utils_constants
from app.utils import i18n as _utils_i18n
from app.utils import io as _utils_io
from app.utils.common.log import sources as log_source

from . import push_log as _push_log
from .tools import async_switch_account
from .tools.backup_archive import (
    archive_mas_runtime_backup,
    mas_config_dir,
    owner_for_mode,
    read_overlay_values,
)
from .tools.launcher_start import (
    async_start_game_via_launcher,
    detect_game_maintenance_text,
    find_client_pids,
    find_game_pids,
    find_launcher_pids,
    has_launcher_window,
)

logger = get_logger("OK-WW 自动代理")

# 鸣潮 PC 客户端窗口进程名固定，MAS 接管启动前据此避免重复拉起
_WUWA_CLIENT_PROCESS = "Client-Win64-Shipping.exe"

# 直启客户端时 MAS 内置的启动参数：实测可绕过官方启动器校验直接进入游戏，
# 与用户自配的 Game.Arguments 并存不冲突
_WUWA_DIRECT_LAUNCH_ARG = "-krqlv=hd"

# 多用户切换时等待旧游戏完全退出的上限（秒）：
# ok-ww 恒带 `-e` 自退游戏，客户端进程退出不是瞬时的；若不等待完全退出，
# 下个用户会把「正在退出的残影窗口」误判为可用游戏而复用，导致窗口句柄失效。
_GAME_EXIT_WAIT_SECONDS = 90


# ── okww 专项硬编码（不存 ConfigItem，随 MAS 版本同步）──────────────
# 对齐 MaaEnd：专项内置日志片段，Okww 不向用户暴露成功/失败日志关键词配置。
# 「游戏更新成功」是环境变更而非脚本错误，命中后至少保证再跑一轮（见 main_task）。
_OKWW_GAME_UPDATED_LOG = "游戏更新成功, 游戏即将重启"
_OKWW_GAME_UPDATED_MSG = "游戏更新成功，即将重启任务"
_OKWW_BUILTIN_FATAL: tuple[tuple[str, str], ...] = (
    (_OKWW_GAME_UPDATED_LOG, _OKWW_GAME_UPDATED_MSG),
    ("info_set 错误", "OK-WW 流程产生错误，请检查游戏状态"),
)
# 窗口丢失的日志有两条形态：hwnd>0 但 IsWindow(hwnd) 返回 0 时 exists 是 int → `connected:0`；
# hwnd<=0 时 exists 仍是 bool → `connected:False`。两种都要认。
# 它不进内置 fatal：ok-ww 成功后按 -e 关游戏（stop_hwnd）同样会打 connected:0，只比完成日志晚
# 约 5s；日志监控若跨过这 5s，两行会落进同一批，故只在没有完成日志时判未连接（见 check_log）。
_OKWW_DISCONNECT_LOG: tuple[str, ...] = ("connected:False", "connected:0")
_OKWW_DISCONNECT_MSG = "OK-WW 未连接游戏客户端"
# 成功只认任务级完成日志：ok-ww 的 DailyTask 正常跑完（run() 末尾）才会打印；
# 窗口关闭日志（Window closed exit_event.is_set）在任何退出路径都会出现，不能作为完成依据。
_OKWW_SUCCESS_LOG = "Daily Task Completed"

# ok-ww 项目结构固定相对路径（从 RootPath 派生，不依赖用户存储值）
# ⚠️ 与前端 OkwwScriptEdit.vue 的 OKWW_EXE_NAME 保持同步，改这里时需同步改前端
_OKWW_REL_EXE = "ok-ww.exe"
_OKWW_REL_APP_JSON = "data/apps/ok-ww/app.json"
_OKWW_REL_CONFIG_DIR = "data/apps/ok-ww/working/configs"
_OKWW_REL_LOG_FILE = "data/apps/ok-ww/working/logs/ok-script.log"
_OKWW_REL_PYTHONW = "data/apps/ok-ww/python/pythonw.exe"
_OKWW_TRACK_PROCESS_NAME = "pythonw.exe"
_OKWW_UPDATE_METHOD = "AUTO_UPDATE"
# ok-ww 只调度日常任务（-t 1 = DailyTask）；账号切换由 MAS 侧 account_switch
# 实现，不再暴露上游 MultiAccountDailyTask（其 -t 序号与 MAS 面板语义不符）。
_OKWW_TASK_INDEX = 1
_OKWW_LOG_TIME_START = 1
_OKWW_LOG_TIME_END = 23
_OKWW_LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S,%f"


def _okww_config_base(raw: object) -> str:
    """读取 OK-WW 配置来源（base 三态），并兼容旧版字面量。"""

    return _utils_constants.normalize_base_source(raw) or _utils_constants.BASE_SHARED


def _okww_mas_config_dir(script_id: str, user_id: str, base: str) -> Path:
    base = _okww_config_base(base)
    owner = owner_for_mode(base, user_id)
    if owner is None:
        raise ValueError("原生来源不使用 MAS 全量配置目录")
    return mas_config_dir(script_id, owner)


def _update_json(path: Path, values: dict[str, object]) -> None:
    data: object = {}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8").removeprefix("\ufeff"))
    if not isinstance(data, dict):
        raise ValueError(f"OK-WW 配置文件格式错误: {path.name}")
    data.update(values)
    _utils_io.write_file(path, data)


def _configure_okww_launcher(script_root_path: Path) -> None:
    """补齐 OK-WW 启动器设置（缺省才补、无事零写入）。

    只补 ``auto_start`` / ``update_method`` 两项启动器默认值，不改动用户安装
    时选择的更新渠道（``current_profile`` 由 ok-ww 安装包决定，与游戏区服
    无关，MAS 不接管）。
    """
    app_json_path = script_root_path / _OKWW_REL_APP_JSON
    if not app_json_path.is_file():
        return

    app_config = json.loads(
        app_json_path.read_text(encoding="utf-8").removeprefix("\ufeff")
    )
    if not isinstance(app_config, dict):
        raise ValueError("OK-WW app.json 格式错误")

    changed = False
    if app_config.get("auto_start") is not True:
        app_config["auto_start"] = True
        changed = True
    if "update_method" not in app_config:
        app_config["update_method"] = _OKWW_UPDATE_METHOD
        changed = True
    if not changed:
        return

    _utils_io.write_file(app_json_path, app_config)
    logger.info("已补齐 OK-WW 启动器默认设置")


class AutoProxyTask(ScriptAutoProxyBase[OkwwConfig, OkwwUserConfig]):
    """OK-WW 自动代理：拼 `-t N -e` 启动参数并监控日志"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkwwConfig,
        user_config: ConfigCollection[OkwwUserConfig],
        game_manager: ProcessManager | None,
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.game_manager = game_manager

        self.cur_user_item: UserItem = self.script_info.user_list[
            self.script_info.current_index
        ]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: OkwwUserConfig = self.user_config[self.cur_user_uid]
        self.cur_user_log: LogRecord | None = None
        self.launcher_path: Path | None = None
        self.game_process_path: Path | None = None
        # check() 阶段发现的寻址兜底提示：调度台日志会在 main_task 每轮开头被
        # 整体重置，check() 里直接推会被清屏，改存到这里在启动流程内补推
        self._fallback_notice: str | None = None
        self.okww_process_manager: ProcessManager | None = None
        self.wait_event: asyncio.Event | None = None
        self.script_root_path: Path | None = None
        self.script_exe_path: Path | None = None
        self.script_target_process_info: ProcessInfo | None = None
        self.script_log_path: Path | None = None
        self.log_monitor: LogMonitor | None = None
        # log_box：用户级「是否采集节点详情」关闭时不创建（prepare 按配置启停）
        self._log_source: log_source.LogSource | None = None
        self._log_pipeline: log_box.LogPipeline | None = None
        self._log_user: UserItem | None = None
        self._log_translator: _utils_i18n.PoTranslator | None = None
        self._log_failed = False
        self._log_close_task: asyncio.Task[None] | None = None
        self.script_config_path: Path | None = None

    async def check(self) -> str:
        root = self.script_config.Info.RootPath
        if root is None or not root.is_dir():
            return "请设置ok-ww脚本路径"
        if not (root / _OKWW_REL_EXE).is_file():
            return "请设置ok-ww脚本路径"
        if not (root / _OKWW_REL_APP_JSON).is_file():
            return "请设置ok-ww脚本路径"
        # 启动检查早于每日重置，旧日期的次数不参与今日上限判断。
        curdate = datetime.now(tz=_utils_constants.UTC4).strftime("%Y-%m-%d")
        proxy_times = (
            self.cur_user_config.Data.ProxyTimes
            if self.cur_user_config.Data.LastProxyDate.strftime("%Y-%m-%d") == curdate
            else 0
        )
        # 单独运行脚本是用户主动指定的一次性运行，不受单日代理次数上限约束
        if (
            self.task_info.is_queue_task
            and self.script_config.Run.ProxyTimesLimit != 0
            and proxy_times >= self.script_config.Run.ProxyTimesLimit
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"
        if self.cur_user_config.Info.RemainedDay == 0:
            self.cur_user_item.status = "跳过"
            return "用户剩余天数为 0, 跳过该用户"

        if self.script_config.Game.Enabled:
            launcher_path = Path(str(self.script_config.Game.Path or "").strip())
            client_path = str(self.script_config.Game.ClientPath or "").strip()
            if client_path:
                # 手动指定了客户端程序：以指定值为准，两种启动方式都认它（启动器
                # 态只用它做已运行检测与收尾，更精确）；启动器路径仅服务 MAS 前置
                # 更新（不可用时运行期降级跳过，不阻断启动）。
                # 文件名必须与客户端进程名完全一致（含大小写）：已运行检测、
                # 进程搜索与按名兜底全部是精确匹配，指向其它名字的 exe 会让
                # 这几条链同时失效
                client_exe = Path(client_path)
                if not client_exe.is_file():
                    return "所选鸣潮客户端程序不存在，请重新选择"
                if client_exe.name != _WUWA_CLIENT_PROCESS:
                    return (
                        f"所选程序不是鸣潮客户端（应为 {_WUWA_CLIENT_PROCESS}），"
                        "请重新选择"
                    )
                self.game_process_path = client_exe
            # 启动器失效时按注册表登记找回（官方启动器自己写的安装根）。
            # 直启态已手填客户端时启动器只服务更新，不必为它打扰用户；
            # 但启动器态没有启动器就拉不起游戏，即使已填客户端也必须尝试找回
            launcher_valid = (
                launcher_path.is_file() and launcher_path.name.lower() == "launcher.exe"
            )
            if not launcher_valid and (
                self.game_process_path is None or self._game_launch_type() == "Launcher"
            ):
                # 命中结果必须告诉用户：静默换到另一份安装会让人不知情
                fallback = await asyncio.to_thread(
                    _service_wuthering_waves.discover_wuthering_waves_fallback,
                    str(self.cur_user_config.Info.Resource),
                )
                if fallback.launcher_path is not None:
                    launcher_path = fallback.launcher_path
                    # 不能在这里直接推调度台：main_task 每轮开头会重置日志把它
                    # 清掉，存下来在启动流程内（重置之后）补推一次
                    self._fallback_notice = (
                        f"已按注册表找回鸣潮启动器"
                        f"（{launcher_path.as_posix()}），"
                        "请更新脚本配置中的启动器路径"
                    )
                elif (
                    fallback.process_path is not None
                    and self._game_launch_type() == "Client"
                ):
                    # 只有直启态吃客户端兜底：启动器态没有启动器就拉不起游戏，
                    # 报错文案会引导用户改用直启或重新导入启动器
                    self.game_process_path = fallback.process_path
                    self._fallback_notice = (
                        f"已按注册表找回鸣潮客户端"
                        f"（{self.game_process_path.as_posix()}），"
                        "请在脚本配置的「游戏客户端」中填入该路径"
                    )
            self.launcher_path = launcher_path
            if self._game_launch_type() == "Launcher" and (
                not launcher_path.is_file()
                or launcher_path.name.lower() != "launcher.exe"
            ):
                # 启动器态必须由启动器拉起游戏，没有它整条链无从谈起；
                # 直启态可以只靠手动指定的客户端文件，不在这里拦
                return (
                    "未找到鸣潮官方启动器：请重新导入官方启动器，"
                    "或改用「直接启动」并手动选择游戏客户端文件"
                )
            if self.game_process_path is None:
                # 客户端 exe 由启动器路径解码（两种启动方式都走这里）
                try:
                    self.game_process_path = (
                        _service_wuthering_waves.resolve_wuthering_waves_process_path(
                            launcher_path
                        )
                    )
                except (FileNotFoundError, ValueError) as e:
                    if self._game_launch_type() == "Client":
                        # 直启侧还有「直接指定客户端文件」这条自足的路，别把用户
                        # 打发去重新导入启动器
                        return (
                            "未找到鸣潮客户端程序：请在直启模式下选择游戏客户端"
                            "文件，或重新导入官方启动器以自动定位"
                        )
                    # 启动器态不需要客户端 exe 也能拉起游戏：解不出来只影响已运行
                    # 检测与收尾（改按「名称 + 启动器安装根目录树内」口径），不拦停
                    logger.warning(
                        f"未解析出鸣潮客户端程序，已运行检测与收尾改按进程名处理: {e}"
                    )

        config_base = _okww_config_base(self.cur_user_config.Info.Base)
        if config_base == _utils_constants.BASE_NATIVE:
            config_dir = root / _OKWW_REL_CONFIG_DIR
            if not config_dir.is_dir() or not any(
                item.is_file() for item in config_dir.rglob("*")
            ):
                return "未找到 OK-WW 脚本原有配置，请先在 OK-WW 中保存设置"
        else:
            try:
                from .tools.config_dir import ensure_user_config_dir

                await ensure_user_config_dir(
                    script_config=self.script_config,
                    user_id=str(self.cur_user_uid),
                    base=config_base,
                )
            except FileNotFoundError as e:
                logger.warning(f"初始化 OK-WW 用户默认配置失败: {e}")
                return str(e)
            except (OSError, TypeError, ValueError) as e:
                logger.warning(f"初始化 OK-WW 用户默认配置失败: {e}")
                return "无法读取 OK-WW 默认配置，请检查 OK-WW 脚本路径"
        return "Pass"

    async def prepare(self):
        self.okww_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now().astimezone()

        # ── 所有 Script 路径从 RootPath 实时派生，不依赖 ConfigItem 存储值 ──
        script_root_path = self.script_config.Info.RootPath
        if script_root_path is None:
            raise ValueError("RootPath未配置，请检查路径设置")
        self.script_root_path = script_root_path
        self.script_exe_path = self.script_root_path / _OKWW_REL_EXE

        self.script_target_process_info = ProcessInfo(
            name=_OKWW_TRACK_PROCESS_NAME,
            exe=str(self.script_root_path / _OKWW_REL_PYTHONW),
            cmdline=None,
        )

        self.script_log_path = self.script_root_path / _OKWW_REL_LOG_FILE

        self.log_time_range = (_OKWW_LOG_TIME_START - 1, _OKWW_LOG_TIME_END)
        self.log_time_format = _OKWW_LOG_TIME_FORMAT
        self.log_monitor = LogMonitor(
            self.log_time_range,
            self.log_time_format,
            self.check_log,
        )

        # ── log_box：日志采集推送（MAS 进程宿主，注入 sink 到 push_log）──
        # 受用户级「节点详情推送模式」开关控制：关闭时不创建（不读日志、不翻译、
        # 不匹配、不处理），既省采集开销也符合「不记录」语义；该用户 push_log 保持
        # 为空，报告聚合时自然不含其节点详情。
        self._prepare_log_details(
            self.script_log_path,
            mode=self.cur_user_config.Notify.PushLogMode,
            enabled=self.cur_user_config.Notify.PushLogMode != "关闭",
            rotated_name=f"{self.script_log_path.stem}.%Y-%m-%d{self.script_log_path.suffix}",
        )

        self.task_index = _OKWW_TASK_INDEX
        self.okww_args = ["-t", str(self.task_index), "-e"]

        self.script_config_path = self.script_root_path / _OKWW_REL_CONFIG_DIR

        self.run_book = False

    def _resolve_log_file_path(self) -> Path:
        return self.script_log_path

    def _apply_mas_overrides(self) -> None:
        """overlay 覆盖段：把 MAS 侧运行值覆盖到当前来源配置之上。

        DailyTask.json 是面板 overlay 子集，由 IfQuickConfig 守卫、与来源独立
        ——原生来源+开启同样覆盖，任务结束由 manager 既有整目录快照恢复。

        Basic Options.json 的退出行为同样属 overlay：它不是面板字段，但 MAS
        运行期需要它，且**三态一律覆盖**——覆盖发生在换入后的 working 目录，
        任务结束由同一份整目录快照还原，因此不会固化进任何来源的 base。
        （此前原生来源被排除在外，是「原生来源=原生配置不许动」的旧口径；按 overlay
        语义，只要任务结束能还原，覆盖与来源无关。）
        """

        _update_json(
            self.script_config_path / "Basic Options.json",
            {"Exit App when Game Exits": True},
        )
        if not self.cur_user_config.Info.IfQuickConfig:
            return
        _update_json(
            self.script_config_path / "DailyTask.json",
            {
                "Which to Farm": self.cur_user_config.Task.WhichToFarm,
                "Which Tacet Suppression to Farm": self.cur_user_config.Task.WhichTacetSuppressionToFarm,
                "Which Forgery Challenge to Farm": self.cur_user_config.Task.WhichForgeryChallengeToFarm,
                "Material Selection": self.cur_user_config.Task.MaterialSelection,
                "Farm Nightmare Nest for Daily Echo": self.cur_user_config.Task.FarmNightmareNestForDailyEcho,
                "Additional Tasks to Run After Daily Task": self.cur_user_config.Task.AdditionalTasks,
            },
        )

    async def set_okww(self) -> None:
        """将 MAS 侧 OK-WW 任务配置下发到脚本 working 目录（对齐 General.set_general）。"""

        logger.info("开始配置 OK-WW 运行参数: 自动代理")
        await System.kill_process(self.script_exe_path)
        _configure_okww_launcher(self.script_root_path)

        config_base = _okww_config_base(self.cur_user_config.Info.Base)
        if config_base != _utils_constants.BASE_NATIVE:
            # 下发前归档 MAS 配置到用户池（下发源，运行回写与快速配置覆盖会
            # 改它；指纹去重，失败不阻断运行）。目标路径按三态 owner（shared 来源
            # 共享 Default 目录）。native 池由 manager prepare 在任务级一次
            # 性归档，此处不重复
            archive_mas_runtime_backup(
                self.script_info.script_id,
                str(self.cur_user_uid),
                _okww_mas_config_dir(
                    self.script_info.script_id,
                    str(self.cur_user_uid),
                    config_base,
                ),
                overlay=read_overlay_values(self.cur_user_config),
                # 备份标注来源：tri_state 池跨来源恢复靠它切回
                base=config_base,
            )
            mas_config_dir = _okww_mas_config_dir(
                self.script_info.script_id,
                str(self.cur_user_uid),
                config_base,
            )
            _utils_io.swap_in_dir(mas_config_dir, self.script_config_path)
        else:
            source = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
            if source.is_dir():
                _utils_io.swap_in_dir(source, self.script_config_path)
        self._apply_mas_overrides()
        _utils_io.mark_native_config_injected(
            Path.cwd() / f"data/{self.script_info.script_id}/Temp",
            self.script_config_path,
            script_id=self.script_info.script_id,
        )
        logger.info("OK-WW 运行参数配置完成: 自动代理")

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        await push_dispatch_log(self.script_info, line)

    async def handle_pre_okww_error(
        self, error_message: str, e: Exception | None = None
    ) -> bool:
        """处理前置步骤失败，返回是否已确认旧 OK-WW 进程退出。"""

        if e is None:
            logger.warning(f"用户: {self.cur_user_uid} - {error_message}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=error_message),
            )
        else:
            logger.opt(exception=True).warning(
                f"用户: {self.cur_user_uid} - {error_message}: {e}"
            )
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=f"{error_message}: {e}"),
            )
        error_detail = f"{error_message}: {e}" if e is not None else error_message
        self.cur_user_log.content = [f"{error_detail}, 无日志记录"]
        self.cur_user_log.status = error_detail

        okww_stopped = await self.kill_managed_process(
            kill_game=self._game_management_enabled()
        )

        try:
            await Notify.send_notice(
                LocalNotice(
                    title="OK-WW 自动代理出现异常！",
                    message=f"用户 {self.cur_user_item.name} 自动代理时{error_message}",
                    ticker=f"{self.cur_user_item.name}的自动代理出现异常",
                    duration_seconds=3,
                )
            )
        except Exception:
            pass
        return okww_stopped

    def _game_launch_type(self) -> str:
        """游戏启动方式（缺省回落直启态）：Client=直启客户端，Launcher=经官方启动器。"""

        return str(self.script_config.Game.Type or "Client")

    async def _ensure_wuthering_waves_updated(self) -> None:
        """确保游戏已是官方最新版，需要时由 MAS 自行下载覆写。

        全程不启动官方启动器、不做界面识别：版本元数据取自官方接口，
        包体下载、md5 校验、增量应用与覆写全部由 MAS 完成。
        更新靠启动器路径解码游戏安装目录来确定更新目标，与启动方式无关：直启且
        手动指定了 Game.ClientPath 时，启动器路径也只为更新服务，启动不经过它；
        未配置启动器或路径失效时更新检查不可用（降级跳过，不阻断启动）。

        接口不可用属于「无法判断」，放行启动流程（旧客户端通常仍能登录，
        不该因为查不到版本就拦住用户）；而更新已确认需要却失败，
        则必须抛错阻断，否则会拿旧客户端撞登录失败。
        """

        if not self.script_config.Game.IfAutoUpdate:
            logger.info("已关闭启动前自动更新，跳过鸣潮更新检查")
            return
        # 直启可只填客户端路径，此时启动器可能没配或路径已失效：安装目录只能从
        # 启动器记录解码，更新检查无从下手，按预期跳过而不是报「更新检查失败」
        if self.launcher_path is None or not self.launcher_path.is_file():
            logger.info("鸣潮启动器未配置或文件不存在，跳过启动前自动更新检查")
            return
        resource = str(self.cur_user_config.Info.Resource)
        try:
            update_info = await _service_wuthering_waves.check_wuthering_waves_update(
                self.launcher_path,
                resource,
            )
        except Exception as e:
            logger.warning(f"鸣潮官方更新检查失败，将继续启动游戏: {e}")
            # 本地记录（启动器记录或版本记录）读不出来时客户端靠目录搜索还能
            # 拉起来，更新却无从下手：不说一声用户会一直停在旧版。接口/网络
            # 问题属「无法判断」，按既有决策静默放行
            if not _service_wuthering_waves.is_wuthering_waves_record_usable(
                self.launcher_path
            ):
                await self._push_dispatch_log(
                    "鸣潮本地更新记录不可用，已跳过启动前自动更新，"
                    "请用官方启动器检查游戏更新"
                )
            return

        # 直启可手动指定客户端：若它不在启动器记录的安装目录内，更新会打到另一
        # 份安装上，直启的那个客户端永远升不上去。只提示不改行为
        client_path = str(self.script_config.Game.ClientPath or "").strip()
        if (
            self._game_launch_type() == "Client"
            and client_path
            and not Path(client_path).is_relative_to(update_info.install_dir)
        ):
            message = (
                f"手动指定的客户端不在启动器记录的安装目录内"
                f"（{update_info.install_dir}），自动更新不会作用于该客户端，"
                "请确认两者指向同一份安装"
            )
            logger.warning(message)
            await self._push_dispatch_log(message)

        if update_info.predownload_available:
            logger.info(
                "官方已开放预下载 {}，MAS 暂不接管预下载",
                update_info.predownload_version or "未知",
            )
        if not update_info.update_available:
            return

        await self._push_dispatch_log(
            f"鸣潮需更新: {update_info.current_version}"
            f" -> {update_info.release_version}"
        )
        limit_gb = int(self.script_config.Game.UpdateFullSyncLimit or 0)
        await _service_wuthering_waves_updater.update_wuthering_waves(
            update_info.install_dir,
            resource,
            update_info.current_version,
            on_progress=self._push_dispatch_log,
            full_sync_limit=max(limit_gb, 1) * 1024**3,
        )

    async def _mas_launch_game_before_task(self) -> None:
        """检查并触发官方更新，然后按启动方式拉起鸣潮客户端。

        Client 态（默认）：直启客户端 exe，MAS 内置 ``-krqlv=hd``（实测可绕过
        启动器校验），与用户自配的 Game.Arguments 并存；
        Launcher 态：MAS 拉起官方启动器后由 OCR 流程点击「进入游戏」
        （launcher_start），启动器出现更新/下载时按下载态等待。
        """

        if isinstance(self.game_manager, ProcessManager):
            # check() 阶段的兜底提示在这里补推：此时本轮日志已重置完，推送能
            # 留在调度台上；整个任务只推一次（用户已知晓后不必每轮重复）。
            # 必须排在更新之前：更新失败会直接抛错退出，放它后面提示就丢了
            if self._fallback_notice is not None:
                await self._push_dispatch_log(self._fallback_notice)
                self._fallback_notice = None
            await self._ensure_wuthering_waves_updated()
            if self.game_process_path is None:
                # 路径未知（启动器记录解不出且目录搜索未命中）：只有「名称 + 启动器
                # 根目录树内」这一层信息，扫到即视为已在运行。不把进程交给进程管理
                # 器，否则收尾会按同名误杀同机其它虚幻游戏
                if self.launcher_path is not None and await asyncio.to_thread(
                    find_game_pids, self.launcher_path
                ):
                    logger.info("检测到鸣潮客户端进程正在运行，跳过重复启动")
                    await self._note_launch_arguments_skipped()
                    return
            elif is_process_running(_WUWA_CLIENT_PROCESS):
                try:
                    await self.game_manager.search_process(
                        self._game_process_info(),
                        3.0,
                    )
                except RuntimeError:
                    logger.info("检测到其他鸣潮客户端进程，继续启动已配置的游戏")
                else:
                    logger.info("检测到已配置的鸣潮客户端进程正在运行，跳过重复启动")
                    await self._note_launch_arguments_skipped()
                    return

            if self._game_launch_type() == "Client":
                await self._launch_game_direct()
            else:
                await self._launch_game_via_launcher()
            wait_time = max(int(self.script_config.Game.WaitTime), 0)
            if wait_time:
                await self._push_dispatch_log(f"等待游戏启动（{wait_time} 秒）...")
                await asyncio.sleep(wait_time)

    async def _launch_game_via_launcher(self) -> None:
        """经官方启动器拉起游戏：开启动器并等待 OCR 点击「进入游戏」。"""

        launcher_path = self.launcher_path
        if launcher_path is None:
            raise RuntimeError("未找到鸣潮官方启动器路径，请重新导入启动器")
        await self._push_dispatch_log("未检测到运行中的客户端，正在拉起官方启动器...")
        await self.game_manager.open_process(
            launcher_path, *split_args(self.script_config.Game.Arguments)
        )
        await self._push_dispatch_log("启动器已拉起，正在等待点击「进入游戏」...")
        # 启动器交互在后台线程内同步执行，on_log 契约是同步回调；
        # _push_dispatch_log 是 async 方法，须经 run_coroutine_threadsafe
        # 调度回事件循环（与账号切换的 _push_switch_log 同理）。
        launch_loop = asyncio.get_running_loop()

        def _push_launch_log(line: str) -> None:
            asyncio.run_coroutine_threadsafe(self._push_dispatch_log(line), launch_loop)

        await async_start_game_via_launcher(launcher_path, on_log=_push_launch_log)

    async def _launch_game_direct(self) -> None:
        """直启客户端 exe：内置 -krqlv=hd，与用户启动参数并存。

        待启动的客户端 exe 来自 check()：手动指定了 Game.ClientPath 时用该值，
        否则由启动器路径解码得到。MAS 不打开启动器界面。
        """

        game_process_path = self.game_process_path
        if game_process_path is None:
            raise RuntimeError("未找到鸣潮客户端程序路径，请重新导入启动器")
        await self._push_dispatch_log("未检测到运行中的客户端，正在直启鸣潮...")
        await self.game_manager.open_process(
            game_process_path,
            _WUWA_DIRECT_LAUNCH_ARG,
            *split_args(self.script_config.Game.Arguments),
        )
        await self._push_dispatch_log("鸣潮启动指令已发送")

    def _game_process_info(self) -> ProcessInfo:
        """已运行检测与收尾用的进程标识。

        调用方须保证 ``game_process_path`` 已知：路径未知时按名匹配会把同机其它
        同名进程算进来（收尾即误杀），那种情形改走 ``find_game_pids`` 的
        「名称 + 启动器根目录树内」口径。
        """

        if self.game_process_path is None:
            raise RuntimeError("鸣潮客户端路径未知，不能按精确路径匹配进程")
        return ProcessInfo(
            name=_WUWA_CLIENT_PROCESS,
            exe=str(self.game_process_path),
        )

    async def _note_launch_arguments_skipped(self) -> None:
        """游戏已在运行时不会重复启动，配了启动参数的用户要知道这轮没生效。"""

        arguments = str(self.script_config.Game.Arguments or "").strip()
        if arguments:
            message = f"检测到游戏已在运行，本轮不会应用启动参数（{arguments}）"
            logger.info(message)
            await self._push_dispatch_log(message)

    def _maintenance_detect(self) -> str | None:
        """维护检测：只认本专项运行客户端的窗口，避免读到同名其它游戏。

        ``Client-Win64-Shipping.exe`` 是虚幻通用进程名，同机可能有另一款同名
        进程的游戏；按本专项的启动器安装根目录树内进程与已配置客户端 exe
        路径取 PID，读不到归属时返回 None 放行。
        """

        return detect_game_maintenance_text(
            find_client_pids(self.game_process_path, self.launcher_path)
        )

    async def main_task(self):
        await self.prepare()
        self.curdate = datetime.now(tz=_utils_constants.UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.Data.LastProxyDate.strftime("%Y-%m-%d") != self.curdate:
            self.cur_user_config.Data.LastProxyDate = datetime.now(
                tz=_utils_constants.UTC4
            )
            await self.cur_user_config.commit()
            self.cur_user_config.Data.ProxyTimes = 0
            await self.cur_user_config.commit()

        self.cur_user_item.status = "运行"
        # 任务前脚本每用户一次，先于全部重试；后置脚本由收尾阶段成对执行
        await self.run_user_scripts_before()

        run_limit = int(self.script_config.Run.RunTimesLimit)
        attempt = 0
        game_update_extended = False
        # while 而非 for：游戏更新成功时 run_limit 会在轮次内延长（至少再跑一轮）
        while attempt < run_limit and not self.run_book:
            attempt += 1
            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: {attempt}/{run_limit}"
            )
            self.cur_user_item.status = "运行"
            self.log_start_time = datetime.now().astimezone()
            self.cur_user_item.add_log_record(self.log_start_time, LogRecord())
            self.cur_user_log = self.cur_user_item.log_record[self.log_start_time]
            self.script_info.log = ""

            # 启用游戏配置时始终由 MAS 拉起游戏
            if self.script_config.Game.Enabled and self.game_manager is not None:
                try:
                    await self._mas_launch_game_before_task()
                except Exception as e:
                    await self._push_dispatch_log(f"游戏启动失败: {e}")
                    self.cur_user_log.status = f"游戏启动失败: {e}"
                    self.cur_user_log.content = [f"游戏启动失败: {e}"]
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="error", message=f"游戏启动失败: {e}"
                        ),
                    )
                    await self.kill_managed_process(
                        kill_game=self._game_management_enabled()
                    )
                    try:
                        await Notify.send_notice(
                            LocalNotice(
                                title="OK-WW 自动代理出现异常！",
                                message=f"用户 {self.cur_user_item.name} 游戏启动失败",
                                ticker=f"{self.cur_user_item.name}的自动代理出现异常",
                                duration_seconds=3,
                            )
                        )
                    except Exception:
                        pass
                    if attempt < run_limit:
                        await self._push_dispatch_log(
                            f"游戏启动失败，将在稍后重试 ({attempt}/{run_limit})"
                        )
                        await asyncio.sleep(10)
                    else:
                        self.cur_user_item.status = "异常"
                    continue

            # 游戏窗口已就绪时先做画面维护检测（公告通道覆盖启动前，这里兜底
            # 「公告未覆盖但维护弹窗已出现」的场景）：命中即跳过当前用户；
            # 维护不会在重试间隔内结束，不再消耗剩余尝试次数
            if await self.skip_on_game_maintenance(self._maintenance_detect):
                break

            # 游戏启动成功后、下发脚本配置前，按「运行前强制切换账号」开关切号。
            # 开关在游戏配置区，依赖 Game.Enabled（未启用游戏配置则不生效）；
            # 用户未填写手机号时跳过不切换。
            if (
                self.script_config.Game.AccountSwitch
                and self.script_config.Game.Enabled
                and (self.game_manager is not None)
            ):
                account_id = (self.cur_user_config.Info.Id or "").strip()
                if not account_id:
                    await self._push_dispatch_log("未配置账号，跳过账号切换")
                else:
                    try:
                        await self._push_dispatch_log("正在强制切换鸣潮登录账号...")
                        # 账号切换在后台线程内同步执行，on_log 契约是同步回调；
                        # _push_dispatch_log 是 async 方法，须经 run_coroutine_threadsafe
                        # 调度回事件循环，否则进度不会推送到调度台且产生未等待协程告警。
                        switch_loop = asyncio.get_running_loop()

                        def _push_switch_log(line: str) -> None:
                            asyncio.run_coroutine_threadsafe(
                                self._push_dispatch_log(line), switch_loop
                            )

                        await async_switch_account(account_id, on_log=_push_switch_log)
                        await self._push_dispatch_log(
                            f"鸣潮账号切换成功：****{account_id[-4:]}"
                        )
                    except Exception as e:
                        await self.handle_pre_okww_error("鸣潮账号切换失败", e)
                        if attempt < run_limit:
                            await self._push_dispatch_log(
                                f"鸣潮账号切换失败，将在稍后重试 ({attempt}/{run_limit})"
                            )
                            await asyncio.sleep(10)
                        else:
                            self.cur_user_item.status = "异常"
                        continue

            await self.set_okww()
            await self._push_dispatch_log(f"启动 OK-WW: -t {self.task_index} -e")
            logger.info(
                f"启动 OK-WW 进程: {self.script_exe_path} {' '.join(self.okww_args)}"
            )

            try:
                await self.okww_process_manager.open_process(
                    self.script_exe_path,
                    *self.okww_args,
                    target_process=self.script_target_process_info,
                )
            except (OSError, RuntimeError) as e:
                # 启动器可能已拉起进程；清理后再重试，避免下一轮重复启动。
                if not await self.handle_pre_okww_error("OK-WW 启动失败", e=e):
                    message = (
                        "无法确认旧 OK-WW 进程已退出，停止重试，"
                        "请检查残留进程及结束进程的权限"
                    )
                    self.cur_user_log.status += f"\n{message}"
                    self.cur_user_log.content.append(message)
                    self.cur_user_item.status = "异常"
                    await self._push_dispatch_log(message)
                    break
                if attempt < run_limit:
                    await self._push_dispatch_log(
                        f"OK-WW 启动失败，将在稍后重试 ({attempt}/{run_limit})"
                    )
                    await asyncio.sleep(10)
                else:
                    self.cur_user_item.status = "异常"
                continue

            # 启动日志监控（文件日志）
            await asyncio.sleep(1)
            await self.log_monitor.start_monitor_file(
                self._resolve_log_file_path, self.log_start_time
            )

            self.wait_event.clear()
            maintenance_watch = asyncio.create_task(
                self.watch_game_maintenance(self._maintenance_detect, self.wait_event)
            )
            try:
                await self.wait_event.wait()
            finally:
                # 出等待循环（含用户手动中止与异常路径）都要停掉监视
                maintenance_watch.cancel()
                with suppress(asyncio.CancelledError):
                    await maintenance_watch
            await self.log_monitor.stop()

            # 运行期间命中维护弹窗：按维护跳过收尾，不再重试；结论与内容
            # 在日志监控停止后落笔，避免被 check_log 的末次轮询覆盖
            if (
                self.cur_user_item.maintenance_skipped
                and self._maintenance_reason
                and self.cur_user_log.status != "Success!"
            ):
                self.cur_user_log.status = self._maintenance_reason
                self.cur_user_log.content.append(self._maintenance_reason)
                self.cur_user_item.status = "跳过"
                self.script_info.log = f"{self._maintenance_reason}\n正在中止相关程序"
                # 通知放在最终判定处推送，避免与随后的成功结论互相矛盾
                await self.notify_maintenance_skip(self._maintenance_reason)
                await self.kill_managed_process(
                    kill_game=self._game_management_enabled()
                )
                break

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                # 成功结论晚于维护命中时优先成功，清除标记避免误报维护跳过
                self.clear_maintenance_hit()
                self.script_info.log = (
                    "检测到 OK-WW 已完成任务\n正在等待 OK-WW 自行退出"
                )
                # 等待 OK-WW 自然退出（-e 标志使其任务完成后自行关闭游戏并退出）
                await self._wait_okww_exit(timeout=30)
                await asyncio.sleep(3)
                break

            logger.warning(
                f"用户 {self.cur_user_item.name} - OK-WW 代理异常: {self.cur_user_log.status}"
            )
            self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"
            await self.kill_managed_process(kill_game=self._game_management_enabled())
            try:
                await Notify.send_notice(
                    LocalNotice(
                        title="OK-WW 自动代理出现异常！",
                        message=f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                        ticker=f"{self.cur_user_item.name}的自动代理出现异常",
                        duration_seconds=3,
                    )
                )
            except Exception:
                pass
            if attempt < run_limit:
                self.script_info.log += f"\n将在稍后重试 ({attempt}/{run_limit})"
                await asyncio.sleep(10)
            elif (
                self.cur_user_log.status == _OKWW_GAME_UPDATED_MSG
                and not game_update_extended
            ):
                # 「游戏更新成功」是环境变更而非脚本错误：次数用尽也至少再跑
                # 一轮，否则鸣潮客户端自更新后任务直接以失败收尾。
                # 每个任务只延长一次：再命中说明更新根本没应用成功，属持久性
                # 环境问题，继续盲重试大概率白跑，按异常收尾交用户排查
                game_update_extended = True
                run_limit = attempt + 1
                self.script_info.log += (
                    f"\n游戏更新成功，将重启任务 ({attempt}/{run_limit})"
                )
                await asyncio.sleep(10)

    def _game_management_enabled(self) -> bool:
        return bool(self.script_config.Game.Enabled)

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """按内置日志判定结果，未见成功日志便退出则视为异常。"""
        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log_first_line = log[:-4000].count("\n") + 1
        self.script_info.log = log[-4000:]

        log_status = "OK-WW 正常运行中"
        user_item_status: str | None = None

        for needle, msg in _OKWW_BUILTIN_FATAL:
            if needle in log:
                log_status = msg
                user_item_status = "异常"
                break
        else:
            if _OKWW_SUCCESS_LOG in log:
                log_status = "Success!"
                user_item_status = "完成"
            elif any(needle in log for needle in _OKWW_DISCONNECT_LOG):
                log_status = _OKWW_DISCONNECT_MSG
                user_item_status = "异常"
            elif not await self.okww_process_manager.is_running():
                log_status = "OK-WW 在完成任务前退出"
                user_item_status = "异常"
            elif self.is_log_stalled(
                latest_time, minutes=self.script_config.Run.RunTimeLimit
            ):
                log_status = "OK-WW 运行超时"
                user_item_status = "异常"

        self.cur_user_log.status = log_status
        if user_item_status is not None:
            self.cur_user_item.status = user_item_status

        logger.debug(f"OK-WW 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "OK-WW 正常运行中":
            logger.info(f"OK-WW 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):
        self.task_info.begin_user_history_capture(
            self.script_info,
            self.cur_user_item,
            failed=bool(self.cur_user_item.log_record)
            and not self.run_book
            and not self.cur_user_item.maintenance_skipped
            and not self.stopped_manually,
        )

        # 结束时先清理进程与监控；任务结束后始终关闭游戏（由 Game.Enabled 总开关控制）
        if self.log_monitor is not None:
            with suppress(Exception):
                await self.log_monitor.stop()
        await self.kill_managed_process(kill_game=self._game_management_enabled())

        # box 归并并交付节点后释放翻译资源，报告仍使用原有文本与兜底提示。
        await self._close_log_details()

        # 写入历史记录（对齐 General/SRC/MaaEnd 行为）
        await self._persist_user_run_result()
        await self._wait_game_exit_before_next_user()

        await self.run_user_scripts_after()

        history_records = []
        for t, log_item in self.cur_user_item.iter_history_logs():
            if log_item.status in {"未开始监看日志", "OK-WW 正常运行中"}:
                log_item.status = "任务被用户手动中止"

            was_cancelled = (
                self.stopped_manually
                and log_item is self.cur_user_log
                and log_item.status == "任务被用户手动中止"
            )
            if not log_item.content:
                log_item.content = [log_item.status]

            history_records.append(
                HistoryWrite(
                    time=t.astimezone(_utils_constants.UTC4),
                    username=self.cur_user_item.name,
                    script_name=self.script_info.name,
                    status=(
                        "success"
                        if log_item.status == "Success!"
                        else "skipped"
                        if (
                            log_item is self.cur_user_log
                            and self.cur_user_item.maintenance_skipped
                        )
                        else "cancelled"
                        if was_cancelled
                        else "error"
                    ),
                    message=log_item.status,
                    logs="".join(log_item.content),
                )
            )

        if history_records:
            await self.task_info.save_user_history(
                history_records,
                script=self.script_info,
                user=self.cur_user_item,
                log_warning=logger.opt(exception=True).warning,
            )

        if history_records:
            try:
                statistics = {
                    key: value.value
                    for key, value in aggregate_data(
                        [
                            HistoryAggregationItem(time=record.time, data=record.data)
                            for record in history_records
                        ]
                    ).data.items()
                }
                statistics["user_info"] = self.cur_user_item.name
                start_time = getattr(self, "user_start_time", datetime.now())
                statistics["start_time"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
                statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                statistics["user_result"] = (
                    "代理任务全部完成" if self.run_book else self.cur_user_item.result
                )
                # 维护跳过不是失败，统计标题用中性符号而非失败标记
                success_symbol = (
                    "√"
                    if self.run_book
                    else "-"
                    if self.cur_user_item.maintenance_skipped
                    else "X"
                )
                await Notify.push_statistics_report(
                    payload=build_user_statistics_payload(
                        title=f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的 OK-WW 自动代理统计报告",
                        message=statistics,
                    ),
                    user_config=self.cur_user_config,
                    task_info=self.task_info,
                )
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"推送 OK-WW 用户统计通知时出现异常: {e}"
                )

    async def _persist_user_run_result(self) -> None:
        if self.cur_user_config is None:
            return

        self.cur_user_config.Data.LastTaskIndex = getattr(self, "task_index", 0)
        await self.cur_user_config.commit()
        if self.run_book:
            if (
                self.cur_user_config.Data.ProxyTimes == 0
                and self.cur_user_config.Info.RemainedDay != -1
            ):
                self.cur_user_config.Info.RemainedDay = (
                    self.cur_user_config.Info.RemainedDay - 1
                )
                await self.cur_user_config.commit()
            self.cur_user_config.Data.ProxyTimes = (
                self.cur_user_config.Data.ProxyTimes + 1
            )
            await self.cur_user_config.commit()
            self.cur_user_config.Data.LastProxyStatus = "成功"
            await self.cur_user_config.commit()
            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的 OK-WW 自动代理任务已完成")
        else:
            maintenance_skipped = self.cur_user_item.maintenance_skipped
            # 维护跳过不是失败：保留「跳过」状态并记录维护结果。
            self.cur_user_config.Data.LastProxyStatus = (
                "维护中" if maintenance_skipped else "失败"
            )
            await self.cur_user_config.commit()
            if maintenance_skipped:
                if self.cur_user_item.status not in ("完成", "跳过"):
                    self.cur_user_item.status = "异常"
            elif self.cur_user_item.status != "完成":
                self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"OK-WW 运行异常: {e}"
        logger.opt(exception=True).warning(f"OK-WW 自动代理任务出现异常: {e}")
        if self.wait_event is not None:
            self.wait_event.set()
        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"OK-WW 自动代理任务出现异常: {e}"
                ),
            )
        with suppress(Exception):
            await self.kill_managed_process(kill_game=self._game_management_enabled())
        with suppress(Exception):
            await self._persist_user_run_result()

        # 推送通知（复用 Notify）
        try:
            if (
                self.cur_user_log is not None
                and self.cur_user_log.status
                and self.cur_user_log.status != "Success!"
            ):
                await Notify.send_notice(
                    LocalNotice(
                        title="OK-WW 运行异常",
                        message=f"用户 {self.cur_user_item.name}：{self.cur_user_log.status}",
                        ticker="异常",
                        duration_seconds=3,
                    )
                )
        except Exception:
            pass

    async def _wait_okww_exit(self, *, timeout: int = 30) -> None:
        """等待 OK-WW 自然退出（-e 触发），超时后兜底强杀。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not await self.okww_process_manager.is_running():
                logger.info("OK-WW 已自行退出")
                return
            await asyncio.sleep(1)
        logger.warning(f"OK-WW 未在 {timeout}s 内自行退出，兜底强杀")
        await self._kill_okww_process()

    async def _kill_okww_process(self) -> bool:
        if self.okww_process_manager is not None:
            try:
                await self.okww_process_manager.kill()
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"通过进程管理器中止 OK-WW 进程失败: {e}"
                )
        if self.script_exe_path is not None:
            try:
                if not await System.kill_process(self.script_exe_path):
                    logger.warning("未能完整清理 OK-WW 主进程，将复核退出状态")
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 OK-WW 主进程失败: {e}")
        if self.script_root_path is not None:
            track_exe = self.script_root_path / _OKWW_REL_PYTHONW
            try:
                if not await System.kill_process(track_exe):
                    logger.warning("未能完整清理 OK-WW 追踪进程，将复核退出状态")
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 OK-WW 追踪进程失败: {e}")

        # 清理返回成功也可能仍有残留；管理器丢失句柄时仍须按路径复核。
        paths = []
        if self.script_exe_path is not None:
            paths.append(self.script_exe_path)
        if self.script_root_path is not None:
            paths.append(self.script_root_path / _OKWW_REL_PYTHONW)
        stopped = True
        for path in paths:
            try:
                if not await System.is_process_stopped(path):
                    stopped = False
                    logger.warning(f"无法确认进程已退出: {path}")
            except Exception as e:
                stopped = False
                logger.opt(exception=True).warning(f"复核进程退出状态失败: {path}: {e}")
        return stopped

    async def _kill_game_process(self) -> None:
        """结束游戏与官方启动器：任务结束/失败/异常时始终触发（由 Game.Enabled 总开关控制）"""
        if isinstance(self.game_manager, ProcessManager):
            if (
                self.game_process_path is not None
                and self.game_manager.target_process is None
            ):
                try:
                    await self.game_manager.search_process(
                        self._game_process_info(),
                        1.0,
                    )
                except RuntimeError:
                    logger.debug("未找到待关闭的鸣潮客户端进程")
            try:
                await self.game_manager.kill()
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"通过进程管理器关闭鸣潮客户端失败: {e}"
                )
        if self.game_process_path is not None:
            try:
                await System.kill_process(self.game_process_path)
            except Exception as e:
                logger.opt(exception=True).warning(f"兜底强杀鸣潮客户端失败: {e}")
        if (
            self.launcher_path is not None
            and self.launcher_path.name.lower() == "launcher.exe"
            and self.launcher_path.is_file()
        ):
            # 实际运行的那份可能不在已知路径上（手动指定的客户端与实际启动的不是
            # 同一份，或启动器态压根解不出路径），只按路径匹配会漏杀。兜底按
            # 「名称 + 启动器安装根目录树内」扫——Client-Win64-Shipping.exe 是虚幻
            # 通用进程名，单按名会误伤同机其它虚幻游戏，必须有目录树限定；启动器
            # 路径本身失效时无从限定，只保留上面的按已知路径结束，不冒险按名扫。
            # 有没杀掉的（多为提权进程）要提示用户，不能静默。
            # 注意 kill_process_by_pid 失败时返回 False 而非抛异常，必须看返回值
            try:
                failed = await kill_pids(
                    await asyncio.to_thread(find_game_pids, self.launcher_path)
                )
                if failed:
                    message = (
                        f"有 {failed} 个鸣潮客户端进程未能结束（可能是提权进程，"
                        "MAS 无权结束），请人工确认关闭"
                    )
                    logger.warning(message)
                    await self._push_dispatch_log(message)
            except Exception as e:
                logger.opt(exception=True).warning(f"清理鸣潮客户端进程失败: {e}")
        if self.launcher_path is not None and self._game_launch_type() == "Launcher":
            try:
                # 启动器是进程家族：顶层 launcher.exe 引导器 + 版本目录下的
                # launcher_main.exe（真窗口，版本目录随自更新变化）。launcher.exe
                # 是通用进程名，按「家族 + 安装根目录树内」限定清理，避免误伤
                # 无关程序；每步独立捕获，失败不阻断收尾。
                # 仅启动器启动态清理：直启态 MAS 未打开启动器，不关用户自己的
                # 启动器窗口
                pids = await asyncio.to_thread(find_launcher_pids, self.launcher_path)
                for pid in pids:
                    # 游戏清理在先，启动器进程树里只剩 webview 等子进程，
                    # 连树一并带走避免残留；游戏若意外仍在树内也属应关范围
                    await System.kill_process_by_pid(pid, kill_tree=True)
                # 清理后复核：exe 不可读（提权）的启动器进程不在上面的结果内，
                # 用窗口定位口径再查一次，避免静默残留
                if await asyncio.to_thread(has_launcher_window, self.launcher_path):
                    message = (
                        "检测到鸣潮官方启动器窗口仍残留（可能是提权进程，"
                        "MAS 无权结束），请人工确认关闭"
                    )
                    logger.warning(message)
                    await self._push_dispatch_log(message)
            except Exception as e:
                logger.opt(exception=True).warning(f"关闭鸣潮官方启动器失败: {e}")

    async def kill_managed_process(self, *, kill_game: bool = True) -> bool:
        """中止相关程序，返回是否已确认 OK-WW 退出；游戏清理失败单独记录。"""
        okww_stopped = await self._kill_okww_process()
        if kill_game:
            try:
                await self._kill_game_process()
            except Exception as e:
                logger.opt(exception=True).warning(f"清理鸣潮进程失败: {e}")
        return okww_stopped

    async def _wait_game_exit_before_next_user(self) -> None:
        """多用户切换：等上一用户的游戏完全退出后再进下个用户。

        鸣潮客户端进程退出不是瞬时的（ok-ww 恒带 `-e` 自退）。若不等其完全退出，
        下个用户会把「正在退出的残影窗口」误判为可用游戏而复用，导致窗口句柄
        失效后任务被中止。仅在还有下一个用户时等待；最后一个用户不等待。
        游戏管理开启时 MAS 已同步 taskkill，本方法即为 no-op。
        """
        if self.script_info.current_index >= len(self.script_info.user_list) - 1:
            return
        deadline = time.monotonic() + _GAME_EXIT_WAIT_SECONDS
        while time.monotonic() < deadline:
            # 按进程存活判断（不依赖窗口）：窗口销毁后进程可能仍存活片刻。
            # 全进程扫描是同步 IO，放到线程里免得每秒卡一次事件循环
            if not await asyncio.to_thread(is_process_alive, _WUWA_CLIENT_PROCESS):
                logger.info("鸣潮客户端进程已完全退出，继续下一用户")
                return
            await asyncio.sleep(1)
        logger.warning(
            f"等待鸣潮客户端进程退出超时（{_GAME_EXIT_WAIT_SECONDS}s），继续下一用户"
        )

    def _prepare_log_details(
        self, path: Path, *, mode: str, enabled: bool, rotated_name: str | None
    ) -> None:
        """本专项固定来源与用户；读取和交付时机由自身生命周期控制。"""
        self._log_user = self.cur_user_item
        self._log_user.push_log_mode = mode
        self._log_source = None
        self._log_pipeline = None
        self._log_close_task = None
        self._log_translator = None
        self._log_failed = False
        if not enabled:
            return
        try:
            pipeline = log_box.LogPipeline()
            self._log_translator = _utils_i18n.PoTranslator()
            self._log_translator.load(
                (_push_log.OKWW_REL_I18N_PO,), base=self.script_root_path
            )
            self._log_translator.load_supplement((_push_log._okww_supplement_po(),))
            pipeline.preprocessors.append(self._log_translator.translate)
            for rule in _push_log.OKWW_PUSH_RULES:
                pipeline.add_rule(*rule)
            pipeline.postprocessors.append(_push_log.okww_resolve)
            source = log_source.LogSource(
                path, start_from_end=True, rotated_name=rotated_name
            )
            source.open()
            self._log_source = source
            self._log_pipeline = pipeline
        except Exception:
            self._log_failed = True
            logger.opt(exception=True).warning("Okww 节点采集初始化失败")

    async def _close_log_details(self) -> None:
        """本专项只交付一次；取消先等待交付完成再继续传播。"""
        if self._log_user is None:
            return
        if self._log_close_task is None:
            self._log_close_task = asyncio.create_task(self._collect_log_details())
        cancelled = None
        while not self._log_close_task.done():
            try:
                await asyncio.shield(self._log_close_task)
            except asyncio.CancelledError as error:
                cancelled = error
        self._log_close_task.result()
        if cancelled is not None:
            raise cancelled

    async def _collect_log_details(self) -> None:
        user = self._log_user
        source = self._log_source
        pipeline = self._log_pipeline
        if user is None or (source is None and not self._log_failed):
            return
        if not self._log_failed:
            try:
                assert source is not None and pipeline is not None

                def read():
                    for line in source.read_new():
                        pipeline.feed(line, timestamp=time.time())
                    return pipeline.finish()

                entries = await asyncio.to_thread(read)
                for entry in entries:
                    user.push_log.append((entry.log_type, entry.text, entry.timestamp))
            except Exception:
                self._log_failed = True
                logger.opt(exception=True).warning("节点采集或交付失败")

        if self._log_translator is not None:
            try:
                self._log_translator.clear()
            except Exception:
                self._log_failed = True
                logger.opt(exception=True).warning("OK-WW 翻译资源清理失败")

        if self._log_failed:
            try:
                user.push_log.append((LOG_TYPE_NORMAL, "⚠️ 节点采集失败", time.time()))
            except Exception:
                logger.opt(exception=True).warning("节点采集失败提示无法交付")
