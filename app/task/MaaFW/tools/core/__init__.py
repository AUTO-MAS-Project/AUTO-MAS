"""宿主内置的 MaaFW Core 服务实现。

这些模块来自 MaaFW 插件仓的领域包，但在普通 AUTO-MAS 宿主中作为
内部实现随程序发布，不参与插件发现或插件生命周期。
"""

from .automas_maafw_interface import MaaFWInterfaceService
from .automas_maafw_project_update import MaaFWProjectUpdateService

__all__ = [
    "MaaFWInterfaceService",
    "MaaFWProjectUpdateService",
]
