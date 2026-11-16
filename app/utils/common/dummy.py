"""仅对已声明但缺少实现的能力提供调用时错误。"""

from types import ModuleType

from .errors import UnsupportedPlatformError


def create_dummy(capability: str) -> ModuleType:
    module = ModuleType(f"app.utils.{capability}")

    def get_attribute(name: str):
        if name.startswith("__"):
            raise AttributeError(name)

        def unsupported(*args, **kwargs):
            raise UnsupportedPlatformError(capability)

        return unsupported

    module.__getattr__ = get_attribute
    return module
