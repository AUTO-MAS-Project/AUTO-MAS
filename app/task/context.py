"""每层执行依赖；参数按节点传递，不跨层隐式合并。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace

from pydantic import JsonValue


@dataclass(frozen=True)
class TaskContext:
    params: dict[str, JsonValue] = field(default_factory=dict)

    def with_params(self, params: dict[str, JsonValue]) -> TaskContext:
        return replace(self, params=deepcopy(params))
