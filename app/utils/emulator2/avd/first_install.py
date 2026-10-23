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

"""魔改 AVD 首次安装用到的两样：《Android SDK 许可协议》全文，和包里的「补全组件」脚本。

adb 与系统镜像属于 Google、受《Android SDK 许可协议》约束、不能再分发，ModAVD 的包里没有，由包里的
``tools\\fetch-components.ps1`` 从官方渠道下载。MAS 在界面上展示许可协议全文、用户同意后才带
``-AcceptLicense`` 跑这个脚本（它照样会再取一次全文打印进日志）。许可协议从和脚本相同的三个镜像、
按相同的顺序取（``repository2-3.xml`` 里 ``id="android-sdk-license"`` 的那一段）。

脚本约定（见脚本头部）：Windows PowerShell 5.1 能跑；退出码 0 完成、1 下载 / 校验 / 解压失败、
2 没有同意许可协议、3 文件夹不对（路径含中文、不是模拟器文件夹、空间不够）；日志 ``logs\\fetch-components.log``。
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree

import httpx

from app.utils import get_logger

logger = get_logger("魔改 AVD 首次安装")

#: 和 ``fetch-components.ps1`` 的 ``$Mirrors`` 同样三个、同样的顺序。
SDK_LICENSE_MIRRORS: tuple[tuple[str, str], ...] = (
    (
        "Google 中国下载（googledownloads.cn）",
        "https://googledownloads.cn/android/repository/",
    ),
    (
        "腾讯云镜像（mirrors.cloud.tencent.com）",
        "https://mirrors.cloud.tencent.com/AndroidSDK/",
    ),
    ("Google 官方（dl.google.com）", "https://dl.google.com/android/repository/"),
)
SDK_LICENSE_MANIFEST = "repository2-3.xml"
SDK_LICENSE_ID = "android-sdk-license"
#: 包里的补全组件脚本（相对根目录）与它的日志。
FETCH_COMPONENTS_SCRIPT = Path("tools") / "fetch-components.ps1"
FETCH_COMPONENTS_LOG = Path("logs") / "fetch-components.log"
#: 脚本的退出码 → 用户看得懂的一句话。
FETCH_COMPONENTS_EXIT = {
    1: "下载、校验或解压失败",
    2: "没有同意《Android SDK 许可协议》",
    3: "文件夹不对（路径含中文、不是模拟器文件夹，或磁盘空间不够）",
}
_LICENSE_TIMEOUT = httpx.Timeout(40.0, connect=20.0)


def parse_sdk_license(manifest_xml: bytes | str) -> str:
    """从 ``repository2-3.xml`` 取《Android SDK 许可协议》全文；取不到抛 ``ValueError``。"""
    root = ElementTree.fromstring(manifest_xml)
    for element in root.iter():
        if (
            element.tag.rsplit("}", 1)[-1] == "license"
            and element.get("id") == SDK_LICENSE_ID
        ):
            text = "".join(element.itertext()).strip()
            if text:
                return text
    raise ValueError(f"清单里没有许可协议 {SDK_LICENSE_ID}")


async def fetch_sdk_license(*, proxy: httpx.Proxy | None) -> dict[str, str]:
    """按顺序问三个镜像，第一个取到的为准：``{"text": 全文, "source": 镜像名}``。都取不到抛 ``RuntimeError``。"""
    errors: list[str] = []
    async with httpx.AsyncClient(
        proxy=proxy,
        follow_redirects=True,
        timeout=_LICENSE_TIMEOUT,
        headers={"Accept-Encoding": "identity", "User-Agent": "AutoMasGui"},
    ) as client:
        for name, base in SDK_LICENSE_MIRRORS:
            try:
                response = await client.get(base + SDK_LICENSE_MANIFEST)
                response.raise_for_status()
                text = await asyncio.to_thread(parse_sdk_license, response.content)
            except Exception as e:  # noqa: BLE001 - 换下一个镜像
                errors.append(f"{name}：{type(e).__name__}: {e}")
                continue
            return {"text": text, "source": name}
    raise RuntimeError("取不到《Android SDK 许可协议》全文：" + "；".join(errors))


def _windows_powershell() -> str:
    """Windows PowerShell 5.1（系统自带，脚本按它写的）。"""
    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    path = (
        Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    )
    return str(path) if path.is_file() else "powershell.exe"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


async def run_fetch_components(root: Path, on_line: Callable[[str], None]) -> int:
    """在根目录上跑 ``tools\\fetch-components.ps1 -Root <根> -AcceptLicense``，逐行把输出交给 ``on_line``，
    返回退出码。只有用户在界面上同意了许可协议才调用。

    输出用 UTF-8：Windows PowerShell 5.1 写管道时默认按系统的 OEM 代码页，中文会变成问号。
    """
    script = root / FETCH_COMPONENTS_SCRIPT
    if not script.is_file():
        raise FileNotFoundError(f"包里没有 {FETCH_COMPONENTS_SCRIPT}")
    command = (
        "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "
        f"& {_quote(str(script))} -Root {_quote(str(root))} -AcceptLicense; "
        "exit $LASTEXITCODE"
    )
    logger.info(f"运行补全组件: {script} -Root {root} -AcceptLicense")
    process = await asyncio.create_subprocess_exec(
        _windows_powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        command,
        cwd=str(root),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert process.stdout is not None
    # 下载进度用 \r 原地刷新、不换行，按 \r 和 \n 都切开
    pending = b""
    while chunk := await process.stdout.read(4096):
        *lines, pending = re.split(rb"[\r\n]", pending + chunk)
        for raw in lines:
            if line := raw.decode("utf-8", errors="replace").strip():
                on_line(line)
    if line := pending.decode("utf-8", errors="replace").strip():
        on_line(line)
    code = await process.wait()
    logger.info(f"补全组件结束，退出码 {code}")
    return code


__all__ = [
    "FETCH_COMPONENTS_EXIT",
    "FETCH_COMPONENTS_LOG",
    "FETCH_COMPONENTS_SCRIPT",
    "SDK_LICENSE_MIRRORS",
    "fetch_sdk_license",
    "parse_sdk_license",
    "run_fetch_components",
]
