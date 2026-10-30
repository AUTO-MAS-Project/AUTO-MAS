"""HSR 历史配置兼容入口；不接触运行中的原生配置。"""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from typing import Any

from app.utils import get_logger

logger = get_logger("HSR 兼容迁移")


def migrate_legacy_user_payload(source: dict[str, Any]) -> None:
    """在通用字段兼容之后、冷态校验之前，就地迁移 HSR 用户旧载荷。"""
    control = source.get("Control", {})
    # 旧直控模式优先于 Info.Base，迁移后仍按原生模式运行。
    if (
        isinstance(control, dict)
        and str(control.get("Mode") or "").strip().lower() == "direct"
    ):
        source["Info"]["Base"] = "native"
    migrate_legacy_stage_values(source.get("Stage"))


def migrate_legacy_stage_values(stage: dict[str, Any] | None) -> dict[str, int]:
    """就地修复能确认编号的旧副本，供 JSON 升级和侧车恢复共用。"""
    migrated_fields = {}
    if not isinstance(stage, dict):
        return migrated_fields
    for name in ("ScriptStage", "ScriptEchoOfWar"):
        migrated, count, _unresolved = migrate_sra_legacy_stage_labels(stage.get(name))
        if migrated is not None:
            stage[name] = migrated
            migrated_fields[name] = count
    return migrated_fields


async def archive_legacy_direct_for_upgrade(
    script_config_path: Path,
) -> dict[str, Any] | None:
    """旧快照停用前留档；失败沿用整份备份与启动告警的降级，不阻断升级。"""
    try:
        # 在事件循环上加载 IO 实现，再交线程执行，避免在线程池冷导入。
        from .tools.legacy_direct import archive_legacy_direct_snapshots

        report = await asyncio.to_thread(
            archive_legacy_direct_snapshots, script_config_path
        )
    except Exception as exc:  # noqa: BLE001 - 留档失败不该挡住启动
        logger.opt(exception=True).warning(f"HSR 旧直控快照留档失败：{exc}")
        return None
    return report.notice() if report.needs_notice else None


_SRA_LEGACY_LABEL_PREFIX = "{'id':"


def migrate_sra_legacy_stage_labels(raw: Any) -> tuple[str | None, int, int]:
    """把旧版误读 SRA toml 留下的副本载荷迁成真实关卡编号。

    旧版把 ``trailblaze_power.toml`` 的内联表 ``{ id, name, result }`` 当成字符串，
    存下的 ``label`` 是 Python 字典 repr、``level`` 是数组位置。repr 里带着真实
    ``id``，据此改写 ``level`` / ``label`` / ``detail`` / ``value``，一次性且无损。
    ``label`` 不是 repr 形态的载荷无从判断编号是否正确，一律不动；按位置重排
    正是要修的错误，不能再犯一遍。

    Args:
        raw: ``Stage.ScriptStage`` 或 ``Stage.ScriptEchoOfWar`` 的原始值。

    Returns:
        ``(迁移后的 JSON 字符串或 None, 迁移条数, 无法确认的旧载荷条数)``；
        没有需要改写的载荷时第一项为 None。无法确认的只统计 ``detail`` 为空、
        ``label`` 又不是 repr 的 SRA 载荷——新版选项都带掉落说明。
    """

    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None, 0, 0
    elif isinstance(raw, dict):
        data = raw
    else:
        return None, 0, 0
    if not isinstance(data, dict):
        return None, 0, 0

    counts = {"migrated": 0, "unresolved": 0}

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                visit(child)
            return
        if not isinstance(node, dict):
            return
        nested = node.get("sra")
        if isinstance(nested, dict):
            _migrate_sra_payload(node, nested, counts)
            return
        for child in node.values():
            visit(child)

    visit(data)
    if not counts["migrated"]:
        return None, 0, counts["unresolved"]
    return (
        json.dumps(data, ensure_ascii=False),
        counts["migrated"],
        counts["unresolved"],
    )


def _migrate_sra_payload(
    payload: dict[str, Any], nested: dict[str, Any], counts: dict[str, int]
) -> None:
    label = str(payload.get("label") or "").strip()
    if not label.startswith(_SRA_LEGACY_LABEL_PREFIX):
        if not str(payload.get("detail") or "").strip():
            counts["unresolved"] += 1
        return
    try:
        item = ast.literal_eval(label)
    except (ValueError, SyntaxError):
        counts["unresolved"] += 1
        return
    level = _safe_int(item.get("id")) if isinstance(item, dict) else None
    name = str(item.get("name") or "").strip() if isinstance(item, dict) else ""
    if level is None or level <= 0 or not name:
        counts["unresolved"] += 1
        return

    nested["level"] = level
    payload["label"] = name
    payload["detail"] = str(item.get("result") or "").strip()
    task_id = str(nested.get("id") or payload.get("category") or "").strip()
    if task_id:
        payload["value"] = f"SRA::{task_id}::{level}"
    counts["migrated"] += 1


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
