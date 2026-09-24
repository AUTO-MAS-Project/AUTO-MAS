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

"""M9A 配置备份归档：MAS 用户字段侧车 / M9A 本体 config/ 目录。

备份时机（MAS「动手前」）：

- 任务启动（manager ``prepare``）：``native`` 归档 M9A 安装目录 ``config/``
  当前状态（整目录）——随后非直控运行会换出整目录、重写 ``instances/
  default.json``，直控+快速配置会写入实例配置，归档必须在任何写入前；
- 编辑界面进入（前端 ensure）：``native`` 捕捉「MAS 操作前原始态」
  （用户可能刚在 M9A GUI 里改过）；
- 编辑界面退出（前端 ensure）：``mas`` 归档 MAS 编辑页核心字段终态。

M9A 没有 per-user ConfigFile 目录：MAS 用户配置是字段（Info / Task.Queue，
存共享 ScriptConfig.json），运行时经 ``build_config`` 写入原生 ``instances/
default.json``。因此 ``mas`` 池是**纯字段侧车**（无目录部分），恢复即字段
回填 M9AUserConfig。侧车同时保存原始值（Queue JSON 串等，回填用）与展示
快照（任务选项翻译成中文文本，预览零本体依赖）；展示快照在归档时经
interface.json 任务定义翻译，任务定义不可用时降级保存原始值，预览仍可读。

时间戳快照、指纹去重、保留清理与整目录恢复的通用逻辑由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
M9A 特有的侧车、恢复语义（恢复前强制归档当前）与预览摘要。
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

logger = get_logger("M9A 配置备份")

# ══════════════════ MAS 用户字段侧车（纯侧车，无目录） ══════════════════

_OVERLAY_INFO_KEYS = ("Mode", "IfQuickConfig", "Resource", "Account")
"""MAS 编辑页核心字段（UserData.Info，运行时经 build_config 写入原生实例）"""

_OVERLAY_TASK_KEYS = ("Queue",)
"""任务队列（UserData.Task，JSON 串；队列顺序即运行顺序）"""

_OVERLAY_KEY_GROUPS = {"Info": _OVERLAY_INFO_KEYS, "Task": _OVERLAY_TASK_KEYS}
"""侧车字段的配置段归属（两组键名无交集，侧车内平铺存储）"""

_OVERLAY_KEY_GROUP = {
    key: group for group, keys in _OVERLAY_KEY_GROUPS.items() for key in keys
}

_OVERLAY_PREVIEW_ONLY_KEYS = {"Mode"}
"""仅预览不回填的字段：配置来源决定运行下发方式，恢复时以当前值为准"""

_DISPLAY_KEY = "Display"
"""展示快照专用键（选项中文文本，预览用；不回填、不参与字段分组）"""


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
    """把平铺的侧车字段按配置段分组（恢复回填 M9AUserConfig 用）。

    仅预览字段（配置来源）与展示快照不回填：回填旧来源会静默翻转
    脚本态/用户态/直控。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS or key == _DISPLAY_KEY:
            continue
        grouped.setdefault(_OVERLAY_KEY_GROUP.get(key, "Task"), {})[key] = value
    return grouped


def build_queue_display(queue: list, task_loader=None) -> list[dict]:
    """把任务队列翻译成展示快照（选项值转中文文本，预览零本体依赖）。

    ``queue`` 是 M9ATaskQueueItem 列表（``{name, options}``，options 为
    ``{name, index, selected_cases?, input_values?, sub_options?}``）。
    ``task_loader`` 提供任务定义（``get_full_definition``）时把 index 类
    选项翻译成中文 case 名；不可用或任务定义缺失时降级保存原始值。

    返回 ``[{name, options: [{name, value}]}]``。
    """

    display: list[dict] = []

    def _option_value(option: dict, opt_def: dict | None) -> str:
        # checkbox 的选中项与输入值是自描述文本（case 名/输入名），不依赖定义
        if isinstance(option.get("selected_cases"), list):
            return "、".join(str(case) for case in option["selected_cases"]) or "无"
        if isinstance(option.get("input_values"), dict) and option["input_values"]:
            return "；".join(
                f"{key}={value}" for key, value in option["input_values"].items()
            )
        cases = opt_def.get("cases") if isinstance(opt_def, dict) else None
        if isinstance(cases, list) and cases:
            index = option.get("index", 0)
            if isinstance(index, int) and 0 <= index < len(cases):
                return str(cases[index].get("name", index))
        return str(option.get("index", ""))

    def _options_rows(options: list, option_definitions: dict) -> list[dict]:
        rows: list[dict] = []
        for option in options:
            if not isinstance(option, dict):
                continue
            name = str(option.get("name", ""))
            opt_def = option_definitions.get(name)
            rows.append({"name": name, "value": _option_value(option, opt_def)})
            sub_options = option.get("sub_options")
            if isinstance(sub_options, list) and sub_options:
                rows.extend(_options_rows(sub_options, option_definitions))
        return rows

    for item in queue:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        options = item.get("options")
        task_def = None
        if task_loader is not None:
            try:
                task_def = task_loader.get_full_definition(name)
            except Exception:  # noqa: BLE001 - 定义缺失时降级为原始值展示
                task_def = None
        option_definitions = (
            task_def.get("_option_definitions") if isinstance(task_def, dict) else None
        ) or {}
        rows = (
            _options_rows(options, option_definitions)
            if isinstance(options, list)
            else []
        )
        display.append({"name": name, "options": rows})
    return display


def build_display_overlay(overlay: dict, task_loader=None) -> dict:
    """给侧车补展示快照（``Display`` 键；回填由 :func:`group_overlay` 排除）。"""

    overlay = dict(overlay)
    queue_raw = overlay.get("Queue")
    try:
        queue = json.loads(queue_raw) if isinstance(queue_raw, str) else queue_raw
    except Exception:  # noqa: BLE001 - 坏 JSON 不阻断归档，展示降级为空
        queue = []
    overlay[_DISPLAY_KEY] = {
        "Queue": build_queue_display(
            queue if isinstance(queue, list) else [], task_loader
        )
    }
    return overlay


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/M9ABackups/mas/{user_id}``。

    恒按用户分桶——侧车是用户级字段，脚本态多用户共享同一份字段源
    （共享 ScriptConfig.json），按 owner 分桶会把各自的字段快照混在一起。
    """

    return Path.cwd() / "data" / script_id / "M9ABackups" / "mas" / user_id


def native_backup_root(config_path: str | Path) -> Path:
    """M9A 原生配置的项目级归档目录：``data/M9ABackups/native/{key}``。

    ``key`` 是物理配置根的指纹——同一份物理安装无论被哪个脚本实例引用
    都归同一个池；跨脚本共享、不随脚本删除。
    """

    return Path.cwd() / "data" / "M9ABackups" / "native" / config_root_key(config_path)


def archive_mas_backup(
    script_id: str, user_id: str, overlay: dict, force: bool = False
) -> Path | None:
    """归档 MAS 页面核心字段侧车到用户池（指纹去重，无变化跳过）。

    M9A 无 per-user 目录，侧车是归档内唯一文件；只改表单也会因侧车内容
    变化新建归档（内存 JSON 写入，免临时文件）。``overlay`` 侧车原样保存
    （含 ``Display`` 展示快照）；``force=True`` 恢复前存底（不清理历史
    条目；内容与最新份一致时同样跳过——当前字段已存放在该份备份中，误
    恢复可从它找回）。
    """

    dest = archive_files(
        {OVERLAY_SIDECAR_NAME: json.dumps(overlay, ensure_ascii=False, indent=2)},
        mas_backup_root(script_id, user_id),
        force=force,
    )
    if dest is None:
        logger.info("用户 {} 的 MAS 配置无变化，跳过归档", user_id)
        return None
    logger.info("用户 {} 的 MAS 配置已归档: {}", user_id, dest.name)
    return dest


def list_mas_backups(script_id: str, user_id: str) -> list[str]:
    """用户池的全部归档时间戳（倒序，最新在前）。"""

    return list_times(mas_backup_root(script_id, user_id))


def get_mas_backup_dir(script_id: str, user_id: str, ts: str) -> Path | None:
    """取用户池指定时间戳的归档目录；不存在返回 None。"""

    return get_backup_dir(mas_backup_root(script_id, user_id), ts)


def restore_mas_backup(script_id: str, user_id: str, ts: str) -> dict | None:
    """读取用户池归档的侧车（供调用方回填 M9AUserConfig）。

    mas 池无目录目标，无需先清后拷；恢复前的字段终态由调用方在
    ``restore`` 回调里先归档当前侧车（force）再读取本备份。
    返回侧车 dict；旧版备份（无侧车）或备份不存在语义见各函数。
    """

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    restored = read_overlay_sidecar(backup_dir)
    if restored is not None:
        logger.info("用户 {} 的 MAS 配置已读取备份 {}", user_id, ts)
    return restored


# ══════════════════ M9A 本体原生配置（安装目录 config/ 整目录） ══════════════════


def collect_native_files(config_path: str | Path) -> dict[str, Path]:
    """收集 M9A 安装目录 config/ 文件集（目录缺失或为空返回空 dict）。

    供声明式池声明归档内容（``files`` 回调）；:func:`archive_native_backup`
    亦复用本函数。
    """

    config_path = Path(config_path)
    if not config_path.is_dir() or not any(config_path.iterdir()):
        return {}
    return dir_files(config_path)


def archive_native_backup(config_path: Path, force: bool = False) -> Path | None:
    """归档 M9A 安装目录 config/ 当前状态（整目录）。

    归档落到项目级池（按物理配置根指纹分桶），与脚本实例解耦。
    目录不存在或为空时无可归档内容，返回 ``None``。
    """

    files = collect_native_files(config_path)
    if not files:
        return None
    dest = archive_files(files, native_backup_root(config_path), force=force)
    if dest is None:
        logger.info("M9A 原生配置无变化，跳过归档")
        return None
    logger.info("M9A 原生配置已归档: {}", dest.name)
    return dest


def list_native_backups(config_path: str | Path) -> list[str]:
    """M9A 原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(config_path))


def get_native_backup_dir(config_path: str | Path, ts: str) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(config_path), ts)


def restore_native_backup(config_path: Path, ts: str) -> None:
    """把归档恢复到 M9A 安装目录 config/（恢复前自动归档当前，误恢复可找回）。"""

    backup_dir = get_native_backup_dir(config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    config_path = Path(config_path)
    # 恢复前强制归档当前——「恢复前的配置」在列表里有明确的时间戳条目
    archive_native_backup(config_path, force=True)
    restore_dir(native_backup_root(config_path), ts, config_path)
    logger.info("M9A 原生配置已恢复备份 {}", ts)


# ══════════════════ 备份预览摘要 ══════════════════

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""


def _summary_text(value) -> str:
    """摘要标量值转展示文本（超长截断）。"""

    text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def build_overlay_preview(overlay: dict) -> dict:
    """侧车字段的分区预览（mas 池预览用，纯读）。

    返回分区结构（前端 ``#preview`` 插槽按 ``sections`` 渲染）：

    - **MAS 独有配置**：M9A GUI 无对应概念的字段（配置文件来源/快速配置）；
    - **M9A 配置**：与 M9A GUI 概念对应的字段（服务器资源/账号），加
      「已启用任务」罗列行；
    - **任务配置详情**：每个队列任务一组（任务名 + 选项中文文本行，来自
      展示快照；旧版侧车无展示快照时降级原始值）。

    账号脱敏展示；分区无行时整体省略。
    """

    def _row(key: str, value) -> dict:
        return {"key": key, "value": _summary_text(value)}

    sections: list[dict] = []

    mas_rows: list[dict] = []
    if "Mode" in overlay:
        mas_rows.append(_row("配置文件来源", overlay["Mode"]))
    if mas_rows:
        sections.append({"name": "mas-only", "label": "MAS 独有配置", "rows": mas_rows})

    m9a_rows: list[dict] = []
    if "Resource" in overlay:
        m9a_rows.append(_row("服务器资源", overlay["Resource"]))
    if overlay.get("Account"):
        m9a_rows.append(_row("账号", mask_account(overlay["Account"])))
    queue_display = (overlay.get(_DISPLAY_KEY) or {}).get("Queue")
    if isinstance(queue_display, list) and queue_display:
        names = "、".join(
            str(item.get("name", ""))
            for item in queue_display
            if isinstance(item, dict)
        )
        m9a_rows.append(_row("已启用任务", names or "无"))
    if m9a_rows:
        sections.append({"name": "m9a", "label": "M9A 配置", "rows": m9a_rows})

    task_groups: list[dict] = []
    if isinstance(queue_display, list):
        for item in queue_display:
            if not isinstance(item, dict):
                continue
            rows = [
                {
                    "key": str(option.get("name", "")),
                    "value": _summary_text(option.get("value", "")),
                }
                for option in item.get("options", [])
                if isinstance(option, dict)
            ]
            if rows:
                task_groups.append({"name": str(item.get("name", "")), "rows": rows})
    if task_groups:
        sections.append(
            {"name": "task-details", "label": "任务配置详情", "groups": task_groups}
        )

    return {"sections": sections}


def build_native_preview(config_path: Path, ts: str, task_loader=None) -> dict:
    """原生配置归档预览（native 池，纯读）：逐个反读 ``instances/*.json``。

    M9A GUI 的实例配置是 ``instances/`` 下任意命名的 JSON（default.json
    只是其中之一），全部反读——每个实例一条（ZzzOd 实例折叠列表同语义，
    前端按 ``instances`` 渲染折叠面板）：``name`` 取 JSON 内 ``InstanceName``
    （文件名仅作缺失回退，M9A GUI 的实例文件名是哈希），``rows`` 为服务器
    资源/已启用任务/账号（切换账号任务 data，脱敏）/连接地址/控制器，
    ``details`` 为任务配置详情（选项经任务定义翻译，不可用时降级原始值）。
    与 mas 池同口径（同概念同标签）；config.json 全局设置与随版本漂移的
    内部字段不进预览。
    """

    backup_dir = get_native_backup_dir(config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")

    instance_rels = sorted(
        rel
        for rel in dir_files(backup_dir)
        if rel.startswith("instances/") and rel.endswith(".json")
    )

    instances: list[dict] = []
    for rel in instance_rels:
        fallback_name = Path(rel).stem
        try:
            data = json.loads((backup_dir / rel).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 坏 JSON 不阻断预览
            data = None
        if not isinstance(data, dict):
            continue
        details: list[dict] = []
        task_items = data.get("TaskItems")
        if isinstance(task_items, list) and task_items:
            option_definitions = _load_option_definitions(task_items, task_loader)
            details = _native_task_detail_groups(task_items, option_definitions)
        name = str(data.get("InstanceName") or "").strip() or fallback_name
        instances.append(
            {"name": name, "rows": _native_instance_rows(data), "details": details}
        )

    return {"instances": instances}


def _native_instance_rows(data: dict) -> list[dict]:
    """单个实例配置 → 摘要行（标签与 mas 池同口径）。"""

    rows: list[dict] = []
    if data.get("Resource") is not None:
        rows.append({"key": "服务器资源", "value": _summary_text(data["Resource"])})
    task_items = data.get("TaskItems")
    if isinstance(task_items, list) and task_items:
        names = []
        account = ""
        for item in task_items:
            if not isinstance(item, dict):
                continue
            names.append(str(item.get("name", "")))
            for option in item.get("option") or []:
                if (
                    isinstance(option, dict)
                    and option.get("name") == "目标账号(可选)"
                    and isinstance(option.get("data"), dict)
                ):
                    account = str(option["data"].get("账号", ""))
        rows.append(
            {"key": "已启用任务", "value": "、".join(filter(None, names)) or "无"}
        )
        if account:
            rows.append({"key": "账号", "value": mask_account(account)})
    if data.get("Connect.Address"):
        rows.append(
            {"key": "连接地址", "value": _summary_text(data["Connect.Address"])}
        )
    if data.get("CurrentControllerName"):
        rows.append(
            {"key": "控制器", "value": _summary_text(data["CurrentControllerName"])}
        )
    return rows


def _load_option_definitions(task_items: list, task_loader) -> dict:
    """从任务定义收集反读所需选项定义（任务名 → _option_definitions）。

    任务定义不可用（未配置路径/加载失败）时返回空 dict，反读降级原始值。
    """

    definitions: dict = {}
    if task_loader is None:
        return definitions
    for item in task_items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or name in definitions:
            continue
        try:
            task_def = task_loader.get_full_definition(name)
        except Exception:  # noqa: BLE001 - 定义缺失时降级
            task_def = None
        if isinstance(task_def, dict):
            definitions[name] = task_def.get("_option_definitions") or {}
    return definitions


def _native_task_detail_groups(
    task_items: list, option_definitions: dict
) -> list[dict]:
    """TaskItems → 任务配置详情分组（标签与取值同 mas 池口径）。"""

    groups: list[dict] = []

    def _option_value(option: dict, opt_def: dict | None) -> str:
        # checkbox 的选中项与输入值是自描述文本（case 名/输入名），不依赖定义
        if isinstance(option.get("selected_cases"), list):
            return "、".join(str(case) for case in option["selected_cases"]) or "无"
        if isinstance(option.get("data"), dict) and option["data"]:
            return "；".join(f"{key}={value}" for key, value in option["data"].items())
        cases = opt_def.get("cases") if isinstance(opt_def, dict) else None
        if isinstance(cases, list) and cases:
            index = option.get("index", 0)
            if isinstance(index, int) and 0 <= index < len(cases):
                return str(cases[index].get("name", index))
        return str(option.get("index", ""))

    for item in task_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        rows: list[dict] = []
        for option in item.get("option") or []:
            if not isinstance(option, dict):
                continue
            option_name = str(option.get("name", ""))
            if option_name == "目标账号(可选)":
                continue  # 账号已在上方单独成行（脱敏）
            opt_def = (option_definitions.get(name) or {}).get(option_name)
            rows.append(
                {
                    "key": option_name,
                    "value": _summary_text(_option_value(option, opt_def)),
                }
            )
            sub_options = option.get("sub_options")
            if isinstance(sub_options, list):
                for sub in sub_options:
                    if isinstance(sub, dict):
                        sub_def = (option_definitions.get(name) or {}).get(
                            str(sub.get("name", ""))
                        )
                        rows.append(
                            {
                                "key": str(sub.get("name", "")),
                                "value": _summary_text(_option_value(sub, sub_def)),
                            }
                        )
        if rows:
            groups.append({"name": name, "rows": rows})
    return groups
