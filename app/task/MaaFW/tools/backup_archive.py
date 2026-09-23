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

"""MaaFW 配置备份归档：MAS 用户字段侧车 / MaaFW 项目 config/ 与 interface.json。

备份时机（MAS「动手前」）：

- 任务启动（manager ``prepare``）：``native`` 归档 MaaFW 项目 ``config/``
  目录 + ``interface.json`` 当前状态——运行时物化 preset/选项会写这两处，
  归档必须在任何写入前；
- 编辑界面进入（前端 ensure）：``native`` 捕捉「MAS 操作前原始态」；
- 编辑界面退出（前端 ensure）：``mas`` 归档 MAS 编辑页核心字段终态。

MaaFW 与 M9A 同属 MaaFramework 线：没有 per-user ConfigFile 目录，MAS
用户配置是字段（Info / Task.SelectedPreset / Task.TaskSnapshot / Device 段，
存共享 ScriptConfig.json），运行时物化进项目配置。因此 ``mas`` 池是**纯
字段侧车**（无目录部分），恢复即字段回填 MaaFWUserConfig。``native`` 池 =
项目 ``config/`` 目录（maa_option.json 等 Toolkit 配置）+ ``interface.json``
（任务定义与物化 preset 处），按物理项目根指纹分桶。

时间戳快照、指纹去重、保留清理与目录恢复由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
MaaFW 特有的侧车、恢复语义（恢复前强制归档当前）与预览摘要。
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
    restore_files,
)

logger = get_logger("MaaFW 配置备份")

# ══════════════════ MAS 用户字段侧车（纯侧车，无目录） ══════════════════

_OVERLAY_INFO_KEYS = ("Mode", "IfQuickConfig", "Account", "Controller", "Resource")
"""MAS 编辑页核心字段（UserData.Info，运行时物化进项目配置）"""

_OVERLAY_TASK_KEYS = ("SelectedPreset", "TaskSnapshot")
"""任务快照（UserData.Task：当前 preset 名 + taskOrder/taskChecked/taskOptions JSON）"""

_OVERLAY_DEVICE_KEYS = (
    "AdbAddress",
    "HWnd",
    "PlayCoverAddress",
    "PlayCoverUuid",
)
"""设备覆盖字段（UserData.Device，运行时下发 controller）"""

_OVERLAY_KEY_GROUPS = {
    "Info": _OVERLAY_INFO_KEYS,
    "Task": _OVERLAY_TASK_KEYS,
    "Device": _OVERLAY_DEVICE_KEYS,
}
"""侧车字段的配置段归属（键名无交集，侧车内平铺存储）"""

_OVERLAY_KEY_GROUP = {
    key: group for group, keys in _OVERLAY_KEY_GROUPS.items() for key in keys
}

_OVERLAY_PREVIEW_ONLY_KEYS = {"Mode"}
"""仅预览不回填的字段：配置来源决定运行下发方式，恢复时以当前值为准"""

_OVERLAY_FIELD_LABELS = {
    "Mode": "配置来源",
    "IfQuickConfig": "启用快速配置",
    "Account": "账号",
    "Controller": "Controller",
    "Resource": "Resource",
    "SelectedPreset": "当前方案",
    "TaskSnapshot": "任务快照",
    "AdbAddress": "ADB 地址",
    "HWnd": "窗口句柄",
    "PlayCoverAddress": "PlayCover 地址",
    "PlayCoverUuid": "PlayCover UUID",
}
"""侧车字段中文标签（对齐 MaaFW 编辑页词表）"""


def read_overlay_values(config) -> dict:
    """读取配置对象的 MAS 页面核心字段（鸭子类型，仅需 ``get(group, key)``）。

    值为 ``None``（配置项不存在）的键不纳入侧车。
    """

    values: dict = {}
    for group, keys in _OVERLAY_KEY_GROUPS.items():
        for key in keys:
            if (value := config.get(group, key)) is not None:
                values[key] = value
    return values


def group_overlay(overlay: dict) -> dict[str, dict]:
    """把平铺的侧车字段按配置段分组（恢复回填 MaaFWUserConfig 用）。

    仅预览字段（配置来源）不回填：回填旧来源会静默翻转脚本态/用户态/直控。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS:
            continue
        grouped.setdefault(_OVERLAY_KEY_GROUP.get(key, "Task"), {})[key] = value
    return grouped


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/MaaFWBackups/mas/{user_id}``（恒按用户）。"""

    return Path.cwd() / "data" / script_id / "MaaFWBackups" / "mas" / user_id


def archive_mas_backup(
    script_id: str, user_id: str, overlay: dict | None, force: bool = False
) -> Path | None:
    """归档页面核心字段侧车到用户池（指纹去重，无变化跳过）。

    纯侧车：归档内唯一文件是 ``_mas_overlay.json``（无目录部分）；以内存
    JSON 直接入档（:func:`archive_files` 支持内存内容），免临时文件。
    """

    if not overlay:
        return None
    dest = archive_files(
        {OVERLAY_SIDECAR_NAME: json.dumps(overlay, ensure_ascii=False, indent=2)},
        mas_backup_root(script_id, user_id),
        force=force,
    )
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


def restore_mas_backup(script_id: str, user_id: str, ts: str) -> dict | None:
    """读取用户池归档的侧车（供调用方回填 MaaFWUserConfig）；无目录目标。"""

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    return read_overlay_sidecar(backup_dir)


def archive_mas_runtime_backup(script_id: str, user_id: str, overlay: dict) -> None:
    """运行物化前归档本用户字段侧车（物化会覆盖项目配置，字段本身先存底）。"""

    archive_mas_backup(script_id, user_id, overlay)


# ══════════════════ MaaFW 项目配置（config/ + interface.json） ══════════════════

_INTERFACE_FILE = "interface.json"
"""MaaFW 项目 interface 定义（任务定义与物化 preset 处）"""


def native_backup_root(script_id: str, project_path: str | Path) -> Path:
    """MaaFW 项目配置的**脚本级**归档根：``data/{script_id}/MaaFWBackups/native/{key}``。

    MaaFW 是通用性专项（接入任意 MaaFW 项目，项目属于单个脚本实例）：
    归档生命周期随脚本；``key`` 仍取物理项目根指纹，脚本内换绑项目后旧
    备份不与新项目混淆。
    """

    return (
        Path.cwd()
        / "data"
        / script_id
        / "MaaFWBackups"
        / "native"
        / config_root_key(project_path)
    )


def collect_native_files(project_path: str | Path) -> dict[str, Path]:
    """收集 MaaFW 项目配置文件集（相对键 → 当前路径；缺失项跳过）。

    - ``interface.json``：任务定义与物化 preset 处；
    - ``config/**``：项目配置目录（运行时物化处，排除 resource/ 资产）。
    """

    project_path = Path(project_path)
    files: dict[str, Path] = {}
    interface_path = project_path / _INTERFACE_FILE
    if interface_path.is_file():
        files[_INTERFACE_FILE] = interface_path
    config_dir = project_path / "config"
    if config_dir.is_dir():
        for rel, path in dir_files(config_dir).items():
            files[f"config/{rel}"] = path
    return files


def archive_native_backup(
    script_id: str, project_path: str | Path, force: bool = False
) -> Path | None:
    """归档 MaaFW 项目 ``config/`` 目录 + ``interface.json``（指纹去重）。

    归档落到**脚本级池**（``data/{script_id}/``，生命周期随脚本实例）。
    项目缺 ``config/`` 与 ``interface.json`` 时无可归档内容，返回 ``None``。
    """

    files = collect_native_files(project_path)
    if not files:
        return None
    dest = archive_files(
        files, native_backup_root(script_id, project_path), force=force
    )
    if dest is None:
        logger.info("MaaFW 项目配置无变化，跳过归档")
        return None
    logger.info(f"MaaFW 项目配置已归档: {dest.name}")
    return dest


def list_native_backups(script_id: str, project_path: str | Path) -> list[str]:
    """MaaFW 项目配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(script_id, project_path))


def get_native_backup_dir(
    script_id: str, project_path: str | Path, ts: str
) -> Path | None:
    """取指定时间戳的项目配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(script_id, project_path), ts)


def restore_native_backup(script_id: str, project_path: str | Path, ts: str) -> None:
    """把归档恢复到 MaaFW 项目（恢复前自动归档当前，误恢复可找回）。

    按归档内相对键写回（``interface.json`` → 项目根、``config/*`` →
    项目 ``config/``）；replace 语义：``config/`` 子树整棵按备份替换，残留
    的同前缀文件一并清除，不动 ``resource/`` 等备份外资产。
    """

    backup_dir = get_native_backup_dir(script_id, project_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    project_path = Path(project_path)
    archive_native_backup(script_id, project_path, force=True)
    restore_files(backup_dir, project_path)
    logger.info(f"MaaFW 项目配置已恢复备份 {ts}")


# ══════════════════ 备份预览摘要 ══════════════════

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""


def _summary_text(value) -> str:
    text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def _format_bool(value) -> str:
    return "开启" if bool(value) else "关闭"


def _parse_json_dict(raw) -> dict:
    """解析 JSON 对象字符串字段（TaskSnapshot），非法返回空 dict。"""

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
        except Exception:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def build_overlay_preview(overlay: dict) -> dict:
    """mas 池预览：分区行（MAS 独有 / MaaFW 对应 / 设备覆盖）。"""

    sections: list[dict] = []

    mas_rows: list[dict] = []
    for key in ("Mode", "IfQuickConfig"):
        if key in overlay:
            value = (
                _format_bool(overlay[key])
                if isinstance(overlay[key], bool)
                else _summary_text(overlay[key])
            )
            mas_rows.append({"key": _OVERLAY_FIELD_LABELS[key], "value": value})
    if mas_rows:
        sections.append({"name": "mas-only", "label": "MAS 独有配置", "rows": mas_rows})

    task_rows: list[dict] = []
    if "SelectedPreset" in overlay:
        task_rows.append(
            {"key": "当前方案", "value": _summary_text(overlay["SelectedPreset"])}
        )
    if "TaskSnapshot" in overlay:
        snapshot = _parse_json_dict(overlay["TaskSnapshot"])
        order = snapshot.get("taskOrder") or []
        checked = snapshot.get("taskChecked") or {}
        names = [
            str(name)
            for name in order
            if isinstance(name, str) and bool(checked.get(name, True))
        ]
        names = [name for name in names if name]
        task_rows.append(
            {"key": "已启用任务", "value": "、".join(names) if names else "无"}
        )
    if "Account" in overlay:
        task_rows.append({"key": "账号", "value": mask_account(overlay["Account"])})
    for key in ("Controller", "Resource"):
        if key in overlay:
            task_rows.append(
                {
                    "key": _OVERLAY_FIELD_LABELS[key],
                    "value": _summary_text(overlay[key]),
                }
            )
    if task_rows:
        sections.append({"name": "maafw", "label": "MaaFW 配置", "rows": task_rows})

    device_rows: list[dict] = []
    for key in _OVERLAY_DEVICE_KEYS:
        if key in overlay and str(overlay[key]).strip():
            device_rows.append(
                {
                    "key": _OVERLAY_FIELD_LABELS[key],
                    "value": _summary_text(overlay[key]),
                }
            )
    if device_rows:
        sections.append({"name": "device", "label": "设备覆盖", "rows": device_rows})

    return {"sections": sections}


def build_native_preview(script_id: str, project_path: str | Path, ts: str) -> dict:
    """native 池预览：反读归档内 interface.json 的任务/方案概览。

    MaaFW 项目配置的核心是 interface.json（任务定义、preset 与选中方案）。
    反读 ``tasks`` 定义名列表 + 顶层 ``version``；不深入逐任务参数
    （结构随项目漂移，经「查看详细配置」看原生）。config/ 内 Toolkit
    选项（maa_option.json）为引擎级内部设置，不进预览。
    """

    backup_dir = get_native_backup_dir(script_id, project_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    files = dir_files(backup_dir)
    if not files:
        raise ValueError(f"备份内容为空: {ts}")

    rows: list[dict] = []
    interface_rel = _INTERFACE_FILE
    if interface_rel in files:
        try:
            interface = json.loads(files[interface_rel].read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001 - 坏 JSON 不阻断预览
            interface = None
        if isinstance(interface, dict):
            if interface.get("version") is not None:
                rows.append(
                    {
                        "key": "interface 版本",
                        "value": _summary_text(interface["version"]),
                    }
                )
            tasks = interface.get("task")
            if isinstance(tasks, list) and tasks:
                names = [(t.get("name") if isinstance(t, dict) else t) for t in tasks]
                rows.append({"key": "任务", "value": "、".join(str(n) for n in names)})
    if not rows:
        rows.append({"key": "文件", "value": f"{len(files)} 个（无 interface.json）"})
    return {"sections": [{"name": "maafw", "label": "MaaFW 项目配置", "rows": rows}]}
