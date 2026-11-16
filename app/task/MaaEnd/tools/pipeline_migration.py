"""MaaEnd 合并 pipeline 的专项迁移策略；通用安装器只调用已声明的回调。"""

import shutil
import tempfile
import threading
from pathlib import Path

from app.services.script_install import (
    InstallUnsafeError,
    _check_cancel,
    _reject_link,
    tree_hashes,
)


def refresh_merged_pipelines(
    ready: Path,
    package: Path,
    directory: Path,
    cancelled: threading.Event,
) -> None:
    """重建官方已合并的 pipeline，保留旧版文件的完整独立备份。

    旧拆分 JSON 与新版 nodes.json 共存会产生同名节点，导致资源加载失败。
    只针对发行包明确包含 resource*/pipeline/nodes.json 的完整资源目录；
    旧文件备份在工作区，不会被 MaaFramework 递归加载。
    """
    backup_root: Path | None = None
    for resource in package.iterdir():
        _check_cancel(cancelled)
        if not resource.is_dir() or not resource.name.startswith("resource"):
            continue
        packaged_pipeline = resource / "pipeline"
        if not (packaged_pipeline / "nodes.json").is_file():
            continue
        existing = ready / resource.name / "pipeline"
        if not existing.exists():
            continue
        _reject_link(existing)
        if not existing.is_dir():
            raise InstallUnsafeError("原 pipeline 路径不是目录，不能安全更新")
        # 没有完整旧清单时也要识别新版已废弃的文件。
        # 即使是用户定制的 JSON 也不丢弃：备份后才从运行目录移出。
        has_obsolete = any(
            entry.is_file()
            and not (packaged_pipeline / entry.relative_to(existing)).is_file()
            for entry in existing.rglob("*")
        )
        if not has_obsolete:
            continue
        if backup_root is None:
            saved = directory / "retired-pipelines"
            saved.mkdir(exist_ok=True)
            _reject_link(saved)
            backup_root = Path(tempfile.mkdtemp(prefix="pipeline-", dir=saved))
            (backup_root / "README.txt").write_text(
                "旧版 MaaEnd pipeline 已在完整包升级时迁移到此备份。"
                "这些文件不会再由新版资源加载器读取；需要自定义配置时请手动核对后迁移。\n",
                encoding="utf-8",
            )
        previous_hashes = tree_hashes(existing, cancelled)
        saved_pipeline = backup_root / resource.name / "pipeline"
        saved_pipeline.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(existing, saved_pipeline)
        if tree_hashes(saved_pipeline, cancelled) != previous_hashes:
            raise InstallUnsafeError("旧 pipeline 备份校验失败，已停止安装")
        _check_cancel(cancelled)
        shutil.rmtree(existing)
