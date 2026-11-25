"""记录 OK-NTE 下发配置后的指纹，用于安全处置延后的快照。"""

from hashlib import file_digest
from pathlib import Path

from app.utils import io


def config_file_fingerprint(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def mark_config_injected(
    snapshot_path: Path,
    live_path: Path,
    *,
    script_id: str,
    folder_mode: bool,
) -> None:
    """目录复用原生快照；单文件仅记录本轮新建文件的指纹。"""
    if folder_mode:
        io.mark_native_config_injected(snapshot_path, live_path, script_id=script_id)
        return

    snapshot = io.read_native_config_snapshot(
        snapshot_path, expected_script_id=script_id
    )
    if snapshot is None or snapshot.original_exists or not live_path.is_file():
        return
    io.write_native_config_snapshot(
        snapshot_path,
        script_id=script_id,
        original_exists=False,
        baseline=snapshot.baseline,
        injected=config_file_fingerprint(live_path),
    )


def publish_staged_config(
    staged_path: Path,
    live_path: Path,
    snapshot_path: Path,
    *,
    script_id: str,
    folder_mode: bool,
) -> None:
    """先记下待换入指纹，再原子发布已准备完成的配置。"""
    previous = io.read_native_config_snapshot(
        snapshot_path, expected_script_id=script_id
    )
    mark_config_injected(
        snapshot_path, staged_path, script_id=script_id, folder_mode=folder_mode
    )
    try:
        if folder_mode:
            io.swap_in_dir(staged_path, live_path)
        else:
            staged_path.replace(live_path)
    except Exception:
        # 原子换入失败时现场仍是上一份配置，复原对应的注入指纹。
        if previous is not None:
            io.write_native_config_snapshot(
                snapshot_path,
                script_id=script_id,
                original_exists=previous.original_exists,
                baseline=previous.baseline,
                injected=previous.injected,
            )
        raise
