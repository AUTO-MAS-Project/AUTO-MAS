"""MAA 插件行为测试共用的原生 L3/L4 上下文装配，不实现专项业务。"""

from maa_adapter.tasks.auto_proxy import AutoProxyTask
from maa_adapter.tasks.config_session import ScriptConfigTask
from maa_adapter.tasks.manager import MaaManager

from app.task.history_core import TaskHistorySession


def make_proxy(script, config, users, emulator, *, capture_adb):
    """将现有测试运行树和外部边界传给真实插件执行器，用户配置仍由测试提供。"""
    expander = MaaManager(script, config)
    expander.emulator_manager = emulator
    expander.history = TaskHistorySession(script.task_info)
    user = script.user_list[0]
    worker = AutoProxyTask(expander, user, users[user.user_id])
    worker.accounts = users
    worker.capture_adb = capture_adb
    return worker


def make_config_worker(script, config, users):
    """为保存和停止回归构造真实配置模式执行器，沿用运行树已有的账号身份。"""
    expander = MaaManager(script, config)
    expander.history = TaskHistorySession(script.task_info)
    user = script.user_list[0]
    worker = ScriptConfigTask(expander, user, users[user.user_id])
    from uuid import UUID

    worker.accounts = {UUID(str(uid)): entry for uid, entry in users.items()}
    return worker
