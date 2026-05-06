#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ServiceSpec(BaseModel):
    """插件服务声明模型。"""

    model_config = ConfigDict(extra="forbid")

    provides: list[str] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)
    wants: list[str] = Field(default_factory=list)

    @field_validator("provides", "needs", "wants", mode="before")
    @classmethod
    def norm(cls, raw: Any) -> list[str]:
        """归一化服务声明，支持 str/list/tuple/set 输入。"""
        if raw is None:
            return []

        items: list[Any]
        if isinstance(raw, str):
            items = [raw]
        elif isinstance(raw, (list, tuple, set)):
            items = list(raw)
        else:
            raise ValueError("服务声明仅支持字符串或字符串列表")

        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, str):
                raise ValueError("服务声明项必须是字符串")
            name = item.strip()
            if not name:
                continue
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result

    @classmethod
    def load(cls, plugin_class: type[Any]) -> "ServiceSpec":
        """从插件类读取服务声明并构建标准化模型。"""
        return cls.model_validate(
            {
                "provides": getattr(plugin_class, "provides", None),
                "needs": getattr(plugin_class, "needs", None),
                "wants": getattr(plugin_class, "wants", None),
            }
        )

    def sets(self) -> tuple[set[str], set[str], set[str]]:
        """以 set 形式返回声明，便于加载器进行集合运算。"""
        return set(self.provides), set(self.needs), set(self.wants)
