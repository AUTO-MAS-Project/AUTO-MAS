from __future__ import annotations

from pydantic import BaseModel, Field


class OutBase(BaseModel):
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="操作状态")
    message: str = Field(default="操作成功", description="操作消息")


class ComboBoxItem(BaseModel):
    label: str = Field(..., description="展示值")
    value: str | None = Field(..., description="实际值")


class ComboBoxOut(OutBase):
    data: list[ComboBoxItem] = Field(..., description="下拉框选项")


__all__ = ["OutBase", "ComboBoxItem", "ComboBoxOut"]
