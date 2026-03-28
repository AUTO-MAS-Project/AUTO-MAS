from typing import Annotated as A

from pydantic import BaseModel

from app.core.plugins import plgType, ConfigModel, SchemaModelAdapter, Desc


class RuleRow(BaseModel):
    name: str = "default"
    threshold: float = 0.0


class Config(ConfigModel):
    __extra__ = {
        "enable": {"group": "basic", "order": 1},
        "title": {
            "description": "示例插件显示名称",
            "placeholder": "请输入示例插件标题",
            "group": "basic",
            "order": 2,
        },
        "retry": {"group": "advanced", "min": 0, "step": 1},
    }

    enable: A[bool, Desc("是否启用示例插件")] = True
    title: plgType.String = "DSL v2 Demo"
    retry: A[int, Desc("失败重试次数")] = 3
    watch_paths: A[list[plgType.PathText], Desc("监听路径列表（支持 Path codec）")] = []
    tags: A[plgType.StringList, Desc("标签列表")] = []
    metadata: A[plgType.KeyValueStr, Desc("额外键值配置")]
    rules: A[plgType.TableOf[RuleRow], Desc("规则表（table 示例）")] = []  # pyright: ignore[reportAssignmentType]

    @classmethod
    def validate_config(cls, data: ConfigModel) -> None:
        typed = (
            data
            if isinstance(data, Config)
            else Config.model_validate(data.model_dump())
        )
        if typed.retry < 0:
            raise ValueError("retry 不能小于 0")
        if typed.enable and not str(typed.title).strip():
            raise ValueError("启用时 title 不能为空")


schema = SchemaModelAdapter(Config)
