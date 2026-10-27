"""Windows 注册表窄读取接口。"""

import winreg
from contextlib import suppress


def uninstall_entries(paths):
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
