#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

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

#   Contact: DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA打包程序
v4.3
作者：DLmaster_361
"""

import os
import sys
import json
import shutil
from pathlib import Path


def version_text(version_numb: list) -> str:
    """将版本号列表转为可读的文本信息"""

    while len(version_numb) < 4:
        version_numb.append(0)

    if version_numb[3] == 0:
        version = f"v{'.'.join(str(_) for _ in version_numb[0:3])}"
    else:
        version = (
            f"v{'.'.join(str(_) for _ in version_numb[0:3])}-beta.{version_numb[3]}"
        )
    return version


def version_info_markdown(info: dict) -> str:
    """将版本信息字典转为markdown信息"""

    version_info = ""
    for key, value in info.items():
        version_info += f"## {key}\n"
        for v in value:
            version_info += f"- {v}\n"
    return version_info


if __name__ == "__main__":

    root_path = Path(sys.argv[0]).resolve().parent

    with (root_path / "resources/version.json").open(mode="r", encoding="utf-8") as f:
        version = json.load(f)

    main_version_numb = list(map(int, version["main_version"].split(".")))

    print("Packaging AUTO_MAA main program ...")

    os.system(
        "powershell -Command python -m nuitka --standalone --onefile --mingw64"
        " --enable-plugins=pyside6 --windows-console-mode=attach"
        " --onefile-tempdir-spec='{TEMP}\\AUTO_MAA'"
        " --windows-icon-from-ico=resources\\icons\\AUTO_MAA.ico"
        " --company-name='AUTO_MAA Team' --product-name=AUTO_MAA"
        f" --file-version={version['main_version']}"
        f" --product-version={version['main_version']}"
        " --file-description='AUTO_MAA Component'"
        " --copyright='Copyright © 2024-2025 DLmaster361'"
        " --assume-yes-for-downloads --output-filename=AUTO_MAA"
        " --remove-output main.py"
    )

    print("AUTO_MAA main program packaging completed !")

    print("start to create setup program ...")

    (root_path / "AUTO_MAA").mkdir(parents=True, exist_ok=True)
    shutil.move(root_path / "AUTO_MAA.exe", root_path / "AUTO_MAA/")
    shutil.copytree(root_path / "app", root_path / "AUTO_MAA/app")
    shutil.copytree(root_path / "resources", root_path / "AUTO_MAA/resources")
    shutil.copy(root_path / "main.py", root_path / "AUTO_MAA/")
    shutil.copy(root_path / "requirements.txt", root_path / "AUTO_MAA/")
    shutil.copy(root_path / "README.md", root_path / "AUTO_MAA/")
    shutil.copy(root_path / "LICENSE", root_path / "AUTO_MAA/")

    with (root_path / "app/utils/AUTO_MAA.iss").open(mode="r", encoding="utf-8") as f:
        iss = f.read()
    iss = (
        iss.replace(
            '#define MyAppVersion ""',
            f'#define MyAppVersion "{version["main_version"]}"',
        )
        .replace(
            '#define MyAppPath ""', f'#define MyAppPath "{root_path / "AUTO_MAA"}"'
        )
        .replace('#define OutputDir ""', f'#define OutputDir "{root_path}"')
    )
    with (root_path / "AUTO_MAA.iss").open(mode="w", encoding="utf-8") as f:
        f.write(iss)

    os.system(f'ISCC "{root_path / "AUTO_MAA.iss"}"')

    (root_path / "AUTO_MAA_Setup").mkdir(parents=True, exist_ok=True)
    shutil.move(root_path / "AUTO_MAA-Setup.exe", root_path / "AUTO_MAA_Setup")

    shutil.make_archive(
        base_name=root_path / f"AUTO_MAA_{version_text(main_version_numb)}",
        format="zip",
        root_dir=root_path / "AUTO_MAA_Setup",
        base_dir=".",
    )

    print("setup program created !")

    (root_path / "AUTO_MAA.iss").unlink(missing_ok=True)
    shutil.rmtree(root_path / "AUTO_MAA")
    shutil.rmtree(root_path / "AUTO_MAA_Setup")

    all_version_info = {}
    for v_i in version["version_info"].values():
        for key, value in v_i.items():
            if key in all_version_info:
                all_version_info[key] += value.copy()
            else:
                all_version_info[key] = value.copy()

    (root_path / "version_info.txt").write_text(
        f"{version_text(main_version_numb)}\n\n<!--{json.dumps(version["version_info"], ensure_ascii=False)}-->\n{version_info_markdown(all_version_info)}",
        encoding="utf-8",
    )
