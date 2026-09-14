#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""直控模式：实例原生配置的页面编辑原语（强绑定 one_dragon 原始 YAML）。

与用户模式的字段化配置（ConfigItem 为事实源、运行时注入绑定槽）不同，
直控页面直接读写所选实例目录下的 ``game_account.yml`` 与
``one_dragon/_group.yml``——页面即 zzz-od 原生配置编辑器的 web 化入口，
保存立即落盘，不经过注入/备份/恢复，所见即所得。

- 账号字段：数据驱动元数据表（键 = zzz-od YAML 字段名），白名单过滤写回；
- 任务编排：读取原生 ``app_list``（enabled 保持原样）并与应用目录可选项
  合并；保存时只把启用项写回 ``_group.yml``（缺席 = 不加入编排，与
  zzz-od 原生语义一致）。
"""

from typing import Any

from app.models.schema import ComboBoxItem

from .zzz_od_config import (
    DEFAULT_GAME_ACCOUNT,
    ZZZOD_GAME_LANGUAGE_LABELS,
    ZZZOD_GAME_REGION_LABELS,
    instance_dir,
    read_app_group,
    read_game_account,
    read_instance_run,
    write_app_group,
    write_game_account,
    write_instance_run,
)

# 运行实例白名单（one_dragon.yml 的 instance_run 原生取值）
NATIVE_INSTANCE_RUN_OPTIONS = ("仅运行当前", "全部实例")


def _native_default(key: str) -> str:
    """zzz-od 账号字段的默认值（game_account.yml 只持久化非默认字段）。"""

    value = DEFAULT_GAME_ACCOUNT.get(key)
    return "" if value is None else str(value)


# 直控账号字段元数据：key = game_account.yml 字段名；value 在读取时合并
# DEFAULT_GAME_ACCOUNT 默认值（zzz-od 只持久化非默认字段，缺失即默认）。
# 顺序即页面栅格顺序（两列一行）：账号/密码同行（多账号切换需要两者配套）。
_NATIVE_ACCOUNT_FIELDS: list[dict[str, Any]] = [
    {
        "key": "game_region",
        "title": "游戏区服",
        "options": [
            {"label": label, "value": value}
            for value, label in ZZZOD_GAME_REGION_LABELS.items()
        ],
    },
    {"key": "game_path", "title": "游戏路径", "options": []},
    {"key": "account", "title": "账号", "options": []},
    {"key": "password", "title": "密码", "options": []},
    {"key": "bilibili_account_name", "title": "B服账号名", "options": []},
    {
        "key": "game_language",
        "title": "游戏语言",
        "options": [
            {"label": label, "value": value}
            for value, label in ZZZOD_GAME_LANGUAGE_LABELS.items()
        ],
    },
]


def read_native_account_fields(root, slot_idx: int) -> list[dict]:
    """读取实例原生账号配置为字段列表（缺失字段合并默认值，与一条龙 GUI 一致）。"""

    data = read_game_account(instance_dir(root, int(slot_idx)))
    fields: list[dict] = []
    for meta in _NATIVE_ACCOUNT_FIELDS:
        key = str(meta["key"])
        value = data.get(key)
        if value is None:
            value = _native_default(key)
        fields.append(
            {
                "key": key,
                "title": meta["title"],
                "value": "" if value is None else str(value),
                "options": [ComboBoxItem(**o) for o in meta["options"]],
            }
        )
    return fields


def save_native_account_fields(root, slot_idx: int, values: dict[str, str]) -> None:
    """白名单过滤后写回实例原生 game_account.yml（页面所见即所得）。

    与 zzz-od 行为对齐：值未变即跳过（既不强制写空、也不污染原文件）；
    值变化时全部 patch（含「= 默认」的回退操作——清空密码、改国服必须落盘）。

    判断分支：
    - 字段原文件缺失 + 提交值 = 默认 → 跳过（保持文件干净，与原生 GUI 同步）
    - 字段原文件缺失 + 提交值 ≠ 默认 → 落盘（首次设置）
    - 字段原文件有值 + 提交值相同 → 跳过（值未变）
    - 字段原文件有值 + 提交值不同 → 落盘（含清空回默认：删字段）
    """

    from app.utils.io import read_file

    allowed = {meta["key"] for meta in _NATIVE_ACCOUNT_FIELDS}
    unknown = {str(k) for k in values} - allowed
    if unknown:
        raise ValueError(f"不支持的账号配置字段: {', '.join(sorted(unknown))}")

    slot_path = instance_dir(root, int(slot_idx)) / "game_account.yml"
    existing = read_file(slot_path) or {}
    patch: dict[str, str] = {}
    for raw_k, raw_v in values.items():
        key = str(raw_k)
        new_val = str(raw_v)
        default = _native_default(key)
        old_val = existing.get(key)
        if old_val is None:
            # 原文件缺失：值=默认则保持文件干净不写
            if new_val != default:
                patch[key] = new_val
            continue
        # 原文件有值：值未变就跳过
        if str(old_val) == new_val:
            continue
        patch[key] = new_val
    if patch:
        write_game_account(slot_path.parent, patch)


def read_native_tasks(root, slot_idx: int, catalog: list[dict]) -> list[dict]:
    """读取实例原生任务编排并合并应用目录可选项（供前端渲染任务卡片）。

    原生 ``app_list`` 的项按原顺序返回（enabled 保持原样）；其后追加目录中
    未加入编排的默认组任务（enabled=False），让「未加入」也一屏可见。
    """

    name_book = {str(item.get("app_id")): item for item in catalog}
    tasks: list[dict] = []
    known: set[str] = set()
    for item in read_app_group(instance_dir(root, int(slot_idx))):
        app_id = str(item.get("app_id") or "").strip()
        if not app_id:
            continue
        known.add(app_id)
        meta = name_book.get(app_id) or {}
        tasks.append(
            {
                "app_id": app_id,
                "enabled": bool(item.get("enabled")),
                "app_name": str(meta.get("app_name") or app_id),
                "default_group": bool(meta.get("default_group", True)),
                "configurable": bool(meta.get("configurable", False)),
                "jump": bool(meta.get("jump", False)),
                "priority": int(meta.get("priority", 9999)),
            }
        )
    for item in catalog:
        app_id = str(item.get("app_id") or "").strip()
        if not app_id or not item.get("default_group") or app_id in known:
            continue
        tasks.append(
            {
                "app_id": app_id,
                "enabled": False,
                "app_name": str(item.get("app_name") or app_id),
                "default_group": True,
                "configurable": bool(item.get("configurable", False)),
                "jump": bool(item.get("jump", False)),
                "priority": int(item.get("priority", 9999)),
            }
        )
    return tasks


def save_native_tasks(root, slot_idx: int, tasks: list[dict]) -> None:
    """整表写回实例原生任务编排：保留完整顺序与启用状态（含未启用项）。

    对齐一条龙原生队列语义：未启用项可以排在任意位置（关闭 = 原位保留），
    「启用在前、禁用在后」的整理只在用户显式触发时进行。
    """

    write_app_group(instance_dir(root, int(slot_idx)), tasks)


def read_native_instance_run(root) -> str:
    """读取 one_dragon.yml 的 instance_run 原值（仅运行当前 / 全部实例）。

    值缺失或异常时回退「全部实例」——对齐上游 one_dragon_config 的
    InstanceRun.ALL 默认：键缺失时实际行为就是跑全部实例，页面显示必须
    与之一致（回退「仅运行当前」会让显示与行为相反，且用户无法真正
    选定该值——下拉恒等不触发 @change，保存又因值相同被跳过）。
    白名单外的历史值保持原样返回（不覆盖会话期间由 --instance 临时
    切换的值）。
    """

    value = read_instance_run(root)
    if not value:
        return NATIVE_INSTANCE_RUN_OPTIONS[1]
    return str(value)


def save_native_instance_run(root, value: str) -> None:
    """白名单校验后写回 one_dragon.yml 的 instance_run（仅运行当前 / 全部实例）。"""

    if value not in NATIVE_INSTANCE_RUN_OPTIONS:
        raise ValueError(f"不支持的运行实例取值: {value}")
    write_instance_run(root, str(value))
