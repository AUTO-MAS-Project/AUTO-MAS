#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.utils import get_logger
from app.utils.io import read_file, write_file


logger = get_logger("SRC 配置持久化")


@dataclass(frozen=True, slots=True)
class SrcConfigSnapshotState:
    """一次 SRC 原配置快照的归属信息。"""

    script_id: str
    src_root_path: Path
    installation_id: str
    config_user_id: str | None = None


def read_src_installation_id(src_root_path: Path) -> str:
    """读取基于文件元数据的 SRC 安装实例标识。"""

    src_exe_path = src_root_path.resolve() / "src.exe"
    before_stat = src_exe_path.stat()
    identity = ":".join(
        str(value)
        for value in (
            before_stat.st_dev,
            before_stat.st_ino,
            before_stat.st_size,
            before_stat.st_ctime_ns,
            before_stat.st_mtime_ns,
        )
    )
    after_stat = src_exe_path.stat()
    if (
        before_stat.st_dev,
        before_stat.st_ino,
        before_stat.st_size,
        before_stat.st_ctime_ns,
        before_stat.st_mtime_ns,
    ) != (
        after_stat.st_dev,
        after_stat.st_ino,
        after_stat.st_size,
        after_stat.st_ctime_ns,
        after_stat.st_mtime_ns,
    ):
        raise OSError(f"读取 SRC 安装标识时文件发生变化: {src_exe_path}")
    return identity


def validate_src_installation(
    src_root_path: Path,
    expected_installation_id: str,
) -> None:
    """确认目录仍是指定的 SRC 安装实例。"""

    if read_src_installation_id(src_root_path) != expected_installation_id:
        raise ValueError(f"SRC 安装实例在任务运行期间发生变化: {src_root_path}")


def read_src_config_snapshot_state(
    state_path: Path,
    *,
    expected_script_id: str | None = None,
) -> SrcConfigSnapshotState:
    """读取并校验已提交 SRC 配置快照的归属信息。"""

    state = read_file(state_path, format=".json")
    if not isinstance(state, dict):
        raise ValueError(f"SRC 配置快照状态无效: {state_path}")

    script_id = state.get("script_id")
    if not isinstance(script_id, str) or not script_id.strip():
        raise ValueError(f"SRC 配置快照所属脚本无效: {script_id}")
    if expected_script_id is not None and script_id != expected_script_id:
        raise ValueError(f"SRC 配置快照所属脚本无效: {script_id}")

    src_root_path = state.get("src_root_path")
    if not isinstance(src_root_path, str) or not src_root_path.strip():
        raise ValueError(f"SRC 配置快照根目录无效: {src_root_path}")
    stored_root_path = Path(src_root_path)
    if not stored_root_path.is_absolute():
        raise ValueError(f"SRC 配置快照根目录不是绝对路径: {src_root_path}")

    config_user_id = state.get("config_user_id")
    if config_user_id is not None and (
        not isinstance(config_user_id, str) or not config_user_id.strip()
    ):
        raise ValueError(f"SRC 配置快照设置用户无效: {config_user_id}")

    installation_id = state.get("installation_id")
    if not isinstance(installation_id, str) or not installation_id.strip():
        raise ValueError(f"SRC 配置快照安装标识无效: {installation_id}")

    return SrcConfigSnapshotState(
        script_id=script_id,
        src_root_path=stored_root_path.resolve(),
        installation_id=installation_id,
        config_user_id=config_user_id,
    )


def write_src_config_snapshot_state(
    state_path: Path,
    *,
    script_id: str,
    src_root_path: Path,
    installation_id: str | None = None,
    config_user_id: str | None = None,
) -> None:
    """原子记录 SRC 配置快照的根目录和设置会话归属。"""

    if not isinstance(script_id, str) or not script_id.strip():
        raise ValueError(f"SRC 配置快照所属脚本无效: {script_id}")
    if config_user_id is not None and (
        not isinstance(config_user_id, str) or not config_user_id.strip()
    ):
        raise ValueError(f"SRC 配置快照设置用户无效: {config_user_id}")
    if installation_id is None:
        installation_id = read_src_installation_id(src_root_path)
    elif not isinstance(installation_id, str) or not installation_id.strip():
        raise ValueError(f"SRC 配置快照安装标识无效: {installation_id}")
    write_file(
        state_path,
        {
            "script_id": script_id,
            "src_root_path": str(src_root_path.resolve()),
            "installation_id": installation_id,
            "config_user_id": config_user_id,
        },
        format=".json",
    )


def _transaction_paths(config_path: Path) -> tuple[Path, Path, Path]:
    staging_path = config_path.with_name(config_path.name + ".tmp")
    staging_ready_path = config_path.with_name(config_path.name + ".tmp.ready")
    backup_path = config_path.with_name(config_path.name + ".old")
    return staging_path, staging_ready_path, backup_path


def is_src_config_available(path: Path) -> bool:
    """验证 SRC 配置目录的必要文件能被完整解析。"""

    try:
        json_paths = list(path.glob("*.json"))
        deploy_path = path / "deploy.yaml"
        deploy_template_path = path / "deploy.template-cn.yaml"
        if not json_paths:
            return False
        if deploy_path.exists():
            if not deploy_path.is_file() or not isinstance(
                read_file(deploy_path), dict
            ):
                return False
        elif deploy_template_path.exists():
            if not deploy_template_path.is_file() or not isinstance(
                read_file(deploy_template_path), dict
            ):
                return False
        else:
            return False
        for json_path in json_paths:
            read_file(json_path)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError):
        return False
    return True


def _quarantine_directory(path: Path) -> None:
    quarantine_path = path.with_name(f"{path.name}.untrusted-{uuid.uuid4().hex}")
    path.rename(quarantine_path)
    logger.warning(f"已隔离不完整的 SRC 用户配置: {quarantine_path}")


def _remove_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def has_committed_src_user_config_transaction(config_path: Path) -> bool:
    """判断用户配置替换事务是否已有可恢复的提交副本。"""

    staging_path, staging_ready_path, _ = _transaction_paths(config_path)
    if staging_ready_path.exists():
        if staging_path.exists():
            return is_src_config_available(staging_path)
        return config_path.exists() and is_src_config_available(config_path)
    return False


def recover_src_user_config(
    config_path: Path,
    *,
    preserve_commit_marker: bool = False,
) -> None:
    """恢复上一次用户配置目录替换留下的中间状态。"""

    staging_path, staging_ready_path, backup_path = _transaction_paths(config_path)

    if staging_ready_path.exists() and staging_path.exists():
        if is_src_config_available(staging_path):
            if config_path.exists():
                if backup_path.exists() or not is_src_config_available(config_path):
                    _quarantine_directory(config_path)
                else:
                    config_path.rename(backup_path)
            try:
                staging_path.rename(config_path)
            except BaseException:
                if backup_path.exists() and not config_path.exists():
                    backup_path.rename(config_path)
                raise
            if not preserve_commit_marker:
                staging_ready_path.unlink(missing_ok=True)
                _remove_directory(backup_path)
            return

        _quarantine_directory(staging_path)
        staging_ready_path.unlink(missing_ok=True)
    elif staging_path.exists():
        _quarantine_directory(staging_path)

    # staging 已被提升但 ready 尚未删除时，当前目录就是已提交副本。
    if staging_ready_path.exists() and not staging_path.exists():
        if config_path.exists() and is_src_config_available(config_path):
            if not preserve_commit_marker:
                staging_ready_path.unlink(missing_ok=True)
                _remove_directory(backup_path)
            return
        if backup_path.exists() and is_src_config_available(backup_path):
            if config_path.exists():
                _quarantine_directory(config_path)
            backup_path.rename(config_path)
            staging_ready_path.unlink(missing_ok=True)
            return
        raise RuntimeError(f"SRC 用户配置事务无可恢复副本: {config_path}")

    if config_path.exists():
        if is_src_config_available(config_path):
            _remove_directory(backup_path)
            return
        if backup_path.exists() and is_src_config_available(backup_path):
            _quarantine_directory(config_path)
            backup_path.rename(config_path)
            return
        raise RuntimeError(f"SRC 新旧用户配置均不完整: {config_path}, {backup_path}")

    if backup_path.exists():
        if not is_src_config_available(backup_path):
            raise RuntimeError(f"SRC 用户配置备份不完整: {backup_path}")
        backup_path.rename(config_path)


def save_src_user_config(
    src_set_path: Path,
    config_path: Path,
    *,
    preserve_commit_marker: bool = False,
    expected_installation_id: str | None = None,
) -> None:
    """以可恢复的目录替换事务保存一次 SRC 用户配置。"""

    recover_src_user_config(config_path)
    staging_path, staging_ready_path, backup_path = _transaction_paths(config_path)

    if expected_installation_id is not None:
        validate_src_installation(
            src_set_path.parent,
            expected_installation_id,
        )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_set_path, staging_path)
    if not is_src_config_available(staging_path):
        raise RuntimeError(f"SRC 用户配置内容不完整: {staging_path}")
    if expected_installation_id is not None:
        validate_src_installation(
            src_set_path.parent,
            expected_installation_id,
        )
    write_file(staging_ready_path, {"ready": True}, format=".json")

    if config_path.exists():
        config_path.rename(backup_path)
    try:
        staging_path.rename(config_path)
    except BaseException:
        if backup_path.exists() and not config_path.exists():
            backup_path.rename(config_path)
        raise

    if not preserve_commit_marker:
        staging_ready_path.unlink(missing_ok=True)
        _remove_directory(backup_path)


def recover_interrupted_src_config_swap(
    src_set_path: Path,
    *,
    expected_installation_id: str,
) -> None:
    """回滚只留下备份目录的 SRC 配置交换。"""

    staging_path, _, backup_path = _transaction_paths(src_set_path)
    if src_set_path.exists() or not backup_path.exists():
        return
    if not is_src_config_available(backup_path):
        raise RuntimeError(f"SRC 配置恢复备份不完整: {backup_path}")

    validate_src_installation(src_set_path.parent, expected_installation_id)
    if staging_path.exists():
        _quarantine_directory(staging_path)
    backup_path.rename(src_set_path)
    validate_src_installation(src_set_path.parent, expected_installation_id)
    logger.warning(f"已回滚中断的 SRC 配置目录交换: {src_set_path}")


def _prepare_runtime_config_files(staging_path: Path) -> None:
    """为全新 SRC 安装生成运行期必需的配置入口。"""

    src_json_path = staging_path / "src.json"
    if not src_json_path.exists():
        template_path = next(
            (
                path
                for path in staging_path.glob("*.json")
                if path.name != "template.json"
            ),
            staging_path / "template.json",
        )
        if not template_path.is_file():
            raise RuntimeError(f"SRC 配置缺少 JSON 入口: {staging_path}")
        shutil.copyfile(template_path, src_json_path)

    deploy_path = staging_path / "deploy.yaml"
    deploy_template_path = staging_path / "deploy.template-cn.yaml"
    if not deploy_path.exists() and deploy_template_path.is_file():
        shutil.copyfile(deploy_template_path, deploy_path)


def stage_src_config_update(
    src_set_path: Path,
    *,
    expected_installation_id: str,
    overlay_path: Path | None = None,
) -> Path:
    """在 SRC 配置目录旁构建待提交副本，不直接修改运行目录。"""

    validate_src_installation(src_set_path.parent, expected_installation_id)
    recover_interrupted_src_config_swap(
        src_set_path,
        expected_installation_id=expected_installation_id,
    )
    staging_path = src_set_path.with_name(src_set_path.name + ".tmp")
    backup_path = src_set_path.with_name(src_set_path.name + ".old")
    if staging_path.exists():
        raise RuntimeError(f"SRC 配置目录存在未完成的替换事务: {staging_path}")
    if backup_path.exists():
        if not is_src_config_available(src_set_path):
            raise RuntimeError(f"SRC 配置目录存在未完成的替换事务: {backup_path}")
        _remove_directory(backup_path)
        validate_src_installation(src_set_path.parent, expected_installation_id)
    shutil.copytree(src_set_path, staging_path)
    if overlay_path is not None:
        shutil.copytree(overlay_path, staging_path, dirs_exist_ok=True)
    _prepare_runtime_config_files(staging_path)
    if not is_src_config_available(staging_path):
        raise RuntimeError(f"SRC 待提交配置内容不完整: {staging_path}")
    validate_src_installation(src_set_path.parent, expected_installation_id)
    return staging_path


def promote_src_config_update(
    src_set_path: Path,
    staging_path: Path,
    *,
    expected_installation_id: str,
) -> None:
    """复验安装实例后提交 SRC 配置，并在失败时恢复原目录。"""

    if not is_src_config_available(staging_path):
        raise RuntimeError(f"SRC 待提交配置内容不完整: {staging_path}")
    validate_src_installation(src_set_path.parent, expected_installation_id)
    backup_path = src_set_path.with_name(src_set_path.name + ".old")
    if backup_path.exists():
        raise RuntimeError(f"SRC 配置备份目录已存在: {backup_path}")

    staging_stat = staging_path.stat()
    src_set_path.rename(backup_path)
    try:
        staging_path.rename(src_set_path)
        if not is_src_config_available(src_set_path):
            raise RuntimeError(f"SRC 配置提交结果不完整: {src_set_path}")
        validate_src_installation(src_set_path.parent, expected_installation_id)
    except BaseException:
        if src_set_path.exists():
            promoted_stat = src_set_path.stat()
            if (
                promoted_stat.st_dev,
                promoted_stat.st_ino,
            ) == (
                staging_stat.st_dev,
                staging_stat.st_ino,
            ):
                src_set_path.rename(staging_path)
        if backup_path.exists() and not src_set_path.exists():
            backup_path.rename(src_set_path)
        raise
