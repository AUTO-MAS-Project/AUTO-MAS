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


def version_text(version_numb):
    """将版本号列表转为可读的文本信息"""
    if version_numb[3] == 0:
        version = f"v{'.'.join(str(_) for _ in version_numb[0:3])}"
    elif version_numb[3] == 1:
        version = f"v{'.'.join(str(_) for _ in version_numb[0:3])}_beta"
    return version


with open("res/version.json", "r", encoding="utf-8") as f:
    version = json.load(f)

main_version_numb = list(map(int, version["main_version"].split(".")))
updater_version_numb = list(map(int, version["updater_version"].split(".")))

main_info = f"# UTF-8\n#\nVSVersionInfo(\n  ffi=FixedFileInfo(\n    # filevers and prodvers should be always a tuple with four items: (1, 2, 3, 4)\n    # Set not needed items to zero 0.\n    filevers=({', '.join(str(_) for _ in main_version_numb)}),\n    prodvers=(0, 0, 0, 0),\n    # Contains a bitmask that specifies the valid bits 'flags'r\n    mask=0x3f,\n    # Contains a bitmask that specifies the Boolean attributes of the file.\n    flags=0x0,\n    # The operating system for which this file was designed.\n    # 0x4 - NT and there is no need to change it.\n    OS=0x4,\n    # The general type of file.\n    # 0x1 - the file is an application.\n    fileType=0x1,\n    # The function of the file.\n    # 0x0 - the function is not defined for this fileType\n    subtype=0x0,\n    # Creation date and time stamp.\n    date=(0, 0)\n    ),\n  kids=[\n    VarFileInfo([VarStruct('Translation', [0, 1200])]), \n    StringFileInfo(\n      [\n      StringTable(\n        '000004b0',\n        [StringStruct('Comments', 'https://github.com/DLmaster361/AUTO_MAA/'),\n        StringStruct('CompanyName', 'AUTO_MAA Team'),\n        StringStruct('FileDescription', 'AUTO_MAA Component'),\n        StringStruct('FileVersion', '{version["main_version"]}'),\n        StringStruct('InternalName', 'AUTO_MAA'),\n        StringStruct('LegalCopyright', 'Copyright © 2024 DLmaster361'),\n        StringStruct('OriginalFilename', 'AUTO_MAA.py'),\n        StringStruct('ProductName', 'AUTO_MAA'),\n        StringStruct('ProductVersion', 'v{version["main_version"]}'),\n        StringStruct('Assembly Version', 'v{version["main_version"]}')])\n      ])\n  ]\n)"
updater_info = f"# UTF-8\n#\nVSVersionInfo(\n  ffi=FixedFileInfo(\n    # filevers and prodvers should be always a tuple with four items: (1, 2, 3, 4)\n    # Set not needed items to zero 0.\n    filevers=({', '.join(str(_) for _ in updater_version_numb)}),\n    prodvers=(0, 0, 0, 0),\n    # Contains a bitmask that specifies the valid bits 'flags'r\n    mask=0x3f,\n    # Contains a bitmask that specifies the Boolean attributes of the file.\n    flags=0x0,\n    # The operating system for which this file was designed.\n    # 0x4 - NT and there is no need to change it.\n    OS=0x4,\n    # The general type of file.\n    # 0x1 - the file is an application.\n    fileType=0x1,\n    # The function of the file.\n    # 0x0 - the function is not defined for this fileType\n    subtype=0x0,\n    # Creation date and time stamp.\n    date=(0, 0)\n    ),\n  kids=[\n    VarFileInfo([VarStruct('Translation', [0, 1200])]), \n    StringFileInfo(\n      [\n      StringTable(\n        '000004b0',\n        [StringStruct('Comments', 'https://github.com/DLmaster361/AUTO_MAA/'),\n        StringStruct('CompanyName', 'AUTO_MAA Team'),\n        StringStruct('FileDescription', 'AUTO_MAA Component'),\n        StringStruct('FileVersion', '{version["updater_version"]}'),\n        StringStruct('InternalName', 'AUTO_MAA_Updater'),\n        StringStruct('LegalCopyright', 'Copyright © 2024 DLmaster361'),\n        StringStruct('OriginalFilename', 'Updater.py'),\n        StringStruct('ProductName', 'AUTO_MAA_Updater'),\n        StringStruct('ProductVersion', 'v{version["updater_version"]}'),\n        StringStruct('Assembly Version', 'v{version["updater_version"]}')])\n      ])\n  ]\n)"

with open("AUTO_MAA_info.txt", "w", encoding="utf-8") as f:
    print(main_info, end="", file=f)
with open("Updater_info.txt", "w", encoding="utf-8") as f:
    print(updater_info, end="", file=f)

os.system(
    "pyinstaller -F --version-file AUTO_MAA_info.txt -w --icon=res/AUTO_MAA.ico AUTO_MAA.py --hidden-import plyer.platforms.win.notification"
)
os.system(
    "pyinstaller -F --version-file Updater_info.txt -w --icon=res/AUTO_MAA_Updater.ico Updater.py"
)

with open("update_info.txt", "w", encoding="utf-8") as f:
    print(
        f"{version_text(main_version_numb)}\n{version_text(updater_version_numb)}{version["announcement"]}",
        file=f,
    )
