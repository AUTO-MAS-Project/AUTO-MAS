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
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import app.core.notify.formats.maa as _format_maa
from app.config import ConfigCollection
from app.core import Config, Notify, Publisher
from app.core.history import aggregate_data
from app.core.notify.task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from app.core.notify.task_content import screenshot_entries as screenshot_entries
from app.core.ws import protocol
from app.models.config import (
    MaaConfig,
    MaaUserConfig,
)
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.notification import LocalNotice, NotificationImage
from app.models.schema import (
    HistoryAggregationItem,
    HistoryAttachmentInput,
    HistoryWrite,
    WSTaskNoticeData,
)
from app.models.task import LogRecord, ScriptItem
from app.services import System
from app.task.base import ScriptAutoProxyBase
from app.task.emulator_core import (
    close_emulator,
    mod_avd_open_kwargs,
    resolve_device_ref,
    resolve_host_adb,
    script_process_env,
)
from app.task.failure_capture_core import FailureCapture
from app.task.MAA.stage import maa_stage_service
from app.task.proxy_helpers import (
    CONFIG_BASE_INDEPENDENT,
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
    resolve_config_base,
)
from app.utils import LogMonitor, ProcessManager, get_logger
from app.utils import constants as _utils_constants
from app.utils import emulator2 as _utils_emulator2
from app.utils import game_update as _utils_game_update
from app.utils import io as _utils_io

from . import api_service as maa_api
from .base_preset import (
    MAA_STAMINA_LEGACY_FILENAME,
    canonical_maa_task_identity,
    ensure_maa_default_configuration,
    get_maa_base_preset,
    maa_task_identity,
    seed_maa_base_config,
)
from .constants import (
    ARKNIGHTS_PACKAGE_NAME,
    MAA_MODE_TIME_LIMIT_BOOK,
    MAA_RUN_MOOD_BOOK,
    MAA_TASKS,
    MAA_TASKS_ZH,
)
from .tools import agree_bilibili, log_statistics
from .tools.activity_inventory import resolve_activity_inventory_plans
from .tools.avd import (
    build_maa_connect_settings,
    ensure_mumu_shim,
    screencap_fallback_status,
)
from .tools.backup_archive import (
    archive_mas_runtime_backup,
    read_overlay_values,
    task_type_of,
)
from .tools.cultivate import (
    CultivatePlan,
    OperatorTarget,
    ProviderContext,
    YituliuDataError,
    apply_achievements,
    depot_cultivate_service,
    dump_cultivate_targets,
    filter_observed_cultivate_targets,
    get_certifying_chain,
    get_progression_chain,
    judge_achievements,
    load_oper_box_names,
    parse_cultivate_targets,
    parse_depot_payload,
    resolve_progression,
    summarize_achievements,
    takeover_notice_patch_value,
)
from .tools.native_config import (
    infrast_plan_mode,
    load_infrast_plans,
    maa_scheme_name,
)
from .tools.screenshot import (
    AdbCapture,
    capture_current_image,
    collect_maa_failure_image,
)
from .tools.software_package import read_pending_update, save_deferred_update
from .tools.software_update import (
    compare_versions,
    parse_version,
    read_installed_release,
)
from .tools.task_templates import (
    MAA_ANNIHILATION_FIGHT_BASE,
    MAA_GREEN_TICKET_STORE_TASK,
    MAA_TASK_TRANSITION_METHOD_BOOK,
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
    "完成任务: 理智任务",
    "完成任务: 活动关均衡理智",
    "完成任务: 库存保持与干员养成",
    "完成任务: 理智作战",
    "完成任务: 活动关优先",
    "完成任务: 活动库存保持",
    "完成任务: 库存保持",
    "完成任务: 养成计划",
)
# 养成注入的任务名（语言无关，日志锚定与来源查找都用它，方案决策 27/30）
_MAA_CULTIVATE_TASK_NAME = "养成计划"
_MAA_DATA_UPDATE_TASK_NAME = "更新数据"
# 识别数据档案文件名（MAA 原生格式透传）。方案决策 31 管的是归属：档案按写入时的
# cur_user_uid 归属，安装目录那份 DepotData 是 MAA 自己的工作缓存，不属于查询链——
# 查询、缺口判定与养成注入只读档案。只有 overlay 层（开启覆写常规配置）才在启动前
# 把档案覆写进安装目录，且覆写前键级存底、任务结束还原（见 depot_cache_snapshot_dir）。
_MAA_DEPOT_ARCHIVE_NAME = "DepotData.json"
_MAA_OPER_BOX_ARCHIVE_NAME = "OperBoxData.json"
# 识别链完成标记：锚定注入的任务名 + 链后缀（MAS 强制 zh-cn，方案 §4.2/T0.3）
_MAA_DEPOT_CHAIN_COMPLETION_MARKERS = (
    "完成任务: 活动关均衡理智 (仓库识别)",
    "完成任务: 库存保持与干员养成 (仓库识别)",
    "完成任务: 活动库存保持 (仓库识别)",
    "完成任务: 库存保持 (仓库识别)",
    f"完成任务: {_MAA_CULTIVATE_TASK_NAME} (仓库识别)",
    f"完成任务: {_MAA_DATA_UPDATE_TASK_NAME} (仓库识别)",
)
_MAA_OPER_BOX_CHAIN_COMPLETION_MARKERS = (
    f"完成任务: {_MAA_DATA_UPDATE_TASK_NAME} (干员识别)",
)
_MAA_FIGHT_COMPLETION_MARKER = "Completed Task Chain: Fight"
_MAA_TASK_FAILURE_MARKERS = (
    "任务已完成，但出现错误！",
    "任务已结束，以下任务出现错误",
)


def _has_maa_task_failure(log: str) -> bool:
    return any(marker in log for marker in _MAA_TASK_FAILURE_MARKERS)


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
# MAA v6.17 起内存不足走专属提示，不再带「任务出错:」前缀，实际文案是
# 「{任务链名}」+ 下面这段。只认整段：MAA 的 MirrorChyan 更新说明里也有
# 「任务因内存不足停止时给出专门提示…」这一条，资源热更新会把整份说明写进被监控的
# gui.log，只用前缀匹配会把更新中途的正常运行判成内存不足，代理随即中止并反复重试。
_MAA_OUT_OF_MEMORY_MARKER = "任务因内存不足停止，请关闭部分程序或重启 MAA 后重试"


def _should_retry_maa(status: str, log: str) -> bool:
    """仅对尚未形成 MAA 任务失败终态的运行异常重试。"""

    if status == "Success!":
        return False
    return not (status == "MAA 部分任务执行失败" and _has_maa_task_failure(log))


def _current_week_marker(now: datetime) -> str:
    """返回 ISO 周标记。"""

    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def _current_month_marker(now: datetime) -> str:
    """按 UTC+4 返回月份标记。"""

    # TODO: 动态时区适配时按账号 Info.Server 的 get_game_day_tz() 判断绿票月份；
    # 同步 GreenTicketStoreMonth 的时区声明及前端完成态，保留完整 UTC 时间存储。
    # 固定 UTC+4 在 EN、JP/KR 的月界存在误判，待上述适配统一处理。
    return now.astimezone(_utils_constants.UTC4).strftime("%Y-%m")


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
        # 只认刷关完成行，仓库识别等括号后缀不表示已经刷过关卡。
        if any(
            re.search(rf"{re.escape(marker)}(?:\s+#\d+)?\s*$", line)
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


_MAA_CONFIG_FILES = ("gui.new.json",)


# 每次注入都由 MAS 决定、不从存档取值的任务字段: MAA 运行期改了也不回写。
# PlanSelect 是 MAA 跑完基建后自增的班次指针, 脚本模式下存档全脚本共用,
# 回写会让多个自定义基建用户互相拨对方的班次。PlanList 是每轮生成的绝对库存
# 目标，MAA 保存时补齐计划默认字段也不能把临时目标带回用户来源。
_MAA_TASK_KEYS_NOT_MERGED = frozenset({"PlanSelect", "PlanList"})


_MAA_UPDATE_CONFIG_KEYS = {
    "gui.new.json": (
        ("Update", "CheckOnStartup"),
        ("Update", "CheckOnSchedule"),
        ("Update", "UpdateSource"),
        ("Update", "AutoDownloadUpdatePackage"),
        ("Update", "AutoInstallUpdatePackage"),
    ),
}


def _without_maa_update_changes(current: dict, baseline: dict, name: str) -> dict:
    """移除 MAS 临时接管的更新字段，避免它们进入 MAA 存档。"""
    for path in _MAA_UPDATE_CONFIG_KEYS.get(name, ()):
        current_node: object = current
        baseline_node: object = baseline
        for key in path[:-1]:
            if not isinstance(current_node, dict) or not isinstance(
                baseline_node, dict
            ):
                break
            current_node = current_node.get(key)
            baseline_node = baseline_node.get(key)
        else:
            if isinstance(current_node, dict) and isinstance(baseline_node, dict):
                key = path[-1]
                if key in baseline_node:
                    current_node[key] = deepcopy(baseline_node[key])
                else:
                    current_node.pop(key, None)
    return current


def read_maa_config_with_fallback(maa_set_path: Path) -> dict:
    """读 MAA 的 gui.new.json；缺失或损坏时退回随包预设。

    损坏但存在 ``.bak`` 时优先用 MAA 自己的备份——那是 MAA 上一次成功落盘的
    完整现场，比预设少丢用户数据。都没有时用随包预设（结构完整、含根级
    ``Gui`` / ``Timers``），不再用只含容器路径的骨架：缺根级 ``Gui`` 时 MAA
    会把这次启动当首次运行，直接弹新手引导。返回的 dict 由调用方独立持有，改动不落盘。
    """

    path = maa_set_path / "gui.new.json"
    try:
        doc = _utils_io.read_file(path)
    except (OSError, ValueError) as e:
        logger.opt(exception=True).warning(f"读取 MAA 配置失败(gui.new.json): {e}")
        doc = {}
    if doc:
        return doc
    if path.exists():
        # 文件存在但读不出内容（损坏）：优先用 MAA 自己的 .bak——那是 MAA
        # 上一次成功落盘的完整现场，比预设少丢用户数据。（.bak 后缀不在
        # read_file 的编解码器表里，须显式指定 .json 解析）
        bak = _utils_io.read_file(
            path.with_suffix(path.suffix + ".bak"), format=".json"
        )
        if isinstance(bak, dict) and bak:
            logger.warning("MAA 配置损坏, 采用 MAA 自带备份(gui.new.json.bak)")
            return bak
    logger.warning("MAA 配置缺失, 以随包预设下发(gui.new.json)")
    return get_maa_base_preset()


def _merge_task_queue(
    archive_queue: list | None,
    baseline_queue: list | None,
    current_queue: list,
    *,
    drop_missing: bool = True,
    ignore_keys: frozenset[str] = frozenset(),
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

    ignore_keys 里的字段不回写: 由 MAS 每次注入决定、MAA 运行期改了也不算数。
    """

    if not isinstance(archive_queue, list) or not isinstance(baseline_queue, list):
        return False

    def identity(item: object) -> tuple | None:
        return maa_task_identity(item)

    index_by_id: dict[tuple, int] = {}
    for index, item in enumerate(archive_queue):
        key = identity(item)
        if key is not None:
            index_by_id[key] = index
    canonical_index: dict[tuple, int] = {}
    for index, item in sorted(
        enumerate(archive_queue),
        key=lambda pair: not bool((identity(pair[1]) or ("", ""))[1]),
    ):
        key = canonical_maa_task_identity(item)
        if key is not None:
            # 新旧名称并存时先用原名精确匹配；旧具名库存优先于空名库存。
            canonical_index.setdefault(key, index)
    baseline_by_id: dict[tuple, dict] = {}
    for item in baseline_queue:
        key = identity(item)
        if key is not None:
            baseline_by_id[key] = item
            if key not in index_by_id:
                canonical_key = canonical_maa_task_identity(item)
                if canonical_key in canonical_index:
                    index_by_id[key] = canonical_index[canonical_key]

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
            if key[0] == "DepotMaintain" and "PlanList" in ignore_keys:
                continue
            # 基线认识但存档缺失: 以基线为底补回条目, 让存档向基线结构收敛
            # (MAA 保存重写结构后, 用户对合成任务的修改不丢)
            target = deepcopy(base_task)
            archive_queue.append(target)
            index_by_id[key] = len(archive_queue) - 1
            changed = True
        else:
            target = archive_queue[target_index]
        for key_, value in task.items():
            if key_ in ignore_keys:
                continue
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
            drop_set = {
                identity(archive_queue[index_by_id[key]]) if key in index_by_id else key
                for key in dropped
            }
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
    ignore_keys: frozenset[str] = frozenset(),
) -> bool:
    """把 MAA 运行期配置相对基线快照的变更原地合并进来源存档。

    只透传运行期(相对基线)真正发生的变更。字典键只增改, 任务队列按
    drop_missing 处理条目删除。MAS 注入自己改写的键(baseline 与 current 相同、
    仅与存档不同)不能被带回存档, 否则运行一次就会把用户自己的配置抹成注入值。
    顶层结构不匹配(如写盘半截被截断)整体跳过。
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
                        archive[key],
                        base_value,
                        value,
                        drop_missing=drop_missing,
                        ignore_keys=ignore_keys,
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
                        ignore_keys=ignore_keys,
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
    ignore_keys: frozenset[str] = frozenset(),
) -> bool:
    """按生效方案合并一份 MAA 配置, 返回是否有变更。

    set_maa 会把存档 Current 方案的内容复制进运行目录的 Default 再运行, 运行期
    的变更因此都记在 Default 键上; 存档生效方案不是 Default 时, 把合并目标临时
    指向该方案键, 免得班次推进等原生状态落进未被运行的 Default 方案。
    """

    if scheme == "Default":
        return _merge_maa_changes(
            archive,
            baseline,
            current,
            drop_missing=drop_missing,
            ignore_keys=ignore_keys,
        )

    configurations = archive.get("Configurations")
    if not isinstance(configurations, dict) or not isinstance(
        configurations.get(scheme), dict
    ):
        return _merge_maa_changes(
            archive,
            baseline,
            current,
            drop_missing=drop_missing,
            ignore_keys=ignore_keys,
        )

    original_default = configurations.get("Default")
    configurations["Default"] = configurations[scheme]
    try:
        changed = _merge_maa_changes(
            archive,
            baseline,
            current,
            drop_missing=drop_missing,
            ignore_keys=ignore_keys,
        )
    finally:
        if "Default" in configurations:
            configurations[scheme] = configurations.pop("Default")
        else:
            configurations.pop(scheme, None)
        if original_default is not None:
            configurations["Default"] = original_default
    return changed


def _merge_fight_task(source_task: dict, managed_patch: dict) -> dict:
    """以 MAA 原生配置为底，只用 MAS 托管补丁覆盖它声明接管的键。

    补丁是 merge patch 语义：**补丁里出现的键才算 MAS 接管，没出现的键一律
    透传用户在上游界面里的选择**（临期药、源石、博朗台、周计划、指定材料/
    次数、隐藏项等）。因此补丁表（MAA_ANNIHILATION_FIGHT_BASE）只允许列
    MAS 运行必需且自己会消费的字段；往表里补一个 MAS 不消费的默认值，
    等于把用户的选择静默抹掉。
    """

    return {**deepcopy(source_task), **deepcopy(managed_patch)}


def _find_task_source(
    task_queue: list[dict],
    name: str,
    task_type: str,
) -> dict | None:
    """按 TaskType + Name 匹配原生任务，兼容空名库存保持预设与唯一项。

    MAA 原生任务允许使用空名称；多个同类型任务不能仅按类型区分，避免配置串用。
    """

    identity = (task_type, name)
    canonical = canonical_maa_task_identity({"TaskType": task_type, "Name": name})
    matched = []
    fallback = []
    for task in task_queue:
        task_identity = maa_task_identity(task)
        if task_identity == identity:
            return deepcopy(task)
        if task_identity is None or task_identity[0] != task_type:
            continue
        task_canonical = canonical_maa_task_identity(task)
        if task_canonical == canonical:
            matched.append(task)
            continue
        # 已知阶段不能仅凭类型借用另一阶段的高级字段。
        if task_type == "DepotMaintain" and (
            task_canonical
            in {
                ("DepotMaintain", "活动关均衡理智"),
                ("DepotMaintain", "库存保持与干员养成"),
            }
            or canonical == ("DepotMaintain", "活动关均衡理智")
            or task_identity[1] == _MAA_CULTIVATE_TASK_NAME
        ):
            continue
        if task_type == "Fight" and (
            task_identity[1] == "活动关优先" or name == "活动关优先"
        ):
            continue
        if (
            task_type == "Fight"
            and canonical == ("Fight", "理智任务")
            and (task_identity[1] == "剿灭作战")
        ):
            continue
        fallback.append(task)
    if matched:
        return deepcopy(
            next((task for task in matched if task.get("Name")), matched[0])
        )
    if len(fallback) == 1:
        return deepcopy(fallback[0])
    return None


def _with_type_first(task: dict) -> dict:
    """把条目的 ``$type`` 移到第一个属性位。

    MAA 用 System.Text.Json 的多态元数据读任务条目：``$type`` 不在第一个属性就
    整个配置文件反序列化失败，MAA 退回读 `.bak`（旧值），MAS 写进去的队列与
    启动编排因此全部静默失效。构造条目时必须走这个函数，不能依赖 dict 的键序。
    """

    return {
        "$type": task.get("$type") or f"{task.get('TaskType', '')}Task",
        **task,
    }


def _repair_maa_task_queue(source_queue: list[dict]) -> list[dict]:
    """逐条把队列条目的 ``$type`` 摆到首位，其余内容一律不动。

    队列的成员、顺序、条目字段都是 base 的一部分，归用户与 MAA 自己的界面所有，
    MAS 不校对也不重建——不认识的条目（上游新增类型、用户自定义任务）原样透传。
    这里只修一个 MAS 有责任修的东西：``$type`` 的位置，见 :func:`_with_type_first`。
    """

    return [
        _with_type_first(task) if isinstance(task, dict) else task
        for task in source_queue
    ]


def _copy_matching_depot_plan(source_task: dict, *, stage: str, drop_id: str) -> dict:
    """按关卡与材料匹配来源计划，复制其高级参数供各类库存任务透传。"""

    source_plans = source_task.get("PlanList") or []
    if not isinstance(source_plans, list):
        return {}
    return deepcopy(
        next(
            (
                item
                for item in source_plans
                if isinstance(item, dict)
                and item.get("Stage") == stage
                and item.get("DropId") == drop_id
            ),
            {},
        )
    )


def _build_depot_maintain_task(
    plans_json: str,
    source_task: dict | None = None,
    *,
    name: str = "库存保持与干员养成",
) -> dict:
    """生成 MAA 库存保持任务配置。

    只覆盖 MAS 面板管理的 Stage/DropId/DropCount；其余字段（含用户在 MAA 里设的
    UseMedicine/UseStone 等）从来源任务整条透传——上游私有格式只做值经手，
    不按 MAS 口径改写其语义。
    """

    source_task = source_task or {}

    plans = []
    source_plans = deepcopy(source_task.get("PlanList") or [])
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
            source_index = next(
                (
                    index
                    for index, item in enumerate(source_plans)
                    if isinstance(item, dict)
                    and item.get("Stage") == plan["Stage"]
                    and item.get("DropId") == plan["DropId"]
                ),
                None,
            )
            source_plan = (
                source_plans.pop(source_index) if source_index is not None else {}
            )
            plans.append(
                {
                    **source_plan,
                    "Stage": plan["Stage"],
                    "DropId": plan["DropId"],
                    "DropCount": plan["DropCount"],
                }
            )

    # 必须走 _with_type_first：MAA 用 System.Text.Json 的多态元数据读条目，
    # $type 不在第一个属性就整个配置反序列化失败并静默退回 .bak（旧值）。
    # 下方注入点在 _repair_maa_task_queue 之后执行，不能指望队列级修复兜底。
    return _with_type_first(
        {
            **deepcopy(source_task),
            "Name": name,
            "IsEnable": True,
            "TaskType": "DepotMaintain",
            "PlanList": plans,
        }
    )


_MAA_DEPOT_QUOTA_KEYS = (
    ("UseMedicine", "MedicineCount"),
    ("UseStone", "StoneCount"),
)
"""MAA 库存保持任务成对的「整组总开关 + 计划额度」字段，理智药与源石在上游同构。"""


def _write_depot_plan_quota(task: dict, gate: str, count_key: str, count: int) -> None:
    """把一段额度写到本组每条计划；MAA 的数量字段只存在于计划级。"""

    for plan in task.get("PlanList") or []:
        if isinstance(plan, dict):
            plan.update({gate: count > 0, count_key: count})


def _apply_depot_quota_override(
    task: dict | None, *, medicine: int | None, stone: int | None
) -> None:
    """按 MAS 填写的数量覆盖该组每条计划的理智药与源石额度。

    MAA 的任务级 UseMedicine/UseStone 是整组总开关，关闭时序列化会把计划数量强制
    写成 0，所以填正数时一并打开；填 0 只落到计划上，不影响共用任务的另一组。
    留空表示沿用 MAA 原设置，整段不动。
    """

    if task is None:
        return
    for (gate, count_key), count in zip(
        _MAA_DEPOT_QUOTA_KEYS, (medicine, stone), strict=True
    ):
        if count is None:
            continue
        if count > 0:
            task[gate] = True
        _write_depot_plan_quota(task, gate, count_key, count)


def _build_auto_cultivate_task(
    targets: Sequence[OperatorTarget], catalog: list[dict], source_task: dict | None
) -> dict | None:
    """用现有养成目标驱动 MAA 原生培养任务，游戏操作与结果判定交给 MAA。

    任务参数沿用 MAA v6.19.0-beta.1 的 OperProgressTask 配置入口；模组
    尚无原生培养入口，保留在材料计划中，不下发给培养任务。
    """

    operators = {item["value"]: item for item in catalog}
    plans = []
    for target in targets:
        goals = [
            goal
            for goal in target.goals
            if goal.kind != "module"
            and goal.state not in ("achieved", "pending_confirm")
        ]
        if not goals:
            continue
        operator = operators.get(target.operator_id)
        if operator is None:
            raise ValueError(f"干员 {target.operator_id} 的培养数据缺失")
        mastery_levels = [0, 0, 0]
        skill_indices = {
            skill["value"]: skill["skillIndex"] for skill in operator["skills"]
        }
        elite_level = skill_level = 0
        for goal in goals:
            if goal.kind == "elite":
                elite_level = goal.to_level
            elif goal.kind == "skill":
                skill_level = goal.to_level
            elif goal.kind == "mastery":
                index = skill_indices.get(goal.target_id)
                if index not in (1, 2, 3):
                    raise ValueError(f"干员 {operator['label']} 的专精技能序号缺失")
                mastery_levels[index - 1] = goal.to_level
        plans.append(
            {
                "Role": operator["profession"].title() or "Unknown",
                "Name": operator["label"],
                "Elite": elite_level,
                "SkillLevel": skill_level,
                "SkillMastery": mastery_levels,
                "ShowRole": False,
            }
        )
    if not plans:
        return None
    return _with_type_first(
        {
            **deepcopy(source_task or {}),
            "$type": "OperProgressTask",
            "Name": "干员培养",
            "IsEnable": True,
            "TaskType": "OperProgress",
            "Plans": plans,
        }
    )


def _build_event_depot_maintain_task(
    plans_json: str,
    activity_stages: list[dict],
    source_task: dict | None,
) -> tuple[dict | None, list[tuple[str, str]]]:
    """解析活动目标，保留原生任务身份与高级参数。"""

    source_task = source_task or {}
    plans, notices = resolve_activity_inventory_plans(
        plans_json,
        activity_stages,
        source_plans=source_task.get("PlanList", []),
    )
    if not plans:
        return None, notices
    return (
        _with_type_first(
            {
                **deepcopy(source_task),
                "Name": "活动关均衡理智",
                "IsEnable": True,
                "TaskType": "DepotMaintain",
                "PlanList": [
                    {
                        **_copy_matching_depot_plan(
                            source_task, stage=plan["Stage"], drop_id=plan["DropId"]
                        ),
                        **plan,
                    }
                    for plan in plans
                ],
            }
        ),
        notices,
    )


def _build_cultivate_task(
    plan: "CultivatePlan",
    source_task: dict | None,
    *,
    skip_during_activity: bool,
    skip_during_resource_collection: bool,
) -> dict | None:
    """把内核养成计划映射为 MAA 养成任务（MAA 字段名唯一出现点，方案 §4.1）。

    药石与临期药设置整段沿用 MAA 原任务与计划，MAS 只在显式填写数量时覆盖；
    计划无可用刷取条目时不生成任务。
    DropCount 是 MAA 的"保有量目标"语义（need = DropCount − 该材料现存，
    只比对本材料），故写净缺口 + 档案现存，MAA 现算后落回净缺口。
    """

    source_task = source_task or {}
    plans = []
    for entry in plan.entries:
        source_plan = _copy_matching_depot_plan(
            source_task, stage=entry.stage_code, drop_id=entry.item_id
        )
        plans.append(
            {
                **source_plan,
                "Stage": entry.stage_code,
                "DropId": entry.item_id,
                "DropCount": entry.amount + entry.held,
            }
        )
    if not plans:
        return None

    return {
        "$type": source_task.get("$type", "DepotMaintainTask"),
        "Name": "库存保持与干员养成",
        "IsEnable": True,
        "TaskType": "DepotMaintain",
        # 仓库识别随养成任务执行，缺口由 MAA 按最新库存现算（方案 §9）
        "UpdateDepot": True,
        "IsStageManually": True,
        "SkipDuringActivity": skip_during_activity,
        "SkipDuringResourceCollection": skip_during_resource_collection,
        "OnlyFirstInsufficientPlan": False,
        "SortByProgress": False,
        "UseAutoSeries": source_task.get("UseAutoSeries", False),
        **{
            key: source_task[key]
            for key in (
                "UseMedicine",
                "UseStone",
                "UseExpiringMedicine",
                "MedicineExpireDays",
                "UseExpireMedicineForActivity",
            )
            if key in source_task
        },
        "PlanList": plans,
    }


def _materialize_depot_quota_gates(task: dict) -> None:
    """把任务级药石总开关摊平到本组计划。

    MAA 的 DepotMaintain 用任务级 UseMedicine/UseStone 当整组开关，关闭时序列化
    会把每条计划的数量强制写成 0。合并后的任务只剩一个总开关，先摊平才能让一组
    原本关闭的额度在另一组打开总开关时不复活。
    """

    for gate, count_key in _MAA_DEPOT_QUOTA_KEYS:
        if not task.get(gate, True):
            _write_depot_plan_quota(task, gate, count_key, 0)


def _build_stock_cultivate_task(
    stock_task: dict | None, cultivate_task: dict | None, plan: CultivatePlan
) -> dict | None:
    """先备养成材料，再按完整消耗提高各条常备库存的保有量目标。"""

    if stock_task is None:
        return cultivate_task
    stock = deepcopy(stock_task)
    cultivate = deepcopy(cultivate_task) if cultivate_task is not None else None
    for group in (stock, cultivate):
        if group is not None:
            _materialize_depot_quota_gates(group)
    reservations = {item.item_id: item.amount for item in plan.reservations}
    for item in stock["PlanList"]:
        item["DropCount"] += reservations.get(item["DropId"], 0)
    stock["PlanList"] = (
        cultivate["PlanList"] if cultivate is not None else []
    ) + stock["PlanList"]
    stock.update(
        {
            "OnlyFirstInsufficientPlan": False,
            "SortByProgress": False,
            "SkipDuringActivity": False,
            "SkipDuringResourceCollection": False,
            **{
                gate: stock.get(gate, True)
                or (cultivate is not None and cultivate.get(gate, True))
                for gate, _ in _MAA_DEPOT_QUOTA_KEYS
            },
        }
    )
    return stock


def _merge_cultivate_target_updates(
    raw_targets: object,
    updated_targets: tuple[OperatorTarget, ...] | list[OperatorTarget],
    deferred_targets: Sequence[OperatorTarget],
) -> list[dict]:
    """按原顺序合并已知目标更新，延期干员的配置原文继续保留。"""

    updated = {
        item["operator_id"]: item for item in dump_cultivate_targets(updated_targets)
    }
    deferred_ids = {target.operator_id for target in deferred_targets}
    merged = []
    for item in raw_targets if isinstance(raw_targets, list) else []:
        if not isinstance(item, dict):
            continue
        operator_id = item.get("operator_id")
        if operator_id in deferred_ids:
            merged.append(deepcopy(item))
        elif operator_id in updated:
            merged.append(deepcopy(updated[operator_id]))
    return merged


def _maa_activity_state(
    raw_data: dict, server: str, *, now: datetime
) -> tuple[bool, bool]:
    """从已有区服活动缓存判断活动与限时资源全开放时段。"""

    server_data = raw_data.get("Official" if server == "Bilibili" else server, {})

    def is_open(activity: dict) -> bool:
        if not activity:
            return False
        activity_timezone = timezone(timedelta(hours=activity.get("TimeZone", 8)))
        start = datetime.strptime(
            activity["UtcStartTime"], "%Y/%m/%d %H:%M:%S"
        ).replace(tzinfo=activity_timezone)
        end = datetime.strptime(activity["UtcExpireTime"], "%Y/%m/%d %H:%M:%S").replace(
            tzinfo=activity_timezone
        )
        return start < now < end

    return (
        any(
            is_open(item["Activity"])
            for item in server_data.get("sideStoryStage", {}).values()
        ),
        is_open(server_data.get("resourceCollection", {})),
    )


def _build_data_update_task(
    source_task: dict | None, *, update_oper_box: bool = True
) -> dict:
    """构建更新数据任务，按需识别干员并始终识别仓库。

    识别结果供 check_log 采集落用户档案，缺口始终由 MAA 执行时现算。
    """

    source_task = source_task or {}
    return {
        **deepcopy(source_task),
        "$type": source_task.get("$type", "UserDataUpdateTask"),
        "Name": _MAA_DATA_UPDATE_TASK_NAME,
        "IsEnable": True,
        "TaskType": "UserDataUpdate",
        "UpdateOperBox": update_oper_box,
        "UpdateDepot": True,
        "TriggerInterval": "EveryTime",
    }


def depot_cache_snapshot_dir(script_id: str) -> Path:
    """库存缓存存底目录（键级存底，覆盖 overlay 对该文件的覆写）。

    安装目录的 data/DepotData.json 不在原生配置整目录快照（config）范围内，
    overlay 覆写它是不可还原写入；不在整目录快照范围内的目标必须自带键级快照。
    目录存在即为「已存底」；目录里没有 DepotData.json 表示覆写前安装目录本来
    就没有该文件。

    Args:
        script_id: 脚本标识，决定 data/<script_id>/TempDepot 的归属。

    Returns:
        存底目录路径。
    """

    return Path.cwd() / f"data/{script_id}/TempDepot"


def snapshot_depot_cache(maa_root_path: Path, snapshot_dir: Path) -> bool:
    """覆写安装目录库存缓存前存底；已存底时保持第一次的现场。

    Args:
        maa_root_path: MAA 安装根目录，工作缓存在其 data/DepotData.json。
        snapshot_dir: 存底目录；已存在即视为已存底并直接放行。

    Returns:
        可以覆写时为 True；存底失败为 False（调用方不得覆写）。
    """

    if snapshot_dir.is_dir():
        return True
    live = maa_root_path / "data" / _MAA_DEPOT_ARCHIVE_NAME
    try:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        if live.is_file():
            shutil.copy2(live, snapshot_dir / _MAA_DEPOT_ARCHIVE_NAME)
    except OSError:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        logger.opt(exception=True).warning(
            "MAA 库存缓存存底失败, 本轮不覆写安装目录缓存"
        )
        return False
    return True


def restore_depot_cache(maa_root_path: Path, snapshot_dir: Path) -> None:
    """按存底还原安装目录库存缓存（结束还原与崩溃恢复共用）。

    存底目录存在才算覆写过；还原失败保留存底，交给下一次 prepare 重试。

    Args:
        maa_root_path: MAA 安装根目录，工作缓存在其 data/DepotData.json。
        snapshot_dir: 存底目录；不存在表示没覆写过，直接放行。
    """

    if not snapshot_dir.is_dir():
        return
    live = maa_root_path / "data" / _MAA_DEPOT_ARCHIVE_NAME
    saved = snapshot_dir / _MAA_DEPOT_ARCHIVE_NAME
    try:
        if saved.is_file():
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, live)
        else:
            live.unlink(missing_ok=True)
    except OSError:
        logger.opt(exception=True).warning(
            f"MAA 库存缓存还原失败, 保留存底: {snapshot_dir}"
        )
        return
    shutil.rmtree(snapshot_dir, ignore_errors=True)


class AutoProxyTask(ScriptAutoProxyBase[MaaConfig, MaaUserConfig]):
    """自动代理模式"""

    # 养成采集状态：prepare() 每轮重置；类级默认保证未跑 prepare 的
    # 实例（如单测直接构造）调用 check_log 时不炸
    _cultivate_collected_depot: bool = False
    _cultivate_collected_oper_box: bool = False
    _cultivate_auto_raise_injected: bool = False
    # 每轮重新判断来源参与条件；数据不可用或触发跳过时同时暂停自动培养。
    _cultivate_round_paused: bool = True
    _cultivate_execution_targets: tuple[OperatorTarget, ...] = ()
    _cultivate_progress_synced: bool = False
    # 完成活动阶段后，其他任务重试不能重新领取该阶段药石额度。
    _event_depot_completed: bool = False
    # 普通库存重试时仍下发目标，已执行过的阶段不再领取药石额度。
    _stock_depot_completed: bool = False

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaConfig,
        user_config: ConfigCollection[MaaUserConfig],
        emulator_manager: DeviceBase,
        *,
        capture_adb: AdbCapture,
        game_update_result: _utils_game_update.GameUpdateResult | None = None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.capture_adb = capture_adb
        self._failure_capture = FailureCapture(stopped=lambda: self.stopped_manually)
        self.game_update_result = game_update_result
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        # base 来源三态与独立的快速配置开关：来源决定是否下发 MAS 托管配置，
        # 快速配置决定是否把面板值写进 MAA 原生配置（两段互不替代）。
        self.config_base, self.native_base = resolve_config_base(
            self.cur_user_config, CONFIG_BASE_SHARED
        )
        self.check_result = "-"
        self.maa_root_path: Path | None = None
        self.pending_update: tuple[str, str] | None = None
        self._annihilation_weekly_completion_recorded = False
        # 无时段排班表本轮注入的班次：同一用户的多次重试都注入这一个值，
        # 基建换班完成后只把用户配置里的指针推进一次
        self._infrast_plan_index: int | None = None
        self._infrast_plan_count = 0
        self._infrast_plan_advanced = False
        self._cultivate_archive_positions: dict[str, int] = {}
        self._cultivate_archive_versions: dict[str, tuple[int, int, int]] = {}

    async def check(self) -> str:

        if (
            self.config_base == CONFIG_BASE_INDEPENDENT
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
        # 本轮打开的模拟器信息；收尾补截失败画面时取 adb 地址用
        self.emulator_info: DeviceInfo | None = None
        # 失败尝试在关模拟器前补截的现场画面；收尾组装通知时消费
        self._failure_shot: Path | None = None
        # 本用户的失败画面资源（标签+图片），manager 汇总「代理结果」时收集
        self.report_image_pairs: list[tuple[str, NotificationImage]] = []
        self.maa_log_monitor = LogMonitor(
            (1, 20),
            "%Y-%m-%d %H:%M:%S",
            self.check_log,
            except_logs=list(_MAA_STALL_NOTICE_MARKERS),
        )
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now().astimezone()
        self.if_game_hot_update = False
        self.pending_res_version = ""
        # 更新阶段只提供资源版本信号；资源热更新仍由 MAA 原生开始唤醒执行。
        if (
            self.game_update_result is not None
            and self.game_update_result.resource_version
        ):
            self.pending_res_version = self.game_update_result.resource_version
            self.if_game_hot_update = (
                self.pending_res_version != self.cur_user_config.Data.LastResVersion
            )
        self._maa_config_baseline: dict[str, dict] | None = None
        # 养成采集：本轮是否采到过识别数据（每类以最后一次标记为准覆盖档案，
        # 见 _collect_cultivate_archive）；
        # 达成文案供 final_task 的统计信息报告，按 (干员, 档位) 去重累积
        self._cultivate_collected_depot = False
        self._cultivate_collected_oper_box = False
        self._cultivate_auto_raise_injected = False
        self._cultivate_round_paused = True
        self._cultivate_progress_synced = False
        self._cultivate_achievement_summary: list[str] = []
        # 已提示过的「找不到原生任务」：重试轮每次都重新合成队列，同一条只提示一次
        self._missing_task_source_warned: set[str] = set()

        maa_root_path = self.script_config.Info.Path
        if maa_root_path is None:
            raise ValueError("Path未配置，请检查路径设置")
        self.maa_root_path = maa_root_path
        self.maa_set_path = self.maa_root_path / "config"
        self.maa_log_path = self.maa_root_path / "debug/gui.log"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"
        self.maa_tasks_path = self.maa_root_path / "resource/tasks/tasks.json"

        quick_config = self.cur_user_config.Info.IfQuickConfig
        self.run_book = {
            "GreenTicketStore": not quick_config
            or not self.cur_user_config.Task.IfGreenTicketStore,
            "Annihilation": not quick_config
            or self.cur_user_config.Task.Annihilation == "Close",
            "Routine": False,
        }

        if not self.run_book["GreenTicketStore"]:
            completed_at = self.cur_user_config.Data.GreenTicketStoreMonth

            if completed_at is not None and _current_month_marker(
                completed_at
            ) == _current_month_marker(datetime.now(tz=_utils_constants.UTC4)):
                self.run_book["GreenTicketStore"] = True
                logger.info(
                    f"用户 {self.cur_user_item.name} 本次跳过绿票商店："
                    f"本月记录={completed_at}"
                )

        if not self.run_book["Annihilation"]:
            now = _utils_constants.game_now(self.cur_user_config.Info.Server)
            start_weekday = self.cur_user_config.Task.AnnihilationStartWeekday

            if not _should_run_annihilation(
                start_weekday, self.cur_user_config.Data.AnnihilationCompletedWeek, now
            ):
                self.run_book["Annihilation"] = True
                logger.info(
                    f"用户 {self.cur_user_item.name} 本次跳过剿灭：开始日={start_weekday}，本周记录={self.cur_user_config.Data.AnnihilationCompletedWeek}"
                )

    def _resolve_log_file_path(self) -> Path:
        return self.maa_log_path

    async def main_task(self):
        """自动代理模式主逻辑"""

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

        # 任务前脚本每用户一次，先于全部重试；后置脚本由收尾阶段成对执行
        await self.run_user_scripts_before()

        # 执行绿票商店 + 剿灭 + 日常
        # 绿票商店的任务链只认主界面、跑完也停在商店页，放在最前面由后续模式的开始唤醒收拾界面
        for self.mode in ["GreenTicketStore", "Annihilation", "Routine"]:
            if self.run_book[self.mode]:
                continue

            self._event_depot_completed = False
            self._stock_depot_completed = False
            self.cur_user_item.status = f"运行 - {MAA_RUN_MOOD_BOOK[self.mode]}"

            if not self.cur_user_config.Info.IfQuickConfig:
                # 来源队列整体交给 MAA 执行，不从隐藏面板推导任务或拆分阶段。
                self.task_dict = {}
            elif self.mode == "Routine":
                self.task_dict = {
                    task: getattr(self.cur_user_config.Task, f"If{task}")
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

            for i in range(self.script_config.Run.RunTimesLimit):
                if self.run_book[self.mode]:
                    break
                logger.info(
                    f"用户 {self.cur_user_item.name} - 模式: {self.mode} - 尝试次数: {i + 1}/{self.script_config.Run.RunTimesLimit}"
                )
                self.log_start_time = datetime.now().astimezone()
                self._cultivate_archive_positions.clear()
                self._cultivate_archive_versions.clear()
                self.cur_user_log = LogRecord()
                self.cur_user_item.add_log_record(
                    self.log_start_time, self.cur_user_log
                )

                try:
                    self.script_info.log = "正在启动模拟器"
                    emulator_info = await self.emulator_manager.open(
                        self.script_config.Emulator.Index,
                        ARKNIGHTS_PACKAGE_NAME[self.cur_user_config.Info.Server],
                        **mod_avd_open_kwargs(self.emulator_manager, allowed=True),
                    )
                    self.emulator_info = emulator_info
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

                    await Notify.send_notice(
                        LocalNotice(
                            title="用户自动代理出现异常！",
                            message=f"用户 {self.cur_user_item.name} 的{MAA_RUN_MOOD_BOOK[self.mode]}部分出现一次异常",
                            ticker=f"{self.cur_user_item.name}的{MAA_RUN_MOOD_BOOK[self.mode]}出现异常",
                            duration_seconds=3,
                        )
                    )
                    continue

                logger.info(
                    f"模拟器启动完成: 用户 {self.cur_user_uid} - 模式 {self.mode} - 实例 {self.script_config.Emulator.Index} - ADB {emulator_info.adb_address}"
                )

                if Config.setting.Function.IfSilence:
                    try:
                        await self.emulator_manager.setVisible(
                            self.script_config.Emulator.Index, False
                        )
                    except Exception as e:
                        logger.opt(exception=True).warning(f"模拟器隐藏失败: {e}")

                await self.set_maa(emulator_info)

                # 本轮 MAA 的日志从启动前的文件末尾开始读：gui.log 追加写且跨
                # 运行保留，历史内容里带完成/失败标志的旧行（时间戳闸门分辨不出
                # 它们的「未来」时间戳）会被整段当成本轮日志，MAA 刚启动就被判
                # 失败，随后反复重启模拟器（#19）。
                log_offset = (
                    self.maa_log_path.stat().st_size
                    if self.maa_log_path.is_file()
                    else 0
                )
                logger.info(f"启动MAA进程: {self.maa_exe_path}")
                self.wait_event.clear()
                await self.maa_process_manager.open_process(
                    self.maa_exe_path, env=await self._maa_process_env()
                )
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
                    self._resolve_log_file_path,
                    self.log_start_time,
                    initial_offset=log_offset,
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
                        self.cur_user_config.Data.LastResVersion = (
                            self.pending_res_version
                        )
                        await self.cur_user_config.commit()
                        self.if_game_hot_update = False
                else:
                    logger.warning(
                        f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                    )
                    self.script_info.log = (
                        f"{self.cur_user_log.status}\n正在中止相关程序"
                    )

                    await self.maa_process_manager.kill()
                    # 关模拟器之前把现场画面留下来：模拟器一关 adb 就补不到了。
                    # 每次失败尝试都刷新，最后一次失败的画面才是最终现场。
                    self._failure_shot = await self._take_failure_shot()
                    await close_emulator(self)
                    await System.kill_process(self.maa_exe_path)

                    # 绿票商店每月顺手买一次，失败不重试也不惊动用户，月份没写回下次调度自会再来
                    if self.mode == "GreenTicketStore":
                        self.run_book[self.mode] = True
                    else:
                        await Notify.send_notice(
                            LocalNotice(
                                title="用户自动代理出现异常！",
                                message=f"用户 {self.cur_user_item.name} 的{MAA_RUN_MOOD_BOOK[self.mode]}部分出现一次异常",
                                ticker=f"{self.cur_user_item.name}的{MAA_RUN_MOOD_BOOK[self.mode]}出现异常",
                                duration_seconds=3,
                            )
                        )

                maa_log = "".join(self.cur_user_log.content)
                if self.cur_user_config.Info.IfQuickConfig:
                    self._collect_cultivate_archive(maa_log, finalizing=True)
                    await self._finish_cultivate_round()
                await self._sync_maa_config_updates()

                if not _should_retry_maa(self.cur_user_log.status, maa_log):
                    if self.cur_user_log.status != "Success!":
                        logger.warning(
                            f"用户 {self.cur_user_item.name} 的"
                            f"{MAA_RUN_MOOD_BOOK[self.mode]}已收到 MAA 任务失败终态，停止重试"
                        )
                    break

    def _cultivate_archive_dir(self) -> Path:
        """当前用户的识别数据档案目录（方案决策 31：归属以写入时的
        cur_user_uid 为准；查询、缺口判定与养成注入只读档案。安装目录那份
        DepotData 是 MAA 的工作缓存，只有 overlay 层才按账号覆写它，见
        _apply_depot_context）。"""

        return Path.cwd() / f"data/{self.script_info.script_id}/{self.cur_user_uid}"

    def _apply_depot_context(self, gui_new_set: dict) -> None:
        """overlay 层：把当前用户档案的库存缓存覆写进 MAA 安装目录。

        安装目录那份 DepotData 是 MAA 的工作缓存，物理上跨账号共用；开启覆写
        常规配置时按本账号档案覆写，覆写前键级存底，任务结束在 _finalize_task
        里还原。覆写失败宁可关掉本轮库存保持任务，也不让 MAA 读到别的账号
        留下的库存。
        """

        queue = gui_new_set["Configurations"]["Default"].get("TaskQueue") or []
        depot_tasks = [
            task
            for task in queue
            if isinstance(task, dict)
            and task.get("IsEnable")
            and task_type_of(task) == "DepotMaintain"
        ]
        if not depot_tasks:
            return

        snapshot_dir = depot_cache_snapshot_dir(self.script_info.script_id)
        archive = self._cultivate_archive_dir() / _MAA_DEPOT_ARCHIVE_NAME
        target = self.maa_root_path / "data" / _MAA_DEPOT_ARCHIVE_NAME
        if snapshot_depot_cache(self.maa_root_path, snapshot_dir):
            try:
                if archive.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(archive, target)
                    logger.info(
                        f"用户 {self.cur_user_item.name} 的库存缓存已覆写进 MAA 安装目录"
                    )
                else:
                    # 本账号还没有档案：清掉安装目录里的旧缓存让 MAA 重新识别，
                    # 不拿上一个账号的库存充当本账号的
                    target.unlink(missing_ok=True)
                return
            except OSError:
                logger.opt(exception=True).warning(
                    f"用户 {self.cur_user_item.name} 覆写 MAA 库存缓存失败"
                )

        for task in depot_tasks:
            task["IsEnable"] = False
        self.task_dict["DepotMaintain"] = False
        self.task_dict["EventDepotMaintain"] = False
        logger.warning(
            f"用户 {self.cur_user_item.name} 本轮跳过库存保持/养成执行, "
            "请检查 MAA 数据目录的写入权限"
        )

    async def _finalize_task(self) -> None:
        """收尾：全部收尾动作结束后，还原 overlay 覆写的库存缓存。

        挂在 _finalize_task（收尾主体，由 _run_final_task 放进屏蔽取消的
        独立任务里执行）上，而不是 final_task：收尾被取消或异常中断时它仍会
        执行（wait_for_finalizer_on_cancel）。正常路径在后置脚本后、保存前已还原，
        此处幂等兜底仅覆盖提前异常退出。
        """

        try:
            await super()._finalize_task()
        finally:
            if self.maa_root_path is not None:
                restore_depot_cache(
                    self.maa_root_path,
                    depot_cache_snapshot_dir(self.script_info.script_id),
                )

    def _archive_recognition_file(
        self, name: str, *, require_fresh_sync_time: bool = False
    ) -> bool:
        """把 MAA 安装目录的识别结果只读复制进当前用户档案（T1.17）。

        整份原子覆盖；已归档且源文件未变化时跳过，读取期间仍在写入时
        留待收尾补存，保留此前有效档案。

        Args:
            name: 识别数据文件名（DepotData.json / OperBoxData.json）。
            require_fresh_sync_time: 是否校验 syncTime 不早于本轮开始
                （DepotData 有该字段；OperBoxData 无时间字段，靠会话归因）。

        Returns:
            是否更新档案；跳过或失败时返回 False，不撤销此前成功采集。
        """

        source = self.maa_root_path / "data" / name
        try:
            source_stat = source.stat()
            version = (
                source_stat.st_ino,
                source_stat.st_mtime_ns,
                source_stat.st_size,
            )
            if self._cultivate_archive_versions.get(name) == version:
                return False
            payload = _utils_io.read_dict_file(source)
            source_stat = source.stat()
            if version != (
                source_stat.st_ino,
                source_stat.st_mtime_ns,
                source_stat.st_size,
            ):
                logger.warning(f"识别数据仍在更新, 留待收尾采集: {name}")
                return False
            if require_fresh_sync_time:
                try:
                    _, sync_time = parse_depot_payload(payload)
                except AttributeError as e:
                    raise _utils_io.ConfigCorruptedError(source) from e
                if sync_time < int(self.log_start_time.timestamp()):
                    logger.warning(
                        f"用户 {self.cur_user_item.name} 的 {name} syncTime 早于本轮开始, 弃用本次采集"
                    )
                    return False
            archive_dir = self._cultivate_archive_dir()
            archive_dir.mkdir(parents=True, exist_ok=True)
            _utils_io.write_file(archive_dir / name, payload)
            self._cultivate_archive_versions[name] = version
            logger.info(f"用户 {self.cur_user_item.name} 的识别数据已落档案: {name}")
            return True
        except (OSError, ValueError, TypeError):
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} 采集识别数据失败: {name}"
            )
            return False

    def _collect_cultivate_archive(self, log: str, *, finalizing: bool = False) -> None:
        """新的识别完成标记采集一次完整快照，后续缓存变化在收尾归档。

        归因依据"该链运行在当前用户的 MAA 会话内"（串行调度 + StartUp 已
        切号）；每类数据每轮以最后一次识别标记为准并覆盖档案——队列里养成
        计划（刷取前）与更新数据（刷取后）各有一条仓库识别，取后者下一轮
        缺口判定才用得上刷取后的库存，否则补齐材料后仍会多接管一轮。

        Args:
            log: 当前这次 MAA 运行的累计日志。
            finalizing: 是否在收尾检查已识别文件的变化并补存失败采集。
        """

        for name, markers in (
            (_MAA_DEPOT_ARCHIVE_NAME, _MAA_DEPOT_CHAIN_COMPLETION_MARKERS),
            (_MAA_OPER_BOX_ARCHIVE_NAME, _MAA_OPER_BOX_CHAIN_COMPLETION_MARKERS),
        ):
            position = max(log.rfind(marker) for marker in markers)
            if position < 0:
                continue
            if not finalizing and position <= self._cultivate_archive_positions.get(
                name, -1
            ):
                continue
            # 失败也消费本次标记，普通日志更新不反复尝试，收尾统一补存。
            self._cultivate_archive_positions[name] = position
            if self._archive_recognition_file(
                name, require_fresh_sync_time=name == _MAA_DEPOT_ARCHIVE_NAME
            ):
                if name == _MAA_DEPOT_ARCHIVE_NAME:
                    self._cultivate_collected_depot = True
                else:
                    self._cultivate_collected_oper_box = True

    async def _finish_cultivate_round(self) -> None:
        """采集识别数据或注入自动培养后，刷新达成状态并持久化。

        未采集也未注入时空转；取消时保留标记，交给 final_task 兜底。
        判定只用可自证链，异常只记日志，档案留待下一轮注入前拦截兜底。
        """

        auto_raise_injected = self._cultivate_auto_raise_injected
        if not (
            self._cultivate_collected_depot
            or self._cultivate_collected_oper_box
            or auto_raise_injected
        ):
            return
        self._cultivate_progress_synced = False
        try:
            raw_targets = json.loads(self.cur_user_config.Task.CultivateTargets)
            targets = parse_cultivate_targets(raw_targets)
            if not targets:
                self._cultivate_collected_depot = False
                self._cultivate_collected_oper_box = False
                self._cultivate_auto_raise_injected = False
                return
            # 培养会改变练度，必须重新查询，不能复用培养前的快照。
            # 仅刷材料时沿用 TTL 缓存，保持既有请求次数。
            skland = await maa_api.get_cultivate_skland_progression(
                str(self.script_info.script_id),
                str(self.cur_user_uid),
                force=auto_raise_injected,
            )
            skland_bound = bool(
                self.cur_user_config.Task.CultivateSklandAccount.strip()
                and self.cur_user_config.Task.CultivateSklandUid.strip()
            )
            if skland_bound and not (skland and skland[0]):
                logger.warning(
                    f"用户 {self.cur_user_item.name} 森空岛练度刷新失败, 保留养成目标"
                )
                self._cultivate_collected_depot = False
                self._cultivate_collected_oper_box = False
                self._cultivate_auto_raise_injected = False
                return
            # 库存识别不代表练度已更新；缺少本轮干员识别时保留原计划。
            if not (skland and skland[0]) and not self._cultivate_collected_oper_box:
                return
            context = ProviderContext(
                maa_data_dir=self._cultivate_archive_dir(),
                skland_progressions=skland[0] if skland else {},
                skland_captured_at=skland[1] if skland else 0,
            )
            snapshots = {
                target.operator_id: resolve_progression(
                    operator_id=target.operator_id,
                    chain=get_progression_chain(),
                    context=context,
                )
                for target in targets
            }
            ready_targets, deferred = filter_observed_cultivate_targets(
                targets, snapshots
            )
            certifying_snapshots = {
                target.operator_id: resolve_progression(
                    operator_id=target.operator_id,
                    chain=get_certifying_chain(),
                    context=context,
                )
                for target in ready_targets
            }
            achievements = judge_achievements(ready_targets, certifying_snapshots)
            updated = apply_achievements(ready_targets, achievements)
            if updated != ready_targets:
                names = load_oper_box_names(context)
                # 森空岛可直接确认达成，无干员识别档案时从展示目录补齐名称。
                if any(
                    achievement.achieved
                    and achievement.confident
                    and achievement.operator_id not in names
                    for achievement in achievements
                ):
                    try:
                        catalog = await depot_cultivate_service.operator_catalog(
                            config_path=Config.config_path, proxy=Config.proxy
                        )
                    except YituliuDataError as e:
                        logger.warning(f"养成达成干员名称查询失败, 使用干员编号: {e}")
                    else:
                        names = {
                            operator["value"]: operator["label"] for operator in catalog
                        } | names
                merged_payload = _merge_cultivate_target_updates(
                    raw_targets=raw_targets,
                    updated_targets=updated,
                    deferred_targets=deferred,
                )
                self.cur_user_config.Task.CultivateTargets = json.dumps(
                    merged_payload, ensure_ascii=False
                )
                await self.cur_user_config.commit()
                # 最后一个目标达成被移除后目标清空：接管已不可能，残留的接管
                # 提示要一并清掉——这条路不经过用户配置写入漏斗
                if not merged_payload:
                    await self._set_cultivate_notice("")
                removed = summarize_achievements(
                    targets=ready_targets, achievements=achievements, names=names
                )
                for line in removed:
                    if line not in self._cultivate_achievement_summary:
                        self._cultivate_achievement_summary.append(line)
            self._cultivate_progress_synced = not deferred
        except Exception as e:
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} 养成达成刷新失败: {e}"
            )
        # 刷新被取消时不会执行到这里，收尾仍可重试本轮尚未完成的刷新。
        self._cultivate_collected_depot = False
        self._cultivate_collected_oper_box = False
        self._cultivate_auto_raise_injected = False

    async def _set_cultivate_notice(self, notice: str) -> None:
        """写养成状态提示；值未变化时避免重复写盘。"""

        if self.cur_user_config.Data.CultivateNotice == notice:
            return
        self.cur_user_config.Data.CultivateNotice = notice
        await self.cur_user_config.commit()

    async def _prepare_cultivate_injection(
        self, source_queue: list[dict], *, skip_this_round: bool = False
    ) -> tuple[dict | None, bool, CultivatePlan | None]:
        """准备当轮养成计划，同时保留完整消耗供库存预留。

        仅在开关开启且目标非空时生效（Routine 门控由调用方负责）；数据集、
        练度、库存不可用时暂停本轮养成，保留普通库存及后续理智任务。
        绑定森空岛后拉取失败时暂停自动培养，
        不使用缺少本轮识别保障的旧练度档案。

        Returns:
            (养成刷取任务, 是否存在原始目标, 本轮有效养成计划)
        """

        # 开关关闭或无有效目标时，不让保存的旧目标参与本轮备料与培养。
        self._cultivate_round_paused = True
        self._cultivate_execution_targets = ()
        self._cultivate_progress_synced = False
        raw_targets: object
        try:
            raw_targets = json.loads(self.cur_user_config.Task.CultivateTargets)
        except (TypeError, ValueError):
            raw_targets = []
        notice = takeover_notice_patch_value(
            self.cur_user_config.Task.IfCultivate, raw_targets
        )
        if notice is not None:
            await self._set_cultivate_notice(notice)
            return None, False, None
        if skip_this_round:
            await self._set_cultivate_notice("")
            return None, True, None
        original_targets = parse_cultivate_targets(raw_targets)

        skland_bound = bool(
            self.cur_user_config.Task.CultivateSklandAccount.strip()
            and self.cur_user_config.Task.CultivateSklandUid.strip()
        )
        try:
            # 注入前强刷；未绑定时沿用本地识别，绑定失败时暂停本轮养成。
            skland = await maa_api.get_cultivate_skland_progression(
                str(self.script_info.script_id), str(self.cur_user_uid), force=True
            )
        except Exception as e:
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} 森空岛练度查询失败: {e}"
            )
            skland = None
        if skland_bound and not (skland and skland[0]):
            await self._set_cultivate_notice("")
            message = (
                "森空岛练度同步失败，本轮养成已暂停；请检查网络或重新绑定森空岛，"
                "日常与库存保持照常执行"
            )
            logger.warning(f"用户 {self.cur_user_item.name} {message}")
            if message not in self._missing_task_source_warned:
                self._missing_task_source_warned.add(message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=message,
                        messageKey="core.edit.maaCultivateSklandSyncFailed",
                    ),
                )
            return None, True, None

        try:
            context = ProviderContext(
                maa_data_dir=self._cultivate_archive_dir(),
                skland_progressions=skland[0] if skland else {},
                skland_captured_at=skland[1] if skland else 0,
            )
            snapshots = {
                target.operator_id: resolve_progression(
                    operator_id=target.operator_id,
                    chain=get_progression_chain(),
                    context=context,
                )
                for target in original_targets
            }
            targets, deferred = filter_observed_cultivate_targets(
                original_targets, snapshots
            )
            self._cultivate_progress_synced = (
                bool(skland and skland[0]) and not deferred
            )
            if deferred:
                logger.warning(
                    f"用户 {self.cur_user_item.name} 本轮延期 {len(deferred)} 个缺少练度数据的养成目标: "
                    + ", ".join(target.operator_id for target in deferred)
                )
                message = (
                    "缺少所需练度数据的养成目标本轮暂缓并保留，其他有效目标继续执行；"
                    "可同步森空岛练度后重试。"
                )
                if message not in self._missing_task_source_warned:
                    self._missing_task_source_warned.add(message)
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="warning",
                            message=message,
                            messageKey="core.edit.maaCultivateTargetsDeferred",
                        ),
                    )
            if not targets:
                await self._set_cultivate_notice("")
                return None, True, None
            (
                updated_targets,
                plan,
                _,
                auto_targets,
            ) = await depot_cultivate_service.prepare_cultivate(
                targets=targets,
                maa_data_dir=self._cultivate_archive_dir(),
                config_path=Config.config_path,
                proxy=Config.proxy,
                today=_utils_constants.game_now(
                    self.cur_user_config.Info.Server
                ).date(),
                context=context,
                require_observations=True,
                auto_raise=self.cur_user_config.Task.CultivateAutoRaise,
            )
        except Exception as e:
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} 养成数据准备失败, 本轮跳过养成注入: {e}"
            )
            await self._set_cultivate_notice("")
            message = "养成数据暂时不可用，本轮养成已暂停；库存保持与理智任务继续执行"
            if message not in self._missing_task_source_warned:
                self._missing_task_source_warned.add(message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=message,
                        messageKey="core.edit.maaCultivatePreparationUnavailable",
                    ),
                )
            return None, True, None

        # 达成拦截后把目标状态写回档案：可自证达成的目标已移除（方案 §7.6）；
        # 状态无变化时跳过，避免每轮无谓写盘
        if updated_targets != targets:
            merged_payload = _merge_cultivate_target_updates(
                raw_targets=raw_targets,
                updated_targets=updated_targets,
                deferred_targets=deferred,
            )
            self.cur_user_config.Task.CultivateTargets = json.dumps(
                merged_payload, ensure_ascii=False
            )
            await self.cur_user_config.commit()
        # 旧接管提示清空；养成不再暂停普通库存。
        await self._set_cultivate_notice("")
        if plan is None or not plan.reservations:
            return None, True, None
        self._cultivate_round_paused = False
        self._cultivate_execution_targets = auto_targets

        cultivate_task = None
        if plan.entries:
            cultivate_task = _build_cultivate_task(
                plan,
                _find_task_source(
                    source_queue, _MAA_CULTIVATE_TASK_NAME, "DepotMaintain"
                )
                or _find_task_source(
                    source_queue, "库存保持与干员养成", "DepotMaintain"
                ),
                skip_during_activity=False,
                skip_during_resource_collection=False,
            )
        return cultivate_task, True, plan

    async def _prepare_auto_cultivate_injection(
        self, source_queue: list[dict]
    ) -> dict | None:
        """自动培养独立门控；关闭或森空岛同步失败时不查询目录。"""

        if self._cultivate_round_paused or not (
            self.cur_user_config.Task.IfCultivate
            and self.cur_user_config.Task.CultivateAutoRaise
        ):
            return None
        targets = self._cultivate_execution_targets
        if not any(
            goal.kind != "module" and goal.state not in ("achieved", "pending_confirm")
            for target in targets
            for goal in target.goals
        ):
            return None

        source = _find_task_source(source_queue, "干员培养", "OperProgress")
        release = read_installed_release(self.maa_root_path)
        installed_version = parse_version(release[0]) if release else None
        minimum_version = parse_version("v6.19.0-beta.1")
        assert minimum_version is not None
        # 版本无法确认时仅复用已经存在的原生培养入口，旧版不注入未知任务类型。
        if (
            installed_version is not None
            and compare_versions(installed_version, minimum_version) < 0
        ) or (installed_version is None and source is None):
            message = (
                "自动培养未注入：请使用 MAA v6.19.0-beta.1 或更新版本，"
                "并确认 MAA 中有「干员培养」任务；材料刷取照常执行"
            )
            if message not in self._missing_task_source_warned:
                self._missing_task_source_warned.add(message)
                logger.warning(message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=message,
                        messageKey="core.edit.maaCultivateAutoRaiseUnsupported",
                    ),
                )
            return None
        try:
            catalog = await depot_cultivate_service.operator_catalog(
                config_path=Config.config_path, proxy=Config.proxy
            )
            return _build_auto_cultivate_task(
                targets=targets, catalog=catalog, source_task=source
            )
        except Exception as e:
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} 自动培养准备失败, 本轮不注入: {e}"
            )
            message = "自动培养未注入：培养数据暂时不可用，请刷新干员目录后重试；材料刷取照常执行"
            if message not in self._missing_task_source_warned:
                self._missing_task_source_warned.add(message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=message,
                        messageKey="core.edit.maaCultivateAutoRaiseDataUnavailable",
                    ),
                )
            return None

    async def _warn_missing_task_source(self, source_name: str, affected: str) -> None:
        """提示 MAA 任务队列里认不出某个原生任务，受影响的任务将按默认值运行。

        认不出有两种情况：队列里没有这类任务；或同类任务有多个、名字又都对不上，
        按 ``_find_task_source`` 的约定不猜，免得串用别的任务的配置。

        Args:
            source_name: MAA 任务队列里认不出的任务名。
            affected: 因此按默认值运行的任务，多个用顿号连接。
        """

        message = (
            f"用户 {self.cur_user_item.name} 的 MAA 任务队列里认不出「{source_name}」"
            f"任务（队列里没有，或有多个同类任务且名字都对不上），{affected}本次按"
            f"默认设置运行，在 MAA 里为它设置的选项不会生效"
        )
        if message in self._missing_task_source_warned:
            return
        self._missing_task_source_warned.add(message)

        logger.warning(message)
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="warning", message=message),
        )

    async def set_maa(self, emulator_info: DeviceInfo):
        """配置MAA运行参数"""

        logger.info(f"开始配置MAA运行参数: {self.mode}")

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)
        self._remember_pending_update()

        # 哔哩哔哩用户协议
        if self.cur_user_config.Info.Server == "Bilibili":
            await agree_bilibili(self.maa_tasks_path, True)
        else:
            await agree_bilibili(self.maa_tasks_path, False)

        # 下发前归档 MAS 配置到用户池（下发源，运行回写 _sync_maa_config_updates
        # 会覆盖它；带页面任务字段侧车，指纹去重，失败不阻断运行）。目标路径
        # 按来源 owner（共享来源共享 Default 目录，原生来源无 MAS 配置目录不归档）。
        # native 池由 manager prepare 在任务级一次性归档
        archive_dir = self._config_archive_dir()
        if archive_dir is not None:
            seed_maa_base_config(archive_dir)
            archive_mas_runtime_backup(
                self.script_info.script_id,
                str(self.cur_user_uid),
                archive_dir,
                overlay=read_overlay_values(self.cur_user_config),
                # 备份标注来源：tri_state 池跨来源恢复靠它切回
                base=self.config_base,
            )

        # ── 第一段：来源落盘 ──────────────────────────────────────────
        # 用 MAS 托管配置覆盖 MAA 原生配置目录。原生来源跳过这一段——
        # 原生来源的事实源是 MAA 安装目录里现有的原生配置。
        # 来源目录可能不存在（新建脚本/用户首次运行，或用户删掉专项重建）：
        # 此时保持安装目录现有的 MAA 配置不动，它天然是可运行的默认配置。
        if self.config_base == CONFIG_BASE_SHARED:
            self._copy_source_config(
                Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"
            )
        elif self.config_base == CONFIG_BASE_INDEPENDENT:
            self._copy_source_config(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
            )
        elif self.native_base:
            # 原生来源从本轮原生快照开始，不能继承上一用户或上一阶段的快速配置。
            source = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
            if source.is_dir():
                shutil.copytree(
                    source,
                    self.maa_set_path,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(MAA_STAMINA_LEGACY_FILENAME),
                )

        # base 缺失/损坏时退回 MAA 自带 .bak 或随包预设；预设含完整根级 Gui
        # 与 Timers，缺根级 Gui 时 MAA 会把这次启动当首次运行并弹新手引导。
        gui_new_set = read_maa_config_with_fallback(self.maa_set_path)
        self._remember_pending_update()

        # Default 本身可能缺失——原生来源/沿用安装目录配置时该文件不由 MAS 生成，
        # 兜底必须无条件执行。
        ensure_maa_default_configuration(gui_new_set)

        # 非原生来源才由 MAS 修正队列条目；原生来源的 TaskQueue 完全由用户维护。
        if not self.native_base:
            for configurations in (gui_new_set.get("Configurations") or {}).values():
                if isinstance(configurations, dict):
                    queue = configurations.get("TaskQueue")
                    if isinstance(queue, list):
                        configurations["TaskQueue"] = _repair_maa_task_queue(queue)

        # 使用简体中文
        gui_new_set["Gui"]["Localization"] = "zh-cn"

        # 原生来源的 TaskQueue 由用户在 MAA 原生界面维护；仅保留下方运行期 overlay。
        if not self.native_base and self.cur_user_config.Info.IfQuickConfig:
            await self._apply_maa_quick_config(gui_new_set)

        # 库存缓存按账号隔离属 overlay 层行为，与上方面板覆写同一个开关：
        # 关闭覆写常规配置时不读不写安装目录那份缓存，原样留给 MAA。
        if self.cur_user_config.Info.IfQuickConfig:
            self._apply_depot_context(gui_new_set)

        self._configure_maa_runtime(
            gui_new_set=gui_new_set,
            emulator_info=emulator_info,
        )
        # 待更新包已保留；本次任务启动不再触发安装，结束后恢复登记。
        gui_new_set.setdefault("Update", {})["UpdatePackage"] = ""

        _utils_io.write_file(self.maa_set_path / "gui.new.json", gui_new_set)
        self._snapshot_maa_config()
        _utils_io.mark_native_config_injected(
            Path.cwd() / f"data/{self.script_info.script_id}/Temp",
            self.maa_set_path,
            script_id=self.script_info.script_id,
        )
        logger.success(f"MAA运行参数配置完成: {self.mode}")

    def _copy_source_config(self, source: Path) -> None:
        """把 MAS 托管配置覆盖进 MAA 配置目录；来源不存在时保持现状。

        来源目录缺失是正常情形（新建脚本、新建用户、删除专项后重建），此时
        MAA 安装目录里的现有配置就是可运行的事实源，直接沿用即可，不必也无法
        从空目录拷贝。
        """

        if not source.is_dir():
            logger.info("MAS 配置目录尚未建立, 沿用 MAA 安装目录现有配置")
            return
        shutil.copytree(
            source,
            self.maa_set_path,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(MAA_STAMINA_LEGACY_FILENAME),
        )

    async def _apply_maa_quick_config(self, gui_new_set: dict) -> None:
        """仅开启快速配置时构造面板任务，来源导入与启动设置留在外层。"""

        task_set = {}
        source_queue = gui_new_set["Configurations"]["Default"].get("TaskQueue", [])
        if not isinstance(source_queue, list):
            source_queue = []
        # 存档队列里缺的任务（用户在 MAA 原生界面删掉过它）由随包预设补齐，
        # 见下方 MAA_TASKS 装配循环
        preset_queue = get_maa_base_preset()["Configurations"]["Default"]["TaskQueue"]
        # 活动目标每轮解析；旧活动优先已在配置加载时迁入这一逻辑阶段。
        self.task_dict["EventDepotMaintain"] = False
        activity_stages = []
        if self.mode == "Routine":
            # 普通库存每次尝试都重新参与，养成消耗与常备目标按当轮数据合并。
            self.task_dict["DepotMaintain"] = self.cur_user_config.Task.IfDepotMaintain
            # 活动关卡信息已在 MaaManager.prepare 里刷新过一次, 这里直接用缓存
            stage_info = await maa_stage_service.get_stage_info(
                "Info", server=self.cur_user_config.Info.Server
            )
            activity_stages = stage_info.get("Activity", [])

        # 来源各自判断跳过条件，不能让一方的整段设置跳过另一方。
        activity_open = resource_collection_open = False
        if self.mode == "Routine":
            try:
                activity_open, resource_collection_open = _maa_activity_state(
                    json.loads(Config.setting.Data.StageData),
                    self.cur_user_config.Info.Server,
                    now=datetime.now(timezone.utc),
                )
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                logger.warning(f"活动时段数据不可用，本轮不按活动条件跳过: {e}")

        # 养成仅在常规轮注入；暂时缺数据时继续普通库存与理智任务。
        cultivate_task = None
        cultivate_plan = None
        auto_cultivate_task = None
        update_task = None
        if self.mode == "Routine":
            (
                cultivate_task,
                has_targets,
                cultivate_plan,
            ) = await self._prepare_cultivate_injection(
                source_queue,
                skip_this_round=activity_open
                and self.cur_user_config.Task.CultivateSkipDuringActivity
                or (
                    resource_collection_open
                    and self.cur_user_config.Task.CultivateSkipDuringResourceCollection
                ),
            )
            auto_cultivate_task = await self._prepare_auto_cultivate_injection(
                source_queue
            )
            if has_targets:
                # 更新数据紧跟养成/库存保持注入（方案决策 30），为下一轮
                # 提供归属正确的识别数据
                skland_bound = bool(
                    self.cur_user_config.Task.CultivateSklandAccount.strip()
                    and self.cur_user_config.Task.CultivateSklandUid.strip()
                )
                update_task = _build_data_update_task(
                    _find_task_source(
                        source_queue, _MAA_DATA_UPDATE_TASK_NAME, "UserDataUpdate"
                    ),
                    # 已绑定森空岛时直接使用其练度，省去游戏内干员识别。
                    update_oper_box=not skland_bound,
                )

        # 优先按任务名称匹配，确保多个 Fight 任务各自继承原生高级配置。
        missing_sources: set[str] = set()
        for en_task, zh_task in zip(MAA_TASKS, MAA_TASKS_ZH):
            # 默认关闭时不写入新任务，兼容尚未支持该任务类型的 MAA 版本
            # （库存保持、更换主题；更换主题需 MAA v6.17.3+，旧版无法反序列化未知任务类型）
            if (
                en_task in ("DepotMaintain", "SwitchTheme")
                and not self.task_dict[en_task]
            ):
                continue

            source = _find_task_source(source_queue, zh_task, en_task)
            if source is None:
                missing_sources.add(en_task)
                # 缺了就补随包预设的同名任务，不能塞空壳：MAA 反序列化缺字段的
                # 任务会回填它自己的占位默认值（信用收支落成
                # {{ HighPriorityDefault }} / {{ BlacklistDefault }}）并落盘，
                # 用户之后在 MAA 里再也改不回来
                source = _find_task_source(preset_queue, zh_task, en_task)
            task_set[en_task] = source or {
                "$type": f"{en_task}Task",
                "Name": zh_task,
                "IsEnable": False,
                "TaskType": en_task,
            }

        annihilation_source = _find_task_source(source_queue, "剿灭作战", "Fight")
        # 吃药 / 碎石类任务取不到原生配置就只剩默认值，用户在 MAA 里设的选项
        # 全部失效却看不出来，必须提示。剿灭作战没有同名任务时本就
        # 沿用理智作战，只有理智作战也缺失才会落到默认值
        if "DepotMaintain" in missing_sources:
            await self._warn_missing_task_source(
                "库存保持与干员养成", "库存保持与干员养成"
            )
        if "Fight" in missing_sources:
            affected = []
            if self.task_dict["Fight"] and self.mode == "Routine":
                affected.append("理智任务")
            if (
                self.task_dict["Fight"]
                and self.mode == "Annihilation"
                and annihilation_source is None
            ):
                affected.append("剿灭作战")
            if affected:
                await self._warn_missing_task_source("理智任务", "、".join(affected))

        # 养成组本轮已花掉的额度不影响库存计划，反之亦然，两组各按自己的设置覆盖。
        _apply_depot_quota_override(
            cultivate_task,
            medicine=self.cur_user_config.Task.CultivateMedicineNumb,
            stone=self.cur_user_config.Task.CultivateStoneNumb,
        )
        # 库存保持计划：MAS 快速配置面板维护的计划写回原生 PlanList。只覆盖
        # MAS 管理的三项（Stage/DropId/DropCount），其余原生字段（含用户在 MAA 里
        # 设的药/石开关）整条透传，不按 #927 前的口径硬编码 UseMedicine/UseStone。
        if "DepotMaintain" in task_set:
            task_set["DepotMaintain"] = _build_depot_maintain_task(
                self.cur_user_config.Task.DepotMaintainPlans,
                source_task=task_set["DepotMaintain"],
            )
            stock_task = task_set["DepotMaintain"]
            if self._stock_depot_completed:
                # 重试保留库存目标，但不重新领取已执行阶段的药石额度。
                stock_task.update({gate: False for gate, _ in _MAA_DEPOT_QUOTA_KEYS})
            else:
                _apply_depot_quota_override(
                    stock_task,
                    medicine=self.cur_user_config.Task.DepotMaintainMedicineNumb,
                    stone=self.cur_user_config.Task.DepotMaintainStoneNumb,
                )
            stock_skipped = (
                activity_open and stock_task.get("SkipDuringActivity", False)
            ) or (
                resource_collection_open
                and stock_task.get("SkipDuringResourceCollection", False)
            )
            if stock_skipped:
                conditions = []
                if activity_open and stock_task.get("SkipDuringActivity", False):
                    conditions.append("活动期间跳过")
                if resource_collection_open and stock_task.get(
                    "SkipDuringResourceCollection", False
                ):
                    conditions.append("资源全开放期间跳过")
                logger.info(
                    f"用户 {self.cur_user_item.name} 普通库存本轮暂停，命中来源设置: "
                    + "、".join(conditions)
                )
                del task_set["DepotMaintain"]
                self.task_dict["DepotMaintain"] = False
            elif cultivate_plan is not None and stock_task["PlanList"]:
                task_set["DepotMaintain"] = _build_stock_cultivate_task(
                    stock_task, cultivate_task, cultivate_plan
                )
                cultivate_task = None

        # 加载关卡号配置
        if self.cur_user_config.Stage.StageMode == "Fixed":
            plan_data = {
                stage_key: getattr(self.cur_user_config.Stage, stage_key)
                for stage_key in _utils_constants.MAA_STAGE_KEY
            }
        else:
            plan = Config.PlanConfig[self.cur_user_config.Stage.StageMode]
            plan_data = {
                stage_key: plan.get_current_info(
                    stage_key, server=self.cur_user_config.Info.Server
                )
                for stage_key in _utils_constants.MAA_STAGE_KEY
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
            task_set["Fight"]["AnnihilationStage"] = (
                self.cur_user_config.Task.Annihilation
            )

        elif self.mode == "Routine":
            # 普通理智作战不能继承剿灭任务的语义字段。
            task_set["Fight"].update(
                {
                    "Name": "理智任务",
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

            # 共享来源下托管的配置
            if self.config_base == CONFIG_BASE_SHARED:
                task_set["Fight"]["EnableTimesLimit"] = False
                task_set["Fight"]["EnableTargetDrop"] = False
                fight_source = deepcopy(task_set["Fight"])

            # 基建配置
            if self.cur_user_config.Task.InfrastMode == "Custom":
                infrast_path = (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/Infrastructure/infrastructure.json"
                )
                infrast_plans, infrast_problem = load_infrast_plans(
                    self.cur_user_config.Data.CustomInfrast
                )
                if infrast_problem is None:
                    infrast_path.parent.mkdir(parents=True, exist_ok=True)
                    infrast_path.write_text(
                        self.cur_user_config.Data.CustomInfrast, encoding="utf-8"
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
                    # PlanSelect 不沿用存档: 脚本模式下存档是全脚本共用的, MAA 每跑完
                    # 一次基建就 ++PlanSelect, 多个自定义基建用户会互相拨对方的班次。
                    # 带时段表 → -1, 时间语义整个交给 MAA 按时段选班(-1 不推进);
                    # 无时段表 → 注入用户自己的指针, 一轮里重试几次都是同一个值,
                    # 基建换班完成后由 check_log 推进一次
                    if infrast_plan_mode(infrast_plans) == "rotate":
                        if self._infrast_plan_index is None:
                            self._infrast_plan_count = len(infrast_plans)
                            self._infrast_plan_index = (
                                int(self.cur_user_config.Data.InfrastPlanIndex)
                                % self._infrast_plan_count
                            )
                        task_set["Infrast"]["PlanSelect"] = self._infrast_plan_index
                    else:
                        task_set["Infrast"]["PlanSelect"] = -1
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
                task_set["Infrast"]["Mode"] = self.cur_user_config.Task.InfrastMode

        event_depot_task = None
        if (
            self.mode == "Routine"
            and (not self._event_depot_completed)
            and self.cur_user_config.Task.IfEventDepotMaintain
        ):
            event_depot_source = _find_task_source(
                task_queue=source_queue,
                name="活动关均衡理智",
                task_type="DepotMaintain",
            ) or _find_task_source(
                task_queue=preset_queue,
                name="活动关均衡理智",
                task_type="DepotMaintain",
            )
            event_depot_task, activity_notices = _build_event_depot_maintain_task(
                self.cur_user_config.Task.EventDepotMaintainPlans,
                activity_stages,
                source_task=event_depot_source,
            )
            _apply_depot_quota_override(
                event_depot_task,
                medicine=self.cur_user_config.Task.EventDepotMaintainMedicineNumb,
                stone=self.cur_user_config.Task.EventDepotMaintainStoneNumb,
            )
            for notice_key, notice in activity_notices:
                logger.warning(notice)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=notice,
                        messageKey=notice_key,
                    ),
                )
            self.task_dict["EventDepotMaintain"] = event_depot_task is not None
            if event_depot_task is None:
                logger.info("活动关均衡理智没有当前活动的有效材料计划，本轮跳过")

        # 导出任务配置
        self.task_dict["StartUp"] = True
        task_queue = gui_new_set["Configurations"]["Default"]["TaskQueue"] = []
        for task_type in MAA_TASKS:
            if task_type not in task_set:
                continue

            task_set[task_type]["IsEnable"] = self.task_dict[task_type]
            if task_type == "Fight":
                # 养成刷取或库存保持结束后立即培养、更新数据，再执行日常任务。
                if auto_cultivate_task is not None:
                    task_queue.append(auto_cultivate_task)
                    self._cultivate_auto_raise_injected = True
                    self._cultivate_progress_synced = False
                if update_task is not None:
                    task_queue.append(update_task)
                    if not skland_bound:
                        self._cultivate_progress_synced = False
            task_queue.append(task_set[task_type])

            if task_type == "StartUp" and event_depot_task is not None:
                task_queue.append(event_depot_task)
            if task_type == "StartUp" and cultivate_task is not None:
                # 没有普通库存参与时，养成备料仍位于活动阶段之后。
                task_queue.append(cultivate_task)

        # 绿票商店走 MAA 的自定义任务，本模式下队列里只有它和开始唤醒
        if self.mode == "GreenTicketStore":
            task_queue.append(dict(MAA_GREEN_TICKET_STORE_TASK))

        # 非原生来源队列严格等于 MAS 合成结果：来源队列里的未知任务(自动肉鸽、
        # 生息演算、用户自定义任务等)不透传带回——用户自定义任务队列只在原生
        # 来源存在(MAS 零写入, 安装目录原生配置即现场)。

    def _resolve_avd_device(self) -> tuple[Path, int] | None:
        """这次用的设备是魔改 AVD 实例时返回 ``(根目录, 控制台端口)``，否则 ``None``。"""
        device_ref = resolve_device_ref(
            self.emulator_manager, self.script_config.Emulator.Index
        )
        if device_ref is None or device_ref.emulator_type != "avd":
            return None
        return (
            _utils_emulator2.avd.components.root_from_manager_exe(
                device_ref.manager_path
            ),
            _utils_emulator2.avd.constants.console_port(device_ref.native_index),
        )

    async def _maa_process_env(self) -> dict[str, str] | None:
        """MAA 进程的环境变量。魔改 AVD 实例上把它（连同 MaaCore 起的 adb）指到脚本专用的 adb
        server（``scriptAdbServerPort``，默认 20049），不落到 5037；其余模拟器返回 ``None``，
        照旧继承 MAS 的环境。"""
        return await script_process_env(
            self.emulator_manager, self.script_config.Emulator.Index
        )

    def _configure_maa_runtime(
        self,
        gui_new_set: dict,
        emulator_info: DeviceInfo,
    ) -> None:
        """两种快速配置状态均需的启动、模拟器和账号设置，不改任务选择。"""

        current_gui = gui_new_set["Configurations"]["Default"]["Gui"]

        # 关闭定时，避免与 MAS 调度重叠。
        for timer in gui_new_set.setdefault("Timers", {}).setdefault("List", []):
            if isinstance(timer, dict):
                timer["IsEnabled"] = False

        if emulator_info.adb_address != "Unknown":
            current_gui["ConnectSettings"]["Address"] = emulator_info.adb_address

        # 魔改 AVD 实例：MAA 走假 MuMu 截图通道（MuMu 12 预设 + 桥接 + 实例号 = 控制台端口），
        # 雷电 / MuMu 实例不经过这里。这些键和上面的地址一样，由原生配置快照在任务结束后还原。
        avd = self._resolve_avd_device()
        self._avd_screencap_guard = avd is not None
        if avd is not None:
            avd_root, avd_console = avd
            ensure_mumu_shim(avd_root)
            current_gui["ConnectSettings"] = build_maa_connect_settings(
                avd_root, avd_console, current_gui.get("ConnectSettings")
            )
            logger.info(
                f"魔改 AVD 实例（控制台端口 {avd_console}）：MAA 截图走假 MuMu 通道"
            )
        else:
            # 先按所选实例解析安装，避免多安装管理器沿用上一次命中的 ADB。
            device_ref = resolve_device_ref(
                self.emulator_manager, self.script_config.Emulator.Index
            )
            # 自定义管理器可无专用引用，多安装管理器仍须解析所选安装。
            if device_ref is None and isinstance(
                self.emulator_manager, _utils_emulator2.facade.Emulator2Manager
            ):
                raise ValueError("无法解析所选模拟器实例，请检查模拟器配置")
            connect_settings = current_gui["ConnectSettings"]
            adb_path = self.emulator_manager.get_adb_path()
            if (
                adb_path is None
                and device_ref is not None
                and device_ref.emulator_type == "general"
            ):
                configured_adb = str(connect_settings.get("AdbPath") or "").strip()
                if configured_adb:
                    adb_path = Path(configured_adb)
                    if not adb_path.is_absolute():
                        adb_path = self.maa_set_path.parent / adb_path
            if adb_path is None or not adb_path.is_file():
                raise ValueError("未找到可用的 ADB，请检查模拟器或 MAA 的连接设置")
            address = emulator_info.adb_address.strip()
            if not address or address == "Unknown":
                raise ValueError("无法获取所选模拟器的 ADB 地址，请检查模拟器连接")
            connect_settings.update(
                {
                    "AdbPath": str(adb_path),
                    "Address": address,
                    "AutoDetect": False,
                    "AlwaysAutoDetect": False,
                }
            )

        post_actions = MAA_TASK_TRANSITION_METHOD_BOOK[
            self.script_config.Run.TaskTransitionMethod
        ]
        current_gui["PostActions"] = int(post_actions)
        current_gui["RuntimeSettings"]["StartGame"] = True
        current_gui["StartUpSettings"].update(
            {"RunDirectly": True, "StartEmulator": False}
        )
        update_settings = gui_new_set.setdefault("Update", {})
        update_settings.update(
            {
                "CheckOnSchedule": False,
                "AutoDownloadUpdatePackage": True,
                "AutoInstallUpdatePackage": False,
            }
        )
        # 接管开启即暂停原生更新，不因本轮更新失败而重新启用。
        # GitHub 资源源仅支持手动下载，临时选择随快照恢复，不改变 CDK。
        if self.script_config.Update.TakeoverEnabled:
            update_settings["CheckOnStartup"] = False
            update_settings["AutoDownloadUpdatePackage"] = False
            update_settings["UpdateSource"] = "GitHub"
        if Config.setting.Function.IfSilence:
            # 启动即最小化是同一开关的新键，新 MAA 只读 gui.new.json。
            gui_new_set["Gui"].update(
                {"UseTray": True, "MinimizeToTray": True, "MinimizeOnStartup": True}
            )
            # 无人值守运行，公告与更新后首启的版本说明弹窗一并关闭
            gui_new_set.setdefault("AnnouncementInfo", {})["DoNotShow"] = True
            update_settings["DoNotShowUpdate"] = True

        server = self.cur_user_config.Info.Server
        account = self.cur_user_config.Info.Id
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
                name: deepcopy(_utils_io.read_file(self.maa_set_path / name))
                for name in _MAA_CONFIG_FILES
            }
        except Exception as e:
            logger.opt(exception=True).warning(
                f"记录 MAA 配置基线失败, 本次运行跳过配置回写: {e}"
            )
            self._maa_config_baseline = None

    def _config_archive_dir(self) -> Path | None:
        """当前用户的 MAA 配置来源存档目录, 与 set_maa 的导入路径对称。

        原生来源用户没有 MAS 托管配置目录（对齐 MaaEnd 的「原生来源无 mas 池」），
        返回 ``None``：不下发前归档、运行产出也不回写——安装目录现场由
        任务结束的原生配置快照恢复机制管理。
        """

        if self.config_base == CONFIG_BASE_NATIVE:
            return None
        if self.config_base == CONFIG_BASE_SHARED:
            return Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"
        return (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
        )

    @property
    def update_config_dir(self) -> Path:
        """当前用户的配置来源目录，用于保留其原生更新来源选择。"""
        return self._config_archive_dir() or (
            Path.cwd() / f"data/{self.script_info.script_id}/Temp"
        )

    def _remember_pending_update(self) -> None:
        """保留原生下载登记，供下次启动前交还官方更新入口。"""
        try:
            pending = read_pending_update(self.maa_root_path)
        except (OSError, ValueError) as error:
            logger.warning(f"MAA 本体更新: 无法保留原生待更新登记: {error}")
            return
        if all(pending) and (self.maa_root_path / pending[1]).is_file():
            self.pending_update = pending
            # 保存失败必须向上传播，不能清空唯一登记后继续启动下一阶段。
            save_deferred_update(
                self.maa_root_path, version=pending[0], package=pending[1]
            )

    async def _sync_maa_config_updates(self) -> None:
        """把 MAA 运行期写盘的配置变更(相对本模式基线)回写到配置来源存档。

        MAA 原生的每日状态(如借战/访问好友的最近执行日期)因此能跨托管会话
        存活, 下次托管 MAA 读到自己的记录后自行去重; 失败只记日志不抛出。
        """

        self._remember_pending_update()
        if self.native_base:
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
                current = _utils_io.read_file(self.maa_set_path / name)
                current = _without_maa_update_changes(current, baseline[name], name)
                archive = _utils_io.read_file(archive_dir / name)
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
                maa_scheme_name(archive),
                ignore_keys=_MAA_TASK_KEYS_NOT_MERGED
                if self.cur_user_config.Info.IfQuickConfig
                else frozenset(),
            ):
                continue
            _utils_io.write_file(archive_dir / name, archive_new)
            logger.info(
                f"用户 {self.cur_user_item.name} 的 MAA 配置变更已回写存档: {name}"
            )

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
                    self.cur_user_config.Data.AnnihilationCompletedWeek = (
                        _current_week_marker(
                            _utils_constants.game_now(self.cur_user_config.Info.Server)
                        )
                    )
                    await self.cur_user_config.commit()
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
            self.cur_user_config.Data.GreenTicketStoreMonth = datetime.now(
                tz=_utils_constants.UTC4
            )
            await self.cur_user_config.commit()
            logger.info(f"用户 {self.cur_user_item.name} 已完成本月绿票商店购买")

        # 无时段排班表: 基建换班完成即推进用户自己的班次指针, 一轮内只推一次;
        # 后续重试注入的仍是本轮的班次, 不会把下一班提前换上
        if (
            self.mode == "Routine"
            and self._infrast_plan_index is not None
            and not self._infrast_plan_advanced
            and "完成任务: 基建换班" in log
        ):
            self._infrast_plan_advanced = True
            next_index = (self._infrast_plan_index + 1) % self._infrast_plan_count
            self.cur_user_config.Data.InfrastPlanIndex = next_index
            await self.cur_user_config.commit()
            logger.info(
                f"用户 {self.cur_user_item.name} 基建换班已完成第 "
                f"{self._infrast_plan_index + 1} 班, 下次从第 {next_index + 1} 班开始"
            )

        # 养成采集：识别链完成标记 → 立即读安装目录识别数据落用户档案
        # （方案 §4.2/决策 31，T1.17；无标记时不读不采）
        if self.cur_user_config.Info.IfQuickConfig:
            self._collect_cultivate_archive(log)

        # 魔改 AVD 实例上截图不许回落到普通 adb（约 250 ms，用户 09-26 定「不如不做」）
        avd_fallback = (
            screencap_fallback_status(log)
            if getattr(self, "_avd_screencap_guard", False)
            else None
        )
        # 整份脚本日志可达数 MB，check_log 又每秒轮询一次，收尾判定只扫一遍。
        completed_log = "任务已全部完成！" in log
        failed_log = _has_maa_task_failure(log)
        if avd_fallback is not None:
            self.cur_user_log.status = avd_fallback
        elif "未选择任务" in log:
            self.cur_user_log.status = "MAA 未选择任何任务"
        elif "任务出错: 开始唤醒" in log:
            self.cur_user_log.status = "MAA 未能正确登录 PRTS"
        elif completed_log or failed_log:
            # 常规任务的完成状态取自 MAA 本轮输出。
            for en_task, zh_task in zip(MAA_TASKS, MAA_TASKS_ZH):
                names = {zh_task}
                if en_task == "DepotMaintain":
                    names.update(("库存保持", _MAA_CULTIVATE_TASK_NAME))
                elif en_task == "Fight":
                    names.update(("理智作战", "剿灭作战"))
                task_completed = any(f"完成任务: {name}" in log for name in names)
                if task_completed or any(f"{name} 任务跳过" in log for name in names):
                    if (
                        en_task == "DepotMaintain"
                        and self.task_dict.get(en_task)
                        and task_completed
                    ):
                        self._stock_depot_completed = True
                    self.task_dict[en_task] = False

            if self.task_dict.get("EventDepotMaintain"):
                event_names = ("活动关均衡理智", "活动库存保持")
                # 新版 MAA 收尾明确列出失败的队列名称；识别链或某条 #N 成功
                # 不能覆盖同阶段其他计划的失败，不读取原生 TaskId 等内部状态。
                error_summaries = re.findall(
                    r"任务已结束，以下任务出现错误[:：]\s*([^\r\n]+)", log
                )
                event_failed = any(
                    name in error_summary
                    for name in event_names
                    for error_summary in error_summaries
                ) or any(
                    re.search(
                        rf"任务出错:\s*{re.escape(name)}(?:\s+#\d+| \(仓库识别\))?\s*$",
                        log,
                        re.M,
                    )
                    for name in event_names
                )
                event_completed = re.search(
                    r"完成任务: (?:活动关均衡理智|活动库存保持)(?:\s+#\d+| \(仓库识别\))?\s*$",
                    log,
                    re.M,
                )
                # 旧版只有「部分失败」标题，无法归属失败阶段时仍允许重试。
                completion_known = completed_log or bool(error_summaries)
                if event_completed and not event_failed and completion_known:
                    # 库存充足时只有仓库识别，也由 MAA 收尾确认为整段完成。
                    self.task_dict["EventDepotMaintain"] = False
                    self._event_depot_completed = True
                elif not event_failed and any(
                    f"{name} 任务跳过" in log for name in event_names
                ):
                    # 来源时段跳过只结束本次尝试，下一次仍重新判断条件。
                    self.task_dict["EventDepotMaintain"] = False

            # 培养目标未完成不算整轮错误，不根据培养失败计数触发重试。
            # 最终失败结论以 MAA 收尾日志为准，已完成的仓库识别或刷关子链不能覆盖它。
            if (
                failed_log
                or any(self.task_dict.values())
                or any(
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
        elif _MAA_OUT_OF_MEMORY_MARKER in log:
            self.cur_user_log.status = "MAA 因内存不足停止，请关闭部分程序后重试"
        elif "已停止" in log:
            self.cur_user_log.status = "MAA 在完成任务前中止"
        elif (
            "MaaAssistantArknights GUI exited" in log
            or not await self.maa_process_manager.is_running()
        ):
            self.cur_user_log.status = "MAA 在完成任务前退出"
        elif self.is_log_stalled(
            latest_time,
            minutes=max(
                getattr(self.script_config.Run, MAA_MODE_TIME_LIMIT_BOOK[self.mode]),
                self.script_config.Run.GameUpdateTimeLimit,
            )
            if self.if_game_hot_update
            else getattr(self.script_config.Run, MAA_MODE_TIME_LIMIT_BOOK[self.mode]),
        ):
            self.cur_user_log.status = "MAA 进程超时"
        else:
            self.cur_user_log.status = "MAA 正常运行中"

        logger.debug(f"MAA 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "MAA 正常运行中":
            logger.info(f"MAA 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def _take_failure_shot(self) -> Path | None:
        return await self._failure_capture.run(self._capture_failure_shot)

    async def _capture_failure_shot(self) -> Path | None:
        """取一张失败现场画面：上游 debug/interface 图优先，adb 补截兜底。

        上游图是 MAA 在任务链失败/停止瞬间落的缓存帧；登录链失败、进程超时
        这些上游不落图的场景走 adb 补截当前画面（截到的可能是 MAA 结束动作
        退游戏后的桌面）。诊断旁路：任何失败只记日志并返回 ``None``。
        """

        shot = await asyncio.to_thread(
            collect_maa_failure_image,
            self.maa_root_path,
            not_before=self.log_start_time,
        )
        if shot is not None:
            return shot
        # 魔改 AVD 实例：截图走 MAS 私有 server（它的 adb 不能落到 5037）。
        host_adb = await resolve_host_adb(self)
        image = await capture_current_image(
            capture_adb=self.capture_adb,
            adb_path=self.emulator_manager.get_adb_path(),
            adb_address=self.emulator_info.adb_address
            if self.emulator_info is not None
            else "",
            png_reader=host_adb.screencap_png if host_adb is not None else None,
        )
        return await asyncio.to_thread(
            self._failure_capture.save, image, dir_name="maa-failure"
        )

    async def final_task(self):
        if self.check_result != "Pass":
            logger.info(f"MAA 检查未通过，跳过任务收尾: {self.check_result}")
            return

        self.task_info.begin_user_history_capture(
            self.script_info,
            self.cur_user_item,
            failed=bool(self.cur_user_item.log_record)
            and not (self.run_book["Annihilation"] and self.run_book["Routine"])
            and not self.stopped_manually,
        )

        started_at = time.monotonic()

        logger.info("MAA 收尾: 停止日志监控")
        await self.maa_log_monitor.stop()
        logger.info("MAA 收尾: 停止 MAA 进程")
        # 任务收尾时 MAA 多半还在跑任务, 发关闭消息会弹「确定要退出吗」把收尾卡住;
        # 需要等 MAA 自己退出去落盘的只有配置会话 (ScriptConfig)。
        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)
        self._remember_pending_update()
        logger.info(f"MAA 收尾: 结束残留 MAA 进程: {self.maa_exe_path}")

        # 中止可能绕过每轮结束后的刷新；正常已刷新时标记为空，不重复请求。
        current_log = self.cur_user_item.log_record.get(self.log_start_time)
        if current_log is not None and self.cur_user_config.Info.IfQuickConfig:
            self._collect_cultivate_archive(
                "".join(current_log.content), finalizing=True
            )
        await self._finish_cultivate_round()

        logger.info("MAA 收尾: 回写 MAA 配置")
        await agree_bilibili(self.maa_tasks_path, False)

        # 是否成功提前判定：ExitEmulator 模式随后就关闭模拟器，失败画面的
        # 补截必须赶在关模拟器之前
        if_success = self.run_book["Annihilation"] and self.run_book["Routine"]

        # 失败画面：失败尝试路径已在关模拟器前留下的优先；否则现在取
        # （如总时限中止，模拟器此时仍开着）。成功轮不取，手动停止只保留已有图。
        failure_shot: Path | None = self._failure_shot
        if not if_success and failure_shot is None and not self.stopped_manually:
            failure_shot = await self._take_failure_shot()

        if self.script_config.Run.TaskTransitionMethod == "ExitEmulator":
            logger.info("用户任务结束, 关闭模拟器")
            await close_emulator(self)

        await self.run_user_scripts_after()

        if self.maa_root_path is not None:
            await asyncio.to_thread(
                restore_depot_cache,
                self.maa_root_path,
                depot_cache_snapshot_dir(self.script_info.script_id),
            )

        history_records = []
        if_six_star = False
        for t, log_item in self.cur_user_item.iter_history_logs():
            if log_item.status == "MAA 正常运行中" or (
                self.stopped_manually
                and log_item is self.cur_user_log
                and log_item.status == "未开始监看日志"
            ):
                log_item.status = "任务被用户手动中止"
            data = {}
            try:
                parsed, six_star = log_statistics.parse_maa_statistics(log_item.content)
                if_six_star = if_six_star or six_star
                data = {
                    key: {
                        "kind": (
                            "counter"
                            if key in {"recruit_statistics", "drop_statistics"}
                            else "snapshot"
                        ),
                        "value": value,
                    }
                    for key, value in parsed.items()
                }
            except Exception as error:
                diagnostic = f"MAA 统计解析失败：{error}"
                logger.opt(exception=True).warning(diagnostic)
                log_item.content.append(f"\n{diagnostic}\n")
            history_records.append(
                HistoryWrite(
                    time=t.astimezone(_utils_constants.UTC4),
                    username=self.cur_user_item.name,
                    script_name=self.script_info.name,
                    status="success"
                    if log_item.status == "Success!"
                    else "cancelled"
                    if self.stopped_manually
                    and log_item is self.cur_user_log
                    and log_item.status == "任务被用户手动中止"
                    else "error",
                    message=log_item.status,
                    logs="".join(log_item.content),
                    data=data,
                )
            )

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
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["maa_result"] = (
            "代理任务全部完成"
            if (self.run_book["Annihilation"] and self.run_book["Routine"])
            else self.cur_user_item.result
        )
        # 培养步骤以 MAA 成功日志为准，练度刷新延迟也不漏掉本轮的阶段结果。
        cultivate_progress = log_statistics.parse_cultivate_progress(
            line
            for _, log_item in self.cur_user_item.iter_history_logs()
            for line in log_item.content
        )
        progress_lines = list(cultivate_progress)
        if (
            self.cur_user_config.Info.IfQuickConfig
            and self.cur_user_config.Task.IfCultivate
        ):
            try:
                raw_targets = json.loads(self.cur_user_config.Task.CultivateTargets)
            except (TypeError, ValueError):
                raw_targets = None
            if isinstance(raw_targets, list):
                targets = parse_cultivate_targets(raw_targets)
                remaining = sum(len(target.goals) for target in targets)
                suffix = (
                    "（练度未同步）"
                    if targets and not self._cultivate_progress_synced
                    else ""
                )
                progress_lines.append(
                    f"剩余：{len(targets)} 名干员，{remaining} 个目标{suffix}"
                )
        if progress_lines:
            statistics["cultivate_progress"] = "；".join(progress_lines)
        # 本轮有干员达成养成目标时随统计报告告知用户（目标消失可查）
        if self._cultivate_achievement_summary:
            statistics["cultivate_achievement"] = "、".join(
                self._cultivate_achievement_summary
            )

        success_symbol = "√" if if_success else "X"

        # 任务被中止时，只要日志中已经完成过体力任务，也应发送掉落统计；
        # 失败轮取到现场画面时同样发送——登录失败这类开局即败的轮次，用户
        # 只能靠图看到卡在哪，不能因为没跑过体力就把现场吞掉。
        images: list[NotificationImage] = []
        if not if_success and failure_shot is not None:
            try:
                loaded = await prepare_screenshot_images(
                    [(self.cur_user_item.name, failure_shot)],
                    # ID 带用户序号：manager 汇总拼接各用户的图，前缀不唯一
                    # 会让邮件里同名 cid 互相覆盖
                    image_id_prefix=f"maa{self.script_info.current_index}",
                )
                images = [image for _, image in loaded]
                # 模板的「失败截图」块在这里组装；payload 走展平后的 images
                statistics["screenshots"] = screenshot_entries(loaded)
                # 供 manager 汇总「代理结果」收集（MaaFW 同款）
                self.report_image_pairs = list(loaded)
            except Exception as e:
                logger.warning(f"失败画面转码失败，通知不带图: {e}")
                images = []
        if self.run_book["Annihilation"] and self.run_book["Routine"]:
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

            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
        else:
            logger.warning(f"用户 {self.cur_user_uid} 的自动代理任务未完成")
            self.cur_user_item.status = "异常"

        if failure_shot is not None and history_records:
            # 原图还供上游诊断与问题包使用，归档只复制，不接管源文件。
            history_records[-1].attachments.append(
                HistoryAttachmentInput(
                    path=failure_shot,
                    kind="image",
                    role="failure_screenshot",
                    display_name="失败截图",
                    archive_mode="copy",
                )
            )
        await self.task_info.save_user_history(
            history_records,
            script=self.script_info,
            user=self.cur_user_item,
            log_warning=logger.opt(exception=True).warning,
        )

        if self.run_book["Annihilation"] and self.run_book["Routine"]:
            await Notify.send_notice(
                LocalNotice(
                    title="成功完成一个自动代理任务！",
                    message=f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                    ticker=f"已完成 {self.cur_user_item.name} 的自动代理任务",
                    duration_seconds=3,
                )
            )

        should_send_statistics = (
            if_success
            or bool(images)
            or bool(cultivate_progress)
            or _has_completed_sanity_task(
                [item for _, item in self.cur_user_item.iter_history_logs()]
            )
        )
        if should_send_statistics:
            try:
                await Notify.push_statistics_report(
                    payload=_format_maa.build_statistics_payload(
                        title=f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的自动代理统计报告",
                        message=statistics,
                        images=images,
                    ),
                    user_config=self.cur_user_config,
                    task_info=self.task_info,
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
                logger.info(
                    f"开始推送通知, 模式: 公招六星, 标题: 喜报: 用户 {self.cur_user_item.name} 公招出六星啦！"
                )
                await Notify.dispatch_task_notification(
                    _format_maa.build_recruitment_payload(
                        title=f"喜报: 用户 {self.cur_user_item.name} 公招出六星啦！",
                        message={"user_name": self.cur_user_item.name},
                    ),
                    Notify.recruitment_targets(self.cur_user_config),
                    task_info=self.task_info,
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

        logger.info(f"MAA 任务收尾完成 - 用时: {time.monotonic() - started_at:.3f}秒")

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"自动代理任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"自动代理任务出现异常: {e}"),
        )
