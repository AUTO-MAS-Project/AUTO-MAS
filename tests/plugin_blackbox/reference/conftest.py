"""Deterministic 黑盒测试 conftest:定位 reference 根目录与样本清单。

本测试套件不启动 Agent/游戏/模拟器,不联网,仅做静态文件解析。
"""

from __future__ import annotations

from pathlib import Path

# 测试文件位于:
#   AUTO-MAS-Projects/AUTO-MAS-workspace/worktrees/all-plugins-integration/
#   tests/plugin_blackbox/reference/conftest.py
# 回溯 6 层到 AUTO-MAS-Projects 工作区根（parents[0]=reference 目录本身）。
_WORKSPACE_ROOT: Path = Path(__file__).resolve().parents[6]
REFERENCE_ROOT: Path = _WORKSPACE_ROOT / "reference"

# 源码样本:interface.json 在 assets/ 下;二进制样本:interface.json 在根目录。
# 元素: (样本目录名, interface.json 相对路径)
MAAFW_INTERFACE_SAMPLES: tuple[tuple[str, str], ...] = (
    ("M9A", "assets/interface.json"),
    ("M9A-main", "assets/interface.json"),
    ("Maa_bbb", "assets/interface.json"),
    ("M9A-win-x86_64-v3.10.4", "interface.json"),
    ("M9A-win-x86_64-v3.20.1", "interface.json"),
    ("M9A-win-x86_64-v4.5.0", "interface.json"),
    ("Maa_bbb-win-x86_64-v1.10.9", "interface.json"),
    ("Maa_bbb-win-x86_64-v1.12.5", "interface.json"),
    ("Maa_bbb-win-x86_64-v1.12.8", "interface.json"),
    ("MaaEnd-win-x86_64-v1.16.0-beta.1", "interface.json"),
    ("MaaKes-win-x86_64-v1.1.11", "interface.json"),
    ("MaaYYs-win-x86_64-v3.10.2", "interface.json"),
)

# 非 MaaFW 样本(无 interface.json,纯脚本/二进制/框架源码)。
NON_MAAFW_SAMPLES: tuple[str, ...] = (
    "March7thAssistant",
    "MaaFramework",
    "MAA-v5.16.10-win-x64",
    "MAA-v5.18.3-win-x64",
    "StarRailAssistant-v2.16.1",
)

# MaaFramework 权威 schema 路径。
SCHEMA_PATH: Path = REFERENCE_ROOT / "MaaFramework" / "tools" / "interface.schema.json"
