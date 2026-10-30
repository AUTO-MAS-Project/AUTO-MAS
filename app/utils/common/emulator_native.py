"""非 Windows 宿主保持既有能力降级。"""

from .errors import UnsupportedPlatformError


def shm_exists(port: int) -> bool:
    return False


def cpu_cache_topology() -> bytes:
    return b""


def prepare_window_visibility():
    raise UnsupportedPlatformError("emulator_windows")


def vulkan_probe_path():
    # 非 Windows 的启动预检会拒绝该能力，不启动 Windows 探针。
    return None
