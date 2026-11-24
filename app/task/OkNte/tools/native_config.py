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
