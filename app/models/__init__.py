#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from . import dto, emulator, task
from .config_base import ConfigBase, ConfigItem, MultipleConfig, dump_toml
from .pydantic_base import PydanticConfigBase
from .common import EmulatorConfig, QueueConfig, QueueItem, TimeSet, Webhook
from .maa import MaaConfig, MaaPlanConfig, MaaUserConfig
from .maaend import MaaEndConfig, MaaEndUserConfig
from .src import SrcConfig, SrcUserConfig
from .general import GeneralConfig, GeneralUserConfig
from .global_config import CLASS_BOOK, GlobalConfig, ToolsConfig
from .type import (
    EncryptedString,
    HHMMString,
    JsonDictString,
    JsonListString,
    KeyboardKeyString,
    UrlString,
    YmdHmString,
    YmdHmsString,
    YmdString,
    decrypt_encrypted_string,
)

__all__ = [
    "ConfigBase",
    "MultipleConfig",
    "ConfigItem",
    "dump_toml",
    "PydanticConfigBase",
    "EmulatorConfig",
    "Webhook",
    "QueueItem",
    "TimeSet",
    "QueueConfig",
    "MaaPlanConfig",
    "MaaUserConfig",
    "MaaConfig",
    "MaaEndUserConfig",
    "MaaEndConfig",
    "SrcUserConfig",
    "SrcConfig",
    "GeneralUserConfig",
    "GeneralConfig",
    "ToolsConfig",
    "GlobalConfig",
    "CLASS_BOOK",
    "JsonDictString",
    "JsonListString",
    "HHMMString",
    "YmdHmString",
    "YmdString",
    "YmdHmsString",
    "UrlString",
    "KeyboardKeyString",
    "EncryptedString",
    "decrypt_encrypted_string",
    "dto",
    "emulator",
    "task",
]
