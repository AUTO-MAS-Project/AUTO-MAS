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


"""MAS 托管的云·星穹铁道浏览器。

浏览器用三月七发行包自带的 Chrome for Testing，由 MAS 拉起并按用户分
``--user-data-dir``；命令行带三月七的识别标记，三月七每个模块进程走它自己的
「连接已有浏览器」路径接上来，不会自己再开浏览器。三月七只在「新建浏览器」
路径做的三件事（剪贴板/keyboard_lock 权限、去引导弹窗的 localStorage、
自动战斗开关）由本模块在 profile 首次使用时补上。
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx
import psutil
from websockets.asyncio.client import ClientConnection, connect

from app.utils import ProcessManager, get_logger

logger = get_logger("HSR 云浏览器")

M7A_BROWSER_TAG = "--march-7th-assistant-sr-cloud-game"
"""三月七识别「自己的浏览器」的命令行标记，必须是独立 argv 元素。"""

CLOUD_GAME_URL = "https://sr.mihoyo.com/cloud"
DEFAULT_DEBUG_PORT = 9222
BROWSER_PROCESS_NAME = "chrome.exe"
BROWSER_WINDOW_SIZE = (1920, 1120)
READY_TIMEOUT_SECONDS = 15.0
STOP_TIMEOUT_SECONDS = 3.0
PAGE_TIMEOUT_SECONDS = 30.0

PROFILE_DIRECTORY = "Default"
INITIALIZED_MARKER = "mas-cloud-initialized"
"""profile 根目录下的标记文件：CDP 首次初始化成功后写入，缺失则下次启动重做。"""

INITIAL_LOCAL_STORAGE_RELATIVE = Path("assets", "config", "initial_local_storage.json")
AUTO_BATTLE_STORAGE_KEY = "cg_hkrpg_cn_cloudData"

MISSING_BROWSER_MESSAGE = "三月七安装包缺少内置浏览器，请安装完整版"
START_FAILED_MESSAGE = "云浏览器启动失败"

_USER_DATA_DIR_PREFIX = "--user-data-dir="
_CLOUD_ORIGIN_EXCEPTION = "https://sr.mihoyo.com:443,*"


class CloudBrowserError(RuntimeError):
    """MAS 托管云浏览器的可读错误，消息面向用户。"""


class CloudBrowserMissingError(CloudBrowserError):
    """三月七安装包里找不到内置 Chrome 或 chromedriver。"""


@dataclass(frozen=True, slots=True)
class IntegratedBrowser:
    """三月七发行包内置的浏览器与驱动。"""

    version: str
    chrome_path: Path
    driver_path: Path


def _single_version_dir(parent: Path) -> Path | None:
    """返回 ``parent`` 下唯一的版本目录；不存在或不唯一时返回 None。"""

    if not parent.is_dir():
        return None
    versions = [child for child in parent.iterdir() if child.is_dir()]
    if len(versions) != 1:
        return None
    return versions[0]


def locate_integrated_browser(m7a_root: Path | str) -> IntegratedBrowser:
    """在三月七安装根下定位内置 Chrome 与同版本的 chromedriver。

    版本号取 ``3rdparty/WebBrowser/chrome/win64`` 下唯一的目录名，不写死。

    Raises:
        CloudBrowserMissingError: 版本目录缺失或不唯一、chrome.exe 或同版本
            chromedriver.exe 不存在。
    """

    web_browser = Path(m7a_root) / "3rdparty" / "WebBrowser"
    version_dir = _single_version_dir(web_browser / "chrome" / "win64")
    if version_dir is None:
        raise CloudBrowserMissingError(MISSING_BROWSER_MESSAGE)

    version = version_dir.name
    chrome_path = version_dir / "chrome.exe"
    driver_path = web_browser / "chromedriver" / "win64" / version / "chromedriver.exe"
    if not chrome_path.is_file() or not driver_path.is_file():
        raise CloudBrowserMissingError(MISSING_BROWSER_MESSAGE)
    return IntegratedBrowser(
        version=version, chrome_path=chrome_path, driver_path=driver_path
    )


def is_port_free(port: int) -> bool:
    """端口在 127.0.0.1 与 0.0.0.0 上都能 bind，才算空闲。

    Windows 上别的进程监听 0.0.0.0 时，单绑 127.0.0.1 仍会成功，所以两者都探。
    不用 connect 探测：临时端口段里对本机未用端口 connect 会自连成功。
    """

    for host in ("127.0.0.1", "0.0.0.0"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                return False
    return True


def find_free_debug_port(
    preferred: int = DEFAULT_DEBUG_PORT, max_attempts: int = 100
) -> int:
    """从 ``preferred`` 起递增探测第一个空闲调试端口。

    Raises:
        CloudBrowserError: 连续 ``max_attempts`` 个端口都被占用。
    """

    for port in range(preferred, min(preferred + max_attempts, 65536)):
        if is_port_free(port):
            return port
    raise CloudBrowserError(
        f"找不到空闲的浏览器调试端口（{preferred} 起 {max_attempts} 个均被占用）"
    )


def build_preferences() -> dict[str, Any]:
    """新 profile 的 ``Default/Preferences``，等价三月七的 ``PERFERENCES``。

    给云游戏站点放行 keyboard_lock 与剪贴板权限，兑换码粘贴依赖后者。
    另关掉拼写检查：否则 Chrome for Testing 启动即下载词典到 **exe 所在目录**
    的 ``Dictionaries``（即用户的三月七安装目录），``--disable-spell-checking``
    实测拦不住。
    """

    allow = {_CLOUD_ORIGIN_EXCEPTION: {"setting": 1}}
    return {
        "browser": {"enable_spellchecking": False},
        "profile": {
            "content_settings": {
                "exceptions": {
                    "keyboard_lock": dict(allow),
                    "clipboard": dict(allow),
                }
            }
        },
    }


def ensure_profile(profile_dir: Path | str) -> bool:
    """确保 profile 目录存在；``Default/Preferences`` 缺失时预写权限。

    Returns:
        bool: 本次是否写入了 ``Preferences``（即 profile 首次创建）。
    """

    preferences = Path(profile_dir) / PROFILE_DIRECTORY / "Preferences"
    if preferences.exists():
        return False
    preferences.parent.mkdir(parents=True, exist_ok=True)
    preferences.write_text(
        json.dumps(build_preferences(), ensure_ascii=False), encoding="utf-8"
    )
    return True


def build_browser_arguments(port: int, profile_dir: Path | str) -> list[str]:
    """拼装云浏览器命令行（不含可执行文件本身）。

    第一项是三月七的识别标记；不加 ``--headless=new``（三月七无窗口下拒跑
    锄大地）、不加 ``--start-fullscreen``。``--user-data-dir`` 必须始终传：
    新版 Chromium 对默认 user-data-dir 会忽略 ``--remote-debugging-port``。
    """

    width, height = BROWSER_WINDOW_SIZE
    return [
        M7A_BROWSER_TAG,
        "--disable-infobars",
        "--lang=zh-CN",
        "--log-level=3",
        "--force-device-scale-factor=1",
        f"--app={CLOUD_GAME_URL}",
        "--disable-blink-features=AutomationControlled",
        f"--remote-debugging-port={port}",
        f"{_USER_DATA_DIR_PREFIX}{Path(profile_dir)}",
        f"--profile-directory={PROFILE_DIRECTORY}",
        f"--window-size={width},{height}",
        "--no-sandbox",
    ]


def _normalize_path(path: Path | str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


def _user_data_dir_of(cmdline: Iterable[str]) -> str | None:
    for arg in cmdline:
        if arg.startswith(_USER_DATA_DIR_PREFIX):
            return arg[len(_USER_DATA_DIR_PREFIX) :]
    return None


def is_managed_cloud_browser_cmdline(
    cmdline: Iterable[str] | None, profile_root: Path | str | None = None
) -> bool:
    """命令行是否属于带三月七标记、且 profile 位于 ``profile_root`` 下的浏览器。

    标记必须是独立 argv 元素（与三月七判据一致），不带标记的一律不命中。
    ``profile_root`` 为 None 时只看标记；否则 ``--user-data-dir`` 须等于它或
    位于其下。
    """

    if not cmdline:
        return False
    args = list(cmdline)
    if M7A_BROWSER_TAG not in args:
        return False
    if profile_root is None:
        return True
    user_data_dir = _user_data_dir_of(args)
    if not user_data_dir:
        return False
    root = _normalize_path(profile_root)
    target = _normalize_path(user_data_dir)
    return target == root or target.startswith(root.rstrip(os.sep) + os.sep)


def find_managed_cloud_browsers(
    profile_root: Path | str | None = None,
) -> list[psutil.Process]:
    """列出本机带三月七标记（且 profile 在 ``profile_root`` 下）的 chrome.exe。"""

    found: list[psutil.Process] = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        with suppress(psutil.Error):
            name = proc.info.get("name")
            if not name or name.lower() != BROWSER_PROCESS_NAME:
                continue
            if is_managed_cloud_browser_cmdline(proc.info.get("cmdline"), profile_root):
                found.append(proc)
    return found


def _terminate_tree(
    proc: psutil.Process, timeout: float = STOP_TIMEOUT_SECONDS
) -> None:
    """terminate 进程及其子进程，超时后 kill 残留。"""

    try:
        children = proc.children(recursive=True)
    except psutil.Error:
        children = []
    victims = [proc, *children]
    for victim in victims:
        with suppress(psutil.Error):
            victim.terminate()
    _, alive = psutil.wait_procs(victims, timeout=timeout)
    for victim in alive:
        with suppress(psutil.Error):
            victim.kill()
    if alive:
        psutil.wait_procs(alive, timeout=timeout)


async def cleanup_stale_cloud_browsers(
    profile_root: Path | str | None = None,
) -> int:
    """兜底关闭带三月七标记（且 profile 在 ``profile_root`` 下）的残留浏览器。

    绝不碰不带标记的浏览器。返回关闭的主进程个数。
    """

    def _cleanup() -> int:
        procs = find_managed_cloud_browsers(profile_root)
        for proc in procs:
            _terminate_tree(proc)
        return len(procs)

    count = await asyncio.to_thread(_cleanup)
    if count:
        logger.info(f"已关闭 {count} 个残留的云浏览器进程")
    return count


def load_initial_local_storage(m7a_root: Path | str) -> dict[str, Any]:
    """读取三月七的 ``assets/config/initial_local_storage.json``。"""

    path = Path(m7a_root) / INITIAL_LOCAL_STORAGE_RELATIVE
    return json.loads(path.read_text(encoding="utf-8"))


def build_local_storage_script(items: dict[str, Any]) -> str:
    """把键值逐项 ``localStorage.setItem``，返回写入条数。"""

    payload = json.dumps(items, ensure_ascii=False)
    return (
        "(() => {"
        f" const items = {payload};"
        " for (const [key, value] of Object.entries(items)) {"
        " window.localStorage.setItem(key, value); }"
        " return Object.keys(items).length;"
        " })()"
    )


def build_auto_battle_script(status: bool = True) -> str:
    """复刻三月七 ``change_auto_battle``：改 localStorage 里的自动战斗与二倍速。

    返回页面里读到的 ``App_LastUserID``（没有时为 null）。
    """

    value = 1 if status else 0
    key = json.dumps(AUTO_BATTLE_STORAGE_KEY)
    return (
        "(() => {"
        f" const cloud = JSON.parse(localStorage.getItem({key}) || '{{}}');"
        " if (!('value' in cloud)) cloud.value = {};"
        " const save = JSON.parse(cloud.value.RPGCloudSave || '{}');"
        " const intDicts = save.IntDicts || {};"
        f" intDicts.OtherSettings_AutoBattleOpen = {value};"
        f" intDicts.OtherSettings_IsSaveBattleSpeed = {value};"
        " const uid = intDicts.App_LastUserID;"
        f" if (uid) intDicts['User_' + uid + '_SpeedUpOpen'] = {value};"
        " save.IntDicts = intDicts;"
        " cloud.value.RPGCloudSave = JSON.stringify(save);"
        f" localStorage.setItem({key}, JSON.stringify(cloud));"
        " return uid || null;"
        " })()"
    )


class CdpSession:
    """最小 CDP 客户端：一条 websocket、顺序收发、缓存途经的事件。"""

    def __init__(self, websocket_url: str) -> None:
        self.websocket_url = websocket_url
        self._ws: ClientConnection | None = None
        self._next_id = 0
        self._events: list[dict[str, Any]] = []

    async def __aenter__(self) -> CdpSession:
        self._ws = await connect(
            self.websocket_url,
            proxy=None,
            compression=None,
            max_size=None,
            open_timeout=10,
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._ws is not None:
            with suppress(Exception):
                await self._ws.close()
            self._ws = None

    async def _recv(self, timeout: float) -> dict[str, Any]:
        assert self._ws is not None
        return json.loads(await asyncio.wait_for(self._ws.recv(), timeout=timeout))

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """发一条命令并等待同 id 的结果；CDP 报错时抛 CloudBrowserError。"""

        assert self._ws is not None
        self._next_id += 1
        message_id = self._next_id
        await self._ws.send(
            json.dumps({"id": message_id, "method": method, "params": params or {}})
        )
        deadline = time.monotonic() + timeout
        while True:
            message = await self._recv(max(0.1, deadline - time.monotonic()))
            if message.get("id") != message_id:
                if "method" in message:
                    self._events.append(message)
                continue
            if "error" in message:
                raise CloudBrowserError(f"CDP {method} 失败：{message['error']}")
            return message.get("result", {})

    async def evaluate(self, expression: str, timeout: float = 10.0) -> Any:
        """``Runtime.evaluate`` 并返回值；页面脚本抛错时抛 CloudBrowserError。"""

        result = await self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
            timeout=timeout,
        )
        if "exceptionDetails" in result:
            detail = result["exceptionDetails"]
            text = detail.get("exception", {}).get("description") or detail.get("text")
            raise CloudBrowserError(f"页面脚本执行失败：{text}")
        return result.get("result", {}).get("value")

    async def wait_event(self, method: str, timeout: float) -> dict[str, Any]:
        """等待指定事件（含 call 期间已收到的）。"""

        for index, event in enumerate(self._events):
            if event.get("method") == method:
                return self._events.pop(index)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError
            message = await self._recv(remaining)
            if message.get("method") == method:
                return message
            if "method" in message:
                self._events.append(message)


class CloudBrowser:
    """一个 MAS 用户的云浏览器会话。

    调用方负责串行：任一时刻只应有一个 MAS 云浏览器在跑（三月七只认标记不认
    账号）。``start()`` 会先关掉同一 profile 的残留实例，否则 Chrome 会把新
    启动转交给旧进程后立即退出。
    """

    def __init__(
        self,
        m7a_root: Path | str,
        profile_dir: Path | str,
        user_id: str = "",
        *,
        preferred_port: int = DEFAULT_DEBUG_PORT,
        auto_battle: bool = True,
        ready_timeout: float = READY_TIMEOUT_SECONDS,
    ) -> None:
        self.m7a_root = Path(m7a_root)
        self.profile_dir = Path(os.path.abspath(profile_dir))
        self.user_id = user_id
        self.preferred_port = preferred_port
        self.auto_battle = auto_battle
        self.ready_timeout = ready_timeout
        self.port: int | None = None
        self.browser: IntegratedBrowser | None = None
        self.process = ProcessManager()

    @property
    def pid(self) -> int | None:
        return self.process.main_pid

    @property
    def endpoint(self) -> str:
        if self.port is None:
            raise CloudBrowserError("云浏览器尚未启动")
        return f"http://127.0.0.1:{self.port}"

    @property
    def initialized(self) -> bool:
        return (self.profile_dir / INITIALIZED_MARKER).exists()

    async def start(self) -> None:
        """拉起浏览器并等调试端口就绪；profile 未初始化时做一次 CDP 初始化。

        Raises:
            CloudBrowserMissingError: 三月七安装包缺少内置浏览器。
            CloudBrowserError: 端口探测失败或 ``/json/version`` 在
                ``ready_timeout`` 内未就绪（「云浏览器启动失败」）。
        """

        if await self.is_alive():
            return

        self.browser = locate_integrated_browser(self.m7a_root)
        await cleanup_stale_cloud_browsers(self.profile_dir)
        if ensure_profile(self.profile_dir):
            logger.info(f"已创建云浏览器 profile：{self.profile_dir}")
        self.port = find_free_debug_port(self.preferred_port)

        args = build_browser_arguments(self.port, self.profile_dir)
        logger.info(
            f"启动云浏览器（Chrome {self.browser.version}，端口 {self.port}，"
            f"用户 {self.user_id or '-'}）"
        )
        try:
            await self.process.open_process(
                self.browser.chrome_path, *args, cwd=self.profile_dir
            )
        except OSError as e:
            raise CloudBrowserError(f"{START_FAILED_MESSAGE}：{e}") from e

        try:
            version = await self._wait_ready()
        except CloudBrowserError:
            await self.stop()
            raise
        logger.info(f"云浏览器已就绪（pid {self.pid}）：{version.get('Browser', '')}")

        if not self.initialized:
            await self.initialize_profile()

    async def _wait_ready(self) -> dict[str, Any]:
        deadline = time.monotonic() + self.ready_timeout
        async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
            while time.monotonic() < deadline:
                if not await self.is_alive():
                    raise CloudBrowserError(f"{START_FAILED_MESSAGE}：浏览器进程已退出")
                with suppress(httpx.HTTPError, ValueError):
                    response = await client.get(f"{self.endpoint}/json/version")
                    if response.status_code == 200:
                        return response.json()
                await asyncio.sleep(0.25)
        raise CloudBrowserError(
            f"{START_FAILED_MESSAGE}：调试端口 {self.port} "
            f"{self.ready_timeout:g} 秒内未就绪"
        )

    async def is_alive(self) -> bool:
        return await self.process.is_running()

    async def list_targets(self) -> list[dict[str, Any]]:
        """GET ``/json``，返回全部 CDP target。"""

        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            response = await client.get(f"{self.endpoint}/json")
            response.raise_for_status()
            return response.json()

    async def find_game_page(
        self, timeout: float = PAGE_TIMEOUT_SECONDS
    ) -> dict[str, Any]:
        """等待 URL 以云游戏地址开头的 page target。"""

        deadline = time.monotonic() + timeout
        while True:
            with suppress(httpx.HTTPError, ValueError):
                for target in await self.list_targets():
                    if target.get("type") == "page" and str(
                        target.get("url", "")
                    ).startswith(CLOUD_GAME_URL):
                        return target
            if time.monotonic() >= deadline:
                raise CloudBrowserError("云浏览器中找不到云游戏页面")
            await asyncio.sleep(0.5)

    async def initialize_profile(self) -> bool:
        """CDP 注入三月七初始 localStorage 与自动战斗开关，刷新页面后断开。

        成功后写入标记文件，之后的启动不再重复；失败只记警告（三月七仍能
        处理弹窗），下次启动重试。

        Returns:
            bool: 是否初始化成功。
        """

        try:
            storage = load_initial_local_storage(self.m7a_root)
        except (OSError, ValueError) as e:
            logger.warning(f"读取三月七初始配置失败，跳过云浏览器初始化：{e}")
            return False

        try:
            target = await self.find_game_page()
            async with CdpSession(target["webSocketDebuggerUrl"]) as cdp:
                await self._wait_origin(cdp)
                count = await cdp.evaluate(build_local_storage_script(storage))
                logger.info(f"已向云游戏页面注入三月七初始配置 {count} 项")
                if self.auto_battle:
                    uid = await cdp.evaluate(build_auto_battle_script(True))
                    logger.info(
                        "已开启云游戏自动战斗"
                        + ("与二倍速" if uid else "（未检测到 UID，二倍速留待下次）")
                    )
                await cdp.call("Page.enable")
                await cdp.call("Page.reload", {"ignoreCache": False})
                with suppress(asyncio.TimeoutError):
                    await cdp.wait_event("Page.loadEventFired", PAGE_TIMEOUT_SECONDS)
        except Exception as e:
            logger.warning(f"云浏览器首次初始化失败，下次启动时重试：{e}")
            return False

        (self.profile_dir / INITIALIZED_MARKER).write_text(
            time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8"
        )
        return True

    @staticmethod
    async def _wait_origin(cdp: CdpSession) -> None:
        """等页面文档真正落在云游戏站点上，避免把 localStorage 写进别的源。"""

        deadline = time.monotonic() + PAGE_TIMEOUT_SECONDS
        while True:
            with suppress(CloudBrowserError, asyncio.TimeoutError):
                href = await cdp.evaluate("location.href", timeout=5.0)
                if str(href or "").startswith(CLOUD_GAME_URL):
                    return
            if time.monotonic() >= deadline:
                raise CloudBrowserError("云游戏页面加载超时")
            await asyncio.sleep(0.5)

    async def _close_gracefully(self) -> None:
        """经 CDP ``Browser.close`` 让浏览器正常退出，让 cookie 等落盘。"""

        async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
            response = await client.get(f"{self.endpoint}/json/version")
            ws_url = response.json()["webSocketDebuggerUrl"]
        async with CdpSession(ws_url) as cdp:
            with suppress(Exception):
                await cdp.call("Browser.close", timeout=2.0)

    async def stop(self) -> None:
        """关闭浏览器：先请求正常退出，再 terminate，3 秒后 kill，并清理子进程。"""

        pid = self.pid
        if pid is None or not await self.is_alive():
            # 已退出（常见于三月七 stop_game() 按标记杀掉）：pid 可能已被复用，
            # 不再按 pid 找子进程，只清理本 profile 残留的带标记进程。
            await self.process.clear()
            await cleanup_stale_cloud_browsers(self.profile_dir)
            return

        try:
            children = psutil.Process(pid).children(recursive=True)
        except psutil.Error:
            children = []

        if self.port is not None:
            with suppress(Exception):
                await self._close_gracefully()
                deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
                while await self.is_alive() and time.monotonic() < deadline:
                    await asyncio.sleep(0.1)

        await self.process.kill()

        def _reap() -> None:
            alive = [proc for proc in children if proc.is_running()]
            for proc in alive:
                with suppress(psutil.Error):
                    proc.terminate()
            _, leftover = psutil.wait_procs(alive, timeout=STOP_TIMEOUT_SECONDS)
            for proc in leftover:
                with suppress(psutil.Error):
                    proc.kill()

        await asyncio.to_thread(_reap)
        logger.info(f"云浏览器已关闭（pid {pid}）")
