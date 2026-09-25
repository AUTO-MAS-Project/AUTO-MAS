#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""奇想盒配置恢复服务：MAS 用户字段侧车池 / 上游原生配置池。

池声明只提供**专项知识**（归档什么 + 放哪里 + 恢复语义 + 定制预览），
``list`` / ``snapshot`` / ``read_file`` / ``files`` 兜底全部由基座
（``app.utils.config_restore``）从 ``files`` + ``backup_root`` 声明派生。

- ``mas`` 池（账号级，#879 语义）：奇想盒没有 per-account ConfigFile 目录，
  MAS 面板的一条龙覆盖集与流程开关都是**账号配置字段**（运行时才物化进上游
  ``configs/config.json``），故 mas 池是**纯字段侧车**——归档内唯一文件是
  ``_mas_overlay.json``（覆盖集原始值 + 流程开关 + 展示快照）。恢复 = 读
  侧车回填 ``WhimboxUserConfig``（配置来源只预览不回填，回填旧来源会静默
  翻转 MAS 是否写入），回填后前端重拉表单。池恒按账号分桶——字段是账号级
  数据，与 base 来源无关。
- ``native`` 池（共享）：安装根 ``configs/config.json``，按物理路径指纹
  分桶（项目级，跨脚本实例共享同池）。文件清单与「备份文件」查看由基座从
  ``files`` + ``backup_root`` 派生，专项不拼装。

侧车字段范围（判据：**会注入原生配置的页面字段**进侧车）：``Task.*`` 运行时
物化进上游 OneDragon 节；``OneDragon.IfRunAllAccounts`` 物化为
``change_account``（``auto_close_game`` 由适配层恒置 true，没有页面字段）。
仅由 MAS 自己消费的执行域字段（前后置脚本、通知、剩余天数）不进备份。

归档时机：运行期快照与还原见 ``tools/upstream.py``（``snapshot_pre_run`` /
``ScriptConfig`` 会话进出）；编辑界面进入（native）/ 退出（mas）由前端
``ensure`` 触发。
"""

import json
import uuid
from pathlib import Path

from app.utils import get_logger
from app.utils.config_archive import (
    OVERLAY_SIDECAR_NAME,
    archive_files,
    get_backup_dir,
    read_overlay_sidecar,
)
from app.utils.config_restore import ConfigRestorePool, RestoreContext

from .upstream import WheelAssetsConfigSurface, parse_override_map

logger = get_logger("奇想盒 配置恢复")

_INFO_SECTION = "Info"
"""侧车里只作来源标注的配置段（Mode 只预览不回填）"""


def _surface(ctx: RestoreContext) -> WheelAssetsConfigSurface:
    """从脚本配置取安装根构造配置面；根路径未配置时报可操作错误。"""

    raw = str(ctx.script_config.get("Info", "RootPath") or "").strip()
    if not raw:
        raise ValueError("请先在脚本设置中填入奇想盒安装目录")
    return WheelAssetsConfigSurface(Path(raw))


def _surface_or_none(ctx: RestoreContext) -> WheelAssetsConfigSurface | None:
    """只读回调用的静默降级版本：未配置安装目录返回 ``None``。

    与基座 ``backup_root`` 返回 ``None`` 的 None 防御语义对齐——用户未配置
    安装目录时编辑页的 ``ensure`` / 预览不该报错（恢复仍走 :func:`_surface`，
    那是显式用户操作，报错合理）。
    """

    raw = str(ctx.script_config.get("Info", "RootPath") or "").strip()
    return WheelAssetsConfigSurface(Path(raw)) if raw else None


def _user_guard(ctx: RestoreContext) -> None:
    """恢复守卫：目标用户必须存在，避免把字段回填进孤儿目录。"""

    if uuid.UUID(ctx.user_id) not in ctx.script_config.UserData:
        raise ValueError("奇想盒用户不存在，请刷新后重试")


def _read_overlay(ctx: RestoreContext) -> dict:
    """读 MAS 页面字段（会注入原生配置的部分 + 来源标注）。"""

    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    return {
        _INFO_SECTION: {"Mode": user.get("Info", "Mode")},
        "OneDragon": {
            "IfRunAllAccounts": bool(user.get("OneDragon", "IfRunAllAccounts")),
        },
        "Task": {
            "Tasks": str(user.get("Task", "Tasks") or "{}"),
            "Options": str(user.get("Task", "Options") or "{}"),
        },
    }


def _group_restore(overlay: dict) -> dict[str, dict]:
    """把侧车分组为可回填的结构（来源段与展示快照排除）。

    来源（``Info.Mode``）回填旧值会静默翻转「MAS 是否写入上游」，恢复以
    当前来源为准；展示快照是预览派生数据，无回填语义。
    """

    return {
        section: dict(values)
        for section, values in overlay.items()
        if section in ("OneDragon", "Task") and isinstance(values, dict)
    }


def _display_names(surface: WheelAssetsConfigSurface | None) -> tuple[dict, dict]:
    """取上游目录的键→显示名映射（catalog 不可用时返回空映射，展示降级用原始键）。

    键是稳定的上游配置键、显示名只是文案，故预览读当前目录即可——上游升级
    改文案时旧备份跟着显示新文案，不会译错语义。
    """

    if surface is None:
        return {}, {}
    try:
        catalog = surface.read_catalog()
    except Exception as e:  # noqa: BLE001 - 目录不可用时展示降级，不阻断归档
        logger.warning(f"读取奇想盒任务目录失败，预览降级为原始键: {e}")
        return {}, {}
    return (
        {step.key: step.display for step in catalog.steps},
        {option.key: option.display for option in catalog.options},
    )


def _build_display(overlay: dict, surface: WheelAssetsConfigSurface | None) -> dict:
    """给侧车补展示快照（``Display`` 键；回填由 :func:`_group_restore` 排除）。

    只列覆盖集里**用户动过**的项（未动的键运行时按上游模板默认值走，不属
    于这份备份的内容）。
    """

    step_names, option_names = _display_names(surface)
    tasks = parse_override_map(overlay.get("Task", {}).get("Tasks"))
    options = parse_override_map(overlay.get("Task", {}).get("Options"))
    return {
        "steps": [
            {"key": key, "display": step_names.get(key, key), "value": bool(value)}
            for key, value in tasks.items()
        ],
        "options": [
            {"key": key, "display": option_names.get(key, key), "value": str(value)}
            for key, value in options.items()
        ],
    }


def _on_off(value: object) -> str:
    return "开启" if value else "关闭"


# ══ mas 池：MAS 用户字段侧车（纯字段，恒按用户分桶） ══════════════════════


def _mas_root(ctx: RestoreContext) -> Path:
    """MAS 池归档根：``data/{script_id}/WhimboxBackups/mas/{user_id}``。"""

    return Path.cwd() / "data" / ctx.script_id / "WhimboxBackups" / "mas" / ctx.user_id


async def _mas_files(ctx: RestoreContext) -> dict[str, str] | None:
    """归档内容 = MAS 页面字段侧车（内存 JSON，免临时文件）。"""

    _user_guard(ctx)
    overlay = _read_overlay(ctx)
    overlay["Display"] = _build_display(overlay, _surface_or_none(ctx))
    return {OVERLAY_SIDECAR_NAME: json.dumps(overlay, ensure_ascii=False, indent=2)}


async def _mas_backup_root(ctx: RestoreContext) -> Path:
    return _mas_root(ctx)


async def _preview_mas(ctx: RestoreContext, ts: str) -> dict:
    """预览载荷：来源标注 + 流程开关 + 覆盖集（展示快照，可读性优先）。"""

    backup_dir = get_backup_dir(_mas_root(ctx), ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    overlay = read_overlay_sidecar(backup_dir)
    if overlay is None:
        return {"sections": []}

    sections: list[dict] = []
    mode = overlay.get(_INFO_SECTION, {}).get("Mode")
    if mode:
        sections.append(
            {
                "name": "mas-only",
                "label": "MAS 独有配置",
                "rows": [{"key": "配置来源", "value": str(mode)}],
            }
        )

    onedragon = overlay.get("OneDragon", {})
    if onedragon:
        sections.append(
            {
                "name": "onedragon",
                "label": "一条龙流程",
                "rows": [
                    {
                        "key": "循环全部游戏账号",
                        "value": _on_off(onedragon.get("IfRunAllAccounts")),
                    },
                ],
            }
        )

    display = overlay.get("Display", {})
    steps = display.get("steps") if isinstance(display, dict) else None
    if isinstance(steps, list) and steps:
        sections.append(
            {
                "name": "steps",
                "label": "已改动的步骤开关",
                "rows": [
                    {
                        "key": str(item.get("display", "")),
                        "value": _on_off(item.get("value")),
                    }
                    for item in steps
                    if isinstance(item, dict)
                ],
            }
        )

    options = display.get("options") if isinstance(display, dict) else None
    if isinstance(options, list) and options:
        sections.append(
            {
                "name": "options",
                "label": "已设置的参数",
                "rows": [
                    {
                        "key": str(item.get("display", "")),
                        "value": str(item.get("value", "")),
                    }
                    for item in options
                    if isinstance(item, dict)
                ],
            }
        )

    return {"sections": sections}


async def _restore_mas(ctx: RestoreContext, ts: str) -> None:
    _user_guard(ctx)
    # 恢复前把当前字段终态存底（force），误恢复可找回
    overlay = _read_overlay(ctx)
    overlay["Display"] = _build_display(overlay, _surface_or_none(ctx))
    archive_files(
        {OVERLAY_SIDECAR_NAME: json.dumps(overlay, ensure_ascii=False, indent=2)},
        _mas_root(ctx),
        force=True,
    )

    backup_dir = get_backup_dir(_mas_root(ctx), ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    restored = read_overlay_sidecar(backup_dir)
    if not restored:
        return

    user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
    # 回填后前端重拉表单，否则旧表单值下次保存会静默覆盖恢复结果
    await user.update(_group_restore(restored))
    logger.info(f"用户 {ctx.user_id} 的 MAS 字段已恢复备份 {ts}")


# ══ native 池：上游 config.json（文件清单与 read_file 由基座派生） ═════════


async def _native_root(ctx: RestoreContext) -> Path | None:
    """归档根按 config.json 物理路径指纹分桶；未配置安装目录返回 ``None``。"""

    surface = _surface_or_none(ctx)
    return surface.backup_root() if surface is not None else None


async def _native_files(ctx: RestoreContext) -> dict[str, Path] | None:
    """归档内容 = 安装根 ``configs/config.json``（不存在返回 ``None``）。"""

    surface = _surface_or_none(ctx)
    if surface is None or not surface.config_file_exists():
        return None
    return {surface.config_path.name: surface.config_path}


async def _preview_native(ctx: RestoreContext, ts: str) -> dict:
    """预览载荷：config.json 的节/键数摘要（文件清单由基座注入，不在此拼装）。"""

    surface = _surface_or_none(ctx)
    if surface is None:
        return {"sections": []}
    backup_dir = get_backup_dir(surface.backup_root(), ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")

    rows = []
    for name, path in sorted(surface.backup_dir_files(ts).items()):
        summary = ""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                sections = sum(1 for v in data.values() if isinstance(v, dict) and v)
                keys = sum(len(v) for v in data.values() if isinstance(v, dict))
                summary = f"{sections} 节 / {keys} 键"
        except (OSError, json.JSONDecodeError):
            pass
        rows.append({"key": name, "value": summary})
    return {"sections": [{"name": "config", "label": "奇想盒原生配置", "rows": rows}]}


async def _restore_native(ctx: RestoreContext, ts: str) -> None:
    _surface(ctx).restore_entry(ts)


RESTORE_POOLS = [
    ConfigRestorePool(
        key="mas",
        kind="user",
        mas_mode="sidecar_only",
        files=_mas_files,
        backup_root=_mas_backup_root,
        preview=_preview_mas,
        restore=_restore_mas,
    ),
    ConfigRestorePool(
        key="native",
        kind="script",
        files=_native_files,
        backup_root=_native_root,
        preview=_preview_native,
        restore=_restore_native,
    ),
]
