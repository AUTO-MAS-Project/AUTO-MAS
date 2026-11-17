"""公共配置操作读取插件与存量专项的共同信息，不导入具体适配器。"""

from typing import Any, cast

from app.config import ConfigCollection
from app.models.config import ScriptConfigType, ScriptEntry, UserConfigType, UserEntry


def script_users(script: ScriptConfigType) -> ConfigCollection[Any]:
    """取得托管实际用户集合，插件以 users 声明，存量专项保留 UserData。"""
    return (
        script.users
        if isinstance(script, ScriptEntry)
        else cast(ConfigCollection[Any], script.UserData)
    )


def entry_name(entry: ScriptConfigType | UserConfigType) -> str:
    """读取框架统一名称或存量专项名称，供公共列表、锁提示和通知展示。"""
    return (
        entry.info.name
        if isinstance(entry, (ScriptEntry, UserEntry))
        else entry.Info.Name
    )
