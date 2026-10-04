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

"""Emulator 2.0 的第三种后端：魔改 AVD（基于 Android Emulator 的自编版，随内测包发）。

和雷电 / MuMu 不同，这里没有厂商的管理器程序可调。模拟器只认内测包里的自编版（解压到用户选的
根目录，里面是 ``sdk\\emulator``），不下载谷歌原版；平台工具（adb）和系统镜像内测包里没有时，
由用户同意许可后从谷歌仓库下载到同一个根目录。实例（AVD）由我们自己写配置文件管理，
启动 / 关机 / 状态全部直接驱动 ``emulator.exe`` 和一个私有 adb server（默认端口 20050）。

- :mod:`.constants`   端口、固定版本、下载源、实例模板参数
- :mod:`.components`  组件检查、许可证、测速、断点续传下载、校验、解压
- :mod:`.instances`   AVD 配置文件的增删改查
- :mod:`.host`        宿主侧：硬件加速检查、内存预检、进程查找、控制台、私有 adb
- :mod:`.manager`     ``DeviceBase`` 实现（启动调优、首次初始化、冻结看门狗）
- :mod:`.service`     给 API 用的业务入口
"""
