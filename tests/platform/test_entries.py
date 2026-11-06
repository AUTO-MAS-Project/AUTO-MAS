import sys

import pytest

from app.services import power
from app.utils import (
    IS_WINDOWS,
    process_platform,
    secret,
)

platform_process = process_platform.platform_process

pytestmark = pytest.mark.skipif(IS_WINDOWS, reason="仅验证非 Windows 公共入口")


def test_common_entries_do_not_load_windows_dependencies() -> None:
    assert platform_process.creation_flags == 0
    assert power.supported_actions == frozenset()
    assert secret.supports_secret_storage() is False
    assert {"win32gui", "win32crypt"}.isdisjoint(sys.modules)
