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

和雷电 / MuMu 不同，这里没有厂商的管理器程序可调。MAS 不下载组件：用户把 ModAVD 发布包解压到一个
根目录（模拟器只认里面 ``sdk\\emulator`` 的自编版），平台工具和系统镜像由包里的「补全组件.bat」补齐；缺了
说缺哪一项、怎么补。模拟器本体可以在 MAS 里一键更新（:mod:`.updater`）。实例的启动 / 关机 / 状态 /
设置 / 增删都交给根目录里的命令行 ``tools\\modavd.exe``（:mod:`.cli`）；没有它的根目录不支持。
宿主侧另有一个私有 adb server（默认端口 20050）给拉起应用、截图等用。

- :mod:`.constants`      端口、组件位置、实例档位参数
- :mod:`.components`     组件检查（关键文件、自编版探测、内测包编号）、元数据
- :mod:`.instances`      AVD 配置文件的读取与选项校验
- :mod:`.cli`            ModAVD 命令行 ``modavd`` 的客户端
- :mod:`.host`           宿主侧：进程查找、私有 adb、客体日志落盘
- :mod:`.precheck`       开机前检查项的数据类型（检查本身由 modavd 做）
- :mod:`.manager`        ``DeviceBase`` 实现（走 modavd，冻结看门狗）
- :mod:`.service`        给 API 用的业务入口
- :mod:`.update_source`  版本号、下载源（Mirror 酱、GitHub）
- :mod:`.update_range`   GitHub 的整包按区间只取变了的文件
- :mod:`.update_stage`   更新的本机文件操作：解包、核对、换上、崩溃恢复
- :mod:`.updater`        更新流程：查更新，「更新」一键下载、核对、换上，启动恢复
"""


def _get_public_export(name):
    raise AttributeError(name)


_SUBMODULES = {
    "service": ".service",
    "update_range": ".update_range",
    "host": ".host",
    "instances": ".instances",
    "update_source": ".update_source",
    "constants": ".constants",
    "updater": ".updater",
    "precheck": ".precheck",
    "maafw_extras": ".maafw_extras",
    "components": ".components",
    "update_stage": ".update_stage",
    "manager": ".manager",
}


def __getattr__(name):
    if name in _SUBMODULES:
        from importlib import import_module

        value = import_module(_SUBMODULES[name], __name__)
        globals()[name] = value
        return value
    return _get_public_export(name)
