from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.models.task import UserItem

from automas_script_hsr.contracts import HSRRunRequest, HSRRunResult
from automas_script_hsr.runtime.tasks import get_module

from .control import HSRM7AControl
from .runner import M7ARunner


class M7AControllerSessionImpl:
    """M7A controller session with atomic config.yaml restoration."""

    def __init__(self, *, script_id: str, script_config: Any, log, coordinator: Any):
        self.script_id = script_id
        self.script_config = script_config
        self.log = log
        self.coordinator = coordinator
        self.root = Path(str(script_config.get("M7A", "Path") or ""))
        self.config_path = self.root / "config.yaml"
        self.backup_path = (
            Path.cwd() / "data" / script_id / "Temp" / "M7A-session-config.yaml"
        )
        self.config_existed = self.config_path.exists()
        self._closed = False
        self.runner = M7ARunner(
            self.root,
            log_callback=log,
            output_line_callback=(
                coordinator._account_switcher.recover_game_window_if_screenshot_blocked
            ),
        )
        self.control = HSRM7AControl(
            script_config=script_config,
            account_switcher=coordinator._account_switcher,
            append_log=log,
            module_timeout_seconds=coordinator._module_timeout_seconds,
            queue_eow_completion=coordinator._queue_eow_completion_if_confirmed,
            queue_weekly_completion=coordinator._queue_weekly_completion,
            record_module_result=coordinator._record_module_result,
        )

    @classmethod
    async def create(cls, **kwargs) -> "M7AControllerSessionImpl":
        session = cls(**kwargs)
        try:
            session.backup_path.parent.mkdir(parents=True, exist_ok=True)
            if session.config_existed:
                shutil.copy2(session.config_path, session.backup_path)
            session.coordinator.runtime.m7a_runner = session.runner
            return session
        except Exception:
            try:
                await session.close()
            except Exception:
                pass
            raise

    async def run(self, request: HSRRunRequest) -> HSRRunResult:
        module = get_module(request.task.key)
        if module is None or not module.m7a_tasks:
            return HSRRunResult(status="skipped", summary="M7A 不提供该任务")
        item = self.control.create_module_item(
            user_item=UserItem(request.user_id, request.user_name, "运行"),
            user_cfg=request.user_config,
            user_name=request.user_name,
            uid=request.user_id,
            module=module,
            phase=module.category,
            m7a_path=str(self.root),
            m7a_runner=self.runner,
            daily_eow_enabled=bool(request.extra.get("daily_eow_enabled")),
        )
        if item is None:
            return HSRRunResult(status="skipped", summary="M7A 任务无可执行内容")
        result = await item.run()
        if getattr(result, "success", False):
            return HSRRunResult(
                status="completed",
                summary=str(getattr(result, "output", "") or "M7A 任务完成"),
                completion_evidence={"returncode": getattr(result, "returncode", 0)},
                native_result=result,
            )
        return HSRRunResult(
            status="failed",
            error=str(getattr(result, "error", "") or "M7A 任务失败"),
        )

    async def cancel(self) -> None:
        await self.runner.terminate_current_process()

    async def close(self) -> None:
        if self._closed:
            return

        errors: list[str] = []
        try:
            await self.cancel()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"停止 M7A 子进程失败: {exc}")

        try:
            if self.config_existed:
                if not self.backup_path.exists():
                    raise RuntimeError(f"M7A 配置备份不存在: {self.backup_path}")
                temp_path = self.config_path.with_name(
                    f"{self.config_path.name}.restore.tmp"
                )
                shutil.copy2(self.backup_path, temp_path)
                temp_path.replace(self.config_path)
            elif self.config_path.exists():
                self.config_path.unlink()
            if self.backup_path.exists():
                self.backup_path.unlink()
            self._closed = True
        except Exception as exc:  # noqa: BLE001
            errors.append(f"恢复 M7A config.yaml 失败: {exc}")

        if errors:
            raise RuntimeError("；".join(errors))
