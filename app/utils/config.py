'''
配置文件管理, 使用yaml格式\n
注意: 此文件仅处理程序配置项而非用户配置
'''

from pathlib import Path
from typing import Any, ClassVar
import yaml
from pydantic import BaseModel

class BaseYAMLConfig(BaseModel):
    # 必要项
    CONFIG_PATH: ClassVar[Path]

    @classmethod
    def load(cls, config_path: Path | None = None) -> "BaseYAMLConfig":
        """
        从 YAML 文件加载配置。如果文件不存在或为空，则使用类中定义的默认值。
        """
        # 使用传入路径或类变量路径
        if not cls.CONFIG_PATH:
            raise ValueError("CONFIG_PATH必须被设置")
        path = (config_path or cls.CONFIG_PATH).resolve()

        if not path.exists():
            # print(f"[Warning] Config file '{path}' not found. Using default values.")
            data: dict[str, Any] = {}
        else:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data is None:
                        data = {}
                    if not isinstance(data, dict):
                        raise ValueError(f"Expected dict in {path}, got {type(data)}")
            except Exception as e:
                raise RuntimeError(f"Failed to load config from {path}: {e}")

        try:
            return cls.model_validate(data)
        except Exception as e:
            raise ValueError(f"Invalid config for {cls.__name__}: {e}")


class LogConfig (BaseModel):
    """
    日志配置
    """
    CONFIG_PATH:ClassVar[Path] = Path("config.yaml")

    level: str = "DEBUG"
    writelevel: str = "INFO"
    log_dir: str = "logs"
    max_size: int = 10























