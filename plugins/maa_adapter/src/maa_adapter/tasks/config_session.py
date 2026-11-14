"""MAA 配置编辑会话入口。"""

from auto_mas_core import ScriptConfigWorker, TaskMode

from .session import MaaGuiSession


class ScriptConfigTask(MaaGuiSession, ScriptConfigWorker):
    mode = TaskMode.SCRIPT_CONFIG
