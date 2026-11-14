"""阻止两个 MAS 后端同时写入同一工作目录。"""

import os
from pathlib import Path

import pytest

from app.core.desktop_session.ownership import data_owner


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows 启用桌面分身数据交接")
def test_workspace_has_one_writer_until_owner_releases(tmp_path: Path):
    main = tmp_path / "main"
    other = tmp_path / "other"
    with data_owner(main):
        with pytest.raises(RuntimeError), data_owner(main):
            pytest.fail("第二个写入者取得了同一工作目录")
        with data_owner(other):
            assert (other / "temp" / "desktop-session-data.lock").is_file()

    with data_owner(main):
        assert (main / "temp" / "desktop-session-data.lock").is_file()
