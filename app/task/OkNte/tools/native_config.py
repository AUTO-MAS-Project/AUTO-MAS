"""记录 OK-NTE 下发配置后的指纹，用于安全处置延后的快照。"""

from functools import partial
from hashlib import file_digest
from pathlib import Path

from app.utils import io


def config_file_fingerprint(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def publish_staged_config(
    staged_path: Path,
    live_path: Path,
    snapshot_path: Path,
    *,
    script_id: str,
    folder_mode: bool,
) -> None:
    """先记下待换入指纹，再原子发布已准备完成的配置。"""
    snapshot = io.read_native_config_snapshot(
        snapshot_path, expected_script_id=script_id
    )
    if snapshot is not None:
        fingerprint = io.dir_fingerprint if folder_mode else config_file_fingerprint
        pending = fingerprint(staged_path)
        previous = snapshot.injected
        if (
            snapshot.pending_injected is not None
            and (live_path.is_dir() if folder_mode else live_path.is_file())
            and fingerprint(live_path) == snapshot.pending_injected
        ):
            previous = snapshot.pending_injected
        save_snapshot = partial(
            io.write_native_config_snapshot,
            snapshot_path,
            script_id=script_id,
            original_exists=snapshot.original_exists,
            baseline=snapshot.baseline,
        )
        save_snapshot(injected=previous, pending_injected=pending)

    if folder_mode:
        io.swap_in_dir(staged_path, live_path)
    else:
        staged_path.replace(live_path)

    if snapshot is not None:
        save_snapshot(injected=pending)
