from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.models.task import UserItem

from automas_script_hsr.contracts import HSRRunRequest, HSRRunResult
from automas_script_hsr.runtime.tasks import get_module

from .control import HSRSRAControl
from .runner import (
    SRAProcessRegistry,
    cleanup_sra_temp_config,
    disable_sra_windows_notifications,
    get_sra_app_data_dir,
)


class SRAControllerSessionImpl:
    """Isolated SRA controller session used by the HSR orchestrator."""

    def __init__(self, *, script_id: str, script_config: Any, log, coordinator: Any):
        self.script_id = script_id
        self.script_config = script_config
        self.log = log
        self.coordinator = coordinator
        self.process_registry = SRAProcessRegistry()
        self.temp_files: list[Path] = []
        self._backup_root = Path.cwd() / "data" / script_id / "Temp" / "SRA-session"
        self._backup_targets: list[tuple[Path, Path, bool]] = []
        self._closed = False
        self.control = HSRSRAControl(
            script_config=script_config,
            account_switcher=coordinator._account_switcher,
            append_log=log,
            phase_timeout_seconds=coordinator._phase_timeout_seconds,
            module_timeout_seconds=coordinator._module_timeout_seconds,
            queue_eow_completion=coordinator._queue_eow_completion_if_confirmed,
            queue_weekly_completion=coordinator._queue_weekly_completion,
            record_module_result=coordinator._record_module_result,
        )

    @classmethod
    async def create(cls, **kwargs) -> "SRAControllerSessionImpl":
        session = cls(**kwargs)
        try:
            session._backup_app_data()
            disable_sra_windows_notifications()
            coordinator = session.coordinator
            coordinator.runtime.sra_process_registry = session.process_registry
            return session
        except Exception:
            try:
                await session.close()
            except Exception:
                pass
            raise

    async def run(self, request: HSRRunRequest) -> HSRRunResult:
        root = Path(str(self.script_config.get("SRA", "Path") or ""))
        if request.task.key == "StartGame":
            item = self.control.create_start_item(
                user_item=UserItem(request.user_id, request.user_name, "运行"),
                user_cfg=request.user_config,
                user_name=request.user_name,
                uid=request.user_id,
                phase=request.task.phase,
                sra_exe_path=root / "SRA-cli.exe",
                script_id=request.script_id,
                temp_files=self.temp_files,
            )
            return self._normalize_result(await item.run(), "SRA 登录/切号完成")

        module = get_module(request.task.key)
        if module is None or module.sra_task is None:
            return HSRRunResult(status="skipped", summary="SRA 不提供该任务")
        item = self.control.create_module_item(
            user_item=UserItem(request.user_id, request.user_name, "运行"),
            user_cfg=request.user_config,
            user_name=request.user_name,
            uid=request.user_id,
            module=module,
            phase=module.category,
            sra_exe_path=root / "SRA-cli.exe",
            script_id=request.script_id,
            temp_files=self.temp_files,
            daily_eow_enabled=bool(request.extra.get("daily_eow_enabled")),
        )
        if item is None:
            return HSRRunResult(status="skipped", summary="SRA 任务无可执行内容")
        return self._normalize_result(await item.run(), "SRA 任务完成")

    @staticmethod
    def _normalize_result(result: Any, default_summary: str) -> HSRRunResult:
        if getattr(result, "success", False):
            return HSRRunResult(
                status="completed",
                summary=str(getattr(result, "output", "") or default_summary),
                completion_evidence={"returncode": getattr(result, "returncode", 0)},
                native_result=result,
            )
        return HSRRunResult(
            status="failed",
            error=str(getattr(result, "error", "") or "SRA 任务失败"),
        )

    async def cancel(self) -> None:
        await self.process_registry.terminate_current_process()

    async def close(self) -> None:
        if self._closed:
            return

        errors: list[str] = []
        try:
            await self.cancel()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"停止 SRA 子进程失败: {exc}")
        for path in self.temp_files:
            try:
                cleanup_sra_temp_config(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"清理 SRA 临时配置失败({path}): {exc}")
        try:
            self._restore_app_data()
            self._closed = True
        except Exception as exc:  # noqa: BLE001
            errors.append(f"恢复 SRA AppData 失败: {exc}")

        if errors:
            raise RuntimeError("；".join(errors))

    def _backup_app_data(self) -> None:
        shutil.rmtree(self._backup_root, ignore_errors=True)
        app_data = get_sra_app_data_dir()
        for name in ("settings.json", "cache.json", "configs"):
            source = app_data / name
            backup = self._backup_root / name
            existed = source.exists()
            self._backup_targets.append((source, backup, existed))
            if not existed:
                continue
            backup.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, backup)
            else:
                shutil.copy2(source, backup)

    def _restore_app_data(self) -> None:
        errors: list[str] = []
        for source, backup, existed in reversed(self._backup_targets):
            try:
                if not existed:
                    if source.is_dir():
                        shutil.rmtree(source, ignore_errors=True)
                    elif source.exists():
                        source.unlink()
                    continue

                if not backup.exists():
                    raise RuntimeError(f"SRA AppData 备份不存在: {backup}")
                source.parent.mkdir(parents=True, exist_ok=True)
                temp_path = source.with_name(f"{source.name}.restore.tmp")
                if temp_path.is_dir():
                    shutil.rmtree(temp_path, ignore_errors=True)
                elif temp_path.exists():
                    temp_path.unlink()
                if backup.is_dir():
                    shutil.copytree(backup, temp_path)
                else:
                    shutil.copy2(backup, temp_path)
                if source.is_dir():
                    shutil.rmtree(source, ignore_errors=True)
                elif source.exists():
                    source.unlink()
                temp_path.replace(source)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{source}: {exc}")

        if errors:
            raise RuntimeError("；".join(errors))
        shutil.rmtree(self._backup_root, ignore_errors=True)
        self._backup_targets.clear()
