"""静态类型契约，不执行：SDK 导出的模型、泛型与宿主单例不能退化为 Any。"""

from pathlib import Path
from typing import assert_type

from auto_mas_core import Config, ScriptAdapterPlugin, ScriptTypeDecl
from auto_mas_core.host.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    Virtual,
    config_manager,
    virtual_field,
)
from auto_mas_core.host.models_schema import OutBase
from pydantic import Field


class Options(ConfigGroup):
    count: int = 0


class Settings(ConfigEntry):
    options: Options = Field(default_factory=Options)

    class View(ConfigGroup):
        count: Virtual[int] = None

    view: View = Field(default_factory=View)

    @virtual_field("view.count")
    def count(self) -> int:
        """用配置虚拟字段的真实声明验证 SDK 仍保留类型别名与装饰器签名。"""
        return self.options.count


assert_type(Settings.build(), Settings)
assert_type(ConfigCollection[Settings].build([Settings]), ConfigCollection[Settings])
assert_type(config_manager.in_transaction, bool)
assert_type(Config.source_path, Path)
assert_type(OutBase().code, int)
assert_type(ScriptAdapterPlugin.decl, ScriptTypeDecl | None)
