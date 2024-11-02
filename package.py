#   <AUTO_MAA:A MAA Multi Account Management and Automation Tool>
#   Copyright © <2024> <DLmaster361>

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA打包程序
v4.1
作者：DLmaster_361
"""

import os
import json

os.system(
    "pyinstaller -F --version-file res/AUTO_MAA_info.txt -w --icon=res/AUTO_MAA.ico AUTO_MAA.py --hidden-import plyer.platforms.win.notification"
)
os.system(
    "pyinstaller -F --version-file res/Updater_info.txt -w --icon=res/AUTO_MAA.ico Updater.py"
)
with open("res/version.json", "r", encoding="utf-8") as f:
    version = json.load(f)
main_version = list(map(int, version["main_version"].split(".")))
updater_version = list(map(int, version["updater_version"].split(".")))
if main_version[3] == 0:
    main_version = f"v{'.'.join(str(_) for _ in main_version[0:3])}"
elif main_version[3] == 1:
    main_version = f"v{'.'.join(str(_) for _ in main_version[0:3])}_beta"
if updater_version[3] == 0:
    updater_version = f"v{'.'.join(str(_) for _ in updater_version[0:3])}"
elif updater_version[3] == 1:
    updater_version = f"v{'.'.join(str(_) for _ in updater_version[0:3])}_beta"
with open("update_info.txt", "w", encoding="utf-8") as f:
    print(f"{main_version}\n{updater_version}\n{version["announcement"]}", file=f)
