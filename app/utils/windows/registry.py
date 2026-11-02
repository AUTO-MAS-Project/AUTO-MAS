"""Windows 注册表窄读取接口。"""

import winreg
from collections.abc import Iterable, Iterator
from contextlib import suppress


def user_subkey_values(path: str, value_name: str) -> Iterator[tuple[str, str]]:
    """读取当前用户指定键的直接子键值；缺项跳过，不推断业务含义。"""
    with suppress(OSError):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as root:
            for index in range(winreg.QueryInfoKey(root)[0]):
                child = winreg.EnumKey(root, index)
                with suppress(OSError):
                    with winreg.OpenKey(root, child) as entry:
                        yield child, str(winreg.QueryValueEx(entry, value_name)[0])


def uninstall_entries(paths: Iterable[str]) -> Iterator[tuple[str, str]]:
    for path in paths:
        with suppress(FileNotFoundError, OSError):
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                i = 0
                while True:
                    try:
                        child = winreg.EnumKey(key, i)
                        i += 1
                    except OSError:
                        break
                    with suppress(FileNotFoundError, OSError):
                        with winreg.OpenKey(key, child) as subkey:
                            name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                            command, _ = winreg.QueryValueEx(subkey, "UninstallString")
                            if isinstance(name, str) and isinstance(command, str):
                                yield name, command


def com_server(clsid: str) -> str:
    with winreg.OpenKey(
        winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\LocalServer32"
    ) as key:
        return str(winreg.QueryValueEx(key, "")[0])
