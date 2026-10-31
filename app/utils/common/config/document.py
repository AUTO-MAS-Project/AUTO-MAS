"""后端完整初始化前使用的只读配置入口。"""

from pathlib import Path
from typing import Any

from app.utils.common.io import read_dict_file


def read_bootstrap_setting(config_path: Path) -> dict[str, Any]:
    """优先读取 YAML；迁移完成后不再回退旧 JSON。"""
    yaml_path = config_path.parent / "setting.yaml"
    if yaml_path.exists():
        return read_dict_file(yaml_path, allow_empty=True)
    record_path = config_path.parent / ".config-migration-v2.json"
    if record_path.exists() and read_dict_file(record_path).get("complete") is True:
        return {}
    return read_dict_file(config_path.parent / "Config.json")
