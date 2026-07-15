from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

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
        self._restored = False
        self._closed = False
        self.control = HSRSRAControl(
            script_config=script_config,
            account_switcher=coordinator._account_switcher,
            process_registry=self.process_registry,
            append_log=log,
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
        except Exception as setup_error:
            try:
                await session.close()
            except Exception as cleanup_error:
                raise ExceptionGroup(
                    "SRA session setup and cleanup both failed",
                    [setup_error, cleanup_error],
                ) from setup_error
            raise

    async def run(self, request: HSRRunRequest) -> HSRRunResult:
        root = Path(str(self.script_config.get("SRA", "Path") or ""))
        if request.task.key == "StartGame":
            item = self.control.create_start_item(
                user_cfg=request.user_config,
                user_name=request.user_name,
                uid=request.user_id,
                phase=request.task.phase,
                timeout_seconds=request.timeout_seconds,
                sra_exe_path=root / "SRA-cli.exe",
                script_id=request.script_id,
                temp_files=self.temp_files,
            )
            return HSRRunResult.from_native(
                await item.run(),
                default_summary="SRA 登录/切号完成",
                default_error="SRA 登录/切号失败",
            )

        module = get_module(request.task.key)
        if module is None or module.sra_task is None:
            return HSRRunResult(status="skipped", summary="SRA 不提供该任务")
        item = self.control.create_module_item(
            user_cfg=request.user_config,
            user_name=request.user_name,
            uid=request.user_id,
            module=module,
            timeout_seconds=request.timeout_seconds,
            sra_exe_path=root / "SRA-cli.exe",
            script_id=request.script_id,
            temp_files=self.temp_files,
            daily_eow_enabled=bool(request.extra.get("daily_eow_enabled")),
        )
        if item is None:
            return HSRRunResult(status="skipped", summary="SRA 任务无可执行内容")
        return HSRRunResult.from_native(
            await item.run(),
            default_summary="SRA 任务完成",
            default_error="SRA 任务失败",
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
        if not self._restored:
            try:
                self._restore_app_data()
                self._restored = True
            except Exception as exc:  # noqa: BLE001
                errors.append(f"恢复 SRA AppData 失败: {exc}")

        if errors:
            raise RuntimeError("；".join(errors))
        self._closed = True

    def _backup_app_data(self) -> None:
        if self._backup_root.exists():
            shutil.rmtree(self._backup_root)
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
                        shutil.rmtree(source)
                    elif source.exists():
                        source.unlink()
                    continue

                if not backup.exists():
                    raise RuntimeError(f"SRA AppData 备份不存在: {backup}")
                source.parent.mkdir(parents=True, exist_ok=True)
                temp_path = source.with_name(f"{source.name}.restore.tmp")
                if temp_path.is_dir():
                    shutil.rmtree(temp_path)
                elif temp_path.exists():
                    temp_path.unlink()
                if backup.is_dir():
                    shutil.copytree(backup, temp_path)
                else:
                    shutil.copy2(backup, temp_path)
                if source.is_dir():
                    shutil.rmtree(source)
                elif source.exists():
                    source.unlink()
                temp_path.replace(source)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{source}: {exc}")

        if errors:
            raise RuntimeError("；".join(errors))
        if self._backup_root.exists():
            shutil.rmtree(self._backup_root)
        self._backup_targets.clear()
