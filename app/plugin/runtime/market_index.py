"""从标准 Simple 镜像读取发行元数据，不安装或导入插件代码。"""

from __future__ import annotations

import asyncio
import hashlib
import io
import re
from email.message import Message
from email.parser import Parser
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urldefrag, urljoin, urlsplit
from zipfile import ZipFile

import httpx
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


class _Links(HTMLParser):
    """读取 Simple 页面中每个分发文件的链接及标准元数据属性。"""

    def __init__(self) -> None:
        """初始化当前页面的分发文件链接集合。"""
        super().__init__()
        self.files: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """收集带 href 的锚点，保留 yanked 与 metadata 等原始声明。"""
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.files.append(attributes)


class _WheelReader(io.RawIOBase):
    """为 zipfile 提供可定位的远端文件，只请求中央目录和 METADATA 所需区间。"""

    def __init__(self, client: httpx.Client, url: str) -> None:
        """读取包尾以确定总大小；不支持 Range 的镜像只读取一次整包。"""
        self.client = client
        self.url = url
        self.position = 0
        response = client.get(url, headers={"Range": "bytes=-65558"})
        response.raise_for_status()
        self.cache = response.content
        if response.status_code == 200:
            self.start = 0
            self.size = len(self.cache)
        else:
            match = re.fullmatch(
                r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", "")
            )
            if match is None:
                raise ValueError("镜像未返回有效的 wheel 文件区间")
            self.start, end, self.size = map(int, match.groups())
            if end + 1 != self.size or len(self.cache) != self.size - self.start:
                raise ValueError("镜像返回的 wheel 包尾大小不匹配")

    def seekable(self) -> bool:
        """允许 zipfile 在中央目录与目标条目之间定位。"""
        return True

    def readable(self) -> bool:
        """声明当前远端文件仅支持读取。"""
        return True

    def tell(self) -> int:
        """返回 zipfile 当前读取位置。"""
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        """按文件起点、当前位置或文件末尾设置下一次读取位置。"""
        self.position = {
            io.SEEK_SET: 0,
            io.SEEK_CUR: self.position,
            io.SEEK_END: self.size,
        }[whence] + offset
        return self.position

    def read(self, size: int = -1) -> bytes:
        """优先复用已读取区间，否则请求对应字节并核对服务器响应区间。"""
        end = self.size if size < 0 else min(self.size, self.position + size)
        if end <= self.position:
            return b""
        if not (self.start <= self.position and end <= self.start + len(self.cache)):
            response = self.client.get(
                self.url, headers={"Range": f"bytes={self.position}-{end - 1}"}
            )
            response.raise_for_status()
            expected = f"bytes {self.position}-{end - 1}/{self.size}"
            if (
                response.status_code != 206
                or response.headers.get("Content-Range") != expected
                or len(response.content) != end - self.position
            ):
                raise ValueError("镜像返回的 wheel 文件区间不匹配")
            self.start, self.cache = self.position, response.content
        content = self.cache[self.position - self.start : end - self.start]
        self.position = end
        return content


def _read_wheel(url: str, proxy: httpx.Proxy | None) -> Message[Any, Any]:
    """只读取 wheel 的标准 METADATA，所有内容保留内存，不解包、安装或导入代码。"""
    with httpx.Client(timeout=45, follow_redirects=True, proxy=proxy) as client:
        with _WheelReader(client, url) as remote, ZipFile(remote) as archive:
            entries = [
                item
                for item in archive.infolist()
                if item.filename.count("/") == 1
                and item.filename.endswith(".dist-info/METADATA")
            ]
            if len(entries) != 1:
                raise ValueError("wheel 必须包含唯一的标准 METADATA")
            # README 属于不可信远端内容，避免仅浏览市场便无限展开压缩载荷。
            if entries[0].file_size > 8 * 1024 * 1024:
                raise ValueError("wheel 的 METADATA 超过 8 MB")
            return Parser().parsestr(archive.read(entries[0]).decode("utf-8"))


async def fetch_metadata(
    client: httpx.AsyncClient,
    simple: str,
    package: str,
    *,
    proxy: httpx.Proxy | None,
) -> Message[Any, Any] | None:
    """读取镜像最新非撤回 wheel 的元数据；优先标准 sidecar，否则按区间读取 wheel。"""
    page = await client.get(
        urljoin(simple.rstrip("/") + "/", package + "/"),
        headers={"Accept": "application/vnd.pypi.simple.v1+html"},
    )
    if page.status_code == 404:
        return None
    page.raise_for_status()
    parser = _Links()
    parser.feed(page.text)
    wheels: list[tuple[Version, str, dict[str, str | None]]] = []
    for attributes in parser.files:
        url, _ = urldefrag(urljoin(str(page.url), attributes["href"] or ""))
        filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
        if not filename.endswith(".whl") or "data-yanked" in attributes:
            continue
        name, version, _, _ = parse_wheel_filename(filename)
        if name == canonicalize_name(package):
            wheels.append((version, url, attributes))
    if not wheels:
        return None
    stable = [item for item in wheels if not item[0].is_prerelease]
    version, url, attributes = max(stable or wheels, key=lambda item: item[0])
    declaration = attributes.get("data-core-metadata") or attributes.get(
        "data-dist-info-metadata"
    )
    if declaration and declaration != "false":
        response = await client.get(url + ".metadata")
        response.raise_for_status()
        if declaration != "true":
            algorithm, expected = declaration.split("=", 1)
            if hashlib.new(algorithm, response.content).hexdigest() != expected:
                raise ValueError("镜像 METADATA 校验失败")
        metadata = Parser().parsestr(response.content.decode("utf-8"))
    else:
        metadata = await asyncio.to_thread(_read_wheel, url, proxy)
    if (
        canonicalize_name(str(metadata.get("Name", ""))) != canonicalize_name(package)
        or Version(str(metadata.get("Version", ""))) != version
    ):
        raise ValueError("镜像元数据与请求的发行包身份不一致")
    return metadata
