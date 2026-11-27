"""三月七对外公布的配置目录与 Windows 首次迁移入口。"""

import os
import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version

from app.utils import ProcessRunner

from .m7a_runtime import build_m7a_env
from .update.engines import get_spec, read_installed_version


def _uses_userdata(root: Path) -> bool:
    installed = read_installed_version(get_spec("M7A"), root)
    if installed is None:
        return (root / "userdata" / "config.yaml").is_file()
    try:
        return Version(installed) >= Version("2026.11.25b0")
    except InvalidVersion:
        return (root / "userdata" / "config.yaml").is_file()


def resolve_m7a_config_path(root: str | Path) -> Path:
    """取新版配置、尚待迁移的旧配置，或对应版本的默认创建位置。"""
    root = Path(root)
    legacy = root / "config.yaml"
    if not _uses_userdata(root):
        return legacy
    if data_dir := os.environ.get("M7A_DATA_DIR"):
        return (root / data_dir).resolve() / "config.yaml"
    current = root / "userdata" / "config.yaml"
    return current if current.is_file() or not legacy.is_file() else legacy


async def prepare_m7a_config(root: Path) -> Path:
    """让三月七在 MAS 备份或写入托管配置前完成 Windows 自动迁移。"""
    if (
        sys.platform == "win32"
        and (root / "config.yaml").is_file()
        and _uses_userdata(root)
        and not os.environ.get("M7A_DATA_DIR")
    ):
        # 查询入口会先执行上游自己的数据迁移，不启动游戏，也不需要提升权限。
        try:
            result = await ProcessRunner.run_process(
                root / "m7a.exe",
                "--status",
                cwd=root,
                env=build_m7a_env(),
            )
        except (OSError, TimeoutError) as error:
            raise RuntimeError(f"无法检查三月七数据迁移：{root}（{error}）") from error
        if (
            result.returncode != 0
            or (root / "config.yaml").is_file()
            or not (root / "userdata" / "config.yaml").is_file()
        ):
            raise RuntimeError(
                f"三月七数据迁移未完成，请先打开三月七处理迁移提示后重试：{root}"
                f"（检查退出码 {result.returncode}）"
            )
    return resolve_m7a_config_path(root)
