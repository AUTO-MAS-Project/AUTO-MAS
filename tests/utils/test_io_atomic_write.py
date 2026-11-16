"""原子保存失败时保留旧内容，诊断不得泄露配置正文。"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from app.utils import io as _utils_io


def test_failed_atomic_save_preserves_original_and_keeps_contents_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "SyntheticProfileName"
    folder.mkdir()
    path = folder / "config.json"
    path.write_bytes(b"private original payload")
    failure = PermissionError("file is held")
    failure.winerror = 5
    replace = Mock(side_effect=failure)
    logger = Mock()
    monkeypatch.setattr(Path, "replace", value=replace)
    monkeypatch.setattr(_utils_io, "sleep", value=lambda _delay: None)
    monkeypatch.setattr(_utils_io, "logger", value=logger)

    with pytest.raises(PermissionError) as caught:
        _utils_io.atomic_write(path, b"private replacement payload")

    assert caught.value is failure
    assert path.read_bytes() == b"private original payload"
    assert not path.with_name("config.json.tmp").exists()
    diagnostics = "\n".join(getattr(failure, "__notes__", ())) + str(logger.mock_calls)
    assert "private original payload" not in diagnostics
    assert "private replacement payload" not in diagnostics
