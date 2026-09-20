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
import calendar
import json
import re
import shutil
import time
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import (
    MaaConfig,
    MaaUserConfig,
    infrast_plan_mode,
    load_infrast_plans,
    maa_scheme_name,
)
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify, System
from app.task.emulator_core import close_emulator
from app.task.general.tools import execute_script_task
from app.task.proxy_helpers import (
    CONFIG_SOURCE_SCRIPT,
    CONFIG_SOURCE_USER,
    resolve_config_source,
)
from app.utils import LogMonitor, ProcessManager, get_logger
from app.utils.constants import (
    ARKNIGHTS_PACKAGE_NAME,
    MAA_ANNIHILATION_FIGHT_BASE,
    MAA_GREEN_TICKET_STORE_TASK,
    MAA_MODE_TIME_LIMIT_BOOK,
    MAA_REMAIN_FIGHT_BASE,
    MAA_RUN_MOOD_BOOK,
    MAA_STAGE_KEY,
    MAA_TASK_TRANSITION_METHOD_BOOK,
    MAA_TASKS,
    MAA_TASKS_ZH,
    UTC4,
)
from app.utils.io import mark_native_config_injected, read_file, write_file

from .tools import (
    agree_bilibili,
    ensure_game_updated,
    push_notification,
    update_maa,
)
from .tools.backup_archive import archive_mas_runtime_backup, read_overlay_values
from .tools.cultivate import (
    CultivatePlan,
    ProviderContext,
    apply_achievements,
    depot_cultivate_service,
    dump_cultivate_targets,
    get_certifying_chain,
    judge_achievements,
    load_oper_box_names,
    parse_cultivate_targets,
    parse_depot_payload,
    resolve_progression,
    summarize_achievements,
)

# OLD: 旧版 MAA（PR #17392 前）gui.json 的 ClientType 字符串 → 新版枚举整数映射
# 新版：Official=0, Bilibili=1, YoStarEN=2, YoStarJP=3, YoStarKR=4, txwy=5
_MAA_CLIENT_TYPE_TO_INT = {
    "Official": 0,
    "Bilibili": 1,
    "YoStarEN": 2,
    "YoStarJP": 3,
    "YoStarKR": 4,
    "txwy": 5,
}


logger = get_logger("MAA 自动代理")
_ANNIHILATION_PROGRESS_RE = re.compile(
    r"(?:剿灭模式|剿滅模式|Annihilation(?: Mode| weekly limit)|殲滅作戦|섬멸 모드)\s*[:：]\s*(\d+)\s*/\s*(\d+)",
    re.IGNORECASE,
)
_MAA_SANITY_RECOGNITION_RE = re.compile(r"理智\s*[:：]\s*\d+\s*/\s*\d+")
# MAA 走到能看到理智的界面（进到副本门口）后，gui.log 才会出现无时间戳的
# 「理智: X/Y」识别行（v6.17.5 国服实测，繁服同字）；其余界面语言样本未核实，
# 命中不到时一律视为未进入战斗流程。
_MAA_SANITY_COMPLETION_MARKERS = (
    "完成任务: 理智作战",
    "完成任务: 活动关优先",
    "完成任务: 库存保持",
    "完成任务: 剩余理智",
    "完成任务: 养成计划",
)
# 养成注入的任务名（语言无关，日志锚定与来源查找都用它，方案决策 27/30）
_MAA_CULTIVATE_TASK_NAME = "养成计划"
_MAA_DATA_UPDATE_TASK_NAME = "更新数据"
# 识别数据档案文件名（MAA 原生格式透传，MAS 绝不回写 MAA，方案决策 31）
_MAA_DEPOT_ARCHIVE_NAME = "DepotData.json"
_MAA_OPER_BOX_ARCHIVE_NAME = "OperBoxData.json"
# 识别链完成标记：锚定注入的任务名 + 链后缀（MAS 强制 zh-cn，方案 §4.2/T0.3）
_MAA_DEPOT_CHAIN_COMPLETION_MARKERS = (
    "完成任务: 库存保持 (仓库识别)",
    f"完成任务: {_MAA_CULTIVATE_TASK_NAME} (仓库识别)",
    f"完成任务: {_MAA_DATA_UPDATE_TASK_NAME} (仓库识别)",
)
_MAA_OPER_BOX_CHAIN_COMPLETION_MARKERS = (
    f"完成任务: {_MAA_DATA_UPDATE_TASK_NAME} (干员识别)",
)
_MAA_FIGHT_COMPLETION_MARKER = "Completed Task Chain: Fight"
# MAA 的停滞提示：只说明任务没有推进，本身不是推进信号。若让它参与 latest_time
# 更新，MAA 每隔一个提醒间隔（默认 30 分钟）写一条就会把停滞计时重置一次，卡死的
# 任务永远攒不满超时阈值，等不到 "MAA 进程超时"。这些片段仅从 latest_time 活跃度
# 判定中排除，日志本身照常写入任务日志。
# 每条按 MAA 支持的 5 种界面语言取一段不含 {0}/{1} 变量的固定文本，已逐条核对在
# MAA 本地化资源中只命中该消息本身。
_MAA_STALL_NOTICE_MARKERS = (
    # TaskStallWarning：MAA 现行文案
    "任务日志输出已超过",
    "任務日誌輸出已超過",
    "Task log output has not been updated for",
    "タスクログ出力が",
    "작업 로그 출력이",
    # TaskTimeoutWarning：旧版 MAA 文案，保留以兼容未升级的 MAA
    "如果长时间无进一步日志更新，可能需要手动干预。",
    "若長時間無進一步日誌更新，可能需要手動干預。",
    "If there are no further log updates for a long time, manual intervention may be required.",
    "長時間ログの更新がない場合、手動で介入する必要があるかもしれません。",
    # 韩文旧文案在句中换行，换行后那半是独立一行、无时间戳，本就不影响
    # latest_time，故取带时间戳那半行的固定结尾。
    "분째 실행 중입니다",
)


def _current_week_marker(now: datetime) -> str:
    """返回 ISO 周标记。"""

    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def _current_month_marker(now: datetime) -> str:
    """返回月份标记。"""

    return now.strftime("%Y-%m")


def _should_run_annihilation(
    start_weekday: str,
    completed_week: str,
    now: datetime,
) -> bool:
    """判断当前用户本次是否应执行剿灭。"""

    if completed_week == _current_week_marker(now):
        return False
    return now.weekday() >= getattr(calendar, start_weekday.upper())


def _parse_annihilation_weekly_progress(log: str) -> tuple[int, int] | None:
    """解析 MAA 输出的剿灭周进度。"""

    matches = _ANNIHILATION_PROGRESS_RE.findall(log)
    if not matches:
        return None
    current, total = (int(value) for value in matches[-1])
    return (current, total) if total > 0 else None


def _has_completed_annihilation_week(log: str) -> bool:
    """判断剿灭日志是否表明本周额度已完成。

    MAA 剿灭结束都会打印「完成任务: 剿灭作战」，以理智识别行区分战斗流程：

    - 无理智识别行：MAA 未进到副本门口，完成即周内剿灭在代理开始前已完成；
    - 有理智识别行但无进度行：进到门口却因理智不足没有开战，未达标；
    - 有进度行但 current < total：开战了但理智不足没能打满进度，未达标；
    - 进度 current >= total：本周剿灭已完成。

    未达标时不记周完成标记，宁可下次代理重试。
    """

    if "完成任务: 剿灭作战" not in log:
        return False

    if not _MAA_SANITY_RECOGNITION_RE.search(log):
        return True

    progress = _parse_annihilation_weekly_progress(log)
    return progress is not None and progress[0] >= progress[1]


def _has_completed_sanity_task(log_records: list[LogRecord]) -> bool:
    """判断日志记录中是否已经完成过体力任务。"""

    for log_record in log_records:
        lines = log_record.content
        if any(
            marker in line
            for line in lines
            for marker in _MAA_SANITY_COMPLETION_MARKERS
        ):
            return True

        for index, line in enumerate(lines):
            if _MAA_FIGHT_COMPLETION_MARKER not in line:
                continue
            previous_task = next(
                (item for item in reversed(lines[:index]) if "完成任务:" in item),
                "",
            )
            if "剿灭" in previous_task:
                continue
            if not previous_task and _ANNIHILATION_PROGRESS_RE.search(
                "".join(lines[max(0, index - 8) : index + 1])
            ):
                continue
            return True

    return False


_MAA_CONFIG_FILES = ("gui.json", "gui.new.json")


def _merge_task_queue(
    archive_queue: list | None,
    baseline_queue: list | None,
    current_queue: list,
    *,
    drop_missing: bool = True,
) -> bool:
    """按 (TaskType, Name) 把运行期任务队列相对基线的变更合并进存档队列。

    两侧都按身份对齐而不是按位置: 队列顺序由 MAS 安排, 用户在 MAA 里插一条、
    删一条都会让下标整体错位, 按下标回写会把 A 的改动写进存档的 B。MAS 没安排
    过的条目(用户自己加的自定义任务等)在存档里找不到对应项, 一律跳过: 队列
    顺序由 MAS 决定, 用户塞进来的东西不回写; 删除同样不透传。

    drop_missing=True(运行回写)时, 基线有而当前没有的条目视为用户删除, 从
    存档一并移除、下次按默认重建; False(脚本设置会话)时保留——设置会话里
    MAA 用自己的默认队列保存, 合成任务从当前队列消失是回写行为而非用户删除,
    不能据此抹掉存档里用户在这些任务上的高级字段。
    """

    if not isinstance(archive_queue, list) or not isinstance(baseline_queue, list):
        return False

    def identity(item: object) -> tuple | None:
        if not isinstance(item, dict):
            return None
        return (item.get("TaskType"), item.get("Name"))

    index_by_id: dict[tuple, int] = {}
    for index, item in enumerate(archive_queue):
        key = identity(item)
        if key is not None:
            index_by_id[key] = index
    baseline_by_id: dict[tuple, dict] = {}
    for item in baseline_queue:
        key = identity(item)
        if key is not None:
            baseline_by_id[key] = item

    changed = False
    for task in current_queue:
        key = identity(task)
        if key is None:
            continue
        base_task = baseline_by_id.get(key)
        if base_task is None:
            continue
        target_index = index_by_id.get(key)
        if target_index is None:
            # 基线认识但存档缺失: 以基线为底补回条目, 让存档向基线结构收敛
            # (MAA 保存重写结构后, 用户对合成任务的修改不丢)
            target = deepcopy(base_task)
            archive_queue.append(target)
            index_by_id[key] = len(archive_queue) - 1
            changed = True
        else:
            target = archive_queue[target_index]
        for key_, value in task.items():
            if base_task.get(key_) != value and target.get(key_) != value:
                target[key_] = deepcopy(value)
                changed = True

    # 运行期从队列里消失的条目: 用户在 MAA 里删掉了这条任务。MAS 的队列顺序由
    # 自己安排, 删除不改变「下次照样生成」, 但要让重建回到默认: 把存档里的这条
    # 一并移除, 托管任务下次按空壳重建、未知任务不再复活。
    if drop_missing:
        current_keys = {identity(task) for task in current_queue}
        dropped = [key for key in baseline_by_id if key not in current_keys]
        if dropped:
            drop_set = set(dropped)
            archive_queue[:] = [
                item for item in archive_queue if identity(item) not in drop_set
            ]
            for _, name in dropped:
                logger.info(
                    f"用户已从 MAA 队列删除「{name}」，存档设置一并重置，下次按默认重建"
                )
            changed = True
    return changed


def _merge_maa_changes(
    archive: dict | list,
    baseline: dict | list,
    current: dict | list,
    *,
    drop_missing: bool = True,
) -> bool:
    """把 MAA 运行期配置相对基线快照的增改原地合并进来源存档。

    只透传运行期(相对基线)真正发生的变更, 新增与修改透传、删除不透传; MAS 托管
    注入自己改写的键(baseline 与 current 相同、仅与存档不同)不能被带回存档,
    否则运行一次就会把用户自己的配置抹成注入值。顶层结构不匹配(如写盘半截被
    截断)整体跳过。
    """

    if type(archive) is not type(baseline) or type(baseline) is not type(current):
        return False
    changed = False
    if isinstance(current, dict):
        for key, value in current.items():
            if key not in baseline:
                if archive.get(key) != value:
                    archive[key] = deepcopy(value)
                    changed = True
                continue
            base_value = baseline[key]
            if isinstance(base_value, dict) and isinstance(value, dict):
                # 存档缺该子树时不把运行期内容整棵写入
                if not isinstance(archive.get(key), dict):
                    continue
                changed = (
                    _merge_maa_changes(
                        archive[key], base_value, value, drop_missing=drop_missing
                    )
                    or changed
                )
            elif key == "TaskQueue" and isinstance(value, list):
                changed = (
                    _merge_task_queue(
                        archive.get("TaskQueue"),
                        base_value,
                        value,
                        drop_missing=drop_missing,
                    )
                    or changed
                )
            elif base_value != value and archive.get(key) != value:
                archive[key] = deepcopy(value)
                changed = True
    return changed


def _merge_maa_config_file(
    archive: dict,
    baseline: dict,
    current: dict,
    scheme: str,
    *,
    drop_missing: bool = True,
) -> bool:
    """按生效方案合并一份 MAA 配置, 返回是否有变更。

    set_maa 会把存档 Current 方案的内容复制进运行目录的 Default 再运行, 运行期
    的变更因此都记在 Default 键上; 存档生效方案不是 Default 时, 把合并目标临时
    指向该方案键, 免得班次推进等原生状态落进未被运行的 Default 方案。
    """

    if scheme == "Default":
        return _merge_maa_changes(archive, baseline, current, drop_missing=drop_missing)

    configurations = archive.get("Configurations")
    if not isinstance(configurations, dict) or not isinstance(
        configurations.get(scheme), dict
    ):
        return _merge_maa_changes(archive, baseline, current, drop_missing=drop_missing)

    original_default = configurations.get("Default")
    configurations["Default"] = configurations[scheme]
    try:
        changed = _merge_maa_changes(
            archive, baseline, current, drop_missing=drop_missing
        )
    finally:
        merged = configurations["Default"]
        if original_default is None:
            del configurations["Default"]
        else:
            configurations["Default"] = original_default
        configurations[scheme] = merged
    return changed


def _restrict_task_queue_to_baseline(
    archive: dict, baseline: dict, scheme: str
) -> bool:
    """把存档生效方案的 TaskQueue 收敛到会话基线(即 set_maa 合成结果)的成员与顺序。

    脚本设置会话里 MAA 保存会用内存默认队列整体重写, 基线之外的原生/自定义条目
    不是用户对 MAS 队列的表达(用户自定义任务队列只在直控模式存在), 一律移除;
    基线任务按身份保留(字段已由身份对齐合并先行写入)并按 MAS 顺序重排。返回
    是否发生变更。gui.json(OLD 格式)没有 TaskQueue, 原样跳过。
    """

    configurations = archive.get("Configurations")
    if not isinstance(configurations, dict):
        return False
    target = configurations.get(scheme)
    base_configurations = baseline.get("Configurations")
    base_default = (
        base_configurations.get("Default")
        if isinstance(base_configurations, dict)
        else None
    )
    if not isinstance(target, dict) or not isinstance(base_default, dict):
        return False
    base_queue = base_default.get("TaskQueue")
    queue = target.get("TaskQueue")
    if not isinstance(base_queue, list) or not isinstance(queue, list):
        return False

    def identity(item: object) -> tuple | None:
        if not isinstance(item, dict):
            return None
        return (item.get("TaskType"), item.get("Name"))

    order: dict[tuple, int] = {}
    for index, item in enumerate(base_queue):
        key = identity(item)
        if key is not None and key not in order:
            order[key] = index

    restricted: list[dict] = []
    seen: set[tuple] = set()
    for item in queue:
        key = identity(item)
        if key is None or key not in order or key in seen:
            continue
        seen.add(key)
        restricted.append(item)
    restricted.sort(key=lambda item: order[identity(item)])
    if restricted == queue:
        return False
    target["TaskQueue"] = restricted
    return True


def _merge_fight_task(source_task: dict, managed_patch: dict) -> dict:
    """以 MAA 原生配置为底，只用 MAS 托管补丁覆盖它声明接管的键。

    补丁是 merge patch 语义：**补丁里出现的键才算 MAS 接管，没出现的键一律
    透传用户在上游界面里的选择**（临期药、源石、博朗台、周计划、指定材料/
    次数、隐藏项等）。因此补丁表（MAA_ANNIHILATION_FIGHT_BASE /
    MAA_REMAIN_FIGHT_BASE）只允许列 MAS 运行必需且自己会消费的字段；往表里
    补一个 MAS 不消费的默认值，等于把用户的选择静默抹掉。
    """

    return {**deepcopy(source_task), **deepcopy(managed_patch)}


def _find_task_source(
    task_queue: list[dict],
    name: str,
    task_type: str,
    *,
    allow_type_fallback: bool = True,
) -> dict | None:
    """按任务名称取原生配置，必要时兼容旧配置中的类型匹配。"""

    for task in task_queue:
        if (
            isinstance(task, dict)
            and task.get("TaskType") == task_type
            and task.get("Name") == name
        ):
            return deepcopy(task)
    if allow_type_fallback:
        for task in task_queue:
            if isinstance(task, dict) and task.get("TaskType") == task_type:
                return deepcopy(task)
    return None


def _build_maa_preset_task_queue(source_queue: list[dict]) -> list[dict]:
    """复用 MAA 原生预设队列，补充 MAS 合成任务并移除生息演算。"""

    source_tasks = [deepcopy(task) for task in source_queue if isinstance(task, dict)]

    def source_or_default(
        name: str,
        task_type: str,
        *,
        allow_type_fallback: bool = True,
    ) -> dict:
        task = _find_task_source(
            source_tasks,
            name,
            task_type,
            allow_type_fallback=allow_type_fallback,
        )
        if task is None:
            # 用户在上游删掉了这条托管任务：只补一个空壳，字段全交给 MAA
            # 自己的默认值；下次会话照此重新生成，用户不必再删一次
            logger.info(f"用户队列中缺少「{name}」，本次按 MAA 默认设置重新生成")
            task = {"$type": f"{task_type}Task", "IsEnable": True}
        # 设置界面队列开关统一为开启（视觉一致）：用户在 MAA GUI 里的真实
        # 开关选择由会话结束的配置回写按身份对齐合并回来，不以这里为准
        task.update({"Name": name, "TaskType": task_type, "IsEnable": True})
        return task

    fight_source = (
        _find_task_source(source_tasks, "理智作战", "Fight", allow_type_fallback=False)
        or {}
    )
    annihilation = _merge_fight_task(
        _find_task_source(source_tasks, "剿灭作战", "Fight", allow_type_fallback=False)
        or {},
        MAA_ANNIHILATION_FIGHT_BASE,
    )
    activity = _build_activity_priority_fight(
        _find_task_source(
            source_tasks, "活动关优先", "Fight", allow_type_fallback=False
        )
        or fight_source,
        "",
        0,
    )
    remain = _find_task_source(
        source_tasks, "剩余理智", "Fight", allow_type_fallback=False
    )
    if remain is None:
        remain = _merge_fight_task(fight_source, MAA_REMAIN_FIGHT_BASE)
    remain.update({"Name": "剩余理智", "TaskType": "Fight", "IsEnable": True})
    depot = _find_task_source(source_tasks, "库存保持", "DepotMaintain")
    if depot is None:
        depot = _build_depot_maintain_task("[]")
    depot.update({"Name": "库存保持", "TaskType": "DepotMaintain", "IsEnable": True})

    queue = [
        source_or_default("开始唤醒", "StartUp"),
        annihilation,
        source_or_default("自动公招", "Recruit"),
        source_or_default("基建换班", "Infrast"),
        activity,
        depot,
        source_or_default("理智作战", "Fight", allow_type_fallback=False),
        remain,
        source_or_default("信用收支", "Mall"),
        source_or_default("领取奖励", "Award"),
    ]

    # 非直控模式队列严格等于 MAS 合成结果：上游其余任务(自动肉鸽、生息演算、
    # 用户自定义任务等)不是 MAS 预设队列的成员，一律不透传带回——用户自定义
    # 任务队列只在直控模式存在（安装目录原生配置即现场，MAS 零写入）。
    return queue


def _build_depot_maintain_task(
    plans_json: str,
    source_task: dict | None = None,
) -> dict:
    """生成 MAA 库存保持任务配置。"""

    source_task = source_task or {}
    source_plans = source_task.get("PlanList") or []
    if not isinstance(source_plans, list):
        source_plans = []
    plans = []
    for plan in json.loads(plans_json):
        if (
            isinstance(plan, dict)
            and isinstance(plan.get("Stage"), str)
            and bool(plan["Stage"])
            and isinstance(plan.get("DropId"), str)
            and bool(plan["DropId"])
            and isinstance(plan.get("DropCount"), int)
            and not isinstance(plan.get("DropCount"), bool)
            and plan["DropCount"] > 0
        ):
            source_plan = next(
                (
                    item
                    for item in source_plans
                    if isinstance(item, dict)
                    and item.get("Stage") == plan["Stage"]
                    and item.get("DropId") == plan["DropId"]
                ),
                {},
            )
            plans.append(
                {
                    **deepcopy(source_plan),
                    "UseMedicine": False,
                    "MedicineCount": 0,
                    "UseStone": False,
                    "StoneCount": 0,
                    "Stage": plan["Stage"],
                    "DropId": plan["DropId"],
                    "DropCount": plan["DropCount"],
                }
            )

    return {
        "$type": source_task.get("$type", "DepotMaintainTask"),
        "Name": "库存保持",
        "IsEnable": True,
        "TaskType": "DepotMaintain",
        "UpdateDepot": source_task.get("UpdateDepot", True),
        "IsStageManually": source_task.get("IsStageManually", False),
        "SkipDuringActivity": source_task.get("SkipDuringActivity", False),
        "SkipDuringResourceCollection": source_task.get(
            "SkipDuringResourceCollection", False
        ),
        "UseAutoSeries": source_task.get("UseAutoSeries", True),
        "PlanList": plans,
    }


def _build_cultivate_task(
    plan: "CultivatePlan",
    source_task: dict | None,
    *,
    skip_during_activity: bool,
    skip_during_resource_collection: bool,
) -> dict | None:
    """把内核养成计划映射为 MAA 养成任务（MAA 字段名唯一出现点，方案 §4.1）。

    药剂/源石按决策 5 硬编码关闭；计划无可用刷取条目时不生成任务。
    DropCount 是 MAA 的"保有量目标"语义（need = DropCount − 该材料现存，
    只比对本材料），故写净缺口 + 档案现存，MAA 现算后落回净缺口。
    """

    source_task = source_task or {}
    source_plans = source_task.get("PlanList") or []
    if not isinstance(source_plans, list):
        source_plans = []
    plans = []
    for entry in plan.entries:
        source_plan = next(
            (
                item
                for item in source_plans
                if isinstance(item, dict)
                and item.get("Stage") == entry.stage_code
                and item.get("DropId") == entry.item_id
            ),
            {},
        )
        plans.append(
            {
                **deepcopy(source_plan),
                "UseMedicine": False,
                "MedicineCount": 0,
                "UseStone": False,
                "StoneCount": 0,
                "Stage": entry.stage_code,
                "DropId": entry.item_id,
                "DropCount": entry.amount + entry.held,
            }
        )
    if not plans:
        return None

    return {
        "$type": source_task.get("$type", "DepotMaintainTask"),
        "Name": _MAA_CULTIVATE_TASK_NAME,
        "IsEnable": True,
        "TaskType": "DepotMaintain",
        # 仓库识别随养成任务执行，缺口由 MAA 按最新库存现算（方案 §9）
        "UpdateDepot": True,
        "IsStageManually": True,
        "SkipDuringActivity": skip_during_activity,
        "SkipDuringResourceCollection": skip_during_resource_collection,
        "OnlyFirstInsufficientPlan": False,
        "UseAutoSeries": False,
        "UseMedicine": False,
        "UseStone": False,
        "UseExpiringMedicine": False,
        "PlanList": plans,
    }


def _build_data_update_task(source_task: dict | None) -> dict:
    """构建更新数据任务（干员识别 + 仓库识别，方案决策 7/30）。

    识别结果供 check_log 采集落用户档案，缺口始终由 MAA 执行时现算。
    """

    source_task = source_task or {}
    return {
        **deepcopy(source_task),
        "$type": source_task.get("$type", "UserDataUpdateTask"),
        "Name": _MAA_DATA_UPDATE_TASK_NAME,
        "IsEnable": True,
        "TaskType": "UserDataUpdate",
        "UpdateOperBox": True,
        "UpdateDepot": True,
        "TriggerInterval": "EveryTime",
    }


def _resolve_activity_stage(
    activity_stages: list[dict], configured_index: int
) -> str | None:
    """按序号选择当前活动材料关卡，序号失效时回退到第一项。"""

    stages = [
        stage["Value"]
        for stage in activity_stages
        if isinstance(stage, dict)
        and isinstance(stage.get("Value"), str)
        and stage["Value"]
    ]
    if not stages:
        return None
    return (
        stages[configured_index - 1] if configured_index <= len(stages) else stages[0]
    )


def _build_activity_priority_fight(
    fight_task: dict, activity_stage: str, medicine_numb: int
) -> dict:
    """生成 MAA 活动关优先任务，使用独立理智药额度。

    活动关优先与理智作战刻意保持为两个独立任务，分别使用各自的理智药
    额度（Task.ActivityMedicineNumb 与计划表 MedicineNumb），互不转移。
    """

    activity_fight = deepcopy(fight_task)
    activity_fight.update(
        {
            "Name": "活动关优先",
            "IsEnable": True,
            "TaskType": "Fight",
            "StagePlan": [activity_stage],
            "IsStageManually": True,
            "UseOptionalStage": False,
            "UseWeeklySchedule": False,
            # 活动关优先不继承理智作战的「指定材料 / 指定次数」门禁：它是同一套
            # 打法换个关卡，带上这些门禁会在刷够材料或跑满次数后提前收工
            "EnableTargetDrop": False,
            "DropId": "",
            "DropCount": 0,
            "IsInventoryTarget": False,
            "EnableTimesLimit": False,
            "UseMedicine": medicine_numb > 0,
            "MedicineCount": medicine_numb,
        }
    )
    activity_fight.setdefault("$type", "FightTask")
    return activity_fight


class AutoProxyTask(TaskExecuteBase):
    """自动代理模式"""

    # 养成采集状态：prepare() 每轮重置；类级默认保证未跑 prepare 的
    # 实例（如单测直接构造）调用 check_log 时不炸
    _cultivate_collected_depot: bool = False
    _cultivate_collected_oper_box: bool = False
    _depot_maintain_suppressed: bool = False

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaConfig,
        user_config: MultipleConfig[MaaUserConfig],
        emulator_manager: DeviceBase,
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

    async def check(self) -> str:

        # 单独运行脚本是用户主动指定的一次性运行，不受单日代理次数上限约束
        if (
            self.task_info.is_queue_task
            and self.script_config.get("Run", "ProxyTimesLimit") != 0
            and self.cur_user_config.get("Data", "ProxyTimes")
            >= self.script_config.get("Run", "ProxyTimesLimit")
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"

        if (
            self.cur_user_config.get("Info", "Mode") == "用户"
            and not (
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
            ).exists()
        ):
            self.cur_user_item.status = "异常"
            return "未找到用户的 MAA 配置文件，请先在用户配置页完成 「MAA配置」 步骤"
        return "Pass"

    async def prepare(self):

        self.maa_process_manager = ProcessManager()
        self.maa_log_monitor = LogMonitor(
            (1, 20),
            "%Y-%m-%d %H:%M:%S",
            self.check_log,
            except_logs=list(_MAA_STALL_NOTICE_MARKERS),
        )
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()
        self.if_game_hot_update = False
        self.pending_res_version = ""
        self._maa_config_baseline: dict[str, dict] | None = None
        # 养成采集：本轮是否采到过识别数据（每类以最后一次标记为准覆盖档案，
        # 见 _collect_cultivate_archive）；
        # 达成文案供 final_task 的统计信息报告，按 (干员, 档位) 去重累积
        self._cultivate_collected_depot = False
        self._cultivate_collected_oper_box = False
        self._cultivate_achievement_summary: list[str] = []
        # 上一轮是否真的被养成接管抑制过库存保持：只有抑制过才在下一轮
        # 恢复开关值，否则会把已完成的库存保持重新点亮、重试轮整个重跑
        self._depot_maintain_suppressed = False

        self.maa_root_path = Path(self.script_config.get("Info", "Path"))
        self.maa_set_path = self.maa_root_path / "config"
        self.maa_log_path = self.maa_root_path / "debug/gui.log"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"
        self.maa_tasks_path = self.maa_root_path / "resource/tasks/tasks.json"

        quick_config = self.cur_user_config.get("Info", "IfQuickConfig")
        self.run_book = {
            "GreenTicketStore": not quick_config
            or not self.cur_user_config.get("Task", "IfGreenTicketStore"),
            "Annihilation": not quick_config
            or self.cur_user_config.get("Info", "Annihilation") == "Close",
            "Routine": False,
        }

        if not self.run_book["GreenTicketStore"]:
            completed_month = self.cur_user_config.get("Data", "GreenTicketStoreMonth")

            if completed_month == _current_month_marker(datetime.now(tz=UTC4)):
                self.run_book["GreenTicketStore"] = True
                logger.info(
                    f"用户 {self.cur_user_item.name} 本次跳过绿票商店："
                    f"本月记录={completed_month}"
                )

        if not self.run_book["Annihilation"]:
            now = datetime.now(tz=UTC4)
            start_weekday = self.cur_user_config.get("Info", "AnnihilationStartWeekday")

            if not _should_run_annihilation(
                start_weekday,
                self.cur_user_config.get("Data", "AnnihilationCompletedWeek"),
                now,
            ):
                self.run_book["Annihilation"] = True
                logger.info(
                    f"用户 {self.cur_user_item.name} 本次跳过剿灭："
                    f"开始日={start_weekday}，本周记录="
                    f"{self.cur_user_config.get('Data', 'AnnihilationCompletedWeek')}"
                )

    def _resolve_log_file_path(self) -> Path:
        return self.maa_log_path

    async def main_task(self):
        """自动代理模式主逻辑"""

        # 初始化每日代理状态
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}",
                    ),
                )
            return

        await self.prepare()

        logger.info(f"开始代理用户: {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        # 执行任务前脚本（每用户仅一次）
        if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                "脚本前任务",
            )

        # 执行绿票商店 + 剿灭 + 日常
        # 绿票商店的任务链只认主界面、跑完也停在商店页，放在最前面由后续模式的开始唤醒收拾界面
        for self.mode in ["GreenTicketStore", "Annihilation", "Routine"]:
            if self.run_book[self.mode]:
                continue

            self.cur_user_item.status = f"运行 - {MAA_RUN_MOOD_BOOK[self.mode]}"

            if not self.cur_user_config.get("Info", "IfQuickConfig"):
                # 来源队列整体交给 MAA 执行，不从隐藏面板推导任务或拆分阶段。
                self.task_dict = {}
            elif self.mode == "Routine":
                self.task_dict = {
                    task: self.cur_user_config.get("Task", f"If{task}")
                    for task in MAA_TASKS
                }
            elif self.mode == "Annihilation":
                self.task_dict = {
                    task: bool(task in ("StartUp", "Fight")) for task in MAA_TASKS
                }
            else:  # GreenTicketStore
                self.task_dict = {task: task == "StartUp" for task in MAA_TASKS}

            logger.info(
                f"用户 {self.cur_user_item.name} - 模式: {self.mode} - 任务列表: {list(self.task_dict.values())}"
            )

            for i in range(self.script_config.get("Run", "RunTimesLimit")):
                if self.run_book[self.mode]:
                    break
                logger.info(
                    f"用户 {self.cur_user_item.name} - 模式: {self.mode} - 尝试次数: {i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
                )
                self.log_start_time = datetime.now()
                self.cur_user_item.log_record[self.log_start_time] = (
                    self.cur_user_log
                ) = LogRecord()

                try:
                    self.script_info.log = "正在启动模拟器"
                    emulator_info = await self.emulator_manager.open(
                        self.script_config.get("Emulator", "Index"),
                        ARKNIGHTS_PACKAGE_NAME[
                            self.cur_user_config.get("Info", "Server")
                        ],
                    )
                except Exception as e:
                    logger.opt(exception=True).warning(
                        f"用户: {self.cur_user_uid} - 模拟器启动失败: {e}"
                    )
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="error",
                            message=f"启动模拟器时出现异常: {e}",
                        ),
                    )
                    self.cur_user_log.content = [
                        "模拟器启动失败, MAA 未实际运行, 无日志记录"
                    ]
                    self.cur_user_log.status = "模拟器启动失败"

                    await close_emulator(self)

                    await Notify.push_plyer(
                        "用户自动代理出现异常！",
                        f"用户 {self.cur_user_item.name} 的{MAA_RUN_MOOD_BOOK[self.mode]}部分出现一次异常",
                        f"{self.cur_user_item.name}的{MAA_RUN_MOOD_BOOK[self.mode]}出现异常",
                        3,
                    )
                    continue

                logger.info(
                    f"模拟器启动完成: 用户 {self.cur_user_uid} - 模式 "
                    f"{self.mode} - 实例 "
                    f"{self.script_config.get('Emulator', 'Index')} - "
                    f"ADB {emulator_info.adb_address}"
                )

                if Config.get("Function", "IfSilence"):
                    try:
                        await self.emulator_manager.setVisible(
                            self.script_config.get("Emulator", "Index"), False
                        )
                    except Exception as e:
                        logger.opt(exception=True).warning(f"模拟器隐藏失败: {e}")

                # 需要用户手动更新游戏时重试无意义，直接结束本模式的重试
                if self.script_config.get(
                    "Run", "IfCheckGameUpdate"
                ) and not await self.handle_game_update(emulator_info):
                    break

                await self.set_maa(emulator_info)

                logger.info(f"启动MAA进程: {self.maa_exe_path}")
                self.wait_event.clear()
                await self.maa_process_manager.open_process(self.maa_exe_path)
                logger.info(
                    f"MAA 进程已创建: {self.maa_exe_path} - "
                    f"PID: {self.maa_process_manager.main_pid}"
                )
                await asyncio.sleep(1)  # 等待 MAA 处理日志文件
                logger.info(
                    "MAA 进程等待日志文件后状态: "
                    f"running={await self.maa_process_manager.is_running()}"
                )
                await self.maa_log_monitor.start_monitor_file(
                    self._resolve_log_file_path, self.log_start_time
                )
                await self.wait_event.wait()
                await self.maa_log_monitor.stop()

                if self.cur_user_log.status == "Success!":
                    self.run_book[self.mode] = True
                    logger.info(f"用户: {self.cur_user_uid} - MAA进程完成代理任务")
                    self.script_info.log = (
                        "检测到 MAA 完成代理任务\n正在等待相关程序结束"
                    )
                    if self.pending_res_version:
                        # 代理成功说明资源热更新已走完，记录版本供下次比对
                        await self.cur_user_config.set(
                            "Data", "LastResVersion", self.pending_res_version
                        )
                        self.if_game_hot_update = False
                else:
                    logger.warning(
                        f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                    )
                    self.script_info.log = (
                        f"{self.cur_user_log.status}\n正在中止相关程序"
                    )

                    await self.maa_process_manager.kill()
                    await close_emulator(self)
                    await System.kill_process(self.maa_exe_path)

                    # 绿票商店每月顺手买一次，失败不重试也不惊动用户，月份没写回下次调度自会再来
                    if self.mode == "GreenTicketStore":
                        self.run_book[self.mode] = True
                    else:
                        await Notify.push_plyer(
                            "用户自动代理出现异常！",
                            f"用户 {self.cur_user_item.name} 的{MAA_RUN_MOOD_BOOK[self.mode]}部分出现一次异常",
                            f"{self.cur_user_item.name}的{MAA_RUN_MOOD_BOOK[self.mode]}出现异常",
                            3,
                        )

                if self.cur_user_config.get("Info", "IfQuickConfig"):
                    await self._finish_cultivate_round()
                await self._sync_maa_config_updates()

                await update_maa(self.maa_root_path)
                await asyncio.sleep(3)

        # 执行任务后脚本（每用户仅一次）
        if self.cur_user_config.get("Info", "IfScriptAfterTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                "脚本后任务",
            )

    def _cultivate_archive_dir(self) -> Path:
        """当前用户的识别数据档案目录（方案决策 31：归属以写入时的
        cur_user_uid 为准，查询与注入判定只读档案，绝不回写 MAA）。"""

        return Path.cwd() / f"data/{self.script_info.script_id}/{self.cur_user_uid}"

    def _archive_recognition_file(
        self, name: str, *, require_fresh_sync_time: bool = False
    ) -> bool:
        """把 MAA 安装目录的识别结果只读复制进当前用户档案（T1.17）。

        整份原子覆盖：识别数据是全量快照且档案可由下一轮重跑再生，
        无 diff、无回滚（方案决策 31）。

        Args:
            name: 识别数据文件名（DepotData.json / OperBoxData.json）。
            require_fresh_sync_time: 是否校验 syncTime 不早于本轮开始
                （DepotData 有该字段；OperBoxData 无时间字段，靠会话归因）。

        Returns:
            是否成功落档；失败不阻断运行，下一轮重新采集。
        """

        source = self.maa_root_path / "data" / name
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
            if require_fresh_sync_time:
                _, sync_time = parse_depot_payload(payload)
                if sync_time < int(self.log_start_time.timestamp()):
                    logger.warning(
                        f"用户 {self.cur_user_item.name} 的 {name} syncTime 早于本轮开始, 弃用本次采集"
                    )
                    return False
            archive_dir = self._cultivate_archive_dir()
            archive_dir.mkdir(parents=True, exist_ok=True)
            write_file(archive_dir / name, payload)
            logger.info(f"用户 {self.cur_user_item.name} 的识别数据已落档案: {name}")
            return True
        except (OSError, ValueError, TypeError):
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} 采集识别数据失败: {name}"
            )
            return False

    async def _collect_cultivate_archive(self, log: str) -> None:
        """识别链完成标记 → 立即读安装目录识别数据落用户档案（方案 §4.2）。

        归因依据"该链运行在当前用户的 MAA 会话内"（串行调度 + StartUp 已
        切号）；每类数据每轮以最后一次识别标记为准并覆盖档案——队列里养成
        计划（刷取前）与更新数据（刷取后）各有一条仓库识别，取后者下一轮
        缺口判定才用得上刷取后的库存，否则补齐材料后仍会多接管一轮。
        """

        if any(marker in log for marker in _MAA_DEPOT_CHAIN_COMPLETION_MARKERS):
            self._cultivate_collected_depot = self._archive_recognition_file(
                _MAA_DEPOT_ARCHIVE_NAME, require_fresh_sync_time=True
            )
        if any(marker in log for marker in _MAA_OPER_BOX_CHAIN_COMPLETION_MARKERS):
            self._cultivate_collected_oper_box = self._archive_recognition_file(
                _MAA_OPER_BOX_ARCHIVE_NAME
            )

    async def _finish_cultivate_round(self) -> None:
        """运行结束钩子：本轮采集到识别数据时刷新达成状态并持久化（T1.11）。

        无采集观测时 no-op（绿票/剿灭轮天然空转）；判定只用可自证链，
        异常只记日志，档案留待下一轮注入前拦截兜底。
        """

        if not (self._cultivate_collected_depot or self._cultivate_collected_oper_box):
            return
        self._cultivate_collected_depot = False
        self._cultivate_collected_oper_box = False
        try:
            targets = parse_cultivate_targets(
                json.loads(self.cur_user_config.get("Task", "CultivateTargets"))
            )
            if not targets:
                return
            # 森空岛快照走 TTL 缓存（force=False）：注入时刚强刷过，运行末
            # 复用当轮观测即可；缓存过期才再拉一次（决策 38）
            skland = await Config.get_maa_cultivate_skland_progression(
                str(self.script_info.script_id), str(self.cur_user_uid)
            )
            context = ProviderContext(
                maa_data_dir=self._cultivate_archive_dir(),
                skland_progressions=skland[0] if skland else {},
                skland_captured_at=skland[1] if skland else 0,
            )
            snapshots = {
                target.operator_id: resolve_progression(
                    target.operator_id, get_certifying_chain(), context
                )
                for target in targets
            }
            achievements = judge_achievements(targets, snapshots)
            updated = apply_achievements(targets, achievements)
            if updated != list(targets):
                await self.cur_user_config.set(
                    "Task",
                    "CultivateTargets",
                    json.dumps(dump_cultivate_targets(updated), ensure_ascii=False),
                )
                removed = summarize_achievements(
                    targets, achievements, load_oper_box_names(context)
                )
                for line in removed:
                    if line not in self._cultivate_achievement_summary:
                        self._cultivate_achievement_summary.append(line)
        except Exception as e:
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} 养成达成刷新失败: {e}"
            )

    async def _set_cultivate_notice(self, notice: str) -> None:
        """写接管提示字段；值未变化时跳过，避免每轮无谓的配置写盘。"""

        if self.cur_user_config.get("Data", "CultivateNotice") == notice:
            return
        await self.cur_user_config.set("Data", "CultivateNotice", notice)

    async def _prepare_cultivate_injection(
        self, source_queue: list[dict]
    ) -> tuple[dict | None, bool, bool]:
        """准备养成计划注入：达成拦截 → 计划构建 → 接管判定（方案 §4.1/§9）。

        仅在开关开启且目标非空时生效（Routine 门控由调用方负责）；数据集、
        练度、库存任何异常一律 fail-open——本轮不注入、不接管，既有任务
        队列不受影响（决策 28）。

        Returns:
            (养成任务配置, 是否存在原始目标, 是否接管抑制库存保持)
        """

        if not self.cur_user_config.get("Task", "IfCultivate"):
            await self._set_cultivate_notice("")
            return None, False, False
        try:
            raw_targets = json.loads(
                self.cur_user_config.get("Task", "CultivateTargets")
            )
        except (TypeError, ValueError):
            raw_targets = []
        targets = parse_cultivate_targets(raw_targets)
        if not targets:
            await self._set_cultivate_notice("")
            return None, False, False

        try:
            # 森空岛练度注入前强刷（决策 38：注入前重新查询一次，滞后≈0）；
            # 未绑定/凭据失效/网络失败返回 None，链短路落 local，不炸注入
            skland = await Config.get_maa_cultivate_skland_progression(
                str(self.script_info.script_id), str(self.cur_user_uid), force=True
            )
            (
                updated_targets,
                plan,
                gap,
            ) = await depot_cultivate_service.prepare_cultivate(
                targets=targets,
                # 只读用户档案（归属正确）：隔日档案对达成判定只会保守
                # （练度单调），缺口判定的新鲜度由每轮采集保底（方案决策 31）
                maa_data_dir=self._cultivate_archive_dir(),
                config_path=Config.config_path,
                proxy=Config.proxy,
                skland=skland,
            )
        except Exception as e:
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} 养成数据准备失败, 本轮跳过养成注入: {e}"
            )
            await self._set_cultivate_notice("")
            return None, True, False

        # 达成拦截后把目标状态写回档案：可自证达成的目标已移除（方案 §7.6）；
        # 状态无变化时跳过，避免每轮无谓写盘
        if updated_targets != list(targets):
            await self.cur_user_config.set(
                "Task",
                "CultivateTargets",
                json.dumps(dump_cultivate_targets(updated_targets), ensure_ascii=False),
            )
        # 接管态写提示字段供前端展示（方案 T1.19；空 = 未接管）
        await self._set_cultivate_notice(
            "材料存在缺口，本轮库存保持暂停，由养成计划接管" if gap else ""
        )

        cultivate_task = None
        # gap 与计划条目同源（同一份净需求），缺口为假即无条目可刷；
        # 显式门控，接管判定与注入判定不允许出现任何分歧
        if plan is not None and gap:
            cultivate_task = _build_cultivate_task(
                plan,
                _find_task_source(
                    source_queue, _MAA_CULTIVATE_TASK_NAME, "DepotMaintain"
                ),
                skip_during_activity=self.cur_user_config.get(
                    "Task", "CultivateSkipDuringActivity"
                ),
                skip_during_resource_collection=self.cur_user_config.get(
                    "Task", "CultivateSkipDuringResourceCollection"
                ),
            )
        return cultivate_task, True, gap

    def _restore_depot_maintain(self) -> None:
        """按开关事实恢复库存保持，仅限上一轮确实被养成接管抑制过时。

        每次 set_maa 都无条件恢复会把上一轮已完成（check_log 已置 False）
        的库存保持重新点亮，重试轮把它整个重跑一遍；决策 28 的 fail-open
        只在抑制过的那一轮之后需要。
        """

        if not self._depot_maintain_suppressed:
            return
        self.task_dict["DepotMaintain"] = self.cur_user_config.get(
            "Task", "IfDepotMaintain"
        )
        self._depot_maintain_suppressed = False

    async def set_maa(self, emulator_info: DeviceInfo):
        """配置MAA运行参数"""

        logger.info(f"开始配置MAA运行参数: {self.mode}")

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)

        # 哔哩哔哩用户协议
        if self.cur_user_config.get("Info", "Server") == "Bilibili":
            await agree_bilibili(self.maa_tasks_path, True)
        else:
            await agree_bilibili(self.maa_tasks_path, False)

        # 下发前归档 MAS 配置到用户池（下发源，运行回写 _sync_maa_config_updates
        # 会覆盖它；带页面任务字段侧车，指纹去重，失败不阻断运行）。目标路径
        # 按来源 owner（脚本态共享 Default 目录，直控无 MAS 配置目录不归档）。
        # native 池由 manager prepare 在任务级一次性归档
        archive_dir = self._config_archive_dir()
        if archive_dir is not None:
            archive_mas_runtime_backup(
                self.script_info.script_id,
                str(self.cur_user_uid),
                archive_dir,
                overlay=read_overlay_values(self.cur_user_config),
                # 备份标注来源：tri_state 池跨来源恢复靠它切回
                mode=str(self.cur_user_config.get("Info", "Mode") or "").strip()
                or None,
            )

        # ── 第一段：来源落盘 ──────────────────────────────────────────
        # 用 MAS 托管配置覆盖 MAA 原生配置目录。直控来源跳过这一段——
        # 直控的事实源是 MAA 安装目录里现有的原生配置。
        if self.config_mode == CONFIG_SOURCE_SCRIPT:
            shutil.copytree(
                (Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"),
                self.maa_set_path,
                dirs_exist_ok=True,
            )
        elif self.config_mode == CONFIG_SOURCE_USER:
            shutil.copytree(
                (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
                ),
                self.maa_set_path,
                dirs_exist_ok=True,
            )
        elif self.direct_control:
            # 直控从本轮原生快照开始，不能继承上一用户或上一阶段的快速配置。
            source = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
            if source.is_dir():
                shutil.copytree(source, self.maa_set_path, dirs_exist_ok=True)

        gui_set = read_file(self.maa_set_path / "gui.json")
        gui_new_set = read_file(self.maa_set_path / "gui.new.json")

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

        # 使用简体中文
        global_set["GUI.Localization"] = "zh-cn"  # OLD: 即将移除
        gui_new_set.setdefault("Gui", {})["Localization"] = "zh-cn"

        if self.cur_user_config.get("Info", "IfQuickConfig"):
            await self._apply_maa_quick_config(gui_new_set)
        self._configure_maa_runtime(gui_set, gui_new_set, emulator_info)

        write_file(self.maa_set_path / "gui.json", gui_set)
        write_file(self.maa_set_path / "gui.new.json", gui_new_set)
        self._snapshot_maa_config()
        mark_native_config_injected(
            Path.cwd() / f"data/{self.script_info.script_id}/Temp",
            self.maa_set_path,
            script_id=self.script_info.script_id,
        )
        logger.success(f"MAA运行参数配置完成: {self.mode}")

    async def _apply_maa_quick_config(self, gui_new_set: dict) -> None:
        """仅开启快速配置时构造面板任务，来源导入与启动设置留在外层。"""

        task_set = {}
        source_queue = gui_new_set["Configurations"]["Default"].get("TaskQueue", [])
        if not isinstance(source_queue, list):
            source_queue = []
        # 活动关优先是独立任务，仅由自身开关控制，不受理智作战开关影响
        activity_stage = None
        if self.mode == "Routine" and self.cur_user_config.get(
            "Task", "IfActivityFirst"
        ):
            # 活动关卡信息已在 MaaManager.prepare 里刷新过一次, 这里直接用缓存
            stage_info = await Config.get_stage_info(
                "Info",
                server=self.cur_user_config.get("Info", "Server"),
            )
            activity_stage = _resolve_activity_stage(
                stage_info.get("Activity", []),
                self.cur_user_config.get("Task", "ActivityStageIndex"),
            )

        # 养成计划注入，仅 Routine 模式（方案决策 27）：剿灭/绿票轮不注入。
        # 必须在下方 MAA_TASKS 装配循环之前执行：接管抑制靠提前置
        # task_dict["DepotMaintain"] = False 走既有"开关关→整条不写"路径
        # （方案决策 20/28，不得只从队列剔除）
        cultivate_task = None
        update_task = None
        if self.mode == "Routine":
            self._restore_depot_maintain()
            (
                cultivate_task,
                has_targets,
                takes_over,
            ) = await self._prepare_cultivate_injection(source_queue)
            if has_targets:
                # 更新数据紧跟养成/库存保持注入（方案决策 30），为下一轮
                # 提供归属正确的识别数据
                update_task = _build_data_update_task(
                    _find_task_source(
                        source_queue, _MAA_DATA_UPDATE_TASK_NAME, "UserDataUpdate"
                    )
                )
            if takes_over:
                self.task_dict["DepotMaintain"] = False
                self._depot_maintain_suppressed = True
                logger.info(
                    f"用户 {self.cur_user_item.name} 养成计划接管本轮, 库存保持暂停注入"
                )

        # 优先按任务名称匹配，确保多个 Fight 任务各自继承原生高级配置。
        for en_task, zh_task in zip(MAA_TASKS, MAA_TASKS_ZH):
            # 默认关闭时不写入新任务，兼容尚未支持该任务类型的 MAA 版本
            # （库存保持、更换主题；更换主题需 MAA v6.17.3+，旧版无法反序列化未知任务类型）
            if (
                en_task in ("DepotMaintain", "SwitchTheme")
                and not self.task_dict[en_task]
            ):
                continue

            task_set[en_task] = _find_task_source(
                source_queue,
                zh_task,
                en_task,
                allow_type_fallback=en_task != "Fight",
            ) or {
                "$type": f"{en_task}Task",
                "Name": zh_task,
                "IsEnable": False,
                "TaskType": en_task,
            }

        annihilation_source = _find_task_source(
            source_queue, "剿灭作战", "Fight", allow_type_fallback=False
        )
        activity_source = _find_task_source(
            source_queue, "活动关优先", "Fight", allow_type_fallback=False
        )
        remain_source = _find_task_source(
            source_queue, "剩余理智", "Fight", allow_type_fallback=False
        )

        if "DepotMaintain" in task_set:
            task_set["DepotMaintain"] = _build_depot_maintain_task(
                self.cur_user_config.get("Task", "DepotMaintainPlans"),
                source_task=task_set["DepotMaintain"],
            )

        # 加载关卡号配置
        if self.cur_user_config.get("Info", "StageMode") == "Fixed":
            plan_data = {
                stage_key: self.cur_user_config.get("Info", stage_key)
                for stage_key in MAA_STAGE_KEY
            }
        else:
            plan = Config.PlanConfig[
                uuid.UUID(self.cur_user_config.get("Info", "StageMode"))
            ]
            plan_data = {
                stage_key: plan.get_current_info(stage_key).getValue()
                for stage_key in MAA_STAGE_KEY
            }

        fight_source = deepcopy(task_set["Fight"])

        # 理智作战相关配置项
        if self.mode == "Annihilation":
            # 关卡配置
            task_set["Fight"] = _merge_fight_task(
                annihilation_source or fight_source, MAA_ANNIHILATION_FIGHT_BASE
            )
            task_set["Fight"]["UseMedicine"] = bool(
                plan_data.get("MedicineNumb", 0) != 0
            )
            task_set["Fight"]["MedicineCount"] = plan_data.get("MedicineNumb", 0)
            task_set["Fight"]["AnnihilationStage"] = self.cur_user_config.get(
                "Info", "Annihilation"
            )

        elif self.mode == "Routine":
            # 普通理智作战不能继承剿灭任务的语义字段。
            task_set["Fight"].update(
                {
                    "Name": "理智作战",
                    "TaskType": "Fight",
                    "UseCustomAnnihilation": False,
                }
            )
            # 理智药配置
            task_set["Fight"]["UseMedicine"] = bool(
                plan_data.get("MedicineNumb", 0) != 0
            )
            task_set["Fight"]["MedicineCount"] = plan_data.get("MedicineNumb", 0)
            # 关卡配置
            task_set["Fight"]["Series"] = int(plan_data.get("SeriesNumb", "0"))
            task_set["Fight"]["StagePlan"] = [
                (
                    ""
                    if plan_data.get(stage_key, "-") == "*"
                    else plan_data.get(stage_key, "-")
                )
                for stage_key in ("Stage", "Stage_1", "Stage_2", "Stage_3")
                if plan_data.get(stage_key, "-") != "-"
            ]
            task_set["Fight"]["IsStageManually"] = True
            task_set["Fight"]["UseOptionalStage"] = True
            task_set["Fight"]["UseWeeklySchedule"] = False

            # 脚本模式下托管的配置
            if self.cur_user_config.get("Info", "Mode") == "脚本":
                task_set["Fight"]["EnableTimesLimit"] = False
                task_set["Fight"]["EnableTargetDrop"] = False
                fight_source = deepcopy(task_set["Fight"])

            # 基建配置
            if self.cur_user_config.get("Info", "InfrastMode") == "Custom":
                infrast_path = (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/Infrastructure/infrastructure.json"
                )
                infrast_plans, infrast_problem = load_infrast_plans(
                    self.cur_user_config.get("Data", "CustomInfrast")
                )
                if infrast_problem is None:
                    infrast_path.parent.mkdir(parents=True, exist_ok=True)
                    infrast_path.write_text(
                        self.cur_user_config.get("Data", "CustomInfrast"),
                        encoding="utf-8",
                    )
                    task_set["Infrast"]["Mode"] = "Custom"
                    task_set["Infrast"]["Filename"] = str(infrast_path)
                    task_set["Infrast"]["InfrastPlan"] = [
                        {
                            "Index": index,
                            "Name": infrast.get("name", f"第 {index + 1} 班"),
                            "Description": infrast.get("description", ""),
                            "DescriptionPost": infrast.get("description_post", ""),
                            "Period": infrast.get("period", []),
                        }
                        for index, infrast in enumerate(infrast_plans)
                    ]
                    # PlanSelect 保留用户存档中的值(不按轮次改写)——带时段表默认 -1=MAA
                    # 按时段自动选班; 手动选班/无时段表的轮换推进均由 MAA 原生「自动保存
                    # 为下个计划」完成, 经运行后配置回写管道存回每用户存档
                    if (
                        infrast_plan_mode(infrast_plans) == "rotate"
                        and task_set["Infrast"].get("PlanSelect", -1) == -1
                    ):
                        # 无时段表: 缺省与显式「自动换班」(-1)都归一到第一班开始轮换。
                        # -1 时 MAA 匹配不到时段, 会永远跑第一班且无法推进(并打错误日志)
                        task_set["Infrast"]["PlanSelect"] = 0
                else:
                    logger.warning(
                        f"用户 {self.cur_user_item.name} 的{infrast_problem}, 将使用普通基建模式"
                    )
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="warning",
                            message=(
                                f"用户 {self.cur_user_item.name} 的{infrast_problem}，"
                                f"将使用普通基建模式"
                            ),
                        ),
                    )
                    task_set["Infrast"]["Mode"] = "Normal"
            else:
                task_set["Infrast"]["Mode"] = self.cur_user_config.get(
                    "Info", "InfrastMode"
                )

        activity_fight = None
        if self.mode == "Routine" and activity_stage:
            activity_medicine_numb = self.cur_user_config.get(
                "Task", "ActivityMedicineNumb"
            )
            activity_fight = _build_activity_priority_fight(
                activity_source or fight_source, activity_stage, activity_medicine_numb
            )

        # 导出任务配置
        self.task_dict["StartUp"] = True
        task_queue = gui_new_set["Configurations"]["Default"]["TaskQueue"] = []
        for task_type in MAA_TASKS:
            if task_type not in task_set:
                continue

            task_set[task_type]["IsEnable"] = self.task_dict[task_type]
            if task_type == "Fight" and update_task is not None:
                # 更新数据位于库存保持之后、理智作战之前（方案 §9 队列 #5）
                task_queue.append(update_task)
            task_queue.append(task_set[task_type])

            if task_type == "StartUp" and activity_fight:
                task_queue.append(activity_fight)
            if task_type == "StartUp" and cultivate_task is not None:
                # 养成计划位于活动关优先之后、库存保持之前（方案 §9 队列 #3）
                task_queue.append(cultivate_task)

            # 剩余理智关卡配置
            if (
                self.mode == "Routine"
                and task_type == "Fight"
                and self.task_dict["Fight"]
                and plan_data.get("Stage_Remain", "-") != "-"
            ):
                remain_fight = _merge_fight_task(
                    remain_source or fight_source, MAA_REMAIN_FIGHT_BASE
                )
                remain_fight["StagePlan"] = [
                    (
                        ""
                        if plan_data.get("Stage_Remain", "-") == "*"
                        else plan_data.get("Stage_Remain", "-")
                    )
                ]
                remain_fight["Series"] = int(plan_data.get("SeriesNumb", "0"))
                task_queue.append(remain_fight)

        # 绿票商店走 MAA 的自定义任务，本模式下队列里只有它和开始唤醒
        if self.mode == "GreenTicketStore":
            task_queue.append(dict(MAA_GREEN_TICKET_STORE_TASK))

        # 非直控模式队列严格等于 MAS 合成结果：来源队列里的未知任务(自动肉鸽、
        # 生息演算、用户自定义任务等)不透传带回——用户自定义任务队列只在直控
        # 模式存在(MAS 零写入, 安装目录原生配置即现场)。

    def _configure_maa_runtime(
        self, gui_set: dict, gui_new_set: dict, emulator_info: DeviceInfo
    ) -> None:
        """两种快速配置状态均需的启动、模拟器和账号设置，不改任务选择。"""

        global_set = gui_set["Global"]
        default_set = gui_set["Configurations"]["Default"]
        current_gui = gui_new_set["Configurations"]["Default"].setdefault("Gui", {})

        # 关闭定时，避免与 MAS 调度重叠。
        for i in range(1, 9):
            global_set[f"Timer.Timer{i}"] = "False"
        for timer in gui_new_set.setdefault("Timers", {}).setdefault("List", []):
            if isinstance(timer, dict):
                timer["IsEnabled"] = False

        if emulator_info.adb_address != "Unknown":
            default_set["Connect.Address"] = emulator_info.adb_address
            current_gui.setdefault("ConnectSettings", {})["Address"] = (
                emulator_info.adb_address
            )

        post_actions = MAA_TASK_TRANSITION_METHOD_BOOK[
            self.script_config.get("Run", "TaskTransitionMethod")
        ]
        default_set["MainFunction.PostActions"] = post_actions
        current_gui["PostActions"] = int(post_actions)
        default_set["Start.StartGame"] = "True"
        default_set["Start.RunDirectly"] = "True"
        default_set["Start.OpenEmulatorAfterLaunch"] = "False"
        current_gui.setdefault("RuntimeSettings", {})["StartGame"] = True
        current_gui.setdefault("StartUpSettings", {}).update(
            {"RunDirectly": True, "StartEmulator": False}
        )
        global_set["VersionUpdate.ScheduledUpdateCheck"] = "False"
        global_set["VersionUpdate.AutoDownloadUpdatePackage"] = "True"
        global_set["VersionUpdate.AutoInstallUpdatePackage"] = "False"
        gui_new_set.setdefault("Update", {}).update(
            {
                "CheckOnSchedule": False,
                "AutoDownloadUpdatePackage": True,
                "AutoInstallUpdatePackage": False,
            }
        )
        if Config.get("Function", "IfSilence"):
            global_set["GUI.UseTray"] = "True"
            global_set["GUI.MinimizeToTray"] = "True"
            global_set["Start.MinimizeDirectly"] = "True"
            gui_new_set.setdefault("Gui", {}).update(
                {"UseTray": True, "MinimizeToTray": True, "MinimizeOnStartup": True}
            )
            # 无人值守运行，公告与更新后首启的版本说明弹窗一并关闭
            global_set["Announcement.DoNotShowAnnouncement"] = "True"
            global_set["VersionUpdate.doNotShowUpdate"] = "True"
            gui_new_set.setdefault("AnnouncementInfo", {})["DoNotShow"] = True
            gui_new_set.setdefault("Update", {})["DoNotShowUpdate"] = True

        server = self.cur_user_config.get("Info", "Server")
        account = self.cur_user_config.get("Info", "Id")
        default_set["Start.ClientType"] = server
        current_gui["RuntimeSettings"]["ClientType"] = _MAA_CLIENT_TYPE_TO_INT.get(
            server, 0
        )
        # 账号属于基本信息；关闭快速配置时只更新来源中已有的开始唤醒任务。
        for task in gui_new_set["Configurations"]["Default"].get("TaskQueue", []):
            if task.get("TaskType") != "StartUp" or server not in (
                "Official",
                "Bilibili",
            ):
                continue
            task["AccountName"] = (
                f"{account[:3]}****{account[7:]}"
                if server == "Official" and len(account) == 11
                else account
            )
            # MAA 账号切换需要独立开关，空账号仍由 MAA 沿用登录态。
            task["AccountSwitchEnabled"] = True

    def _snapshot_maa_config(self) -> None:
        """记录托管注入完成后的 MAA 配置基线, 供任务结束后甄别 MAA 自身的写盘变更。"""

        try:
            self._maa_config_baseline = {
                name: deepcopy(read_file(self.maa_set_path / name))
                for name in _MAA_CONFIG_FILES
            }
        except Exception as e:
            logger.opt(exception=True).warning(
                f"记录 MAA 配置基线失败, 本次运行跳过配置回写: {e}"
            )
            self._maa_config_baseline = None

    def _config_archive_dir(self) -> Path | None:
        """当前用户的 MAA 配置来源存档目录, 与 set_maa 的导入路径对称。

        直控用户没有 MAS 托管配置目录（对齐 MaaEnd 的「直控无 mas 池」），
        返回 ``None``：不下发前归档、运行产出也不回写——安装目录现场由
        任务结束的原生配置快照恢复机制管理。
        """

        mode = str(self.cur_user_config.get("Info", "Mode") or "").strip()
        if mode == "直控":
            return None
        if mode == "脚本":
            return Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"
        return (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
        )

    async def _sync_maa_config_updates(self) -> None:
        """把 MAA 运行期写盘的配置变更(相对本模式基线)回写到配置来源存档。

        MAA 原生的每日状态(如借战/访问好友的最近执行日期)因此能跨托管会话
        存活, 下次托管 MAA 读到自己的记录后自行去重; 失败只记日志不抛出。
        """

        if self.direct_control:
            return
        baseline = self._maa_config_baseline
        if baseline is None:
            return
        archive_dir = self._config_archive_dir()
        if archive_dir is None or not archive_dir.is_dir():
            return

        for name in _MAA_CONFIG_FILES:
            if not baseline.get(name):
                continue
            try:
                current = read_file(self.maa_set_path / name)
                archive = read_file(archive_dir / name)
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"读取 MAA 配置以对比回写失败({name}): {e}"
                )
                continue
            if not current or not archive:
                # MAA 写盘半截或存档缺失时不回写, 宁可下次多跑一次
                continue

            archive_new = deepcopy(archive)
            # 运行期写盘的是归一后的 Default 方案, 生效方案不是 Default 时合并回该方案键
            if not _merge_maa_config_file(
                archive_new,
                baseline[name],
                current,
                maa_scheme_name(archive_dir, archive),
            ):
                continue
            write_file(archive_dir / name, archive_new)
            logger.info(
                f"用户 {self.cur_user_item.name} 的 MAA 配置变更已回写存档: {name}"
            )

    async def handle_game_update(self, emulator_info: DeviceInfo) -> bool:
        """启动 MAA 前接管游戏更新。

        Returns:
            bool: 是否可以继续本次代理；``False`` 表示需要用户手动更新游戏。
        """

        self.script_info.log = "正在检查游戏更新"

        async def report(text: str) -> None:
            self.script_info.log = text

        try:
            result = await ensure_game_updated(
                adb_path=self.emulator_manager.get_adb_path(),
                adb_address=emulator_info.adb_address,
                server=self.cur_user_config.get("Info", "Server"),
                package_name=ARKNIGHTS_PACKAGE_NAME[
                    self.cur_user_config.get("Info", "Server")
                ],
                apk_dir=Path.cwd() / "data/GameApk",
                if_auto_install=self.script_config.get("Run", "IfAutoInstallGameApk"),
                time_limit=self.script_config.get("Run", "GameUpdateTimeLimit"),
                progress=report,
            )
        except Exception as e:
            # 检查本身异常不应阻断代理，交回 MAA 原有流程判定
            logger.opt(exception=True).warning(f"游戏更新检查异常: {e}")
            return True

        logger.info(f"游戏更新检查结果: {result.status} - {result.message}")

        # 服务端资源版本与上次成功代理时不一致，说明本次开始唤醒会触发资源热更新
        if result.resource_version:
            self.pending_res_version = result.resource_version
            self.if_game_hot_update = (
                result.resource_version
                != self.cur_user_config.get("Data", "LastResVersion")
            )
            if self.if_game_hot_update:
                logger.info(
                    f"检测到待下载的游戏资源热更新: {result.resource_version}，"
                    f"本次超时限制放宽至 {self.script_config.get('Run', 'GameUpdateTimeLimit')} 分钟"
                )

        if result.status != "NeedManualUpdate":
            return True

        self.cur_user_log.content = [result.message]
        self.cur_user_log.status = "游戏需要手动更新"
        self.script_info.log = result.message

        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=result.message),
        )
        await close_emulator(self)

        await Notify.push_plyer(
            "游戏需要手动更新！",
            result.message,
            f"{self.cur_user_item.name}的游戏需要手动更新",
            3,
        )
        return False

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """日志回调"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        if self.mode == "Annihilation":
            progress = _parse_annihilation_weekly_progress(log)
            completed = _has_completed_annihilation_week(log)
            if completed:
                self.task_dict["Fight"] = False
                self.run_book["Annihilation"] = True
                if not self._annihilation_weekly_completion_recorded:
                    await self.cur_user_config.set(
                        "Data",
                        "AnnihilationCompletedWeek",
                        _current_week_marker(datetime.now(tz=UTC4)),
                    )
                    self._annihilation_weekly_completion_recorded = True
                    progress_text = (
                        f"{progress[0]}/{progress[1]}" if progress else "完成任务日志"
                    )
                    logger.info(
                        f"用户 {self.cur_user_item.name} 剿灭已达到本周上限："
                        f"{progress_text}"
                    )

        # MAA 完成自定义任务时打印的是队列项名称，据此记录本月已购买
        if (
            self.mode == "GreenTicketStore"
            and not self.run_book["GreenTicketStore"]
            and f"完成任务: {MAA_GREEN_TICKET_STORE_TASK['Name']}" in log
        ):
            self.run_book["GreenTicketStore"] = True
            await self.cur_user_config.set(
                "Data",
                "GreenTicketStoreMonth",
                _current_month_marker(datetime.now(tz=UTC4)),
            )
            logger.info(f"用户 {self.cur_user_item.name} 已完成本月绿票商店购买")

        # 养成采集：识别链完成标记 → 立即读安装目录识别数据落用户档案
        # （方案 §4.2/决策 31，T1.17；无标记时不读不采）
        if self.cur_user_config.get("Info", "IfQuickConfig"):
            await self._collect_cultivate_archive(log)

        if "未选择任务" in log:
            self.cur_user_log.status = "MAA 未选择任何任务"
        elif "任务出错: 开始唤醒" in log:
            self.cur_user_log.status = "MAA 未能正确登录 PRTS"
        elif "任务已全部完成！" in log:
            # 关闭时不读取/反推来源队列；成功与失败均取自 MAA 本轮输出。
            for en_task, zh_task in zip(MAA_TASKS, MAA_TASKS_ZH):
                if (
                    f"完成任务: {zh_task}" in log
                    or f"{zh_task} 任务跳过" in log
                    or (en_task == "Fight" and "完成任务: 剿灭作战" in log)
                ):
                    self.task_dict[en_task] = False

            if any(self.task_dict.values()) or (
                not self.cur_user_config.get("Info", "IfQuickConfig")
                and any(
                    log.rfind(f"任务出错: {name}") > log.rfind(f"完成任务: {name}")
                    for name in re.findall(r"任务出错: ([^\r\n]+)", log)
                )
            ):
                self.cur_user_log.status = "MAA 部分任务执行失败"
            else:
                self.cur_user_log.status = "Success!"

        elif "请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣" in log:
            self.cur_user_log.status = "MAA 的 ADB 连接异常"
        elif "未检测到任何模拟器" in log:
            self.cur_user_log.status = "MAA 未检测到任何模拟器"
        elif "已停止" in log:
            self.cur_user_log.status = "MAA 在完成任务前中止"
        elif (
            "MaaAssistantArknights GUI exited" in log
            or not await self.maa_process_manager.is_running()
        ):
            self.cur_user_log.status = "MAA 在完成任务前退出"
        elif self.is_log_stalled(
            latest_time,
            minutes=(
                # 本次开始唤醒会触发资源热更新时放宽超时，避免把正常更新误判为卡死
                max(
                    self.script_config.get("Run", MAA_MODE_TIME_LIMIT_BOOK[self.mode]),
                    self.script_config.get("Run", "GameUpdateTimeLimit"),
                )
                if self.if_game_hot_update
                else self.script_config.get("Run", MAA_MODE_TIME_LIMIT_BOOK[self.mode])
            ),
        ):
            self.cur_user_log.status = "MAA 进程超时"
        else:
            self.cur_user_log.status = "MAA 正常运行中"

        logger.debug(f"MAA 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "MAA 正常运行中":
            logger.info(f"MAA 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):
        if self.check_result != "Pass":
            logger.info(f"MAA 检查未通过，跳过任务收尾: {self.check_result}")
            return

        started_at = time.monotonic()

        logger.info("MAA 收尾: 停止日志监控")
        await self.maa_log_monitor.stop()
        logger.info("MAA 收尾: 停止 MAA 进程")
        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)
        logger.info(f"MAA 收尾: 结束残留 MAA 进程: {self.maa_exe_path}")
        logger.info("MAA 收尾: 回写 MAA 配置")
        await agree_bilibili(self.maa_tasks_path, False)
        if self.script_config.get("Run", "TaskTransitionMethod") == "ExitEmulator":
            logger.info("用户任务结束, 关闭模拟器")
            await close_emulator(self)

        user_logs_list = []
        if_six_star = False
        for t, log_item in self.cur_user_item.log_record.items():
            if log_item.status == "MAA 正常运行中":
                log_item.status = "任务被用户手动中止"

            dt = t.astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            if await Config.save_maa_log(log_path, log_item.content, log_item.status):
                if_six_star = True

        statistics = await Config.merge_statistic_info(user_logs_list)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["maa_result"] = (
            "代理任务全部完成"
            if (self.run_book["Annihilation"] and self.run_book["Routine"])
            else self.cur_user_item.result
        )
        # 本轮有干员达成养成目标时随统计报告告知用户（目标消失可查）
        if self._cultivate_achievement_summary:
            statistics["cultivate_achievement"] = "、".join(
                self._cultivate_achievement_summary
            )

        # 判断是否成功
        if_success = self.run_book["Annihilation"] and self.run_book["Routine"]
        success_symbol = "√" if if_success else "X"

        # 任务被中止时，只要日志中已经完成过体力任务，也应发送掉落统计。
        should_send_statistics = if_success or _has_completed_sanity_task(
            list(self.cur_user_item.log_record.values())
        )
        if should_send_statistics:
            try:
                await push_notification(
                    "统计信息",
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的自动代理统计报告",
                    statistics,
                    self.cur_user_config,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送统计通知时出现异常: {e}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送统计通知时出现异常: {e}"
                    ),
                )

        # 六星通知独立处理，避免单个通知异常阻断掉落统计。
        if if_six_star:
            try:
                await push_notification(
                    "公招六星",
                    f"喜报: 用户 {self.cur_user_item.name} 公招出六星啦！",
                    {"user_name": self.cur_user_item.name},
                    self.cur_user_config,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送六星通知时出现异常: {e}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送六星通知时出现异常: {e}"
                    ),
                )

        if self.run_book["Annihilation"] and self.run_book["Routine"]:
            if (
                self.cur_user_config.get("Data", "ProxyTimes") == 0
                and self.cur_user_config.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_config.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_config.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_config.set(
                "Data",
                "ProxyTimes",
                self.cur_user_config.get("Data", "ProxyTimes") + 1,
            )

            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                f"已完成 {self.cur_user_item.name} 的自动代理任务",
                3,
            )
        else:
            logger.warning(f"用户 {self.cur_user_uid} 的自动代理任务未完成")
            self.cur_user_item.status = "异常"

        logger.info(f"MAA 任务收尾完成 - 用时: {time.monotonic() - started_at:.3f}秒")

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"自动代理任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"自动代理任务出现异常: {e}"),
        )
