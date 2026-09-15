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
#   You should have received a copy of the GNU Affero General Public
#   License along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MaaEnd 配置备份归档：MAS 用户配置 / 脚本原生配置，两类独立快照。

备份时机（MAS「动手前」，此时 MaaEnd 尚未被触碰）：

- 任务 / 配置会话启动（manager ``prepare``）：``native`` 归档 MaaEnd 安装
  目录 ``config/`` 当前状态（整目录）——安装配置物理上跨用户共享，只在
  任务级归档一次；
- 运行 / 配置会话下发前（AutoProxy / ScriptConfig 的 ``set_maaend``）：
  ``mas`` 归档本轮下发源（脚本态共享 Default 目录、用户态当前用户目录，
  按 owner 各归各的；会话保存会覆盖它）；
- 编辑界面进入 / 退出（前端 ensure）：进入时归档 ``native``（MAS 触碰前
  原始态）、退出时归档 ``mas``（编辑会话包络的 MAS 侧终态）。

``mas`` 池的内容 = ConfigFile 整目录 + **快速配置覆盖层字段侧车**：页面
任务配置卡片（快速配置）的字段存在 MAS 用户配置里、运行时才覆盖进
mxu-MaaEnd.json 的任务开关与选项，不在 ConfigFile 中——侧车让「MAS 用户
配置备份」真正覆盖用户在 MAS 页面配的东西，恢复时随文件一起回滚并回填
表单（对齐 ok-ww 覆盖层模式）。MAS 配置目录 owner 由用户当前的
``Info.Mode`` 决定（脚本=Default 共享、用户=独立目录、直控=无 MAS 配置），
解析逻辑见 ``restore_service``。时间戳快照、指纹去重、保留清理与整目录
恢复的通用逻辑由公共模块 ``app.utils.config_archive`` 提供（默认每池保留
10 份），本模块只保留 MaaEnd 特有的 owner 目录布局、覆盖层侧车、恢复
语义（恢复前强制归档当前）与归档目录布局。
"""

import json
from pathlib import Path

from app.utils import get_logger
from app.utils.config_archive import (
    OVERLAY_SIDECAR_NAME,
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
    mask_account,
    read_overlay_sidecar,
    restore_dir,
)
from app.utils.constants import (
    MAAEND_AUTO_COLLECT_TASK,
    MAAEND_DELIVERY_TASK,
    MAAEND_TASK_GROUPS,
    MAAEND_TASKS,
)

logger = get_logger("MaaEnd 配置备份")


def backup_root(script_id: str) -> Path:
    """某脚本的备份归档根目录（MAS 用户池用）：``data/{script_id}/MaaEndBackups``。"""

    return Path.cwd() / "data" / script_id / "MaaEndBackups"


def project_backup_root() -> Path:
    """MaaEnd 备份的项目级根目录：``data/MaaEndBackups``。

    native（脚本原生配置）池挂在这里而不是脚本目录下——同一份物理安装
    可被多个脚本实例引用，原生备份按物理配置根指纹分桶、跨脚本共享、
    不随脚本删除（mas 用户池仍按脚本，见 :func:`mas_backup_root`）。
    """

    return Path.cwd() / "data" / "MaaEndBackups"


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/MaaEndBackups/mas/{user_id}``。

    **恒按用户分桶**——备份内容（ConfigFile 快照 + 快速配置覆盖层侧车）
    的侧车是用户级的，按用户分桶才能保证每个用户只看到、只恢复自己的
    备份。池与恢复目标解耦：脚本态用户的下发源是共享 Default 目录，但
    其池仍是 ``mas/{user_id}``。
    """

    return backup_root(script_id) / "mas" / user_id


def native_backup_root(config_path: str | Path) -> Path:
    """MaaEnd 原生配置的项目级归档目录：``data/MaaEndBackups/native/{key}``。

    ``key`` 是物理配置根的指纹（:func:`config_root_key`）——同一份物理
    配置无论被哪个脚本引用都归同一个池；跨脚本共享、不随脚本删除。
    """

    return project_backup_root() / "native" / config_root_key(config_path)


def mas_config_dir(script_id: str, owner: str) -> Path:
    """MAS 配置目录：``data/{script_id}/{owner}/ConfigFile``。"""

    return Path.cwd() / "data" / script_id / owner / "ConfigFile"


# ══════════════════ MAS 配置（池按用户，目标路径按 owner） ══════════════════

_OVERLAY_INFO_KEYS = (
    "Mode",
    "Id",
    "IfQuickConfig",
    "SanityMode",
)
"""MAS 页面基础字段（UserData.Info）：来源仅预览，账号/快速配置/理智模式参与回填"""

_OVERLAY_SANITY_KEYS = (
    "SanityTaskType",
    "OperatorProgression",
    "WeaponProgression",
    "CrisisDrills",
    "RewardsSetOption",
    "AutoEssenceSpecifiedLocation",
    "AutoEssenceMenu",
    "AutoEssenceTargetWeapons",
)
"""理智任务选项字段（UserData.Task，快速配置开启时运行时写入任务选项）"""

_OVERLAY_TASK_KEYS = (
    *(f"If{task}" for task in MAAEND_TASKS),
    "IfSeizeDeliveryJobs",
    "SeizeDeliveryJobsReward",
    "SeizeDeliveryJobsCommissionSource",
    "IfAutoCollect",
    "AutoCollectMode",
    "AutoCollectRoutes",
    "AutoCollectCommonRoutes",
    "DailyOnceTasks",
    *_OVERLAY_SANITY_KEYS,
)
"""快速配置覆盖层字段（UserData.Task，运行时覆盖进 mxu-MaaEnd.json 任务开关与选项）"""

_OVERLAY_KEY_GROUPS = {"Info": _OVERLAY_INFO_KEYS, "Task": _OVERLAY_TASK_KEYS}
"""侧车字段的配置段归属（两组键名无交集，侧车内平铺存储）"""

_OVERLAY_KEY_GROUP = {
    key: group for group, keys in _OVERLAY_KEY_GROUPS.items() for key in keys
}

_OVERLAY_PREVIEW_ONLY_KEYS = {"Mode"}
"""仅预览不回填的字段：配置文件来源决定恢复目标目录，恢复时以当前值为准"""

_TASK_LABELS = {
    name: zh for group in MAAEND_TASK_GROUPS.values() for name, zh in group["tasks"]
}
_TASK_LABELS[MAAEND_DELIVERY_TASK] = "抢委托送货"
_TASK_LABELS[MAAEND_AUTO_COLLECT_TASK] = "自动采集"
# MaaEnd 本体 interface 的其余任务（源码 zh_cn 词表，emoji 去除后固化；
# 上游新增任务未收录时预览回退原任务名）
_TASK_LABELS.update(
    {
        "AccountSwitch": "自动切换账号",
        "AeroSalvage": "浮空回收",
        "AutoEssence": "基质刷取",
        "BakerEntry": "会话消息嘴替",
        "BatchAddFriends": "批量添加好友",
        "BatchUseDetector": "批量探测器",
        "ClaimSimulationRewards": "领取模拟空间奖励",
        "Crafting": "简易制作",
        "EssenceFilter": "基质筛选锁定",
        "GearAssembly": "装备制造",
        "GiftOperator": "赠送干员礼物",
        "ImportBluePrints": "一键导入蓝图",
        "IntelArchive": "情报档案库",
        "ItemTransfer": "库存转移",
        "OutpostTrading": "据点交易",
        "ProtocolSpace": "协议空间",
        "PuzzleSolver": "解拼图",
        "ReadAllWiki": "百科已读",
        "RealTimeTask": "实时开荒辅助",
        "ReceiveProdManual": "简制手册领取",
        "SimpleProductionBatch": "批量简易制作",
        "StashBackpack": "存放背包",
        "SwitchTeam": "切换编队",
        "WeaponUpgrade": "升级武器",
        "ZiplineImport": "导入/更新滑索坐标",
    }
)
"""MaaEnd 任务中文名（含独立送货/采集阶段与本体其余任务；不依赖本体运行时）"""

# 快速配置开关覆盖的任务（mas 池「任务启用」罗列行）
_QUICK_CONFIG_TASKS = (*MAAEND_TASKS, MAAEND_DELIVERY_TASK, MAAEND_AUTO_COLLECT_TASK)

_OVERLAY_FIELD_LABELS = {
    "Mode": "配置文件来源",
    "Id": "账号",
    "IfQuickConfig": "快速配置",
    "SanityMode": "理智任务配置模式",
    "IfSeizeDeliveryJobs": "抢委托送货",
    "SeizeDeliveryJobsReward": "送货最低接取价格（万）",
    "SeizeDeliveryJobsCommissionSource": "委托接收点",
    "IfAutoCollect": "自动采集",
    "AutoCollectMode": "采集安排",
    "AutoCollectRoutes": "区域采集路线",
    "AutoCollectCommonRoutes": "通用采集路线",
    "DailyOnceTasks": "每日仅执行一次",
    "SanityTaskType": "理智任务",
    **{f"If{task}": zh for task, zh in _TASK_LABELS.items()},
    # IfSanity 的开关用分组名「理智作战」，与合成的「理智任务」行区分
    "IfSanity": "理智作战",
}
"""侧车字段中文标签（对齐 MaaEnd 用户编辑页词表）"""

_SANITY_TASK_TYPE_LABELS = {
    "OperatorProgression": "干员养成",
    "WeaponProgression": "武器养成",
    "CrisisDrills": "危境预演",
    "Essence": "基质刷取",
}
_SANITY_OPTION_LABELS = {
    "OperatorEXP": "干员经验",
    "Promotions": "干员进阶",
    "T-Creds": "钱币收集",
    "SkillUp": "技能提升",
    "WeaponEXP": "武器经验",
    "WeaponTune": "武器进阶",
    "AdvancedProgression1": "高阶培养 I",
    "AdvancedProgression2": "高阶培养 II",
    "AdvancedProgression3": "高阶培养 III",
    "AdvancedProgression4": "高阶培养 IV",
    "AdvancedProgression5": "高阶培养 V",
}
_REWARDS_SET_LABELS = {"RewardsSetA": "奖励组 A", "RewardsSetB": "奖励组 B"}
_COMMISSION_SOURCE_LABELS = {
    "Unlimited": "不限",
    "WulingCity": "武陵城",
    "TestArea": "试验园区",
}
_AUTO_COLLECT_MODE_LABELS = {"Distributed": "分散采集", "Concentrated": "集中采集"}
_ESSENCE_MENU_LABELS = {
    "Random": "随机模式",
    "Location": "地区模式",
    "Target": "目标选择",
}
_ESSENCE_LOCATION_LABELS = {
    "VFTheHub": "枢纽区",
    "VFOriginiumSciencePark": "源石研究园",
    "VFOriginLodespring": "矿脉源区",
    "VFPowerPlateau": "供能高地",
    "WLWulingCity": "武陵城区",
    "WLQingboStockade": "清波寨",
    "WLMarkerStone": "首墩",
    "WLTestArea": "试验园区",
    "WLSwordVaultDale": "藏剑谷",
    "WLYinglungPass": "应龙关",
    "WLNorthWulingExclusionZone": "北部禁区",
    "WLSnowyForest": "雪松林",
}
"""枚举字段取值中文词表（源码 zh_cn 词表固化，与 MXU GUI 显示一致、不依赖
本体运行时；未知取值显示原文）"""

_SANITY_CURRENT_FIELD = {
    "OperatorProgression": "OperatorProgression",
    "WeaponProgression": "WeaponProgression",
    "CrisisDrills": "CrisisDrills",
}
"""理智任务类型 → 当前取值所在的 Task 字段（Essence 走基质选项单独合成）"""

# 奖励组选项仅对带 rewards 标记的任务取值有意义（对齐编辑页显隐逻辑）
_REWARDS_OPTION_REWARDS_FLAG = {
    "OperatorEXP": True,
    "Promotions": True,
    "T-Creds": False,
    "SkillUp": True,
    "WeaponEXP": False,
    "WeaponTune": True,
}


def read_overlay_values(config) -> dict:
    """读取配置对象的快速配置覆盖层字段（鸭子类型，仅需 ``get(group, key)``）。

    值为 ``None``（配置项不存在）的键不纳入侧车。
    """

    values: dict = {}
    for group, keys in _OVERLAY_KEY_GROUPS.items():
        for key in keys:
            if (value := config.get(group, key)) is not None:
                values[key] = value
    return values


def group_overlay(overlay: dict) -> dict[str, dict]:
    """把平铺的侧车字段按配置段分组（恢复回填 UserData 用）。

    仅预览字段（配置文件来源等）不回填：恢复目标目录由当前模式决定，
    回填旧值会静默改变脚本态/用户态/直控态。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS:
            continue
        grouped.setdefault(_OVERLAY_KEY_GROUP.get(key, "Task"), {})[key] = value
    return grouped


def collect_mas_files(
    mas_dir: str | Path, overlay: dict | None = None
) -> dict[str, "Path | str"]:
    """收集 MAS 配置目录文件集 + 快速配置覆盖层字段侧车（相对键 → 路径/内存内容）。

    侧车为内存 JSON（:func:`archive_files` 支持内存内容），免临时文件；
    目录缺失或为空时仅归档侧车——用户级目录要等首次运行/播种物化，页面
    字段不能因目录未建而一起丢（否则从未运行的用户切来源、改配置后退出，
    mas 池永远为空）。
    """

    mas_dir = Path(mas_dir)
    files: dict[str, "Path | str"] = {}
    if mas_dir.is_dir():
        files.update(dir_files(mas_dir))
    if overlay:
        files[OVERLAY_SIDECAR_NAME] = json.dumps(overlay, ensure_ascii=False, indent=2)
    return files


def archive_mas_backup(
    script_id: str,
    user_id: str,
    mas_dir: Path,
    overlay: dict | None = None,
    force: bool = False,
) -> Path | None:
    """归档 MAS 配置整份 + 快速配置覆盖层字段侧车到用户池（指纹去重，无变化跳过）。

    ``user_id`` 是池归属（恒按用户分桶，见 :func:`mas_backup_root`）；
    ``mas_dir`` 是归档/恢复目标路径，由调用方按 owner 解析（脚本态共享
    Default 目录、用户态独立目录）——池与目标解耦。
    侧车参与指纹：只改表单覆盖层字段、未动 ConfigFile 时同样新建归档
    （内存 JSON 直接入档，免临时文件）。
    目录不存在或为空时无可恢复内容，返回 ``None``；``force=True`` 恢复前
    存底（不清理历史条目；内容与最新份一致时同样跳过——当前配置已存放在
    该份备份中，误恢复可从它找回）。
    """

    files = collect_mas_files(mas_dir, overlay)
    if not files:
        return None
    dest = archive_files(files, mas_backup_root(script_id, user_id), force=force)
    if dest is None:
        logger.info("MAS 配置无变化，跳过归档")
        return None
    logger.info(f"用户 {user_id} 的 MAS 配置已归档: {dest.name}")
    return dest


def list_mas_backups(script_id: str, user_id: str) -> list[str]:
    """用户池的全部归档时间戳（倒序，最新在前）。"""

    return list_times(mas_backup_root(script_id, user_id))


def get_mas_backup_dir(script_id: str, user_id: str, ts: str) -> Path | None:
    """取用户池指定时间戳的归档目录；不存在返回 None。"""

    return get_backup_dir(mas_backup_root(script_id, user_id), ts)


def restore_mas_backup(
    script_id: str,
    user_id: str,
    ts: str,
    mas_dir: Path,
    overlay: dict | None = None,
) -> dict | None:
    """把用户池归档恢复到 MAS 配置目录（恢复前自动归档当前，误恢复可找回）。

    ``user_id`` 是池归属（与归档一致按用户分桶）；``mas_dir`` 是恢复目标
    路径，由调用方按 owner 解析（脚本态共享 Default 目录、用户态独立目
    录）。``overlay`` 为当前用户的覆盖层字段，随恢复前存底一起归档。
    返回该备份的覆盖层字段（供调用方回填 MAS 用户配置；旧版备份无侧车
    返回 ``None``），侧车文件随即从目录中分离删除，不留在 ConfigFile 里。
    """

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    mas_dir = Path(mas_dir)
    # 恢复前存底不设目录条件：目标目录缺失/为空时页面字段（overlay）仍需
    # 存底——恢复会清空目标，不存底就丢；无可归档内容由 archive 自判
    archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay, force=True)
    restore_dir(mas_backup_root(script_id, user_id), ts, mas_dir)
    restored_overlay = read_overlay_sidecar(mas_dir)
    if restored_overlay is not None:
        (mas_dir / OVERLAY_SIDECAR_NAME).unlink(missing_ok=True)
    logger.info(f"用户 {user_id} 的 MAS 配置已恢复备份 {ts}")
    return restored_overlay


def archive_mas_runtime_backup(
    script_id: str,
    user_id: str,
    mas_dir: Path,
    overlay: dict | None = None,
) -> None:
    """运行 / 配置会话下发前归档 MAS 配置（下发源）到用户池。

    会话保存会覆盖它，下发前存底；指纹去重，失败只记日志，绝不中止随后
    的运行或会话（归档是现场保护，不是前置条件）。
    ``user_id`` 是池归属；``mas_dir`` 是下发源目录，由调用方按当前用户
    owner 解析（脚本态=Default 共享目录、用户态=独立目录；直控用户无 MAS
    配置，调用方不调用本函数）。native 池与此处无关：原生配置跨用户
    共享，由 manager ``prepare`` 在任务级一次性归档
    （见 :func:`archive_native_backup`）。
    """

    archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay)


# ══════════════════ 脚本原生配置（安装目录 config/ 整目录） ══════════════════


def collect_native_files(config_path: str | Path) -> dict[str, Path]:
    """收集 MaaEnd 安装目录 config/ 文件集（相对键 → 当前路径）。

    目录不存在或为空时无可归档内容，返回空 dict。
    """

    config_path = Path(config_path)
    if not config_path.is_dir() or not any(config_path.iterdir()):
        return {}
    return dir_files(config_path)


def archive_native_backup(config_path: Path, force: bool = False) -> Path | None:
    """归档 MaaEnd 安装目录 config/ 当前状态（整目录）。

    归档落到该项目级池（按物理配置根指纹分桶），与脚本实例解耦。
    目录不存在或为空时无可归档内容，返回 ``None``。
    """

    files = collect_native_files(config_path)
    if not files:
        return None
    dest = archive_files(files, native_backup_root(config_path), force=force)
    if dest is None:
        logger.info("MaaEnd 原生配置无变化，跳过归档")
        return None
    logger.info(f"MaaEnd 原生配置已归档: {dest.name}")
    return dest


def list_native_backups(config_path: str | Path) -> list[str]:
    """MaaEnd 原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(config_path))


def get_native_backup_dir(config_path: str | Path, ts: str) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(config_path), ts)


def restore_native_backup(config_path: Path, ts: str) -> None:
    """把归档恢复到 MaaEnd 安装目录 config/（恢复前自动归档当前，误恢复可找回）。

    整目录替换（MaaEnd 原生配置恒为目录，无 Folder/File 双模式）。
    """

    backup_dir = get_native_backup_dir(config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    config_path = Path(config_path)
    # 恢复前强制归档当前——「恢复前的配置」在列表里有明确的时间戳条目
    archive_native_backup(config_path, force=True)
    restore_dir(native_backup_root(config_path), ts, config_path)
    logger.info(f"MaaEnd 原生配置已恢复备份 {ts}")


# ══════════════════ 备份预览摘要 ══════════════════

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""

NATIVE_CONFIG_FILE = "mxu-MaaEnd.json"
"""MaaEnd 原生配置核心文件（预览白名单；恢复仍整目录写回）"""


def _summary_value(value) -> str:
    """摘要标量值转展示文本（布尔转是否、超长截断）。"""

    if isinstance(value, bool):
        return "是" if value else "否"
    text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def _select_instance(config: dict) -> dict | None:
    """按 MXU 语义选择配置实例（AUTO-MAS 实例优先，其次最近活跃）。"""

    instances = config.get("instances")
    if not isinstance(instances, list):
        return None
    last_active = config.get("lastActiveInstanceId")
    for instance in instances:
        if isinstance(instance, dict) and (
            instance.get("id") == "automas" or instance.get("name") == "AUTO-MAS"
        ):
            return instance
    for instance in instances:
        if isinstance(instance, dict) and instance.get("id") == last_active:
            return instance
    for instance in instances:
        if isinstance(instance, dict):
            return instance
    return None


def _native_task_display_name(task: dict) -> str:
    """TaskQueue 任务条目 → 展示名（customName → MAS 词表 → 原任务名）。

    MAS 词表与 mas 池快速配置开关共用（同口径规则：同一任务概念在两池
    同标签）；词表外的任务（上游新增/用户自建）回退 customName 或原名。
    """

    name = str(task.get("taskName", ""))
    custom = task.get("customName")
    if isinstance(custom, str) and custom.strip():
        return custom
    return _TASK_LABELS.get(name, name)


def _native_summary_rows(data: dict) -> list[dict]:
    """mxu-MaaEnd.json 的摘要行（实例 + 任务启用罗列 + 配置内容表单）。

    预览的语义是「这份备份的 MaaEnd 配置是什么样」：任务启用**罗列**启用了
    哪些（与 mas 池任务启用行同词表同格式），配置内容表单展示理智/送货/
    采集任务的具体取值（源码固化 zh_cn 词表，与 MXU GUI 显示一致）。
    """

    instance = _select_instance(data)
    if instance is None:
        return []
    rows: list[dict] = []
    instance_name = instance.get("customName") or instance.get("name") or "AUTO-MAS"
    rows.append({"key": "实例", "value": _summary_value(instance_name)})

    tasks = [
        task
        for task in instance.get("tasks") or []
        if isinstance(task, dict)
        and not str(task.get("taskName", "")).startswith("__MXU_")
    ]
    enabled = [
        _native_task_display_name(task) for task in tasks if task.get("enabled", False)
    ]
    rows.append({"key": "已启用任务", "value": "、".join(enabled) or "无"})
    rows.extend(_native_option_rows(tasks))
    return rows


def _option_case(option: object) -> str | None:
    """select 型选项值（caseName）。"""

    if not isinstance(option, dict):
        return None
    case = option.get("caseName")
    return str(case) if case is not None else None


def _option_cases(option: object) -> list[str]:
    """checkbox 型选项值（caseNames 列表）。"""

    if not isinstance(option, dict):
        return []
    cases = option.get("caseNames")
    if not isinstance(cases, list):
        return []
    return [str(item) for item in cases if str(item)]


def _native_option_rows(tasks: list[dict]) -> list[dict]:
    """从任务 optionValues 提取配置内容表单行（理智/送货/采集的具体取值）。

    取值文本用源码固化的 zh_cn 词表翻译（与 MXU GUI 显示一致、不依赖本体
    运行时）；仅展示存在取值的行。
    """

    by_name = {str(task.get("taskName")): task for task in tasks}
    rows: list[dict] = []

    protocol = by_name.get("ProtocolSpace")
    if isinstance(protocol, dict):
        options = protocol.get("optionValues")
        options = options if isinstance(options, dict) else {}
        tab = _option_case(options.get("ProtocolSpaceTab"))
        if tab:
            rows.append(
                {"key": "理智任务", "value": _SANITY_TASK_TYPE_LABELS.get(tab, tab)}
            )
        for field, label in (
            ("OperatorProgression", "干员养成任务"),
            ("WeaponProgression", "武器养成任务"),
            ("CrisisDrills", "危境预演任务"),
        ):
            value = _option_case(options.get(field))
            if value:
                rows.append(
                    {"key": label, "value": _SANITY_OPTION_LABELS.get(value, value)}
                )

    essence = by_name.get("AutoEssence")
    if isinstance(essence, dict):
        options = essence.get("optionValues")
        options = options if isinstance(options, dict) else {}
        menu = _option_case(options.get("AutoEssenceMenu"))
        if menu:
            rows.append(
                {"key": "基质刷取模式", "value": _ESSENCE_MENU_LABELS.get(menu, menu)}
            )
        location = _option_case(options.get("AutoEssenceSelectLocation")) or (
            _option_case(options.get("AutoEssenceChooseLocation"))
        )
        if location:
            rows.append(
                {
                    "key": "基质地点",
                    "value": _ESSENCE_LOCATION_LABELS.get(location, location),
                }
            )
        weapons = [
            case
            for option_name, option in options.items()
            if isinstance(option, dict) and option_name.startswith("AutoEssenceWeapons")
            for case in _option_cases(option)
        ]
        if weapons:
            rows.append({"key": "目标武器", "value": f"已选 {len(weapons)} 把"})

    delivery = by_name.get(MAAEND_DELIVERY_TASK)
    if isinstance(delivery, dict):
        options = delivery.get("optionValues")
        options = options if isinstance(options, dict) else {}
        source = _option_case(options.get("SeizeDeliveryJobsCommissionSource"))
        if source:
            rows.append(
                {
                    "key": "委托接收点",
                    "value": _COMMISSION_SOURCE_LABELS.get(source, source),
                }
            )
        reward_option = options.get("SeizeDeliveryJobsReward")
        reward_values = (
            reward_option.get("values") if isinstance(reward_option, dict) else None
        )
        reward = (
            reward_values.get("Reward") if isinstance(reward_values, dict) else None
        )
        if reward is not None:
            rows.append({"key": "送货最低接取价格（万）", "value": str(reward)})

    collect = by_name.get(MAAEND_AUTO_COLLECT_TASK)
    if isinstance(collect, dict):
        options = collect.get("optionValues")
        options = options if isinstance(options, dict) else {}
        for field, label in (
            ("AutoCollectRoutes", "区域采集路线"),
            ("AutoCollectCommonRoutes", "通用采集路线"),
        ):
            cases = _option_cases(options.get(field))
            if cases:
                rows.append({"key": label, "value": f"已选 {len(cases)} 条"})
    return rows


def build_backup_file_summary(backup_dir: Path) -> list[dict]:
    """备份目录内 MaaEnd 配置文件的摘要列表（预览用，纯读）。

    每个文件一条 ``{name, label, summary}``。只保留预览白名单内的文件，
    非 JSON / 坏 JSON / 无可展示字段的文件跳过（恢复时仍会随备份完整
    写回）。
    """

    files: list[dict] = []
    for rel in sorted(dir_files(backup_dir)):
        if "/" in rel or rel != NATIVE_CONFIG_FILE:
            continue
        try:
            data = json.loads((backup_dir / rel).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        rows = _native_summary_rows(data)
        if not rows:  # 无可展示字段的文件不进预览
            continue
        files.append({"name": rel, "label": "MaaEnd 配置", "summary": rows})
    return files


def _overlay_value(key: str, value) -> str:
    """覆盖层字段值转展示文本（枚举词表、账号脱敏、布尔转是否、超长截断）。"""

    if key == "Id":
        return mask_account(value)  # 账号脱敏展示；侧车原值仍完整保存（恢复需要）
    if isinstance(value, bool):
        return "是" if value else "否"
    enum = {
        "SeizeDeliveryJobsCommissionSource": _COMMISSION_SOURCE_LABELS,
        "AutoCollectMode": _AUTO_COLLECT_MODE_LABELS,
        "SanityTaskType": _SANITY_TASK_TYPE_LABELS,
        "RewardsSetOption": _REWARDS_SET_LABELS,
        "OperatorProgression": _SANITY_OPTION_LABELS,
        "WeaponProgression": _SANITY_OPTION_LABELS,
        "CrisisDrills": _SANITY_OPTION_LABELS,
    }.get(key)
    if enum is not None:
        text = enum.get(str(value), str(value))
    elif key == "SanityMode":
        # 计划表 UID 无意义，restore_service 会尽力补计划名称
        text = "固定" if str(value) == "Fixed" else "计划表"
    else:
        text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def _sanity_rows(overlay: dict) -> list[dict]:
    """理智任务详情行（对齐编辑页字段，全类型已存配置都记录）。

    理智任务行是当前选中的类型（运行时生效的那份）；干员养成/武器养成/
    危境预演/基质各行是各类型已存的配置（切换理智任务类型时即生效）。
    基质刷取模式/地点的取值文本来自源码固化的 zh_cn 词表（与 MXU GUI
    显示一致、不依赖本体运行时）。
    """

    rows: list[dict] = []
    if "SanityTaskType" in overlay:
        task_type = str(overlay["SanityTaskType"])
        rows.append(
            {
                "key": "理智任务",
                "value": _SANITY_TASK_TYPE_LABELS.get(task_type, task_type),
            }
        )
    if "AutoEssenceMenu" in overlay:
        menu = str(overlay["AutoEssenceMenu"])
        rows.append(
            {"key": "基质刷取模式", "value": _ESSENCE_MENU_LABELS.get(menu, menu)}
        )
    location = overlay.get("AutoEssenceSpecifiedLocation")
    if location:
        rows.append(
            {
                "key": "基质地点",
                "value": _ESSENCE_LOCATION_LABELS.get(str(location), str(location)),
            }
        )
    weapons = overlay.get("AutoEssenceTargetWeapons")
    if isinstance(weapons, list) and weapons:
        rows.append({"key": "目标武器", "value": f"已选 {len(weapons)} 把"})
    for field, label in (
        ("OperatorProgression", "干员养成任务"),
        ("WeaponProgression", "武器养成任务"),
        ("CrisisDrills", "危境预演任务"),
    ):
        if field in overlay:
            rows.append({"key": label, "value": _overlay_value(field, overlay[field])})
    if _rewards_set_visible(overlay):
        rows.append(
            {
                "key": "奖励组",
                "value": _overlay_value(
                    "RewardsSetOption", overlay.get("RewardsSetOption")
                ),
            }
        )
    return rows


def _rewards_set_visible(overlay: dict) -> bool:
    """奖励组选项仅在当前任务取值带奖励组时显示（对齐编辑页显隐逻辑）。"""

    task_type = str(overlay.get("SanityTaskType", "OperatorProgression"))
    if task_type == "OperatorProgression":
        current = str(overlay.get("OperatorProgression", ""))
    elif task_type == "WeaponProgression":
        current = str(overlay.get("WeaponProgression", ""))
    else:
        return False
    return _REWARDS_OPTION_REWARDS_FLAG.get(current, False)


def _route_count_text(overlay: dict, key: str, options: tuple | None) -> str:
    """采集路线显示为已选数量（路线名列表过长，逐条展示无阅读价值）。

    选项总数由调用方从本体资源派生（随版本动态变化）；不可用时退化为
    只显示已选数量。
    """

    routes = overlay.get(key)
    selected = len(routes) if isinstance(routes, list) else 0
    if not options:
        return f"已选 {selected} 条"
    return f"已选 {selected} / {len(options)} 条"


def build_overlay_summary(
    overlay: dict, route_options: dict[str, tuple] | None = None
) -> list[dict]:
    """覆盖层字段侧车的分区预览（mas 池预览用，纯读）。

    ``route_options`` 为自动采集两类路线的当前可选值（按 configKey 索引，
    从本体资源动态派生），用于展示「已选 X / Y 条」的分母；缺省（资源
    不可读）退化为只显示已选数量。

    返回三个分区（前端按文件集逐区渲染）：**任务启用**用罗列行（启用了
    哪些），**配置内容**用表单行（具体刷本等细节），二者按**概念是否有
    MaaEnd GUI 对应**归入 MaaEnd 对应区；MaaEnd GUI 无对应概念的调度类
    字段（配置文件来源/快速配置/每日仅执行一次）归 MAS 独有区。

    快速配置关闭时，覆盖层字段运行时不生效（任务启用以 mxu 配置原值为
    准），任务启用与配置内容区随门控隐藏（账号除外——登录与账号切换
    不受快速配置影响）。分区无行时整体省略（旧版备份可能只有部分字段）。
    """

    quick_config_on = bool(overlay.get("IfQuickConfig"))
    sections: list[dict] = []

    mas_rows: list[dict] = []
    if "Mode" in overlay:
        mas_rows.append(
            {"key": "配置文件来源", "value": _overlay_value("Mode", overlay["Mode"])}
        )
    if "IfQuickConfig" in overlay:
        mas_rows.append(
            {
                "key": "快速配置",
                "value": _overlay_value("IfQuickConfig", overlay["IfQuickConfig"]),
            }
        )
    if "DailyOnceTasks" in overlay:
        mas_rows.append({"key": "每日仅执行一次", "value": _daily_once_text(overlay)})
    if mas_rows:
        sections.append(
            {"name": "mas-only", "label": "MAS 独有配置", "summary": mas_rows}
        )

    if quick_config_on:
        enabled = [
            _OVERLAY_FIELD_LABELS[f"If{name}"]
            for name in _QUICK_CONFIG_TASKS
            if overlay.get(f"If{name}")
        ]
        sections.append(
            {
                "name": "tasks",
                "label": "任务启用",
                "summary": [{"key": "已启用任务", "value": "、".join(enabled) or "无"}],
            }
        )

    config_rows: list[dict] = []
    if "Id" in overlay:
        config_rows.append(
            {"key": "账号", "value": _overlay_value("Id", overlay["Id"])}
        )
    if quick_config_on:
        if "SanityMode" in overlay:
            config_rows.append(
                {
                    "key": "理智任务配置模式",
                    "value": _overlay_value("SanityMode", overlay["SanityMode"]),
                }
            )
        config_rows.extend(_sanity_rows(overlay))
        if "SeizeDeliveryJobsReward" in overlay:
            config_rows.append(
                {
                    "key": "送货最低接取价格（万）",
                    "value": _overlay_value(
                        "SeizeDeliveryJobsReward", overlay["SeizeDeliveryJobsReward"]
                    ),
                }
            )
        if "SeizeDeliveryJobsCommissionSource" in overlay:
            config_rows.append(
                {
                    "key": "委托接收点",
                    "value": _overlay_value(
                        "SeizeDeliveryJobsCommissionSource",
                        overlay["SeizeDeliveryJobsCommissionSource"],
                    ),
                }
            )
        if "AutoCollectMode" in overlay:
            config_rows.append(
                {
                    "key": "采集安排",
                    "value": _overlay_value(
                        "AutoCollectMode", overlay["AutoCollectMode"]
                    ),
                }
            )
        for field, label in (
            ("AutoCollectRoutes", "区域采集路线"),
            ("AutoCollectCommonRoutes", "通用采集路线"),
        ):
            if field in overlay:
                config_rows.append(
                    {
                        "key": label,
                        "value": _route_count_text(
                            overlay, field, (route_options or {}).get(field)
                        ),
                    }
                )
    if config_rows:
        sections.append({"name": "config", "label": "配置内容", "summary": config_rows})
    return sections


def _daily_once_text(overlay: dict) -> str:
    """每日仅执行一次任务列表 → 中文名顿号串（未知任务名显示原文）。"""

    raw = overlay.get("DailyOnceTasks")
    names: list[str] = []
    if isinstance(raw, list):
        names = [str(item) for item in raw]
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                names = [str(item) for item in parsed]
        except json.JSONDecodeError:
            names = []
    labels = [
        _TASK_LABELS.get(name, _OVERLAY_FIELD_LABELS.get(f"If{name}", name))
        for name in names
        if name
    ]
    joined = "、".join(labels)
    return joined if joined else "无"
