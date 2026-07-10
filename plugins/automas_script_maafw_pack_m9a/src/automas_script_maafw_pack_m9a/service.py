from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import (
    M9AMigrationDraft,
    M9ANotificationContent,
    M9APackDefinition,
    M9APeriodRule,
)


PERIOD_RULES = [
    M9APeriodRule(task="Psychube", period="daily"),
    M9APeriodRule(task="SleepDream", period="monthly"),
]

DEFAULT_TASK_QUEUE = [
    "StartUp",
    "Psychube",
    "SleepDream",
    "Award",
    "CloseDown",
]

RESERVED_TASK_SEMANTICS = {
    "Psychube": {"period": "daily", "label": "每日心相"},
    "SleepDream": {"period": "monthly", "label": "深眠浅梦"},
}


class M9APackService:
    """maafw.pack.m9a.v1 service."""

    def get_definition(self) -> M9APackDefinition:
        return M9APackDefinition(
            key="m9a",
            display_name="M9A",
            project_repo="MAA1999/M9A",
            interface_path="interface.json",
            supported_controllers=["adb", "win32"],
            default_controller="adb",
            default_resource="resource",
            default_preset="日常任务",
            default_task_queue=DEFAULT_TASK_QUEUE,
            period_rules=PERIOD_RULES,
            reserved_task_semantics=RESERVED_TASK_SEMANTICS,
            icon="automas_script_maafw_pack_m9a:assets/m9a.png",
            notes="M9A 专项插件包 — 重返未来：1999 自动化",
            framework="maafw",
            capabilities=[
                "period_rules",
                "notification_translation",
                "create_only_migration",
            ],
        )

    def translate_notification(
        self,
        result: Any,
        *,
        script_name: str = "M9A",
        user_name: str = "",
        started_at: str | None = None,
        ended_at: str | None = None,
    ) -> M9ANotificationContent:
        payload = _to_mapping(result)
        success = bool(payload.get("success"))
        completed_tasks = [
            str(item)
            for item in payload.get("completedTasks", [])
            if str(item).strip()
        ]
        failed_task = str(payload.get("failedTask") or "").strip()
        error_message = str(payload.get("errorMessage") or "").strip()

        subject = user_name or script_name or "M9A"
        title = f"{subject} 的 M9A 任务已完成" if success else f"{subject} 的 M9A 任务未完成"
        lines = []
        if started_at or ended_at:
            lines.append(f"开始时间: {started_at or '-'}")
            lines.append(f"结束时间: {ended_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if completed_tasks:
            lines.append("已完成任务: " + ", ".join(completed_tasks))
        else:
            lines.append("已完成任务: 无")
        if failed_task:
            lines.append(f"失败任务: {failed_task}")
        if error_message:
            lines.append(f"失败原因: {error_message}")
        if not error_message and not success:
            lines.append("失败原因: MaaFW runner 未返回成功状态")
        return M9ANotificationContent(title=title, text="\n".join(lines))

    def create_migration_draft(
        self,
        old_script_config: dict[str, Any] | None,
        old_user_configs: list[dict[str, Any]] | None = None,
        *,
        script_name: str = "M9A",
    ) -> M9AMigrationDraft:
        warnings = [
            "迁移入口只创建新插件配置草稿，不覆盖旧 M9A 配置。",
            "项目来源、controller、resource、preset、任务队列和模板必须通过通用 MaaFW 流程现拉。",
        ]
        script_payload = {
            "type": "PluginScriptConfig",
            "Meta": {"PluginTypeKey": "M9A"},
            "Info": {"Name": script_name},
            "PluginData": {
                "Config": {
                    "pack": "m9a",
                    "legacy": _filter_legacy_script_fields(old_script_config or {}),
                }
            },
        }

        users: list[dict[str, Any]] = []
        for index, old_user in enumerate(old_user_configs or [], start=1):
            user_name = _extract_user_name(old_user) or f"M9A 用户 {index}"
            users.append(
                {
                    "type": "PluginUserConfig",
                    "Meta": {"PluginTypeKey": "M9A"},
                    "Info": {"Name": user_name},
                    "PluginData": {
                        "Config": {
                            "pack": "m9a",
                            "legacy": _filter_legacy_user_fields(old_user),
                        }
                    },
                }
            )

        return M9AMigrationDraft(script=script_payload, users=users, warnings=warnings)


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        data = value.model_dump(mode="json")
        return data if isinstance(data, dict) else {}
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}


def _filter_legacy_script_fields(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": _nested_get(value, "Info", "Path"),
        "autoUpdate": _nested_get(value, "Run", "IfAutoUpdateAfterQueue"),
        "weeklyTasks": _nested_get(value, "Run", "WeeklyOnceTasks"),
        "monthlyTasks": _nested_get(value, "Run", "MonthlyOnceTasks"),
    }


def _filter_legacy_user_fields(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _extract_user_name(value),
        "taskQueue": _nested_get(value, "Task", "Queue"),
        "notifyEnabled": _nested_get(value, "Notify", "Enabled"),
    }


def _nested_get(value: dict[str, Any], section: str, key: str) -> Any:
    section_value = value.get(section)
    if isinstance(section_value, dict):
        return section_value.get(key)
    return None


def _extract_user_name(value: dict[str, Any]) -> str:
    info = value.get("Info")
    if isinstance(info, dict):
        name = info.get("Name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    name = value.get("name")
    return name.strip() if isinstance(name, str) else ""
