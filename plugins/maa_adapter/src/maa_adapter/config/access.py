import uuid

from auto_mas_core.host.core import Config
from auto_mas_core.host.utils import get_logger

from maa_adapter.config.script import MaaConfig

logger = get_logger("MAA")


def _maa_script_config(script_id: str) -> MaaConfig:
    """解析 MAA 脚本配置并拒绝跨类型 ID 访问。"""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, MaaConfig):
        raise TypeError(f"托管 {script_id} 不是 MAA 脚本")
    return script_config
