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


import re
import sys
import time
import json
import psutil
import base64
import zipfile
import requests
import argparse
import truststore
import subprocess
import win32crypt

from packaging import version
from pathlib import Path
from typing import List, Dict

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))


MIRROR_ERROR_INFO = {
    1001: "获取版本信息的URL参数不正确",
    7001: "填入的 CDK 已过期",
    7002: "填入的 CDK 错误",
    7003: "填入的 CDK 今日下载次数已达上限",
    7004: "填入的 CDK 类型和待下载的资源不匹配",
    7005: "填入的 CDK 已被封禁",
    8001: "对应架构和系统下的资源不存在",
    8002: "错误的系统参数",
    8003: "错误的架构参数",
    8004: "错误的更新通道参数",
    1: "未知错误类型",
}


def dpapi_decrypt(note: str, entropy: None | bytes = None) -> str:
    """
    使用Windows DPAPI解密数据

    :param note: 数据密文
    :type note: str
    :param entropy: 随机熵
    :type entropy: bytes
    :return: 解密后的明文
    :rtype: str
    """

    if note == "":
        return ""

    decrypted = win32crypt.CryptUnprotectData(
        base64.b64decode(note), entropy, None, None, 0
    )
    return decrypted[1].decode("utf-8")


def kill_process(path: Path) -> None:
    """
    根据路径中止进程

    :param path: 进程路径
    """

    print(f"开始中止进程: {path}")

    for pid in search_pids(path):
        killprocess = subprocess.Popen(
            f"taskkill /F /T /PID {pid}",
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        killprocess.wait()

    print(f"进程已中止: {path}")


def search_pids(path: Path) -> list:
    """
    根据路径查找进程PID

    :param path: 进程路径
    :return: 匹配的进程PID列表
    """

    print(f"开始查找进程 PID: {path}")

    pids = []
    for proc in psutil.process_iter(["pid", "exe"]):
        try:
            if proc.info["exe"] and proc.info["exe"].lower() == str(path).lower():
                pids.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # 进程可能在此期间已结束或无法访问，忽略这些异常
            pass
    return pids


truststore.inject_into_ssl()
parser = argparse.ArgumentParser(
    prog="AUTO-MAS更新器", description="为AUTO-MAS前端提供更新服务"
)
parser.add_argument(
    "--version", "-v", type=str, required=False, default=None, help="前端程序版本号"
)
args = parser.parse_args()

if (Path.cwd() / "config/Config.json").exists():
    config = json.loads(
        (Path.cwd() / "config/Config.json").read_text(encoding="utf-8")
    ).get(
        "Update",
        {
            "MirrorChyanCDK": "",
            "ProxyAddress": "",
            "Source": "GitHub",
            "UpdateType": "stable",
        },
    )
else:
    config = {
        "MirrorChyanCDK": "",
        "ProxyAddress": "",
        "Source": "GitHub",
        "UpdateType": "stable",
    }

if (
    config.get("Source", "GitHub") == "MirrorChyan"
    and dpapi_decrypt(config.get("MirrorChyanCDK", "")) == ""
):
    print("使用 MirrorChyan源但未填写 MirrorChyanCDK，转用 GitHub 源")
    config["Source"] = "GitHub"
    config["MirrorChyanCDK"] = ""

print(f"当前配置: {config}")


download_source = config.get("Source", "GitHub")
proxies = {
    "http": config.get("ProxyAddress", ""),
    "https": config.get("ProxyAddress", ""),
}

if args.version:
    current_version = args.version
else:
    current_version = "v0.0.0"

print(f"当前版本: {current_version}")


response = requests.get(
    f"https://mirrorchyan.com/api/resources/AUTO_MAA/latest?user_agent=AutoMaaGui&current_version={current_version}&cdk={dpapi_decrypt(config.get('MirrorChyanCDK', ''))}&channel={config.get('UpdateType', 'stable')}",
    timeout=10,
    proxies=proxies,
)
if response.status_code == 200:
    version_info = response.json()
else:
    try:
        result = response.json()

        if result["code"] != 0:
            if result["code"] in MIRROR_ERROR_INFO:
                print(f"获取版本信息时出错：{MIRROR_ERROR_INFO[result['code']]}")
            else:
                print(
                    "获取版本信息时出错：意料之外的错误，请及时联系项目组以获取来自 Mirror 酱的技术支持"
                )
            print(f"                    {result['msg']}")
        sys.exit(1)
    except Exception:
        print(f"获取版本信息时出错：{response.text}")

        sys.exit(1)


remote_version = version_info["data"]["version_name"]

if version.parse(remote_version) > version.parse(current_version):

    # 版本更新信息
    print(f"发现新版本：{remote_version}，当前版本：{current_version}")

    version_info_json: Dict[str, Dict[str, List[str]]] = json.loads(
        re.sub(
            r"^<!--\s*(.*?)\s*-->$",
            r"\1",
            version_info["data"]["release_note"].splitlines()[0],
        )
    )

    update_version_info = {}
    for v_i in [
        info
        for ver, info in version_info_json.items()
        if version.parse(ver) > version.parse(current_version)
    ]:

        for key, value in v_i.items():
            if key not in update_version_info:
                update_version_info[key] = []
            update_version_info[key] += value

    for key, value in update_version_info.items():
        print(f"{key}：")
        for v in value:
            print(f"  - {v}")

    if download_source == "GitHub":

        download_url = f"https://github.com/DLmaster361/AUTO_MAA/releases/download/{remote_version}/AUTO_MAA_{remote_version}.zip"

    elif download_source == "MirrorChyan":
        if "url" in version_info["data"]:
            with requests.get(
                version_info["data"]["url"],
                allow_redirects=True,
                timeout=10,
                stream=True,
                proxies=proxies,
            ) as response:
                if response.status_code == 200:
                    download_url = response.url
        else:
            print(f"MirrorChyan 未返回下载链接，使用自建下载站")
            download_url = f"https://download.auto-mas.top/d/AUTO_MAA/AUTO_MAA_{remote_version}.zip"

    elif download_source == "AutoSite":
        download_url = (
            f"https://download.auto-mas.top/d/AUTO_MAA/AUTO_MAA_{remote_version}.zip"
        )

    else:
        print(f"未知的下载源：{download_source}，请检查配置文件")
        sys.exit(1)

    print(f"开始下载：{download_url}")

    # 清理可能存在的临时文件
    if (Path.cwd() / "download.temp").exists():
        (Path.cwd() / "download.temp").unlink()

    check_times = 3
    while check_times != 0:

        try:

            start_time = time.time()

            response = requests.get(
                download_url, timeout=10, stream=True, proxies=proxies
            )

            if response.status_code not in [200, 206]:

                if check_times != -1:
                    check_times -= 1

                print(
                    f"连接失败：{download_url}，状态码：{response.status_code}，剩余重试次数：{check_times}",
                )

                time.sleep(1)
                continue

            print(f"连接成功：{download_url}，状态码：{response.status_code}")

            file_size = int(response.headers.get("content-length", 0))
            downloaded_size = 0
            last_download_size = 0
            last_time = time.time()
            with (Path.cwd() / "download.temp").open(mode="wb") as f:

                for chunk in response.iter_content(chunk_size=8192):

                    f.write(chunk)
                    downloaded_size += len(chunk)

                    # 更新指定线程的下载进度，每秒更新一次
                    if time.time() - last_time >= 1.0:
                        speed = (
                            (downloaded_size - last_download_size)
                            / (time.time() - last_time)
                            / 1024
                        )
                        last_download_size = downloaded_size
                        last_time = time.time()

                        if speed >= 1024:
                            print(
                                f"正在下载：AUTO-MAS 已下载：{downloaded_size / 1048576:.2f}/{file_size / 1048576:.2f} MB （{downloaded_size / file_size * 100:.2f}%） 下载速度：{speed / 1024:.2f} MB/s",
                            )
                        else:
                            print(
                                f"正在下载：AUTO-MAS 已下载：{downloaded_size / 1048576:.2f}/{file_size / 1048576:.2f} MB （{downloaded_size / file_size * 100:.2f}%） 下载速度：{speed:.2f} KB/s",
                            )

            print(
                f"下载完成：{download_url}，实际下载大小：{downloaded_size} 字节，耗时：{time.time() - start_time:.2f} 秒",
            )

            break

        except Exception as e:

            if check_times != -1:
                check_times -= 1

            print(
                f"下载出错：{download_url}，错误信息：{e}，剩余重试次数：{check_times}",
            )
            time.sleep(1)

    else:

        if (Path.cwd() / "download.temp").exists():
            (Path.cwd() / "download.temp").unlink()
        print(f"下载失败：{download_url}")
        sys.exit(1)

    print(f"开始解压：{Path.cwd() / 'download.temp'} 到 {Path.cwd()}")

    while True:

        try:
            with zipfile.ZipFile(Path.cwd() / "download.temp", "r") as zip_ref:
                zip_ref.extractall(Path.cwd())
            print(f"解压完成：{Path.cwd() / 'download.temp'} 到 {Path.cwd()}")
            break
        except PermissionError:
            print(f"解压出错：AUTO_MAA正在运行，正在尝试将其关闭")
            kill_process(Path.cwd() / "AUTO_MAA.exe")
            time.sleep(1)

    print("正在删除临时文件")
    if (Path.cwd() / "changes.json").exists():
        (Path.cwd() / "changes.json").unlink()
    if (Path.cwd() / "download.temp").exists():
        (Path.cwd() / "download.temp").unlink()

    print("正在启动AUTO_MAA")
    subprocess.Popen(
        [Path.cwd() / "AUTO_MAA.exe"],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NO_WINDOW,
    )

    print("更新完成")
    sys.exit(0)

else:

    print(f"当前版本为最新版本：{current_version}")
    sys.exit(0)
