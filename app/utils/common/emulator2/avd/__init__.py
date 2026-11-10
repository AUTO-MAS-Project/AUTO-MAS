#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""Emulator 2.0 的第三种后端：ModAVD（基于 Android Emulator 的自编版，随内测包发）。

MAS 只通过根目录里的 ModAVD 命令行 ``tools\\modavd.exe``（:mod:`.cli`）控制 ModAVD：实例的启动 / 关机 /
状态 / 设置 / 增删、客体里的命令（``modavd shell`` / ``modavd adb``）、adb server（``modavd servers``）、
组件与电脑检查（``modavd check``）、整包更新（:mod:`.updater`，``modavd update``）都交给它；没有它的
根目录不支持。MAS 不读写 ModAVD 自己的文件，端口、adb 路径都取命令行报的。

- :mod:`.constants`      实例档位参数、看门狗与关机时限
- :mod:`.components`     根目录的路径换算（规范化键、实例锁的键）
- :mod:`.instances`      实例选项校验
- :mod:`.cli`            ModAVD 命令行 ``modavd`` 的客户端
- :mod:`.host`           宿主侧：脚本用的 adb server（``modavd servers``）、端口冲突
- :mod:`.precheck`       开机前检查项的数据类型（检查本身由 modavd 做）
- :mod:`.manager`        ``DeviceBase`` 实现（走 modavd，冻结看门狗）
- :mod:`.service`        给 API 用的业务入口
- :mod:`.updater`        更新：查更新、「更新」（准备、换上）、启动恢复，都交给 ``modavd update``
"""


def _get_public_export(name):
    raise AttributeError(name)


_SUBMODULES = {
    "service": ".service",
    "host": ".host",
    "instances": ".instances",
    "constants": ".constants",
    "updater": ".updater",
    "precheck": ".precheck",
    "maafw_extras": ".maafw_extras",
    "components": ".components",
    "manager": ".manager",
}


def __getattr__(name):
    if name in _SUBMODULES:
        from importlib import import_module

        value = import_module(_SUBMODULES[name], __name__)
        globals()[name] = value
        return value
    return _get_public_export(name)
