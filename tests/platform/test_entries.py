import sys

import pytest

from app.services.platform.power import power
from app.utils.platform import IS_WINDOWS, window
from app.utils.platform.common.errors import UnsupportedPlatformError
from app.utils.platform.common.process import get_main_window_handle, get_window_handles
from app.utils.platform.process import platform_process

pytestmark = pytest.mark.skipif(IS_WINDOWS, reason="仅验证非 Windows 公共入口")


def test_common_entries_do_not_load_windows_dependencies() -> None:
    assert platform_process.creation_flags == 0
    assert power.supported_actions == frozenset()
    assert {"win32gui", "win32crypt"}.isdisjoint(sys.modules)


def test_unsupported_window_entry_reports_capability() -> None:
    with pytest.raises(UnsupportedPlatformError, match="window"):
        window.get_window_handles(1)


def test_desktop_callers_use_common_fallbacks() -> None:
    assert (get_window_handles(1), get_main_window_handle(1)) == ([], None)
    assert "win32gui" not in sys.modules
