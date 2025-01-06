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
from pathlib import Path

from app import version_text


if __name__ == "__main__":

    root_path = Path.cwd()

    with (root_path / "resources/version.json").open(mode="r", encoding="utf-8") as f:
        version = json.load(f)

    main_version_numb = list(map(int, version["main_version"].split(".")))
    updater_version_numb = list(map(int, version["updater_version"].split(".")))

    print("Packaging AUTO_MAA main program ...")

    result = subprocess.run(
        f"powershell -Command nuitka --standalone --onefile --mingw64"
        f" --enable-plugins=pyside6 --windows-console-mode=disable"
        f" --onefile-tempdir-spec=%TEMP%\\AUTO_MAA"
        f" --windows-icon-from-ico=resources\\icons\\AUTO_MAA.ico"
        f" --company-name='AUTO_MAA Team' --product-name=AUTO_MAA"
        f" --file-version={version["main_version"]}"
        f" --product-version={version["main_version"]}"
        f" --file-description='AUTO_MAA Component'"
        f" --copyright='Copyright © 2024 DLmaster361'"
        f" --assume-yes-for-downloads --output-filename=AUTO_MAA"
        f" --remove-output main.py",
        shell=True,
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    print(result.stderr)
    print("AUTO_MAA main program packaging completed !")

    shutil.copy(root_path / "app/utils/Updater.py", root_path)

    file_content = (root_path / "Updater.py").read_text(encoding="utf-8")

    (root_path / "Updater.py").write_text(
        file_content.replace(
            "from .version import version_text", "from app import version_text"
        ),
        encoding="utf-8",
    )

    print("Packaging AUTO_MAA update program ...")

    result = subprocess.run(
        f"powershell -Command nuitka --standalone --onefile --mingw64"
        f" --enable-plugins=pyside6 --windows-console-mode=disable"
        f" --onefile-tempdir-spec=%TEMP%\\AUTO_MAA_Updater"
        f" --windows-icon-from-ico=resources\\icons\\AUTO_MAA_Updater.ico"
        f" --company-name='AUTO_MAA Team' --product-name=AUTO_MAA"
        f" --file-version={version["updater_version"]}"
        f" --product-version={version["main_version"]}"
        f" --file-description='AUTO_MAA Component'"
        f" --copyright='Copyright © 2024 DLmaster361'"
        f" --assume-yes-for-downloads --output-filename=Updater"
        f" --remove-output Updater.py",
        shell=True,
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    print(result.stderr)
    print("AUTO_MAA update program packaging completed !")

    (root_path / "Updater.py").unlink()

    (root_path / "version_info.txt").write_text(
        f"{version_text(main_version_numb)}\n{version_text(updater_version_numb)}{version["announcement"]}",
        encoding="utf-8",
    )
