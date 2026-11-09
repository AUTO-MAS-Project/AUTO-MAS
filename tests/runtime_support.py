"""专项单元测试的运行态能力替身；任务树提交与并发由 core 回归单独覆盖。"""

from datetime import datetime
from types import SimpleNamespace


class RuntimeStub(SimpleNamespace):
    def user_state(self, user):
        # 专项单元测试将报告素材作为独立替身传入，不模拟公共运行树。
        return user

    def __getattr__(self, name):
        if name == "execution_mode":
            return getattr(self, "mode", "AutoProxy")
        if name == "task_info":
            return self
        raise AttributeError(name)

    async def set_state(self, **fields):
        for name, value in fields.items():
            setattr(self, name, value)

    async def set_current_index(self, value):
        self.current_index = value

    async def set_users(self, value):
        self.user_list = value

    async def set_log(self, value):
        self.log = value

    async def append_log(self, value):
        self.log = getattr(self, "log", "") + value

    async def set_log_first_line(self, value):
        self.log_first_line = value

    async def increment_log_first_line(self, value):
        self.log_first_line = getattr(self, "log_first_line", 1) + value

    async def append_content(self, *lines):
        self.content.extend(lines)

    async def append_push_log(self, value):
        self.push_log.append(value)

    async def add_log_record(self, started_at: datetime, record):
        self.log_record[started_at] = record
        return record

    def submit(self, operation):
        # 这些测试只替代立即完成的状态写入，不模拟 Config 的事务调度。
        try:
            operation.send(None)
        except StopIteration:
            return
        operation.close()
        raise AssertionError("运行态替身不能承接会挂起的业务操作")

    async def drain(self):
        pass


async def create_runtime_tree(*, script_id="script", user_id="user"):
    """创建不登记文件、不启动执行器的真实运行树，供宿主状态与日志测试使用。"""
    from app.models.task import TaskItem, TaskScriptItem, TaskUserItem

    root = TaskItem()
    await root.activate()
    sid = root.scripts.add(
        TaskScriptItem, payload={"info": {"script_id": script_id, "name": "Script"}}
    )
    await root.scripts.commit()
    script = root.scripts[sid]
    uid = script.users.add(
        TaskUserItem, payload={"info": {"user_id": user_id, "name": "User"}}
    )
    await script.users.commit()
    await root.set_current_index(0)
    return root, script, script.users[uid]
