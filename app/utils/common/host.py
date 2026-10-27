"""非 Windows 平台的兼容默认值。"""

IS_WINDOWS = False
IS_ELEVATED = True


def is_admin() -> bool:
    return True


def is_long_path_supported() -> bool:
    return True
