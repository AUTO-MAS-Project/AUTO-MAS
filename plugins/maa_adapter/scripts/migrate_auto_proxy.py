"""One-off: autoproxy.py → task/auto_proxy.py (MaaAutoProxy worker)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "maa_adapter"
SRC = ROOT / "autoproxy.py"
DST = ROOT / "task" / "auto_proxy.py"

STAGE_KEYS = {
    "MedicineNumb",
    "SeriesNumb",
    "Stage",
    "Stage_1",
    "Stage_2",
    "Stage_3",
    "Stage_Remain",
}


def pascal_to_snake(name: str) -> str:
    s = name.strip()
    if s.startswith("If") and len(s) > 2:
        tail = re.sub(r"(?!^)(?=[A-Z])", "_", s[2:]).lower()
        return "if_" + tail
    return re.sub(r"(?!^)(?=[A-Z])", "_", s).lower()


def get_expr(root: str, group: str, name: str) -> str:
    if group == "Emulator" and name == "Id":
        return f"{root}.info.game_id"
    if group == "Emulator" and name == "Index":
        return f"{root}.info.game_device_id"
    if group == "Info" and name == "Status":
        return f"{root}.info.enabled"
    if group == "Info" and name == "Id":
        return f"{root}.info.account_id"
    if group == "Info" and name == "StageMode":
        return (
            f'("Fixed" if ({root}.info.plan_id or "-") in ("-", "Fixed", "") '
            f"else str({root}.info.plan_id))"
        )
    if group == "Info" and name == "Path":
        return f"str({root}.info.path or '')"
    if group == "Info" and name in ("ScriptBeforeTask", "ScriptAfterTask"):
        return f"str({root}.info.{pascal_to_snake(name)} or '')"
    if group == "Info" and name in STAGE_KEYS:
        return f"{root}.info.{pascal_to_snake(name)}"
    grp = pascal_to_snake(group)
    attr = pascal_to_snake(name)
    return f"{root}.{grp}.{attr}"


GET_PAT = re.compile(
    r'self\.(script_config|cur_user_config)\.get\(\s*"([^"]+)",\s*"([^"]+)"'
    r"(?:,\s*([^)]+))?\s*\)"
)

SET_PAT = re.compile(
    r'await self\.(script_config|cur_user_config)\.set\(\s*"([^"]+)",\s*"([^"]+)",\s*([^)]+)\)'
)


def repl_get(m: re.Match) -> str:
    root = (
        "self.script_entry" if m.group(1) == "script_config" else "self.user_entry"
    )
    return get_expr(root, m.group(2), m.group(3))


def repl_set(m: re.Match) -> str:
    root_name = "script_entry" if m.group(1) == "script_config" else "user_entry"
    group, name, val = m.group(2), m.group(3), m.group(4).strip()
    if group == "Info" and name == "Status":
        return (
            f"self.{root_name}.info.enabled = bool({val}); "
            f"await self.{root_name}.commit()"
        )
    if group == "Info" and name == "Id":
        return (
            f"self.{root_name}.info.account_id = str({val}); "
            f"await self.{root_name}.commit()"
        )
    if group == "Info" and name == "StageMode":
        return (
            f'self.{root_name}.info.plan_id = "-" if {val} in ("Fixed", "", None) '
            f"else str({val}); await self.{root_name}.commit()"
        )
    grp = pascal_to_snake(group)
    attr = pascal_to_snake(name)
    return (
        f"self.{root_name}.{grp}.{attr} = {val}; "
        f"await self.{root_name}.commit()"
    )


def main() -> None:
    text = SRC.read_text(encoding="utf-8")

    # imports / facades
    text = text.replace("from maa_adapter.facades import ConfigCompat, LogRec, close_emulator\n", "")
    text = text.replace("Config = ConfigCompat()\nLogRecord = LogRec\n\n", "")
    text = text.replace("from maa_adapter.proxy_helpers import", "from ..shared.proxy_helpers import")
    text = text.replace("from maa_adapter.constants import game_now", "")
    text = text.replace("from maa_adapter.maa_native import", "from ..maa_native import")
    text = text.replace("from maa_adapter.notify_types import", "from ..notify_types import")
    text = text.replace("from maa_adapter.execute_script import", "from ..execute_script import")

    const_block = """from ..constants import (
    ARKNIGHTS_PACKAGE_NAME,
    MAA_ANNIHILATION_FIGHT_BASE,
    MAA_GREEN_TICKET_STORE_TASK,
    MAA_MODE_TIME_LIMIT_BOOK,
    MAA_RUN_MOOD_BOOK,
    MAA_STAGE_KEY,
    MAA_TASKS,
    MAA_TASKS_ZH,
    UTC4,
    game_now,
)
"""
    text = text.replace(
        "from auto_mas_core.utils import (\n    ARKNIGHTS_PACKAGE_NAME,\n    LogMonitor,\n    MAA_ANNIHILATION_FIGHT_BASE,\n    MAA_GREEN_TICKET_STORE_TASK,\n    MAA_MODE_TIME_LIMIT_BOOK,\n    MAA_RUN_MOOD_BOOK,\n    MAA_STAGE_KEY,\n    MAA_TASKS,\n    MAA_TASKS_ZH,\n    ProcessManager,\n    UTC4,\n    get_logger,\n    mark_native_config_injected,\n    read_file,\n    write_file,\n)",
        "from auto_mas_core import Config as HostConfig, HistoryRecordData, Publisher, TaskMode, protocol, WSTaskNoticeData\nfrom auto_mas_core.adapters.script import AutoProxyWorker\nfrom auto_mas_core.utils import (\n    LogMonitor,\n    ProcessManager,\n    get_logger,\n    mark_native_config_injected,\n    read_file,\n    write_file,\n)\nfrom auto_mas_core import LogRecordEntry\n"
        + const_block,
    )

    text = text.replace("from auto_mas_core import Config, Publisher, protocol, WSTaskNoticeData\n", "")
    text = GET_PAT.sub(repl_get, text)
    text = SET_PAT.sub(repl_set, text)

    # Init replacement before global script_config rename
    old_init = '''    def __init__(
        self,
        script_info,
        script_config,
        user_config,
        emulator_manager,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        # 配置来源三态与独立的快速配置开关：来源决定是否下发 MAS 托管配置，
        # 快速配置决定是否把面板值写进 MAA 原生配置（两段互不替代）。
        self.config_mode, self.direct_control = resolve_config_source(
            self.cur_user_config, CONFIG_SOURCE_SCRIPT
        )
        self.check_result = "-"
        self._annihilation_weekly_completion_recorded = False
        # 无时段排班表本轮注入的班次：同一用户的多次重试都注入这一个值，
        # 基建换班完成后只把用户配置里的指针推进一次
        self._infrast_plan_index: int | None = None
        self._infrast_plan_count = 0
        self._infrast_plan_advanced = False
'''

    new_init_prefix = '''class _ScriptProgress:
    def __init__(self, worker: "MaaAutoProxy"):
        self._w = worker

    @property
    def script_id(self) -> str:
        return str(self._w.script_entry.uid)

    @property
    def name(self) -> str:
        return self._w.script_item.info.name

    @property
    def current_index(self) -> int:
        return 0

    @property
    def log(self) -> str:
        return self._w.script_item.current.log or ""

    @log.setter
    def log(self, value: str) -> None:
        self._w._set_progress_log(value)


class MaaAutoProxy(AutoProxyWorker):
    """自动代理模式"""

    mode = TaskMode.AUTO_PROXY
    stopped_manually = False
    runtime: object | None = None

    _cultivate_collected_depot: bool = False
    _cultivate_collected_oper_box: bool = False
    _depot_maintain_suppressed: bool = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_mode, self.direct_control = resolve_config_source(
            self.user_entry, CONFIG_SOURCE_SCRIPT
        )
        self._check_result = "Pass"
        self._annihilation_weekly_completion_recorded = False
        self._infrast_plan_index: int | None = None
        self._infrast_plan_count = 0
        self._infrast_plan_advanced = False
        self._log_progress: dict = {}
        self._cur_log: LogRecordEntry | None = None
        self._progress = _ScriptProgress(self)

    @property
    def user_item(self):
        return self.script_item.users[self.user_uid]

    @property
    def task_id(self) -> str:
        parent = self.script_item.parent
        if parent is not None:
            return str(parent.uid)
        return str(self.script_entry.uid)

    @property
    def is_queue_task(self) -> bool:
        parent = self.script_item.parent
        if parent is None:
            return False
        return bool(getattr(getattr(parent, "info", None), "queue_id", None))

    def _device(self):
        rt = self.runtime
        if rt is None or getattr(rt, "device", None) is None:
            raise RuntimeError("未订阅游戏设备")
        return rt.device

    async def _close_emulator(self) -> None:
        rt = self.runtime
        if rt is not None and rt.device is not None:
            try:
                await rt.device.close()
            except Exception as e:
                logger.warning(f"关闭模拟器失败: {e}")

    def _is_log_stalled(self, latest_time, minutes, key="default"):
        now = time.monotonic()
        previous = self._log_progress.get(key)
        if previous is None or previous[0] != latest_time:
            self._log_progress[key] = (latest_time, now)
            return False
        return now - previous[1] > minutes * 60

    def _set_progress_log(self, value: str) -> None:
        if self._cur_log is None:
            return
        self._cur_log.info.content = value.splitlines(keepends=True) or [value]

    async def _begin_log_record(self) -> None:
        uid = self.user_item.log_record.add(LogRecordEntry)
        await self.user_item.commit()
        self._cur_log = self.user_item.log_record[uid]
        self._cur_log.info.start_time = self.log_start_time
        self._cur_log.info.content = []
        self._cur_log.info.status = "未开始监看日志"
        await self.user_item.commit()

    async def check(self) -> str:
        return await self._maa_check()

    async def main_logic(self) -> None:
        minutes = self.script_entry.run.hard_time_limit
        try:
            async with asyncio.timeout(minutes * 60):
                await self._maa_main()
        except TimeoutError:
            self.user_item.info.status = "异常"
            logger.warning(f"运行超过 {minutes} 分钟，已终止")

    async def final_task(self) -> None:
        await self._maa_final()
        await self._rewrite_running_logs()
        await super().final_task()
        await self._send_stat_notifications()

'''

    if old_init not in text:
        raise SystemExit("init block not found")
    text = text.replace(
        'class AutoProxyTask:\n    """自动代理模式"""\n\n    stopped_manually = False\n\n    def is_log_stalled(self, latest_time, minutes, key="default"):\n        from maa_adapter.facades import is_log_stalled as _stalled\n\n        return _stalled(self, latest_time, minutes, key)\n\n    async def on_crash(self, e):\n        logger.opt(exception=True).warning(f"MAA 自动代理异常: {e}")\n\n\n    # 养成采集状态：prepare() 每轮重置；类级默认保证未跑 prepare 的\n    # 实例（如单测直接构造）调用 check_log 时不炸\n    _cultivate_collected_depot: bool = False\n    _cultivate_collected_oper_box: bool = False\n    _depot_maintain_suppressed: bool = False\n\n' + old_init,
        new_init_prefix,
    )

    # Device / task context
    text = text.replace("self.script_config", "self.script_entry")
    text = text.replace("self.cur_user_config", "self.user_entry")

    # Rename internal methods
    text = text.replace("async def check(self) -> str:\n\n        # 单独运行脚本", "async def _maa_check(self) -> str:\n\n        # 单独运行脚本")
    text = text.replace("async def main_task(self):", "async def _maa_main(self):")
    text = text.replace(
        "async def final_task(self):\n        if self._check_result != \"Pass\":",
        "async def _maa_final(self):\n        if self._check_result != \"Pass\":",
    )

    text = text.replace("self.check_result", "self._check_result")
    text = text.replace("self.cur_user_item", "self.user_item")
    text = text.replace("self.cur_user_uid", "self.user_uid")
    text = text.replace("self.cur_user_log", "self._cur_log.info")
    text = text.replace("self.script_info", "self._script_progress")
    text = text.replace("self.task_info.task_id", "self.task_id")
    text = text.replace("self.task_info.is_queue_task", "self.is_queue_task")
    text = text.replace("self.emulator_manager", "self._device()")
    text = text.replace("await close_emulator(self)", "await self._close_emulator()")

    # Fix script progress placeholder - need a small namespace
    text = text.replace(
        "class MaaAutoProxy(AutoProxyWorker):",
        '''class _ScriptProgress:
    def __init__(self, worker: "MaaAutoProxy"):
        self._w = worker

    @property
    def script_id(self) -> str:
        return str(self._w.script_entry.uid)

    @property
    def name(self) -> str:
        return self._w.script_item.info.name

    @property
    def current_index(self) -> int:
        return 0

    @property
    def log(self) -> str:
        return self._w.script_item.current.log or ""

    @log.setter
    def log(self, value: str) -> None:
        self._w._set_progress_log(value)


class MaaAutoProxy(AutoProxyWorker):''',
    )
    text = text.replace("self._script_progress", "self._progress")
    text = text.replace(
        "        self._log_progress: dict = {}\n        self._cur_log: LogRecordEntry | None = None\n",
        "        self._log_progress: dict = {}\n        self._cur_log: LogRecordEntry | None = None\n        self._progress = _ScriptProgress(self)\n",
    )

    # log record creation
    text = text.replace(
        """                self.cur_user_item.log_record[self.log_start_time] = (
                    self.cur_user_log
                ) = LogRecord()""",
        "                await self._begin_log_record()",
    )

    # Config host
    text = text.replace("Config.build_history_log_path", "_UNUSED_build_history_log_path")
    text = text.replace("await Config.merge_statistic_info", "_UNUSED_merge")
    text = text.replace("await Config.get_stage_info", "await HostConfig.get_stage_info")
    text = text.replace("await Config.get_stage(", "await HostConfig.get_stage(")
    text = text.replace("Config.PlanConfig", "HostConfig.PlanConfig")
    text = text.replace("Config.config_path", "HostConfig.config_path")
    text = text.replace("Config.proxy", "getattr(HostConfig, 'proxy', None)")
    text = text.replace(
        'Config.get("Function", "IfSilence")',
        "HostConfig.setting.function.if_silence",
    )

    # log_statistics import
    text = text.replace("from .tools import (\n    agree_bilibili,", "from .log_statistics import parse_maa_log\nfrom ..tools import (\n    agree_bilibili,")

    text = text.replace("from . import api_service as maa_api", "from .. import api as maa_api")

    text = text.replace("from .base_preset import", "from ..base_preset import")
    text = text.replace("from .tools.backup_archive import", "from ..tools.backup_archive import")
    text = text.replace("from .tools.cultivate import", "from ..tools.cultivate import")
    text = text.replace("from .tools.screenshot import", "from ..tools.screenshot import")

    # _has_completed_sanity_task type
    text = text.replace("def _has_completed_sanity_task(log_records: list[LogRecord])", "def _has_completed_sanity_task(log_records)")

    # Fix _cur_log.info attribute access on status lines that used .content on LogRec
    # cur_user_log.content already mapped to _cur_log.info.content - good
    # status: self._cur_log.info.status

    # Remove duplicate class attrs at top of class
    text = re.sub(
        r'class MaaAutoProxy\(AutoProxyWorker\):\n    """自动代理模式"""\n\n    stopped_manually = False\n\n    def is_log_stalled',
        'class MaaAutoProxy(AutoProxyWorker):\n    """自动代理模式"""\n\n    def is_log_stalled',
        text,
        count=1,
    )

    # Fix broken is_log_stalled duplicate method - remove old method
    text = re.sub(
        r"\n    def is_log_stalled\(self, latest_time, minutes, key=\"default\"\):\n        return self\._is_log_stalled\(latest_time, minutes, key\)\n",
        "\n",
        text,
        count=1,
    )

    # final_task in _maa_final - strip old notification block manually later
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(text, encoding="utf-8")
    remaining_get = len(GET_PAT.findall(text))
    remaining_set = len(SET_PAT.findall(text))
    print(f"Wrote {DST}, remaining get={remaining_get} set={remaining_set}")


if __name__ == "__main__":
    main()
