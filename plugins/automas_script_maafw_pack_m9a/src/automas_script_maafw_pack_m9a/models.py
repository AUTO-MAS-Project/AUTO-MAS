from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class M9APeriodRule(BaseModel):
    task: str
    period: Literal["daily", "weekly", "monthly"]


class M9APackDefinition(BaseModel):
    """M9A project pack 定义，对应文档 6.3 MaaFWProjectPackDefinition。"""

    key: str = "m9a"
    display_name: str = "M9A"
    project_repo: str | None = None
    interface_path: str = "interface.json"
    supported_controllers: list[str] = Field(default_factory=lambda: ["adb", "win32"])
    default_controller: str = "adb"
    default_resource: str | None = None
    default_preset: str | None = None
    default_task_queue: list[str] | None = None
    period_rules: list[M9APeriodRule] = Field(default_factory=list)
    reserved_task_semantics: dict[str, Any] = Field(default_factory=dict)
    icon: str | None = "automas_script_maafw_pack_m9a:assets/m9a.png"
    notes: str | None = None
    # 额外能力声明（非 6.3 标准字段）
    framework: str = "maafw"
    capabilities: list[str] = Field(default_factory=list)


class M9ANotificationContent(BaseModel):
    title: str
    text: str
    html: str | None = None


class M9AMigrationDraft(BaseModel):
    script: dict[str, Any]
    users: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
