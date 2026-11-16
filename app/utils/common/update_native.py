"""Linux/macOS FluxDown 布局；其他平台仅支持显式报错。"""

import sys

# macOS/Linux FluxDown 发布包使用无 .exe 后缀的命令行程序。
FLUXDOWN_EXE_NAMES = ("fluxdown",)
FLUXDOWN_AGENT_NAME = "fluxdown-agent"
FLUXDOWN_DAEMON_NAME = "fluxdownd"
HPATCHZ_MEMBER = None
HPATCHZ_FILENAME = None
supports_fluxdown_install = sys.platform in ("linux", "darwin")


def candidate_drives() -> list[str]:
    return []
