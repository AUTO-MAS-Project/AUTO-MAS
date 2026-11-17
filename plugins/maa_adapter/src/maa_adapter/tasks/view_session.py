"""MAA 只读查看会话入口，不继承配置会话。"""

from auto_mas_core import ScriptViewWorker, TaskMode

from .session import MaaGuiSession


class ScriptViewTask(MaaGuiSession, ScriptViewWorker):
    mode = TaskMode.SCRIPT_VIEW
