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

"""MAA 配置备份归档：MAS 用户配置 / 脚本原生配置，两类独立快照。

备份时机（MAS「动手前」，此时 MAA 配置尚未被触碰）：

- 任务 / 配置会话启动（manager ``prepare``）：``native`` 归档 MAA 安装
  目录 ``config/`` 当前状态（整目录）——安装配置物理上跨用户共享，只在
  任务级归档一次；下发处按用户归档会把上一轮下发的 MAS 配置误当原生
  内容挤进保留池；
- 运行 / 配置会话下发前（AutoProxy / ScriptConfig 的 ``set_maa``）：
  ``mas`` 归档本轮下发源（脚本态共享 Default 目录、用户态当前用户目录，
  按 owner 各归各的；运行回写与会话保存会覆盖它）；
- 编辑界面进入 / 退出（前端 ensure）：进入时归档 ``native``（MAS 触碰前
  原始态）、退出时归档 ``mas``（编辑会话包络的 MAS 侧终态）。

``mas`` 池的内容 = ConfigFile 整目录 + **页面核心字段侧车**（Info / Task
两段，覆盖 MAS 编辑页全部可配置核心内容）：这些字段运行时注入 gui.json、
  不落盘在 ConfigFile——侧车让「MAS 用户配置备份」与页面认知一致，恢复时
  随文件一起回滚并按段分组回填表单（对齐 ZzzOd / ok-ww 字段回填模式）。
  池恒按用户分桶（``mas/{user_id}``），多用户共享同一份 Default 目录时各自
  持有快照、互不混淆（教训见 config-restore.md §1.1.1）。时间戳快照、指纹
  去重、保留清理与整目录恢复的通用逻辑由公共模块
  ``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
  MAA 特有的目录布局、侧车、恢复语义（恢复前强制归档当前）与归档目录布局。
"""

import json
import tempfile
from pathlib import Path

from app.utils import get_logger
from app.utils.config_archive import (
    archive_dir,
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
    restore_dir,
)
from app.utils.constants import MAA_TASKS, MAA_TASKS_ZH

logger = get_logger("MAA 配置备份")

_MAA_CONFIG_FILES = ("gui.json", "gui.new.json")
"""MAA 原生配置核心文件（预览白名单；恢复仍整目录写回）"""


def backup_root(script_id: str) -> Path:
    """某脚本的备份归档根目录（MAS 用户池用）：``data/{script_id}/MaaBackups``。"""

    return Path.cwd() / "data" / script_id / "MaaBackups"


def project_backup_root() -> Path:
    """MAA 备份的项目级根目录：``data/MaaBackups``。

    native（脚本原生配置）池挂在这里而不是脚本目录下——同一份物理安装
    可被多个脚本实例引用，原生备份按物理配置根指纹分桶、跨脚本共享、
    不随脚本删除（mas 用户池仍按脚本，见 :func:`mas_backup_root`）。
    """

    return Path.cwd() / "data" / "MaaBackups"


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/MaaBackups/mas/{user_id}``。

    **恒按用户分桶**——脚本态多用户共享 Default 下发源，但每个用户要
    看到、恢复自己的备份；池与恢复目标解耦（目标路径见
    :func:`mas_config_dir`，由 Info.Mode 决定 Default 或用户目录）。
    """

    return backup_root(script_id) / "mas" / user_id


def native_backup_root(config_path: str | Path) -> Path:
    """MAA 原生配置的项目级归档目录：``data/MaaBackups/native/{key}``。

    ``key`` 是物理配置根的指纹（:func:`config_root_key`）——同一份物理
    配置无论被哪个脚本引用都归同一个池；跨脚本共享、不随脚本删除。
    """

    return project_backup_root() / "native" / config_root_key(config_path)


def mas_config_dir(script_id: str, owner: str) -> Path:
    """MAS 配置目录：``data/{script_id}/{owner}/ConfigFile``。"""

    return Path.cwd() / "data" / script_id / owner / "ConfigFile"


# ══════════════════ MAS 配置（池按用户，目标路径按 owner） ══════════════════

_OVERLAY_SIDECAR_NAME = "_mas_overlay.json"
"""页面核心字段侧车文件名（只在归档内；恢复时分离回填 MAS 用户配置，不落入 ConfigFile）"""

_OVERLAY_INFO_KEYS = (
    "Server",
    "Id",
    "Mode",
    "StageMode",
    "MedicineNumb",
    "SeriesNumb",
    "Stage",
    "Stage_1",
    "Stage_2",
    "Stage_3",
    "Stage_Remain",
    "Annihilation",
    "AnnihilationStartWeekday",
    "InfrastMode",
    "InfrastName",
)
"""MAS 页面基础/战斗/基建字段（UserData.Info，运行时注入 gui.json）"""

_OVERLAY_TASK_KEYS = (
    "IfStartUp",
    "IfFight",
    "IfInfrast",
    "IfRecruit",
    "IfMall",
    "IfAward",
    "IfSwitchTheme",
    "IfRoguelike",
    "IfReclamation",
    "IfDepotMaintain",
    "IfGreenTicketStore",
    "IfActivityFirst",
    "ActivityStageIndex",
    "ActivityMedicineNumb",
    "DepotMaintainPlans",
)
"""MAS 页面任务开关与参数（UserData.Task，运行时注入 gui.json）"""

_OVERLAY_KEY_GROUPS = {"Info": _OVERLAY_INFO_KEYS, "Task": _OVERLAY_TASK_KEYS}
"""侧车字段的配置段归属（两组键名无交集，侧车内平铺存储）"""

_OVERLAY_KEY_GROUP = {
    key: group for group, keys in _OVERLAY_KEY_GROUPS.items() for key in keys
}

_OVERLAY_PREVIEW_ONLY_KEYS = {"Mode"}
"""仅预览不回填的字段：配置文件来源决定恢复目标目录，恢复时以当前值为准"""

# 预览分区一：与 MAA GUI 概念对应的字段（恢复后可在 MAA GUI 对照）
_OVERLAY_MAA_ORDER = (
    "Server",
    "Id",
    "IfStartUp",
    "IfFight",
    "IfInfrast",
    "IfRecruit",
    "IfMall",
    "IfAward",
    "IfSwitchTheme",
    "IfRoguelike",
    "IfReclamation",
    "IfDepotMaintain",
    "MedicineNumb",
    "SeriesNumb",
    "Stage",
    "Stage_Remain",
    "Annihilation",
    "InfrastMode",
    "InfrastName",
)
# 预览分区二：MAS 独有字段（MAA GUI 无对应概念，「查看详细配置」看不到，
# 必须全量进预览）
_OVERLAY_MAS_ONLY_ORDER = (
    "Mode",
    "StageMode",
    "AnnihilationStartWeekday",
    "IfActivityFirst",
    "ActivityStageIndex",
    "ActivityMedicineNumb",
    "IfGreenTicketStore",
    "DepotMaintainPlans",
)

_OVERLAY_FIELD_LABELS = {
    "Server": "服务器",
    "Id": "账号",
    "Mode": "配置文件来源",
    "StageMode": "关卡配置模式",
    "IfStartUp": "自动唤醒",
    "IfFight": "理智作战",
    "IfInfrast": "基建换班",
    "IfRecruit": "公开招募",
    "IfMall": "信用收支",
    "IfAward": "领取奖励",
    "IfSwitchTheme": "更换主题",
    "IfRoguelike": "自动肉鸽",
    "IfReclamation": "生息演算",
    "IfDepotMaintain": "库存保持",
    "IfGreenTicketStore": "绿票商店",
    "IfActivityFirst": "活动关优先",
    "ActivityStageIndex": "活动关卡序号",
    "ActivityMedicineNumb": "活动理智药",
    "DepotMaintainPlans": "库存保持计划",
    "MedicineNumb": "吃理智药",
    "SeriesNumb": "连战次数",
    "Stage": "关卡",
    "Stage_Remain": "剩余理智关卡",
    "Annihilation": "剿灭模式",
    "AnnihilationStartWeekday": "剿灭开始星期",
    "InfrastMode": "基建模式",
    "InfrastName": "基建配置",
}
"""侧车字段中文标签（MAA 对应区对齐 MAA 编辑页词表）"""

_SERVER_LABELS = {
    "Official": "官服",
    "Bilibili": "B服",
    "YoStarEN": "国际服（YoStarEN）",
    "YoStarJP": "日服（YoStarJP）",
    "YoStarKR": "韩服（YoStarKR）",
    "txwy": "繁中服（txwy）",
}
_ANNIHILATION_LABELS = {
    "Close": "关闭",
    "Annihilation": "当期剿灭",
    "Chernobog@Annihilation": "切尔诺伯格",
    "LungmenOutskirts@Annihilation": "龙门市郊",
    "LungmenDowntown@Annihilation": "龙门市区",
}
_WEEKDAY_LABELS = {
    "Monday": "周一",
    "Tuesday": "周二",
    "Wednesday": "周三",
    "Thursday": "周四",
    "Friday": "周五",
    "Saturday": "周六",
    "Sunday": "周日",
}
_INFRAST_MODE_LABELS = {"Normal": "标准", "Rotation": "轮换", "Custom": "自定义"}
"""枚举字段取值中文词表（对齐编辑页选项；未知取值显示原文）"""


def read_overlay_values(config) -> dict:
    """读取配置对象的 MAS 页面核心字段（鸭子类型，仅需 ``get(group, key)``）。

    覆盖 Info / Task 两段的全部 MAS 可配置核心内容；值为 ``None``（配置项
    不存在）的键不纳入侧车。
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
    回填旧值会静默改变用户态/脚本态。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS:
            continue
        grouped.setdefault(_OVERLAY_KEY_GROUP.get(key, "Task"), {})[key] = value
    return grouped


def _mask_account(value) -> str:
    """账号脱敏：11 位手机号保留前 3 后 4，其余原样。"""

    text = str(value)
    if len(text) == 11 and text.isdigit():
        return f"{text[:3]}****{text[7:]}"
    return text


def _sidecar_temp_file(overlay: dict) -> Path:
    """把页面核心字段写到临时文件（参与归档指纹，归档后即删）。"""

    fd = tempfile.NamedTemporaryFile(
        "w", suffix=f"{_OVERLAY_SIDECAR_NAME}.tmp", delete=False, encoding="utf-8"
    )
    json.dump(overlay, fd, ensure_ascii=False, indent=2)
    fd.close()
    return Path(fd.name)


def read_overlay_sidecar(backup_dir: Path) -> dict | None:
    """读取归档内的页面核心字段侧车；不存在（旧版备份）或损坏返回 ``None``。"""

    sidecar = Path(backup_dir) / _OVERLAY_SIDECAR_NAME
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def archive_mas_backup(
    script_id: str,
    user_id: str,
    mas_dir: Path,
    overlay: dict | None = None,
    force: bool = False,
) -> Path | None:
    """归档 MAS 配置整份 + 页面核心字段侧车到用户池（指纹去重，无变化跳过）。

    ``user_id`` 是池归属（恒按用户分桶，见 :func:`mas_backup_root`）；
    ``mas_dir`` 是归档/恢复目标路径，由调用方按两态 owner 解析（脚本态
    共享 Default 目录、用户态独立目录）——池与目标解耦。
    侧车参与指纹：只改页面配置、未动 ConfigFile 时同样新建归档。
    目录不存在或为空时无可恢复内容，返回 ``None``；``force=True`` 强制
    归档（恢复前存底——让「恢复前的配置」在列表里有明确的时间戳条目）。
    """

    mas_dir = Path(mas_dir)
    if not mas_dir.is_dir() or not any(mas_dir.iterdir()):
        return None
    files = dir_files(mas_dir)
    temp_sidecar: Path | None = None
    if overlay:
        temp_sidecar = _sidecar_temp_file(overlay)
        files[_OVERLAY_SIDECAR_NAME] = temp_sidecar
    try:
        dest = archive_files(files, mas_backup_root(script_id, user_id), force=force)
    finally:
        if temp_sidecar is not None:
            temp_sidecar.unlink(missing_ok=True)
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
    路径，由调用方按两态 owner 解析（脚本态共享 Default 目录、用户态独立
    目录）。``overlay`` 为当前用户的页面核心字段，随恢复前存底一起归档。
    返回该备份的侧车（供调用方回填 MAS 用户配置；旧版备份无侧车返回
    ``None``），侧车文件随即从目录中分离删除，不留在 ConfigFile 里。
    """

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    mas_dir = Path(mas_dir)
    if mas_dir.is_dir() and any(mas_dir.iterdir()):
        archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay, force=True)
    restore_dir(mas_backup_root(script_id, user_id), ts, mas_dir)
    restored_overlay = read_overlay_sidecar(mas_dir)
    if restored_overlay is not None:
        (mas_dir / _OVERLAY_SIDECAR_NAME).unlink(missing_ok=True)
    logger.info(f"用户 {user_id} 的 MAS 配置已恢复备份 {ts}")
    return restored_overlay


def archive_mas_runtime_backup(
    script_id: str,
    user_id: str,
    mas_dir: Path,
    overlay: dict | None = None,
) -> None:
    """运行 / 配置会话下发前归档 MAS 配置（下发源）到用户池。

    运行回写与会话保存会覆盖它，下发前存底；指纹去重，失败只记日志，
    绝不中止随后的运行或会话（归档是现场保护，不是前置条件）。
    ``user_id`` 是池归属；``mas_dir`` 是下发源目录，由调用方按当前用户
    两态解析（脚本态=Default 共享目录、用户态=独立目录）。``overlay``
    为当前用户的页面核心字段。native 池与此处无关：原生配置跨用户共享，
    由 manager ``prepare`` 在任务级一次性归档（见
    :func:`archive_native_backup`）。
    """

    archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay)


# ══════════════════ 脚本原生配置（安装目录 config/ 整目录） ══════════════════


def archive_native_backup(config_path: Path, force: bool = False) -> Path | None:
    """归档 MAA 安装目录 config/ 当前状态（整目录）。

    归档落到该项目级池（按物理配置根指纹分桶），与脚本实例解耦。
    目录不存在或为空时无可归档内容，返回 ``None``。
    """

    config_path = Path(config_path)
    if not config_path.is_dir() or not any(config_path.iterdir()):
        return None
    dest = archive_dir(config_path, native_backup_root(config_path), force=force)
    if dest is None:
        logger.info("MAA 原生配置无变化，跳过归档")
        return None
    logger.info(f"MAA 原生配置已归档: {dest.name}")
    return dest


def list_native_backups(config_path: str | Path) -> list[str]:
    """MAA 原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(config_path))


def get_native_backup_dir(config_path: str | Path, ts: str) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(config_path), ts)


def restore_native_backup(config_path: Path, ts: str) -> None:
    """把归档恢复到 MAA 安装目录 config/（恢复前自动归档当前，误恢复可找回）。

    整目录替换（MAA 原生配置恒为目录，无 Folder/File 双模式）。
    """

    backup_dir = get_native_backup_dir(config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    config_path = Path(config_path)
    # 恢复前强制归档当前——「恢复前的配置」在列表里有明确的时间戳条目
    archive_native_backup(config_path, force=True)
    restore_dir(native_backup_root(config_path), ts, config_path)
    logger.info(f"MAA 原生配置已恢复备份 {ts}")


# ══════════════════ 备份预览摘要 ══════════════════

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""

CONFIG_DISPLAY_NAMES = {
    "gui.json": "MAA 设置",
    "gui.new.json": "MAA 设置（新版）",
}
"""MAA 已知配置文件的展示名（未知文件回退文件名）"""


def _summary_value(value) -> str:
    """摘要标量值转展示文本（布尔转是否、超长截断）。"""

    if isinstance(value, bool):
        return "是" if value else "否"
    text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


_CLIENT_TYPE_TO_LABEL = {
    0: "官服",
    1: "B服",
    2: "国际服（YoStarEN）",
    3: "日服（YoStarJP）",
    4: "韩服（YoStarKR）",
    5: "繁中服（txwy）",
}
"""新版 gui.new.json 的 ClientType 枚举整数 → 服名"""

_LEGACY_CLIENT_TYPE_TO_LABEL = {
    "Official": "官服",
    "Bilibili": "B服",
    "YoStarEN": "国际服（YoStarEN）",
    "YoStarJP": "日服（YoStarJP）",
    "YoStarKR": "韩服（YoStarKR）",
    "txwy": "繁中服（txwy）",
}
"""旧版 gui.json 的 ClientType 字符串 → 服名"""


def _client_type_label(value) -> str:
    """客户端类型转展示文本（新版整数枚举 / 旧版字符串都映射到服名）。"""

    if isinstance(value, int):
        return _CLIENT_TYPE_TO_LABEL.get(value, str(value))
    return _LEGACY_CLIENT_TYPE_TO_LABEL.get(str(value), str(value))


def _bool_text(value) -> str:
    """开关值转是否（新版布尔 / 旧版 "True"/"False" 字符串都映射）。"""

    if isinstance(value, bool):
        return "是" if value else "否"
    text = str(value)
    if text.lower() == "true":
        return "是"
    if text.lower() == "false":
        return "否"
    return text


_TASK_SWITCH_LABELS = {
    "StartUp": "自动唤醒",
    "Fight": "理智作战",
    "Infrast": "基建换班",
    "Recruit": "公开招募",
    "Mall": "信用收支",
    "Award": "领取奖励",
    "SwitchTheme": "更换主题",
    "Roguelike": "自动肉鸽",
    "Reclamation": "生息演算",
    "DepotMaintain": "库存保持",
}
"""TaskQueue 任务类型 → 开关标签（与 MAS 侧侧车词表一致）"""

_TASK_ZH_TO_TYPE = {zh: en for en, zh in zip(MAA_TASKS, MAA_TASKS_ZH)}
"""MAA 任务中文名 → 任务类型（GUI 存的任务可能缺 TaskType，按名兜底）"""


def _task_type_of(task: dict) -> str | None:
    """TaskQueue 任务条目的任务类型（TaskType → $type 后缀 → 中文名兜底）。"""

    task_type = task.get("TaskType")
    if isinstance(task_type, str) and task_type:
        return task_type
    dtype = task.get("$type")
    if isinstance(dtype, str) and dtype.endswith("Task"):
        return dtype[: -len("Task")]
    return _TASK_ZH_TO_TYPE.get(task.get("Name"))


def _stage_plan_text(stage_plan: list) -> str:
    """StagePlan → 关卡展示文本（与 MAA GUI「关卡指定」显示对齐）。

    MAA GUI 的「关卡指定=当前/上次」在配置里就是空 StagePlan——只有 MAS
    侧的剩余理智关卡才有「不选择」哨兵值，native 侧没有。
    """

    stages = [str(stage) for stage in stage_plan if str(stage)]
    return "、".join(stages) if stages else "当前/上次"


def _fight_task_rows(task: dict) -> list[dict]:
    """Fight 任务条目的战斗参数行（标签与取值同 MAS 侧侧车口径）。"""

    rows: list[dict] = []
    if "MedicineCount" in task or "UseMedicine" in task:
        # 直接显示配置里的数量（与 MAA GUI 一致：勾不勾选都显示数字）
        rows.append({"key": "吃理智药", "value": str(task.get("MedicineCount", 0))})
    if task.get("Series") is not None:
        rows.append(
            {
                "key": "连战次数",
                "value": {"0": "AUTO", "-1": "不切换"}.get(
                    str(task["Series"]), str(task["Series"])
                ),
            }
        )
    if isinstance(task.get("StagePlan"), list):
        rows.append({"key": "关卡", "value": _stage_plan_text(task["StagePlan"])})
    if task.get("AnnihilationStage") is not None:
        rows.append(
            {
                "key": "剿灭模式",
                "value": _ANNIHILATION_LABELS.get(
                    str(task["AnnihilationStage"]), str(task["AnnihilationStage"])
                ),
            }
        )
    return rows


def _task_queue_rows(queue) -> list[dict]:
    """TaskQueue 任务条目 → 开关/参数摘要行（标签对齐 MAS 侧；同类型只取首条）。"""

    if not isinstance(queue, list):
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    for task in queue:
        if not isinstance(task, dict):
            continue
        task_type = _task_type_of(task)
        if task_type is None:
            continue
        if task_type == "Fight" and task.get("Name") == "剩余理智":
            # MAA 的剩余理智是第二个 Fight 任务，不并入理智作战：开关 +
            # 关卡（关闭且未配置时与 MAS 侧的「不选择」口径一致）
            rows.append({"key": "剩余理智", "value": _bool_text(task.get("IsEnable"))})
            if isinstance(task.get("StagePlan"), list):
                stages = [str(stage) for stage in task["StagePlan"] if str(stage)]
                value = (
                    "、".join(stages)
                    if stages
                    else ("当前/上次" if task.get("IsEnable") else "不选择")
                )
                rows.append({"key": "剩余理智关卡", "value": value})
            continue
        if task_type in seen:
            continue
        seen.add(task_type)
        if task_type in _TASK_SWITCH_LABELS and "IsEnable" in task:
            label = _TASK_SWITCH_LABELS[task_type]
            rows.append({"key": label, "value": _bool_text(task["IsEnable"])})
        if task_type == "StartUp" and task.get("AccountName"):
            rows.append({"key": "账号", "value": _mask_account(task["AccountName"])})
        if task_type == "Fight":
            rows.extend(_fight_task_rows(task))
        if task_type == "Infrast" and task.get("Mode") is not None:
            mode = _INFRAST_MODE_LABELS.get(str(task["Mode"]), str(task["Mode"]))
            rows.append({"key": "基建模式", "value": mode})
    return rows


def _gui_summary_rows(name: str, data: dict) -> list[dict]:
    """MAA 配置文件的稳定字段摘要（与 MAS 侧预览同口径对齐）。

    预览的语义是「这份备份的 MAA 设置是什么样」。同一配置概念在两池
    必须同口径展示（同标签、同取值文本）：gui.new.json 的 TaskQueue 是
    MAS 任务开关/战斗参数注入的同一载体，反读成与侧车一致的行；仅隶属
    一侧的字段（当前方案/连接地址/启动游戏）单独展示。旧 gui.json 用扁平
    键且任务设置随版本漂移，只取 MAS 读写过的稳定字段。其余内部字段不进
    预览（经「查看详细配置」恢复后在 MAA GUI 里查看）。
    """

    rows: list[dict] = []
    current = data.get("Current")
    if current is not None:
        rows.append({"key": "当前方案", "value": _summary_value(current)})
    configurations = data.get("Configurations")
    default_conf = (
        configurations.get("Default") if isinstance(configurations, dict) else None
    )
    if not isinstance(default_conf, dict):
        return rows
    if name == "gui.json":
        # OLD 扁平键：Configurations.Default["Connect.Address"] 等
        addr = default_conf.get("Connect.Address")
        client_type = default_conf.get("Start.ClientType")
        start_game = default_conf.get("Start.StartGame")
    else:
        # NEW 嵌套：Configurations.Default.Gui.ConnectSettings / RuntimeSettings
        gui = default_conf.get("Gui") or {}
        connect = gui.get("ConnectSettings") or {}
        runtime = gui.get("RuntimeSettings") or {}
        addr = connect.get("Address")
        client_type = runtime.get("ClientType")
        start_game = runtime.get("StartGame")
    if addr:
        rows.append({"key": "连接地址", "value": _summary_value(addr)})
    if client_type is not None:
        rows.append({"key": "服务器", "value": _client_type_label(client_type)})
    if start_game is not None:
        rows.append({"key": "启动游戏", "value": _bool_text(start_game)})
    if name != "gui.json":
        rows.extend(_task_queue_rows(default_conf.get("TaskQueue")))
    return rows


def build_backup_file_summary(backup_dir: Path) -> list[dict]:
    """备份目录内 MAA 配置文件的摘要列表（预览用，纯读）。

    每个文件一条 ``{name, label, summary}``：label 用 MAA 配置展示名
    （未知文件回退文件名），summary 只取稳定字段。只保留预览白名单内的
    文件，非 JSON / 坏 JSON / 无可展示字段的文件跳过（恢复时仍会随备份
    完整写回）。
    """

    files: list[dict] = []
    for rel in sorted(dir_files(backup_dir)):
        if "/" in rel or rel not in _MAA_CONFIG_FILES:
            continue
        try:
            data = json.loads((backup_dir / rel).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        rows = _gui_summary_rows(rel, data)
        if not rows:  # 无可展示字段的文件不进预览
            continue
        files.append(
            {
                "name": rel,
                "label": CONFIG_DISPLAY_NAMES.get(rel, rel),
                "summary": rows,
            }
        )
    return files


def _overlay_value(key: str, value) -> str:
    """侧车字段值转展示文本（枚举词表、账号脱敏、布尔转是否、超长截断）。"""

    if key == "Id":
        return _mask_account(value)  # 账号脱敏展示；侧车原值仍完整保存（恢复需要）
    if isinstance(value, bool):
        return "是" if value else "否"
    enum = {
        "Server": _SERVER_LABELS,
        "Annihilation": _ANNIHILATION_LABELS,
        "AnnihilationStartWeekday": _WEEKDAY_LABELS,
        "InfrastMode": _INFRAST_MODE_LABELS,
    }.get(key)
    if enum is not None:
        text = enum.get(str(value), str(value))
    elif key == "StageMode":
        text = "固定" if str(value) == "Fixed" else "计划表"
    elif key == "SeriesNumb":
        text = {"0": "AUTO", "-1": "不切换"}.get(str(value), str(value))
    elif key.startswith("Stage"):
        # 关卡哨兵值（与配置界面同口径）：- = 禁用（下拉原始标签），
        # * = 当前/上次，空 = 不选择，其余为关卡名/计划 UID
        text = {"-": "禁用", "*": "当前/上次", "": "不选择"}.get(str(value), str(value))
    elif key == "DepotMaintainPlans":
        # JSON 串存计划列表，预览只给数量（恢复仍整串写回）
        try:
            plans = json.loads(value) if isinstance(value, str) else value
            text = f"{len(plans)} 个计划" if isinstance(plans, list) and plans else "无"
        except Exception:
            text = "已配置"
    else:
        text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def _compose_stage_text(overlay: dict) -> str:
    """合成「具体刷什么本」：按注入顺序取非禁用槽位（关卡 → 备选 1-3）。

    与配置界面折叠摘要同口径——全部槽位禁用时不注入任何关卡，MAA 按
    当前/上次执行；`*`（当前/上次）注入为空串槽位。
    """

    slots: list[str] = []
    for key in ("Stage", "Stage_1", "Stage_2", "Stage_3"):
        value = overlay.get(key)
        if value is None or str(value) in ("-", ""):
            continue
        text = str(value)
        slots.append("当前/上次" if text == "*" else text)
    return "、".join(slots) if slots else "当前/上次"


def build_overlay_summary(overlay: dict) -> list[dict]:
    """侧车字段的分区预览（mas 池预览用，纯读）。

    返回两个分区（前端按文件集逐区渲染）：

    - **MAS 独有配置**：MAA GUI 无对应概念、「查看详细配置」看不到的
      字段，必须全量展示（配置文件来源/关卡配置模式/剿灭开始星期/活动关
      优先三项/绿票商店/库存保持计划）；
    - **MAA 配置**：与 MAA GUI 概念对应的字段（服务器/账号/任务开关/
      战斗参数/剿灭/基建），关卡为合成后的具体刷本内容。

    布尔开关为 False 的字段一并展示（用户要确认「当时关没关」）；自定义
    基建名仅在自定义模式下展示；分区无行时整体省略（旧版备份可能只有
    部分字段）。
    """

    def _rows(order: tuple[str, ...]) -> list[dict]:
        rows: list[dict] = []
        for key in order:
            if key not in overlay or key not in _OVERLAY_FIELD_LABELS:
                continue
            if key == "InfrastName" and overlay.get("InfrastMode") != "Custom":
                continue  # 非自定义模式下基建配置名无意义（虚拟字段回退文案）
            if key == "Stage":
                rows.append({"key": "关卡", "value": _compose_stage_text(overlay)})
                continue
            value = overlay[key]
            if isinstance(value, list):
                joined = "、".join(
                    _overlay_value(key, item)
                    for item in value
                    if isinstance(item, (str, int, float, bool))
                )
                rows.append(
                    {"key": _OVERLAY_FIELD_LABELS[key], "value": joined or "无"}
                )
                continue
            rows.append(
                {"key": _OVERLAY_FIELD_LABELS[key], "value": _overlay_value(key, value)}
            )
        return rows

    sections: list[dict] = []
    mas_rows = _rows(_OVERLAY_MAS_ONLY_ORDER)
    if mas_rows:
        sections.append(
            {"name": "mas-only", "label": "MAS 独有配置", "summary": mas_rows}
        )
    maa_rows = _rows(_OVERLAY_MAA_ORDER)
    if maa_rows:
        sections.append({"name": "maa", "label": "MAA 配置", "summary": maa_rows})
    return sections
