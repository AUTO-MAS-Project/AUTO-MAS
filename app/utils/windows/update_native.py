"""更新工具的 Windows 可执行文件布局与发现。"""

import string
from pathlib import Path

FLUXDOWN_EXE_NAMES = ("fluxdown.exe", "fluxdown-cli.exe", "fluxdown-desktop.exe")
FLUXDOWN_AGENT_NAME = "fluxdown-agent.exe"
FLUXDOWN_DAEMON_NAME = "fluxdownd.exe"
HPATCHZ_MEMBER = "windows64/hpatchz.exe"
HPATCHZ_FILENAME = "hpatchz.exe"
supports_fluxdown_install = True


def candidate_drives() -> list[str]:
    return [
        f"{letter}:\\"
        for letter in string.ascii_uppercase
        if Path(f"{letter}:\\").exists()
    ]
