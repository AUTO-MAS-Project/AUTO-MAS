"""ModAVD 根目录 ``mas-avd.json`` 的读改写契约测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.common.emulator2.avd.components import MetadataUnreadable
from app.utils.common.emulator2.avd.constants import METADATA_FILE
from app.utils.common.emulator2.avd.instances import update_instance_meta


def test_update_instance_meta_leaves_unreadable_metadata_untouched(
    tmp_path: Path,
) -> None:
    # 没有 modavd.exe 的旧根目录上，新建实例、首次开机、改设置都走这个写入。文件读不出时
    # 以前按空字典整份写回，sdkRoot、组件版本和别的实例全没了，只剩这一台
    path = tmp_path / METADATA_FILE
    original = b'{"sdkRoot": "sdk", "instances": {"0": {"memoryMb": 4096}}'
    path.write_bytes(original)

    with pytest.raises(MetadataUnreadable):
        update_instance_meta(tmp_path, 7, memoryMb=6144)

    assert path.read_bytes() == original
