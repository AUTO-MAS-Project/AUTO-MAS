"""Deterministic 黑盒测试 conftest:定位 reference 根目录与样本清单。

本测试套件不启动 Agent/游戏/模拟器,不联网,仅做静态文件解析。
"""

from __future__ import annotations

import os
from pathlib import Path

# 优先定位实际存在的外层 reference 语料库。精简 clone 或短路径工作树
# 可能没有原历史目录深度，此时退回宿主仓库旁的可选 reference 路径，
# 由下方严格门禁决定是否要求它存在。
_TEST_FILE = Path(__file__).resolve()
_HOST_ROOT = _TEST_FILE.parents[3]
_WORKSPACE_ROOT = next(
    (
        parent
        for parent in _TEST_FILE.parents
        if (parent / "reference").is_dir()
    ),
    _HOST_ROOT.parent,
)
REFERENCE_ROOT: Path = _WORKSPACE_ROOT / "reference"

# reference 是工作区外部语料，不属于宿主或便携包运行时依赖。开发机可以只保留
# 一部分样本；需要认证完整语料库时显式开启严格门禁。
STRICT_REFERENCE_CORPUS: bool = (
    os.environ.get("AUTO_MAS_REQUIRE_REFERENCE_CORPUS", "").strip() == "1"
)

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
