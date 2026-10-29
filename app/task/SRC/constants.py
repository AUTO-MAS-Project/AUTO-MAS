#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 ClozyA
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

"""SRC 登录与客户端更新使用的星穹铁道运行时声明。"""

STARRAIL_PACKAGE_NAME = {
    "CN-Official": "com.miHoYo.hkrpg",
    "CN-Bilibili": "com.miHoYo.hkrpg.bilibili",
    "VN-Official": "com.HoYoverse.hkrpgvn",
    "OVERSEA-America": "com.HoYoverse.hkrpgoversea",
    "OVERSEA-Asia": "com.HoYoverse.hkrpgoversea",
    "OVERSEA-Europe": "com.HoYoverse.hkrpgoversea",
    "OVERSEA-TWHKMO": "com.HoYoverse.hkrpgoversea",
}
"""崩坏·星穹铁道包名映射表"""

STARRAIL_CN_UPDATE_LINK_URL = (
    "https://act-api-takumi.mihoyo.com/event/download_porter/link"
    "/hkrpg_cn/official/android_default"
)
"""崩坏·星穹铁道国服官服安卓更新入口，302 跳转至 CDN 上的真实安装包地址"""

STARRAIL_UPDATE_LINK_SERVER = {
    "CN-Official": STARRAIL_CN_UPDATE_LINK_URL,
}
"""崩坏·星穹铁道各服务器的更新入口映射表

入口的跳转地址同时提供版本号与安装包，因此版本号与将安装的包必然一致。
目前只有国服官服放出了安卓安装包直链，其余服务器还没有公开可用的安卓入口。

不在此表中的服务器会跳过客户端版本检查。
"""
