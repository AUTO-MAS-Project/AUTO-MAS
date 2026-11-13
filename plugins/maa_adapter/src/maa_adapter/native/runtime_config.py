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


from copy import deepcopy
from pathlib import Path

from auto_mas_core.host.core_notify_task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from auto_mas_core.host.core_notify_task_content import (
    screenshot_entries as screenshot_entries,
)
from auto_mas_core.host.utils import get_logger
from auto_mas_core.host.utils import io as _utils_io

from maa_adapter.constants import _MAA_CULTIVATE_TASK_NAME
from maa_adapter.native.presets import (
    canonical_maa_task_identity,
    get_maa_base_preset,
    maa_task_identity,
)

logger = get_logger("MAA")


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


# 识别数据档案文件名（MAA 原生格式透传）。方案决策 31 管的是归属：档案按写入时的
# cur_user_uid 归属，安装目录那份 DepotData 是 MAA 自己的工作缓存，不属于查询链——
# 查询、缺口判定与养成注入只读档案。只有 overlay 层（开启覆写常规配置）才在启动前
# 把档案覆写进安装目录，且覆写前键级存底、任务结束还原（见 depot_cache_snapshot_dir）。
_MAA_DEPOT_ARCHIVE_NAME = "DepotData.json"


_MAA_OPER_BOX_ARCHIVE_NAME = "OperBoxData.json"


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
        doc = _utils_io.read_dict_file(path)
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
    baseline_queue: object,
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
        """取得上游任务项的公开身份，供合并任务队列时匹配相同任务。"""
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
        assert isinstance(archive, dict) and isinstance(baseline, dict)
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


_MAA_DEPOT_QUOTA_KEYS = (
    ("UseMedicine", "MedicineCount"),
    ("UseStone", "StoneCount"),
)
