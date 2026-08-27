"""MaaFW 第一层·外部运行：UI 外壳家族识别。

按项目根目录里的特征文件判定外壳家族，绝不按 exe 名判定
（M9A 与 MaaKes 同为 MFAAvalonia，但 exe 分别是 m9a.exe / MFAAvalonia.exe；
MaaEnd 与 MaaYYs 同为 MXU，但 exe 分别是 MaaEnd.exe / mxu.exe）。
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class ShellFamily(str, Enum):
    """已识别的 MaaFW UI 外壳家族。"""

    MFAAVALONIA = "MFAAvalonia"
    MXU = "MXU"
    UNKNOWN = "unknown"


# 各家族的「精确特征文件」：目录下同时存在全部特征文件才判定为该家族。
_FAMILY_MARKERS: dict[ShellFamily, tuple[str, ...]] = {
    ShellFamily.MFAAVALONIA: ("MFAAvalonia.dll", "appsettings.json"),
}

# 各家族的「特征 glob」（相对项目根）：命中任一 glob 即判定为该家族。
# MXU 的外壳容器是 config/mxu-<项目名>.json，项目名部分不固定，只能按模式匹配。
_FAMILY_GLOB_MARKERS: dict[ShellFamily, tuple[str, ...]] = {
    ShellFamily.MXU: ("config/mxu-*.json",),
}


def detect_shell_family(project_root: str | Path) -> ShellFamily:
    """按特征文件识别项目所属的 UI 外壳家族。

    Args:
        project_root: MaaFW 项目根目录（含 interface.json 的目录）。

    Returns:
        命中的 ShellFamily；目录不存在或无法识别时返回 ShellFamily.UNKNOWN。
    """
    root = Path(project_root)

    for family, markers in _FAMILY_MARKERS.items():
        if all((root / marker).is_file() for marker in markers):
            return family

    for family, patterns in _FAMILY_GLOB_MARKERS.items():
        if any(any(root.glob(pattern)) for pattern in patterns):
            return family

    return ShellFamily.UNKNOWN
