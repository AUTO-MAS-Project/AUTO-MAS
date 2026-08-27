"""MaaFW 第一层·外部运行：各 UI 外壳映射层共用的输入模型。

`TaskSelection` 表达的是「外壳无关」的选择意图（选了哪个任务、是否勾选、
带什么选项）。各外壳映射层各自 import 本模块，把这些意图翻译成自己的配置
形状，**不要跨外壳互相 import**。

本模块是纯数据定义，不做任何 IO。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class ShellMappingError(ValueError):
    """interface 到某个外壳实例配置的映射失败。

    各外壳映射层复用这个基类；需要区分具体失因时再派生子类。
    """


@dataclass(frozen=True)
class TaskSelection:
    """一个被选中的任务及其勾选 / 选项状态，供各外壳映射层共用。

    字段是外壳无关的意图，具体外壳按自己的形状消费：

    - ``checked``：是否勾选。MFAAvalonia → ``default_check``；MXU → ``enabled``。
    - ``options``：MFAAvalonia 的选项条目列表，按其实际格式原样透传，如
      ``{"name": ..., "index": 0}``。``None`` 表示按 interface 声明的选项名给默认。
    - ``option_values``：MXU 的 ``optionValues`` 字典，整体原样透传。MXU 选项值
      结构随类型而异（switch / select / checkbox / input / hotkey），本层不解释，
      ``None`` 视为空字典 ``{}``。
    - ``pipeline_override``：覆盖 interface task 自带的 ``pipeline_override``；
      ``None`` 表示沿用 interface。
    - ``custom_name``：MXU 的 ``customName``（任务自定义显示名）；``None`` 表示不写。

    某外壳用不到的字段留空即可，映射层会忽略它。
    """

    name: str
    checked: bool = True
    options: Sequence[Mapping[str, Any]] | None = None
    pipeline_override: Mapping[str, Any] | None = None
    option_values: Mapping[str, Any] | None = None
    custom_name: str | None = None
