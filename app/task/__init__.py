#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""任务基础设计：四层嵌套任务，按层级拆分放置。

层级自外向内（设计 §4.2-4.4 / §5.3-5.5），类名即该层做的事：

1. ``app.core.task_dispatcher`` —— ``TaskDispatcher``：派发层，建 ``TaskItem``、启停。
2. :mod:`app.task.script_expander` —— ``ScriptExpander``：把任务展开成脚本列表。
3. :mod:`app.task.user_expander` —— ``UserExpander``：把单个脚本展开成用户列表。
4. :mod:`app.task.mode_worker` —— ``ModeWorker``：干活的那层，跑单用户单模式。

前三层都只做"展开 + 派发"，真正执行落在最内层的 Worker。

支撑模块：:mod:`app.task.base` 是四层共用的可取消执行契约，
:mod:`app.task.params` 是各层共用的传参件（``ExpandError`` / ``is_selected`` /
``queue_script_ids``）。组合合法性由派发层 ``TaskDispatcher.start`` 一处判定并抛
``ExpandError``；两层展开只按同一张表**产出**列表（§5.4 脚本、§5.5 用户），
逻辑分别内联在各自的 ``main_task`` 里，不再重复校验。

运行态的**状态**不在本包 —— 唯一事实源是 ``app.models.task`` 里的配置树
（类级 ``connect`` 在配置类旁同步声明，字段变更直接推 ``TaskItem`` 载荷）。
"""

from .base import TaskBase
from .mode_worker import (
    MODE_WORKERS,
    AutoProxyWorker,
    ManualReviewWorker,
    ModeWorker,
    ScriptConfigWorker,
)
from .context import TaskContext
from .params import ExpandError, is_selected, queue_script_ids
from .script_expander import ScriptExpander
from .user_expander import UserExpander

__all__ = [
    "MODE_WORKERS",
    "AutoProxyWorker",
    "ExpandError",
    "ManualReviewWorker",
    "ModeWorker",
    "ScriptExpander",
    "ScriptConfigWorker",
    "TaskContext",
    "UserExpander",
    "TaskBase",
    "is_selected",
    "queue_script_ids",
]
