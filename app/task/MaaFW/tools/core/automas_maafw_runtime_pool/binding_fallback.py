"""PyPI 缺 ``maafw`` 版本时，从 MaaFramework 的 git tag 源码包自打纯 Python wheel。

背景：MaaEnd v2.29.0 打包了 MaaFramework ``v5.14.0-beta.1`` 的 DLL，运行池据此把 binding
钉成 ``maafw==5.14.0b1``，而 MaaFramework 发版工作流的 pip job 上传失败、PyPI 上没有这个
版本——环境建不出来、任务每次必挂。binding 是纯 Python（``source/binding/Python/maa``），
DLL 由项目自带的 ``maafw/`` 目录提供（``runner.py`` 会 ``Library.open(runtime_path)``），
所以从 tag 源码包打一个不带原生库的 wheel 就够用。

约束：
- 本模块在 ``runtime_pool`` 包内，而 worker 子进程的导入闭包包含整个包、池 venv 里只有
  ``RUNNER_DEFAULT_PACKAGES``——**模块级 import 只允许标准库 + packaging**，HTTP 用
  ``urllib``，代理串由调用方传入（不读 ``Config``）。
- wheel 必须带 ``maa/bin/.auto-mas-no-bundled-dll`` 占位文件：``maa/__init__.py`` 在
  import 时就 ``Library.open(<maa>/bin)``，目录不存在直接 ``FileNotFoundError``；池装完
  依赖后 ``installer._verify_maafw_importable`` 在干净 env 里 ``import maa``，拿不到项目
  路径，给 worker 设 ``MAAFW_BINARY_PATH`` 救不了这一步。
- ``pyproject.toml`` 的 ``dependencies`` 原样全部带入 ``Requires-Dist``，含
  ``MaaAgentBinary``：它不是被 import，而是 ``AdbController.__init__`` 默认参数
  ``agent_path = <maa>/../MaaAgentBinary``，剔了它，落到这份共享环境的 ADB 项目会静默丢
  maatouch / minitouch / minicap。
- 兜底只对自带 ``MaaFramework.dll`` 的项目有意义，无 DLL 项目的守卫在
  ``automas_maafw_runner/environment.py::prepare_runner_environment``。
- agent 侧不覆盖：isolated_venv 的 pip（``agent_env/env.py::_pip_install``）钉同样的
  ``maafw==X``，PyPI 缺货抛 ``MaaFWAgentEnvError`` → 预检失败 → 回滚 → 不升级，这是预期；
  ``project_python`` 不装东西。
- 许可：MaaFramework 是 LGPL-3.0；运行时把源码装进用户自己的 venv 不构成再分发，wheel
  带 ``LICENSE.md``，不 vendor 进 MAS 仓库。
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import tomllib
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from packaging.version import InvalidVersion, Version

logger = logging.getLogger("automas.maafw.runtime_pool.binding_fallback")

MAAFW_REPOSITORY = "MaaXYZ/MaaFramework"
#: tag 源码包的唯一真实来源；``github.com/…/archive/…`` 对任何 tag（含不存在的）都
#: 无条件 302 到它、响应体 0 字节，只作第二候选且必须跟跳转。
SOURCE_ARCHIVE_URL_TEMPLATES: tuple[str, ...] = (
    "https://codeload.github.com/{repo}/zip/refs/tags/{tag}",
    "https://github.com/{repo}/archive/refs/tags/{tag}.zip",
)
BINDING_SOURCE_PREFIX = "source/binding/Python/"
BINDING_SRC_CACHE_RELATIVE_PATH = Path("cache") / "binding-src"
BINDING_WHEEL_CACHE_RELATIVE_PATH = Path("cache") / "binding-wheels"
NO_BUNDLED_DLL_MARKER_NAME = ".auto-mas-no-bundled-dll"
NO_BUNDLED_DLL_MARKER_TEXT = (
    "原生库由项目自带 maafw/ 目录提供；本目录仅为让 maa/__init__.py 的 "
    "Library.open(<maa>/bin) 通过 path.exists()\n"
)
DEFAULT_REQUIRES_PYTHON = ">=3.9"
DOWNLOAD_TIMEOUT_SECONDS = 30
_DOWNLOAD_CHUNK_SIZE = 256 * 1024
# 源码包实测 1.2 MB；给一个远超正常值的上限，防止跟错跳转把整站页面当 zip 落盘。
_MAX_SOURCE_ARCHIVE_BYTES = 64 * 1024 * 1024

# uv 0.11 对「索引上没有这个版本」的两种原文（连不上索引的 ``Request failed after 3
# retries`` / ``Failed to fetch`` 与离线的 ``was not found in the cache`` 都不算）。
# uv 会把长句按 60 列折行，匹配前先把空白归一。
_MISSING_VERSION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"there is no version of maafw==", re.IGNORECASE),
    re.compile(r"maafw was not found in the package registry", re.IGNORECASE),
)


class MaaFWBindingFallbackError(RuntimeError):
    """兜底任一步失败（映射不到 tag、下载不到、源码包不合规、打包失败）。"""


@dataclass(frozen=True)
class BindingSourceInfo:
    """校验过的 tag 源码包里与打 wheel 有关的事实。"""

    top_level: str
    dependencies: tuple[str, ...]
    requires_python: str


def pep440_to_maafw_tag(version_text: str) -> str | None:
    """把 requirement 里的 PEP 440 版本映射成 MaaFramework 的 git tag。

    ``5.14.0b1`` → ``v5.14.0-beta.1``，``5.14.0a2`` → ``v5.14.0-alpha.2``，
    ``5.14.0rc1`` → ``v5.14.0-rc.1``，``5.13.1`` → ``v5.13.1``。
    post / dev / local 任一非空返回 ``None``：nightly 的 DLL 串形如
    ``v5.13.1-post.6-ci.<id>``，PyPI 与 tag 都没有，兜底无从谈起。
    MaaFramework 仓库里没有反向映射可抄（``pip_pack.py::set_toml_ver`` 只是把 CI 传入
    的 tag 原样写进 pyproject），这里按 CI 的命名习惯正向推。
    """

    try:
        version = Version(str(version_text).strip())
    except InvalidVersion:
        return None
    if version.post is not None or version.dev is not None or version.local:
        return None
    base = ".".join(str(part) for part in version.release)
    if version.pre is None:
        return f"v{base}"
    phase, number = version.pre
    suffix = {"a": "alpha", "b": "beta", "rc": "rc"}.get(phase)
    if suffix is None:
        return None
    return f"v{base}-{suffix}.{number}"


def maafw_version_missing_from_index(detail: str | None) -> bool:
    """判断一段 uv stderr 是否表示「索引上没有这个 maafw 版本」。"""

    text = " ".join(str(detail or "").split())
    if not text:
        return False
    return any(pattern.search(text) for pattern in _MISSING_VERSION_PATTERNS)


def source_archive_candidates(tag: str) -> tuple[str, ...]:
    return tuple(
        template.format(repo=MAAFW_REPOSITORY, tag=tag)
        for template in SOURCE_ARCHIVE_URL_TEMPLATES
    )


def local_wheel_requirement(wheel_path: Path) -> str:
    """uv / pip 都接受的本地 wheel 位置参数：``maafw @ file:///D:/abs/path.whl``。"""

    return f"maafw @ {Path(wheel_path).resolve().as_uri()}"


def download_source_archive(
    tag: str,
    cache_dir: Path,
    *,
    proxy_url: str | None = None,
    timeout: float = DOWNLOAD_TIMEOUT_SECONDS,
    check_cancelled: Callable[[], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> Path:
    """下载 ``<tag>`` 的源码 zip 到 ``<cache_dir>/<tag>.zip``，按 tag 缓存，存在即不下。

    ``proxy_url`` 非空时只给 ``urllib`` 传 ``ProxyHandler``；为空时**不要**传
    ``ProxyHandler({})``（那会关掉系统代理），直接 ``build_opener()``。
    """

    cache_dir = Path(cache_dir)
    target = cache_dir / f"{tag}.zip"
    if target.is_file() and zipfile.is_zipfile(target):
        return target
    cache_dir.mkdir(parents=True, exist_ok=True)
    opener = _build_opener(proxy_url)
    failures: list[str] = []
    for url in source_archive_candidates(tag):
        if check_cancelled is not None:
            check_cancelled()
        partial = cache_dir / f"{tag}.zip.part"
        try:
            _download_to_file(
                opener,
                url,
                partial,
                timeout=timeout,
                check_cancelled=check_cancelled,
            )
            if not zipfile.is_zipfile(partial):
                raise MaaFWBindingFallbackError("响应不是 zip 文件")
            os.replace(partial, target)
            if log is not None:
                log(f"[MaaFW Runtime Pool] 已下载 MaaFramework {tag} 源码包: {url}")
            return target
        except MaaFWBindingFallbackError as exc:
            failures.append(f"{url}: {exc}")
        except urllib.error.HTTPError as exc:
            failures.append(f"{url}: HTTP {exc.code}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            failures.append(f"{url}: {exc}")
        finally:
            if partial.exists():
                try:
                    partial.unlink()
                except OSError:
                    pass
    raise MaaFWBindingFallbackError(
        f"下载 MaaFramework {tag} 源码包失败：" + "；".join(failures)
    )


def _build_opener(proxy_url: str | None) -> urllib.request.OpenerDirector:
    proxy = str(proxy_url or "").strip()
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    return urllib.request.build_opener()


def _download_to_file(
    opener: urllib.request.OpenerDirector,
    url: str,
    destination: Path,
    *,
    timeout: float,
    check_cancelled: Callable[[], None] | None,
) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "AUTO-MAS"})
    written = 0
    with opener.open(request, timeout=timeout) as response:
        with destination.open("wb") as stream:
            while True:
                if check_cancelled is not None:
                    check_cancelled()
                chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > _MAX_SOURCE_ARCHIVE_BYTES:
                    raise MaaFWBindingFallbackError("响应体超过源码包大小上限")
                stream.write(chunk)
    if written == 0:
        raise MaaFWBindingFallbackError("响应体为空")


def validate_source_archive(archive: Path) -> BindingSourceInfo:
    """校验 tag 源码包的形状并读出打 wheel 需要的事实。

    zip 有且仅有一个顶层目录；``<top>/source/binding/Python/maa/{__init__,library}.py``
    与 ``<top>/LICENSE.md`` 存在；``pyproject.toml`` 的 ``[project].dependencies`` 原样返回。
    """

    try:
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            tops = {name.split("/", 1)[0] for name in names if name}
            if len(tops) != 1:
                raise MaaFWBindingFallbackError(
                    f"源码包顶层目录不唯一: {sorted(tops)[:5]}"
                )
            top = next(iter(tops))
            base = f"{top}/{BINDING_SOURCE_PREFIX}"
            for required in ("maa/__init__.py", "maa/library.py", "pyproject.toml"):
                if f"{base}{required}" not in names:
                    raise MaaFWBindingFallbackError(f"源码包缺少 {base}{required}")
            if f"{top}/LICENSE.md" not in names:
                raise MaaFWBindingFallbackError(f"源码包缺少 {top}/LICENSE.md")
            try:
                pyproject = tomllib.loads(
                    zf.read(f"{base}pyproject.toml").decode("utf-8")
                )
            except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
                raise MaaFWBindingFallbackError(
                    f"源码包的 pyproject.toml 无法解析: {exc}"
                ) from exc
    except zipfile.BadZipFile as exc:
        raise MaaFWBindingFallbackError(f"源码包不是合法 zip: {exc}") from exc
    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise MaaFWBindingFallbackError("源码包的 pyproject.toml 缺少 [project]")
    raw_dependencies = project.get("dependencies", [])
    if not isinstance(raw_dependencies, list) or not all(
        isinstance(item, str) and item.strip() for item in raw_dependencies
    ):
        raise MaaFWBindingFallbackError(
            "源码包的 pyproject.toml 里 dependencies 不是字符串列表"
        )
    requires_python = str(project.get("requires-python") or "").strip()
    return BindingSourceInfo(
        top_level=top,
        dependencies=tuple(item.strip() for item in raw_dependencies),
        requires_python=requires_python or DEFAULT_REQUIRES_PYTHON,
    )


def build_binding_wheel(
    archive: Path,
    version_text: str,
    output_dir: Path,
    *,
    tag: str,
) -> Path:
    """从校验过的源码包打 ``maafw-<X>-py3-none-any.whl``（纯 zipfile，不依赖构建后端）。

    ``X = str(Version(version_text))``，文件名、dist-info 目录名、METADATA ``Version``
    三处一致（``importlib.metadata.version('maafw')`` 读的就是 METADATA）。
    内容：``maa/**``（剔 ``__pycache__``）+ ``maa/bin/.auto-mas-no-bundled-dll`` 占位 +
    ``maafw-<X>.dist-info/{METADATA, WHEEL, RECORD, licenses/LICENSE.md}``。
    按文件名缓存，已存在且是合法 zip 时不重打。
    """

    try:
        version = str(Version(str(version_text).strip()))
    except InvalidVersion as exc:
        raise MaaFWBindingFallbackError(f"maafw 版本不合法: {version_text}") from exc
    output_dir = Path(output_dir)
    wheel_path = output_dir / f"maafw-{version}-py3-none-any.whl"
    if wheel_path.is_file() and zipfile.is_zipfile(wheel_path):
        return wheel_path

    info = validate_source_archive(archive)
    dist_info = f"maafw-{version}.dist-info"
    metadata_lines = [
        "Metadata-Version: 2.1",
        "Name: maafw",
        f"Version: {version}",
        (
            f"Summary: 由 AUTO-MAS 从 MaaFramework {tag} 源码打包，"
            "无自带原生库（maa/bin 仅占位）"
        ),
        f"Requires-Python: {info.requires_python}",
        *(f"Requires-Dist: {dependency}" for dependency in info.dependencies),
        "License-File: LICENSE.md",
    ]
    metadata = ("\n".join(metadata_lines) + "\n").encode("utf-8")
    wheel_metadata = (
        "Wheel-Version: 1.0\n"
        "Generator: auto-mas\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    ).encode("utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    partial = output_dir / f"{wheel_path.name}.part"
    record_rows: list[str] = []
    try:
        with (
            zipfile.ZipFile(archive) as source,
            zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as wheel,
        ):

            def add(arcname: str, data: bytes) -> None:
                wheel.writestr(arcname, data)
                digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                record_rows.append(
                    f"{arcname},sha256={digest.rstrip(b'=').decode('ascii')},{len(data)}"
                )

            base = f"{info.top_level}/{BINDING_SOURCE_PREFIX}"
            package_prefix = f"{base}maa/"
            members = [
                name
                for name in source.namelist()
                if name.startswith(package_prefix)
                and not name.endswith("/")
                and "__pycache__" not in name
                and not name.endswith(".pyc")
            ]
            if not members:
                raise MaaFWBindingFallbackError("源码包的 maa/ 下没有文件")
            for name in members:
                add(str(PurePosixPath(name[len(base) :])), source.read(name))
            add(
                f"maa/bin/{NO_BUNDLED_DLL_MARKER_NAME}",
                NO_BUNDLED_DLL_MARKER_TEXT.encode("utf-8"),
            )
            add(
                f"{dist_info}/licenses/LICENSE.md",
                source.read(f"{info.top_level}/LICENSE.md"),
            )
            add(f"{dist_info}/METADATA", metadata)
            add(f"{dist_info}/WHEEL", wheel_metadata)
            record_rows.append(f"{dist_info}/RECORD,,")
            wheel.writestr(
                f"{dist_info}/RECORD", ("\n".join(record_rows) + "\n").encode("utf-8")
            )
        os.replace(partial, wheel_path)
    except zipfile.BadZipFile as exc:
        raise MaaFWBindingFallbackError(f"源码包不是合法 zip: {exc}") from exc
    finally:
        if partial.exists():
            try:
                partial.unlink()
            except OSError:
                pass
    return wheel_path


def ensure_binding_wheel(
    version_text: str,
    pool_root: Path,
    *,
    proxy_url: str | None = None,
    check_cancelled: Callable[[], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[Path, str]:
    """整条兜底：映射 tag → 下载（缓存）→ 校验 → 打 wheel（缓存）。返回 ``(wheel, tag)``。"""

    tag = pep440_to_maafw_tag(version_text)
    if tag is None:
        raise MaaFWBindingFallbackError(
            f"maafw {version_text} 映射不到 MaaFramework 的发布 tag（post/dev/local 版本没有源码包）"
        )
    pool_root = Path(pool_root)
    try:
        version = str(Version(str(version_text).strip()))
    except InvalidVersion as exc:
        raise MaaFWBindingFallbackError(f"maafw 版本不合法: {version_text}") from exc
    wheel_dir = pool_root / BINDING_WHEEL_CACHE_RELATIVE_PATH
    cached = wheel_dir / f"maafw-{version}-py3-none-any.whl"
    if cached.is_file() and zipfile.is_zipfile(cached):
        return cached, tag
    archive = download_source_archive(
        tag,
        pool_root / BINDING_SRC_CACHE_RELATIVE_PATH,
        proxy_url=proxy_url,
        check_cancelled=check_cancelled,
        log=log,
    )
    wheel = build_binding_wheel(archive, version, wheel_dir, tag=tag)
    logger.info("已从 MaaFramework %s 源码打包 binding: %s", tag, wheel)
    return wheel, tag


def replace_maafw_requirement(
    requirements: Sequence[str],
    replacement: str,
    *,
    is_maafw: Callable[[str], bool],
) -> list[str]:
    """把 requirements 里的 ``maafw==X`` 换成 ``replacement``，其余原样。"""

    return [replacement if is_maafw(item) else item for item in requirements]
