#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""公共脚本安装备份：安装锁由调用方持有，备份与安装目录始终位于同一磁盘。

状态记录与快照独立于脚本原生更新标记；不改写原生 pending/transaction。
恢复只能在专项确认安装器、子进程和后台写入全部结束之后调用。
"""

import json
import shutil
import threading
from pathlib import Path

from app.services import script_install


class ManagedInstallBackup:
    """统一管理可跨任务重试的安装快照，不能由专项自行删除或回滚。"""

    _PHASES = frozenset(
        {
            "ready",
            "installing",
            "timed_out",
            "retrying",
            "restoring",
            "restored",
            "installed",
        }
    )

    def __init__(self, root: Path, *, script_id: str, script_type: str) -> None:
        self.root = root
        self.script_id = script_id
        self.script_type = script_type
        self.directory = script_install.workspace(root) / "managed-install"
        self.record = self.directory / "state.json"
        self.snapshot = self.directory / "snapshot"
        self.staging = self.directory / "staging"
        self.failed = self.directory / "failed-install"

    def read(self) -> dict | None:
        """记录异常或存在无主备份时拒绝继续，不能猜测状态。"""
        if not self.directory.exists():
            return None
        script_install._reject_link(self.directory)
        if not self.record.exists():
            if any(self.directory.iterdir()):
                raise script_install.InstallUnsafeError(
                    "检测到无恢复记录的脚本安装备份，已保留现场"
                )
            return None
        script_install._reject_link(self.record)
        try:
            state = json.loads(self.record.read_text(encoding="utf-8"))
            if (
                not isinstance(state, dict)
                or state.get("root") != str(self.root.resolve())
                or state.get("script_id") != self.script_id
                or state.get("script_type") != self.script_type
                or state.get("phase") not in self._PHASES
                or not isinstance(state.get("files"), dict)
                or not state["files"]
                or (
                    state.get("version") is not None
                    and not isinstance(state.get("version"), str)
                )
            ):
                raise ValueError("invalid backup record")
            return state
        except (OSError, ValueError, TypeError) as error:
            raise script_install.InstallUnsafeError(
                "脚本安装备份记录损坏或身份变化，拒绝自动恢复"
            ) from error

    def _write(self, state: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        script_install._reject_link(self.directory)
        script_install._write_state(self.directory, state, "state.json")

    def _create(self, cancelled: threading.Event, version: str | None) -> None:
        if self.read() is not None:
            raise script_install.InstallUnsafeError(
                "脚本存在尚未结算的安装备份，禁止覆盖旧版"
            )
        if not self.root.is_dir():
            raise script_install.InstallUnsafeError(
                "原脚本安装目录不存在，无法建立可信旧版备份"
            )
        script_install._reject_link(self.root)
        original = script_install.tree_hashes(self.root, cancelled)
        if not original:
            raise script_install.InstallUnsafeError("原安装为空，不能作为恢复备份")
        if self.directory.exists() and any(self.directory.iterdir()):
            raise script_install.InstallUnsafeError("备份工作目录已有未知文件")
        self.directory.mkdir(parents=True, exist_ok=True)
        script_install._reject_link(self.directory)
        required = sum(
            path.stat().st_size for path in self.root.rglob("*") if path.is_file()
        )
        if shutil.disk_usage(self.directory).free < required + 256 * 1024**2:
            raise OSError("磁盘空间不足，无法为本次更新保存完整原版")
        try:
            shutil.copytree(self.root, self.staging, symlinks=True)
            if script_install.tree_hashes(self.staging, cancelled) != original:
                raise script_install.InstallUnsafeError("安装备份复制后完整性不一致")
            if script_install.tree_hashes(self.root, cancelled) != original:
                raise script_install.InstallUnsafeError("备份期间原安装发生外部修改")
            self.staging.replace(self.snapshot)
            self._write(
                {
                    "root": str(self.root.resolve()),
                    "script_id": self.script_id,
                    "script_type": self.script_type,
                    "phase": "ready",
                    "version": version,
                    "files": original,
                }
            )
        except BaseException:
            # 尚未进入安装阶段，此时创建失败不会修改原安装。
            if not self.record.exists():
                for path in (self.staging, self.snapshot):
                    if path.is_dir() and not path.is_symlink():
                        shutil.rmtree(path)
            raise

    async def create(self, version: str | None) -> None:
        await script_install.run_worker(self._create, version=version)

    def set_phase(self, phase: str) -> None:
        if phase not in self._PHASES:
            raise ValueError("invalid backup phase")
        state = self.read()
        if state is None:
            raise script_install.InstallUnsafeError("脚本安装恢复记录已丢失")
        self._write({**state, "phase": phase})

    def _hashes(self, root: Path, cancelled: threading.Event) -> dict[str, str]:
        return script_install.tree_hashes(root, cancelled)

    def _restore(self, cancelled: threading.Event) -> None:
        state = self.read()
        if state is None or state["phase"] not in {
            "ready",
            "installing",
            "timed_out",
            "retrying",
            "restoring",
        }:
            raise script_install.InstallUnsafeError("没有可恢复的安装备份事务")
        expected = state["files"]
        if self.snapshot.exists():
            script_install._reject_link(self.snapshot)
            if self._hashes(self.snapshot, cancelled) != expected:
                raise script_install.InstallUnsafeError("安装备份文件不完整，拒绝覆盖")
            if self.failed.exists() and self.root.exists():
                raise script_install.InstallUnsafeError(
                    "恢复工作目录尚有冲突，已保护现场"
                )
        elif state["phase"] != "restoring":
            raise script_install.InstallUnsafeError("原版安装备份已丢失")
        self.set_phase("restoring")
        if self.snapshot.exists():
            if self.root.exists():
                script_install._reject_link(self.root)
                self.root.replace(self.failed)
            self.snapshot.replace(self.root)
        if not self.root.exists() or self._hashes(self.root, cancelled) != expected:
            raise script_install.InstallUnsafeError("原版恢复后文件完整性检查失败")
        self.set_phase("restored")

    async def restore(self) -> None:
        await script_install.run_worker(self._restore)

    def verify_restored(self) -> bool:
        state = self.read()
        if state is None or state["phase"] != "restored":
            return False
        return self._hashes(self.root, threading.Event()) == state["files"]

    def _finish(self, cancelled: threading.Event, *, restored: bool) -> None:
        state = self.read()
        if state is None:
            raise script_install.InstallUnsafeError("安装事务记录已丢失")
        if restored:
            if (
                state["phase"] != "restored"
                or not self._hashes(self.root, cancelled) == state["files"]
            ):
                raise script_install.InstallUnsafeError(
                    "原版还原尚未确认，不能清理恢复记录"
                )
            if self.snapshot.exists():
                raise script_install.InstallUnsafeError("恢复后仍存在未处理的备份")
            if self.failed.exists():
                script_install._reject_link(self.failed)
                shutil.rmtree(self.failed)
        else:
            if state["phase"] not in {
                "ready",
                "installing",
                "timed_out",
                "retrying",
                "installed",
            }:
                raise script_install.InstallUnsafeError("安装备份当前不能提交")
            self.set_phase("installed")
            if self.snapshot.exists():
                script_install._reject_link(self.snapshot)
                shutil.rmtree(self.snapshot)
        self.record.unlink()
        if not any(self.directory.iterdir()):
            self.directory.rmdir()

    async def finish_success(self) -> None:
        await script_install.run_worker(self._finish, restored=False)

    async def finish_restore(self) -> None:
        await script_install.run_worker(self._finish, restored=True)
