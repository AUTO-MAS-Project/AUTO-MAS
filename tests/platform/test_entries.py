import ast
import importlib
import sys
from pathlib import Path

import pytest

from app.services.platform.power import power
from app.utils.platform import IS_WINDOWS, window
from app.utils.platform.common.errors import UnsupportedPlatformError
from app.utils.platform.process import platform_process


@pytest.mark.skipif(IS_WINDOWS, reason="仅验证非 Windows 公共入口")
def test_common_entries_do_not_load_windows_dependencies() -> None:
    assert platform_process.creation_flags == 0
    assert power.supported_actions == frozenset()
    assert "win32gui" not in sys.modules
    assert "win32crypt" not in sys.modules


@pytest.mark.skipif(IS_WINDOWS, reason="仅验证非 Windows 公共入口")
def test_unsupported_window_entry_reports_capability() -> None:
    with pytest.raises(UnsupportedPlatformError) as error:
        window.get_window_handles(1)

    assert error.value.capability == "window"


def _exported_names(path: Path) -> set[str]:
    """静态解析模块的公开导出名，避免在非 Windows 上导入 pywin32。"""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    names.add(target.id)
    return names


@pytest.mark.parametrize(
    ("common_path", "windows_path"),
    [
        ("common/window.py", "windows/window.py"),
        ("common/secret.py", "windows/secret.py"),
    ],
)
def test_platform_entries_expose_identical_names(
    common_path: str, windows_path: str
) -> None:
    """各平台实现必须暴露同名导出，防止调用方在另一平台上撞 AttributeError。"""

    root = Path(__file__).resolve().parents[2] / "app" / "utils" / "platform"
    assert _exported_names(root / common_path) == _exported_names(root / windows_path)


@pytest.mark.skipif(IS_WINDOWS, reason="仅验证非 Windows 不加载 pywin32")
def test_ocr_tool_imports_without_pywin32() -> None:
    """OCR 模块的 ADB 路径不应因桌面窗口能力缺失而无法导入。"""

    importlib.import_module("app.utils.OCR.OCRtool")

    assert "win32gui" not in sys.modules
    assert "win32con" not in sys.modules


def _class_members(path: Path, class_name: str) -> set[str]:
    """静态解析类的公开成员（方法与类属性）。"""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            members: set[str] = set()
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not item.name.startswith("_"):
                        members.add(item.name)
                elif isinstance(item, ast.AnnAssign) and isinstance(
                    item.target, ast.Name
                ):
                    members.add(item.target.id)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            members.add(target.id)
            return members
    raise AssertionError(f"{path} 中未找到类 {class_name}")


def test_process_platforms_expose_identical_members() -> None:
    """进程平台实现两侧成员必须一致，否则调用方在另一平台撞 AttributeError。"""

    root = Path(__file__).resolve().parents[2] / "app" / "utils" / "platform"
    common = _class_members(
        root / "common" / "process_platform.py", "CommonProcessPlatform"
    )
    windows = _class_members(root / "windows" / "process.py", "WindowsProcessPlatform")
    assert common == windows
