#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""BAAH 配置备份归档：MAS 用户字段侧车 / BAAH 原生配置（动态目标文件）。

备份时机（MAS「动手前」）：

- 任务启动（AutoProxy ``prepare`` 之后、``run_once`` 托管写入之前）：
  ``native`` 归档当前用户 ``ConfigName`` 指向的用户配置 JSON 与
  ``software_config.json``——随后托管项写入会改这两个文件，任务结束按
  ``managed_backup`` 键级还原（还原 ≠ 归档：托管键之外的内容不还原）；
- 编辑界面进入（前端 ensure）：``native`` 捕捉「MAS 操作前原始态」；
- 编辑界面退出（前端 ensure）：``mas`` 归档 MAS 编辑页字段侧车终态。

BAAH 与其它专项的根本差异：**用户身份 = BAAH 侧的 JSON 文件名**（
``Info.ConfigName``），MAS 不持有配置本体；用户在 BAAH jsoneditor 里改坏/
误删配置后 MAS 侧无从找回——native 池是本专项的核心价值。池 key 恒为
``native``，**目标文件按当前用户 ConfigName 动态解析**（配置名可改可
不存在），归档内以 ``{config_name}.json`` 保存；缺失（未创建/被误删）
时无可归档内容。

mas 池当前只有元字段（配置来源/快速配置/配置文件名）——BAAH 无字段化
配置面板，这些值不注入 BAAH 配置，仅作「未来 MAS 侧扩展配置内容」的
预留（恢复即回填）。

预览：native 反读关键字段（目标设备/串号直连/托管键取值/任务编排
``TASK_ORDER``+``TASK_ACTIVATE``），扁平 JSON 结构稳定可读；mas 为分区行。
账号类敏感值不存在于 BAAH 配置
顶层（账号在任务子配置里，不归本池），无需脱敏。

时间戳快照、指纹去重、保留清理与整目录恢复由公共模块
``app.utils.config_archive`` 提供，本模块只保留 BAAH 特有的动态目标
解析、恢复语义（恢复前强制归档当前）与预览摘要。
"""

import json
from pathlib import Path

from app.task.BAAH.tools.config_manager import (
    SOFTWARE_CONFIG_RELATIVE,
    resolve_config_name,
)
from app.utils import get_logger
from app.utils.config_archive import (
    OVERLAY_SIDECAR_NAME,
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
    read_overlay_sidecar,
)

logger = get_logger("BAAH 配置备份")

# ══════════════════ MAS 用户字段侧车 ══════════════════

_OVERLAY_INFO_KEYS = ("Mode", "IfQuickConfig", "ConfigName")
"""MAS 编辑页字段（UserData.Info；当前均为元字段，预留未来扩展）"""

_OVERLAY_PREVIEW_ONLY_KEYS = {"Mode", "IfQuickConfig"}
"""仅预览不回填的字段：来源与快速配置决定 MAS 是否写入 BAAH，恢复以当前值为准"""


def read_overlay_values(config) -> dict:
    """读取配置对象的 MAS 页面字段（鸭子类型，仅需 ``get(group, key)``）。"""

    values: dict = {}
    for key in _OVERLAY_INFO_KEYS:
        if (value := config.get("Info", key)) is not None:
            values[key] = value
    return values


def group_overlay(overlay: dict) -> dict[str, dict]:
    """把平铺的侧车字段分组（恢复回填 BAAHUserConfig 用）。

    来源与快速配置只预览不回填：回填旧值会静默改变 MAS 是否写入 BAAH。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS:
            continue
        grouped.setdefault("Info", {})[key] = value
    return grouped


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/BAAHBackups/mas/{user_id}``（恒按用户）。"""

    return Path.cwd() / "data" / script_id / "BAAHBackups" / "mas" / user_id


def archive_mas_backup(
    script_id: str, user_id: str, overlay: dict, force: bool = False
) -> Path | None:
    """归档 MAS 页面字段侧车到用户池（指纹去重，无变化跳过）。"""

    dest = archive_files(
        {OVERLAY_SIDECAR_NAME: json.dumps(overlay, ensure_ascii=False, indent=2)},
        mas_backup_root(script_id, user_id),
        force=force,
    )
    if dest is None:
        logger.info("用户 %s 的 MAS 配置无变化，跳过归档", user_id)
        return None
    logger.info("用户 %s 的 MAS 配置已归档: %s", user_id, dest.name)
    return dest


def list_mas_backups(script_id: str, user_id: str) -> list[str]:
    return list_times(mas_backup_root(script_id, user_id))


def get_mas_backup_dir(script_id: str, user_id: str, ts: str) -> Path | None:
    return get_backup_dir(mas_backup_root(script_id, user_id), ts)


def restore_mas_backup(script_id: str, user_id: str, ts: str) -> dict | None:
    """读取用户池归档的侧车（供调用方回填 BAAHUserConfig）；无目录目标。"""

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    return read_overlay_sidecar(backup_dir)


# ══════════════════ BAAH 原生配置（ConfigName 动态目标） ══════════════════

_SOFTWARE_CONFIG_KEY = "software_config.json"
"""归档内软件配置的固定键（与用户配置文件名不会冲突：resolve_config_name 禁路径分隔符）"""


def native_backup_root(config_dir: str | Path, user_id: str) -> Path:
    """BAAH 配置目录的项目级归档根：``data/BAAHBackups/native/{key}/{user_id}``。

    ``key`` 按物理配置目录指纹分桶（同一份 BAAH 安装跨脚本实例共享）；
    **再按用户分桶**——归档内容是用户绑定的 ``<ConfigName>.json``，是用户
    级数据，多用户绑定同一安装时必须隔离，否则用户 A 的列表会出现用户 B
    的备份、点恢复会串配置（§1.1.1 池分桶教训）。software_config.json
    是安装级共享文件，随每个用户的备份一并归档（恢复各自写同一份）。
    """

    return (
        Path.cwd()
        / "data"
        / "BAAHBackups"
        / "native"
        / config_root_key(config_dir)
        / user_id
    )


def resolve_native_targets(config_dir: Path, config_name: str) -> dict[str, Path]:
    """解析当前用户配置名的归档目标文件集（用户配置 + 软件配置）。

    ``config_name`` 经 :func:`resolve_config_name` 校验（防空/防路径穿越）；
    用户配置文件不存在时抛 ``FileNotFoundError``（调用方决定跳过或报错）。
    """

    name = resolve_config_name(config_name)
    user_config_path = config_dir / f"{name}.json"
    if not user_config_path.is_file():
        raise FileNotFoundError(f"BAAH 配置文件不存在: {user_config_path}")
    targets = {f"{name}.json": user_config_path}
    software_config_path = config_dir.parent / SOFTWARE_CONFIG_RELATIVE
    if software_config_path.is_file():
        targets[_SOFTWARE_CONFIG_KEY] = software_config_path
    return targets


def collect_native_files(config_dir: str | Path, config_name: str) -> dict[str, Path]:
    """收集当前配置名的归档目标文件集（用户配置 + 软件配置）。

    配置目录缺失、配置名非法或用户配置文件不存在时返回空 dict（缺失项
    跳过）；供声明式池声明归档内容（``files`` 回调），也供
    :func:`archive_native_backup` 复用。
    """

    config_dir = Path(config_dir)
    if not config_dir.is_dir():
        return {}
    try:
        targets = resolve_native_targets(config_dir, config_name)
    except (ValueError, FileNotFoundError) as e:
        logger.info(f"跳过 BAAH 配置归档: {e}")
        return {}
    return targets


def archive_native_backup(
    config_dir: Path, config_name: str, user_id: str, force: bool = False
) -> Path | None:
    """归档 BAAH 用户配置 + 软件配置（指纹去重，无变化跳过）。

    配置文件不存在（未创建/已被误删）时无可归档内容，返回 ``None``——
    「归档了但内容为空」比「列表为空」更接近真实，但此时连归档对象都没有，
    与其它专项「目录为空跳过」语义一致。
    """

    config_dir = Path(config_dir)
    targets = collect_native_files(config_dir, config_name)
    if not targets:
        return None
    dest = archive_files(targets, native_backup_root(config_dir, user_id), force=force)
    if dest is None:
        logger.info("BAAH 配置无变化，跳过归档")
        return None
    logger.info("BAAH 配置已归档: %s", dest.name)
    return dest


def list_native_backups(config_dir: str | Path, user_id: str) -> list[str]:
    return list_times(native_backup_root(config_dir, user_id))


def get_native_backup_dir(config_dir: str | Path, user_id: str, ts: str) -> Path | None:
    return get_backup_dir(native_backup_root(config_dir, user_id), ts)


def restore_native_backup(
    config_dir: Path, config_name: str, user_id: str, ts: str
) -> str:
    """把归档恢复到 BAAH 配置目录（恢复前强制归档当前，误恢复可找回）。

    只覆盖归档内包含的文件；恢复用户配置后**不回填 ConfigName**——备份
    文件名即 ``{归档时的配置名}.json``，若与当前 ConfigName 不同说明用户
    改过绑定，恢复内容写到当前 ConfigName 指向的文件（覆盖语义，确认弹窗
    已提示）。返回归档时的配置文件名（供预览/日志展示）。
    """

    backup_dir = get_native_backup_dir(config_dir, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    config_dir = Path(config_dir)
    name = resolve_config_name(config_name)  # 当前名合法性校验（防空/防穿越）

    # 恢复前强制归档当前——「恢复前的配置」在列表里有明确的时间戳条目
    archive_native_backup(config_dir, config_name, user_id, force=True)

    files = dir_files(backup_dir)
    user_files = [
        rel for rel in files if rel != _SOFTWARE_CONFIG_KEY and rel.endswith(".json")
    ]
    if not user_files:
        raise ValueError(f"备份内容为空: {ts}")
    dest_user = config_dir / f"{name}.json"
    for rel, path in files.items():
        target = (
            dest_user
            if rel.endswith(".json") and rel != _SOFTWARE_CONFIG_KEY
            else config_dir.parent / SOFTWARE_CONFIG_RELATIVE
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())

    archived_name = Path(user_files[0]).stem
    logger.info("BAAH 配置已恢复备份 %s（%s.json → %s.json）", ts, archived_name, name)
    return archived_name


# ══════════════════ 备份预览摘要 ══════════════════

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""


def _summary_text(value) -> str:
    text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def build_overlay_preview(overlay: dict) -> dict:
    """mas 池预览：分区行（BAAH 独有 = 来源/快速配置；BAAH 配置 = 配置文件名）。"""

    def _row(key: str, value) -> dict:
        return {"key": key, "value": _summary_text(value)}

    sections: list[dict] = []

    mas_rows: list[dict] = []
    if "Mode" in overlay:
        mas_rows.append(_row("配置文件来源", overlay["Mode"]))
    if mas_rows:
        sections.append({"name": "mas-only", "label": "MAS 独有配置", "rows": mas_rows})

    baah_rows: list[dict] = []
    if "ConfigName" in overlay:
        baah_rows.append(_row("BAAH 配置文件名", overlay["ConfigName"]))
    if baah_rows:
        sections.append({"name": "baah", "label": "BAAH 配置", "rows": baah_rows})

    return {"sections": sections}


def build_native_preview(config_dir: Path, user_id: str, ts: str) -> dict:
    """native 池预览：反读备份内用户配置关键字段（扁平 JSON 结构稳定可读）。

    反读范围：目标设备（IP:端口 / 串号直连）、BAAH 行为键（自动关闭等）、
    任务编排（``TASK_ORDER`` + ``TASK_ACTIVATE`` 对位合成「已启用任务」，
    实测结构，缺任一键则降级不反读）；其余内部字段不进预览。软件配置
    单列日志开关一行。

    用户配置文件名取备份内实际存在的 json（与当前 ConfigName 无关）——
    用户改过绑定后看旧备份仍能预览；恢复时同样按备份内实际文件写当前名
    （覆盖语义，见 :func:`restore_native_backup`）。
    """

    backup_dir = get_native_backup_dir(config_dir, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")

    files = dir_files(backup_dir)
    user_rels = [
        rel for rel in files if rel != _SOFTWARE_CONFIG_KEY and rel.endswith(".json")
    ]
    if not user_rels:
        raise ValueError(f"备份内容为空: {ts}")
    user_rel = user_rels[0]
    user_path = backup_dir / user_rel
    archived_name = Path(user_rel).stem

    try:
        data = json.loads(user_path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 - 坏 JSON 不阻断预览
        data = None

    rows: list[dict] = []
    detail_groups: list[dict] = []
    rows.append({"key": "配置文件名", "value": archived_name})
    if isinstance(data, dict):
        if data.get("ADB_DIRECT_USE_SERIAL_NUMBER"):
            rows.append(
                {
                    "key": "目标设备",
                    "value": _summary_text(data.get("ADB_SEIAL_NUMBER", "")),
                }
            )
        elif data.get("TARGET_IP_PATH"):
            rows.append(
                {
                    "key": "目标设备",
                    "value": _summary_text(
                        f"{data['TARGET_IP_PATH']}:{data.get('TARGET_PORT', '')}"
                    ),
                }
            )
        if data.get("TARGET_EMULATOR_PATH"):
            rows.append(
                {
                    "key": "模拟器路径",
                    "value": _summary_text(data["TARGET_EMULATOR_PATH"]),
                }
            )

        behavior_rows = _managed_key_rows(data)
        if behavior_rows:
            detail_groups.append({"name": "BAAH 行为", "rows": behavior_rows})

        # 任务编排 = TASK_ORDER（顺序）+ TASK_ACTIVATE（启用布尔，与顺序对位）；
        # 任一缺失则不反读（旧版配置结构差异，降级不臆造）
        task_order = data.get("TASK_ORDER")
        task_activate = data.get("TASK_ACTIVATE")
        if (
            isinstance(task_order, list)
            and task_order
            and isinstance(task_activate, list)
        ):
            enabled_tasks = [
                str(name)
                for i, name in enumerate(task_order)
                if isinstance(name, str)
                and name
                and (i < len(task_activate) and bool(task_activate[i]))
            ]
            rows.append(
                {"key": "已启用任务", "value": "、".join(enabled_tasks) or "无"}
            )
    else:
        rows.append({"key": "配置内容", "value": "无法解析（非 JSON 对象）"})

    software_rows: list[dict] = []
    software_path = backup_dir / _SOFTWARE_CONFIG_KEY
    if software_path.is_file():
        try:
            software = json.loads(software_path.read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            software = None
        if isinstance(software, dict) and software.get("SAVE_LOG_TO_FILE") is not None:
            software_rows.append(
                {
                    "key": "日志写文件",
                    "value": "开启" if software["SAVE_LOG_TO_FILE"] else "关闭",
                }
            )

    sections: list[dict] = []
    if rows:
        sections.append({"name": "baah", "label": "BAAH 配置", "rows": rows})
    if software_rows:
        sections.append(
            {"name": "software", "label": "软件配置", "rows": software_rows}
        )
    if detail_groups:
        sections.append(
            {"name": "details", "label": "配置详情", "groups": detail_groups}
        )
    return {"sections": sections}


def _managed_key_rows(data: dict) -> list[dict]:
    """BAAH 行为键反读行（仅展示用户可理解的开关类键，缺失跳过）。"""

    labels = {
        "CLOSE_BAAH_FINISH": "运行结束自动关闭 BAAH",
        "CLOSE_BAAH_ERROR": "出错自动关闭 BAAH",
        "CLOSE_EMULATOR_FINISH": "结束自动关闭模拟器",
        "CLOSE_EMULATOR_ERROR": "出错自动关闭模拟器",
        "CLOSE_GAME_FINISH": "结束自动关闭游戏",
        "CLOSE_GAME_ERROR": "出错自动关闭游戏",
        "RETRY_WHEN_ERROR": "出错自动重试次数",
        "KILL_PORT_IF_EXIST": "启动前清理占用端口的进程",
        "ADB_DIRECT_USE_SERIAL_NUMBER": "按串号直连设备",
    }
    rows: list[dict] = []
    for key, label in labels.items():
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, bool):
            text = "开启" if value else "关闭"
        else:
            text = _summary_text(value)
        rows.append({"key": label, "value": text})
    return rows
