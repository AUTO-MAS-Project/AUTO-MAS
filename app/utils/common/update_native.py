"""没有专用工具布局时，只使用显式配置与 PATH 入口。"""

FLUXDOWN_EXE_NAMES = ()
FLUXDOWN_AGENT_NAME = None
FLUXDOWN_DAEMON_NAME = None
HPATCHZ_MEMBER = None
HPATCHZ_FILENAME = None


def candidate_drives() -> list[str]:
    return []
