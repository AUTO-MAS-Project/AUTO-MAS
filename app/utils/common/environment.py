"""应用运行环境：只有显式 production 才启用生产行为。"""

import os
from typing import Literal

ApplicationEnvironment = Literal["development", "production"]


def get_application_environment() -> ApplicationEnvironment:
    """读取启动方传入的环境；独立启动和未知值均按开发环境处理。"""

    raw = os.getenv("AUTO_MAS_ENV", "").strip().lower()
    return "production" if raw == "production" else "development"


def is_development_environment() -> bool:
    """判断当前进程是否使用开发环境行为。"""

    return get_application_environment() == "development"
