"""完整 ZIP 重建契约：原始头和目录不重编码，最终仍验证独立整包摘要。"""

import hashlib
import io
import threading
import zipfile

import pytest

from app.utils.common.zip_range import rebuild_zip


@pytest.mark.parametrize("failure", [None, "digest", "cancel"])
def test_rebuild_preserves_target_zip_bytes_and_rejects_invalid_result(
    tmp_path, failure
):
    old, target = tmp_path / "old.zip", tmp_path / "target.zip"
    with zipfile.ZipFile(old, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("same.bin", b"unchanged" * 10000)
        archive.writestr("deleted.bin", b"obsolete")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("added.bin", b"new")
        info = zipfile.ZipInfo("same.bin", date_time=(2026, 11, 14, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, b"unchanged" * 10000)
        archive.comment = b"keep the target comment"
    content = target.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    cancel = threading.Event()
    if failure == "cancel":
        cancel.set()
    if failure:
        with pytest.raises(InterruptedError if failure == "cancel" else ValueError):
            rebuild_zip(
                old,
                io.BytesIO(content),
                tmp_path / "rebuilt.zip",
                len(content),
                "0" * 64 if failure == "digest" else digest,
                cancel,
            )
    else:
        reused, fetched = rebuild_zip(
            old,
            io.BytesIO(content),
            tmp_path / "rebuilt.zip",
            len(content),
            digest,
            cancel,
        )
        assert (reused, fetched) == (1, 1)
        assert (tmp_path / "rebuilt.zip").read_bytes() == content
