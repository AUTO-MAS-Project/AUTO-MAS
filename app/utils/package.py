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
v4.2
作者：DLmaster_361
"""

import os
import json
import shutil
import subprocess

from app import version_text


if __name__ == "__main__":

    with open("resources/version.json", "r", encoding="utf-8") as f:
        version = json.load(f)

    main_version_numb = list(map(int, version["main_version"].split(".")))
    updater_version_numb = list(map(int, version["updater_version"].split(".")))

    print("Packaging AUTO-MAA main program ...")

    result = subprocess.run(
        f"powershell -Command nuitka --standalone --onefile --mingw64"
        f" --enable-plugins=pyside6 --windows-console-mode=disable"
        f" --windows-icon-from-ico=resources\\icons\\AUTO_MAA.ico"
        f" --company-name='AUTO_MAA Team' --product-name=AUTO_MAA"
        f" --file-version={version["main_version"]}"
        f" --product-version={version["main_version"]}"
        f" --file-description='AUTO_MAA Component'"
        f" --copyright='Copyright © 2024 DLmaster361'"
        f" --assume-yes-for-downloads --show-progress"
        f" --output-filename=AUTO_MAA --remove-output"
        f" main.py",
        shell=True,
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    print(result.stderr)
    print("AUTO-MAA main program packaging completed !")

    shutil.copy(os.path.normpath("app/utils/Updater.py"), os.path.normpath("."))

    with open(os.path.normpath("Updater.py"), "r", encoding="utf-8") as f:
        file_content = f.read()

    file_content = file_content.replace(
        "from .version import version_text", "from app import version_text"
    )

    with open(os.path.normpath("Updater.py"), "w", encoding="utf-8") as f:
        f.write(file_content)

    print("Packaging AUTO-MAA update program ...")

    result = subprocess.run(
        f"powershell -Command nuitka --standalone --onefile --mingw64"
        f" --enable-plugins=pyside6 --windows-console-mode=disable"
        f" --windows-icon-from-ico=resources\\icons\\AUTO_MAA_Updater.ico"
        f" --company-name='AUTO_MAA Team' --product-name=AUTO_MAA"
        f" --file-version={version["updater_version"]}"
        f" --product-version={version["updater_version"]}"
        f" --file-description='AUTO_MAA Component'"
        f" --copyright='Copyright © 2024 DLmaster361'"
        f" --assume-yes-for-downloads --show-progress"
        f" --output-filename=Updater --remove-output"
        f" Updater.py",
        shell=True,
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    print(result.stderr)
    print("AUTO-MAA update program packaging completed !")

    os.remove(os.path.normpath("Updater.py"))

    with open("update_info.txt", "w", encoding="utf-8") as f:
        print(
            f"{version_text(main_version_numb)}\n{version_text(updater_version_numb)}{version["announcement"]}",
            file=f,
        )
