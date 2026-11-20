"""Windows 桌面分身插件与宿主共享的会话能力。"""

from app.core.desktop_session.lifecycle import DesktopSessionLifecycle
from app.utils.common.io import atomic_write as atomic_write
from app.utils.windows.desktop_session.native import (
    SYSTEM32 as SYSTEM32,
)
from app.utils.windows.desktop_session.native import (
    bind as bind,
)
from app.utils.windows.desktop_session.native import (
    checked as checked,
)
from app.utils.windows.desktop_session.native import (
    child_session as child_session,
)
from app.utils.windows.desktop_session.native import (
    current_identity as current_identity,
)
from app.utils.windows.desktop_session.native import (
    handle_scope as handle_scope,
)
from app.utils.windows.desktop_session.native import (
    kernel32 as kernel32,
)
from app.utils.windows.desktop_session.native import (
    process_session as process_session,
)
from app.utils.windows.desktop_session.native import (
    session_state as session_state,
)
from app.utils.windows.desktop_session.native import (
    set_dpi_awareness as set_dpi_awareness,
)
from app.utils.windows.desktop_session.native import (
    token_sid as token_sid,
)
from app.utils.windows.desktop_session.native import (
    user32 as user32,
)
from app.utils.windows.desktop_session.native import (
    wtsapi32 as wtsapi32,
)
from app.utils.windows.host import IS_ELEVATED as IS_ELEVATED


def assert_preview_closed() -> None:
    """检查当前客户端是否仍占用桌面分身插件。"""
    DesktopSessionLifecycle.assert_preview_closed()
