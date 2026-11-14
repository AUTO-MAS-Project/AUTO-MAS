"""L4：使用 L3 传入的已锁用户配置执行模式，恢复结束后归还上层。"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar

from app.models.config import UserConfigType, UserEntry
from app.models.task import TaskMode
from app.task.lifecycle import TaskBase
from app.utils.common.process.scope import process_finalizer_scope

if TYPE_CHECKING:
    from app.models.task import TaskUserItem
    from app.task.user_expander import UserExpander


class ModeWorker(TaskBase):
    mode: ClassVar[TaskMode]

    def __init__(
        self,
        expander: UserExpander,
        user: TaskUserItem,
        config: UserConfigType | UserEntry | None,
    ) -> None:
        """绑定 L3 展开器、用户运行节点与已锁配置，合并用户任务参数并初始化执行阶段标记。"""
        super().__init__()
        self.expander = expander
        self.task_info = expander.task_info
        self.script_info = expander.script_info
        self.user_info = user
        self.context = expander.context.with_params(user.info.params)
        self.user_config = config
        self._entered = False

    async def main_task(self) -> None:
        if self.mode != self.task_info.mode:
            raise ValueError("插件执行器不支持当前模式")
        user = self.user_info
        if user.info.user_id != "default" and self.user_config is None:
            raise ValueError("执行器未收到已锁用户配置")
        await self.script_info.set_current_index(self.script_info.user_list.index(user))
        await user.set_state(status="运行")
        self._entered = True
        reason = await self.check()
        if reason:
            raise ValueError(reason)
        await self.prepare()
        await self.main_logic()

    async def check(self) -> str | None:
        """单用户公开能力检查。"""
        return None

    async def prepare(self) -> None:
        """准备脚本配置；暂存修改由本执行协程提交。"""

    @abstractmethod
    async def main_logic(self) -> None:
        """调用插件实际能力，明确给出用户结果并就地提交主流程暂存。"""

    async def finish(self) -> None:
        """用户锁内恢复资源和保存结果。"""

    async def on_crash(self, exc: BaseException) -> None:
        try:
            await self.expander.record_user_state(
                self.user_info, status="异常", reason=str(exc)
            )
        except Exception as failure:
            await super().on_crash(failure)
        await super().on_crash(exc)

    async def final_task(self) -> None:
        """在进程停止确认范围内完成当前层级恢复、保存及状态提交。"""
        with process_finalizer_scope():
            try:
                if self._entered:
                    await self.finish()
            finally:
                if self.user_config is not None:
                    await self.user_config.commit()
            if self.cancelled or self.task_info.info.status == "cancelled":
                await self.user_info.set_state(status="已取消")
            elif (
                self.error is None and self._entered and self.user_info.status == "运行"
            ):
                raise RuntimeError("插件执行结束但未给出用户结果")


class AutoProxyWorker(ModeWorker):
    mode = TaskMode.AUTO_PROXY


class ScriptConfigWorker(ModeWorker):
    mode = TaskMode.SCRIPT_CONFIG


class ScriptViewWorker(ModeWorker):
    mode = TaskMode.SCRIPT_VIEW


MODE_WORKERS: dict[TaskMode, type[ModeWorker]] = {
    TaskMode.AUTO_PROXY: AutoProxyWorker,
    TaskMode.SCRIPT_CONFIG: ScriptConfigWorker,
    TaskMode.SCRIPT_VIEW: ScriptViewWorker,
}
