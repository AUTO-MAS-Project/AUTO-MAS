"""项目自带的 MaaFramework 原生库：在哪、什么版本、本机能不能用（只读项目目录）。

runner、agent 环境、项目更新与宿主接缝都从这里取；本模块只依赖本库的其它模块与
``packaging``，不导入 runner / agent_env / runtime_pool / project_update。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version

from .architecture import (
    RID_ARCHITECTURE_ALIASES,
    UNSUPPORTED_ARCHITECTURE_MARKER,
    host_architecture,
)
from .pe import detect_pe_architecture, pe_imported_dlls

# 内置运行能驱动的最低 MaaFramework 版本。
#
# runner 侧 import 了 ``maa.event_sink``，而该模块是 **5.0.0** 才加进 py binding
# 的：逐个 minor 首版查过 PyPI 上的 wheel，4.0.0 到 4.5.0 全部没有它，5.0.0 起
# 才有。装上更老的 binding，worker 会在启动时 ``ModuleNotFoundError``。
#
# MaaFramework 上游自己的支持线更高——5.1 之前一律不再支持。这里取 5.0.0 是
# 因为它是**本代码实际需要**的下限，不替上游表态。
#
# 官方目录里踩线的项目（2026-08-30 勘察）：MMleo 自带 4.5.3、MaaEOV 自带 4.5.6。
# 这两个用内置运行跑不起来，属已知边界而非缺陷——太老的不支持是正常的。
PROJECT_MAAFW_DLL_NAME = "MaaFramework.dll"

# 兜底搜索的最大深度。真实布局最深是 ``runtimes/<rid>/native``（3 层），
# 留一层余量吸收未来的挪动；再深就会扫进 ``python/Lib/site-packages/maa/bin``
# 那种项目自带解释器的副本，那是 agent 的，不是外壳的。
_RUNTIME_SEARCH_MAX_DEPTH = 4

# MaaFramework 把自身版本以 ``v5.13.0-beta.2`` 这样的形式内嵌在原生库里。
# 用已知版本的样本校验过：来自 ``maafw==5.12.3`` 包的那份原生库提取出的正是
# ``5.12.3``，说明取到的确实是它自己的版本而非别的字符串。
_MAAFW_DLL_VERSION_RE = re.compile(
    rb"(?<![0-9A-Za-z.])v(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)(?![0-9A-Za-z.])"
)


def _host_rid_os_prefixes() -> tuple[str, ...]:
    if sys.platform == "win32":
        return ("win",)
    if sys.platform == "darwin":
        return ("osx", "macos")
    if sys.platform.startswith("linux"):
        return ("linux",)
    return ()


def runtime_identifier_matches_host(rid: str) -> bool:
    """``runtimes/<rid>`` 的 rid 是不是本机能加载的那一种（系统前缀 + 架构都对上）。

    认 ``win-x64``、``win10-x64``、``linux-musl-arm64`` 这类写法：最后一段是架构，
    其余是系统（``osx.10.12`` 这种带版本的也按前缀认）。
    """

    system, separator, architecture = str(rid).casefold().rpartition("-")
    if not separator:
        return False
    if RID_ARCHITECTURE_ALIASES.get(architecture) != host_architecture():
        return False
    return any(system.startswith(prefix) for prefix in _host_rid_os_prefixes())


def _project_runtime_rid_dirs(project_path: Path) -> list[Path]:
    """``runtimes/`` 下的 rid 目录，本机架构的排在前面，其余照名字顺序。"""

    runtimes = project_path / "runtimes"
    try:
        rids = [item for item in sorted(runtimes.iterdir()) if item.is_dir()]
    except OSError:
        return []
    host = [item for item in rids if runtime_identifier_matches_host(item.name)]
    return host + [item for item in rids if item not in host]


def host_runtime_rid_dirs(project_path: Path) -> list[Path]:
    """``runtimes/`` 下与本机架构对应的 rid 目录（存在的才给）。"""

    return [
        item
        for item in _project_runtime_rid_dirs(project_path)
        if runtime_identifier_matches_host(item.name)
    ]


def _iter_project_maafw_candidates(project_path: Path):
    """按优先级产出可能放着 MaaFramework.dll 的目录。

    先枚举已知布局，再退到有界的逐层搜索——不写死具体 rid，也不指望布局
    永远不变。
    """

    yield project_path / "maafw"

    # .NET 把原生库放在 runtimes/<rid>/native/ 下（MFAAvalonia 即如此）。
    # 用枚举而不是钉死 win-x64，arm64 / linux-x64 同样能命中；同时带好几种架构时
    # 本机那一种先出——按名字排 win-arm64 在 win-x64 前面，x64 机器上会选到 arm64。
    rids = _project_runtime_rid_dirs(project_path)
    for rid in rids:
        yield rid / "native"
    for rid in rids:
        yield rid


def _search_project_maafw_dll(project_path: Path) -> Path | None:
    """逐层就近搜索，返回最浅的那一份。"""

    frontier = [project_path]
    for _ in range(_RUNTIME_SEARCH_MAX_DEPTH):
        following: list[Path] = []
        for directory in frontier:
            try:
                entries = sorted(directory.iterdir())
            except OSError:
                continue
            for item in entries:
                if item.is_dir():
                    following.append(item)
                elif item.name == PROJECT_MAAFW_DLL_NAME:
                    return directory
        if not following:
            break
        frontier = following
    return None


def project_maafw_runtime_path(project_path: Path | None) -> Path | None:
    """项目自带的 MaaFramework 运行时目录。

    优先用项目自己的原生库而不是 runner venv 里那份：同一个版本号下二进制未必
    相同（实测 MaaYYs 与 MaaEnd 自带的 MaaFramework.dll 互不相同，也都不同于
    PyPI 的 maafw 包），项目的自定义构建只有用它自己的库才对得上。
    """

    if project_path is None:
        return None

    # 与本机架构不符的（PE 头读得出且对不上）跳过继续找；一个对得上的都没有时退回
    # 第一份不符的，让调用方走架构不符的报错（describe_runtime_architecture_mismatch）。
    mismatched: Path | None = None
    loadable: list[Path] = []
    for candidate in _iter_project_maafw_candidates(project_path):
        if not (candidate / PROJECT_MAAFW_DLL_NAME).is_file():
            continue
        if _runtime_loadable_on_host(candidate):
            loadable.append(candidate)
        elif mismatched is None:
            mismatched = candidate
    if loadable:
        return _newest_runtime(loadable)
    found = _search_project_maafw_dll(project_path)
    if found is not None and (mismatched is None or _runtime_loadable_on_host(found)):
        return found
    return mismatched


def _newest_runtime(candidates: list[Path]) -> Path:
    """同时有好几份原生库时取版本最高的。读不出版本的那份不参与比较；版本相同、或一份
    都读不出时按候选顺序取第一份。问题包检查（``maafwProjectRuntimeProbe.ts`` 的
    ``findNativeDir``）按同一口径选，改时两边一起改。

    多份并存几乎都是残留：本地导入的目录被外壳原地升级过（老布局的 ``maafw/`` 留着），
    全量包更新又把导入来的文件原样带进新载荷。M9A v4.11.0 实测 ``maafw/`` 是 5.9.2、
    ``runtimes/win-x64/native`` 是 5.14.0；它的 agent（``agent/maafw_paths.py``）先找
    ``runtimes/``，按固定顺序先取 ``maafw/`` 的 runner 就与 agent 协议不一致（7 对 8），
    每次都等满连接超时。残留天然比发行包带的旧，取最高版本不依赖任何布局约定。
    """

    if len(candidates) == 1:
        return candidates[0]
    best = candidates[0]
    best_version: Version | None = None
    for candidate in candidates:
        text = read_runtime_maafw_version(candidate)
        if text is None:
            continue
        version = Version(text)
        if best_version is None or version > best_version:
            best, best_version = candidate, version
    return best


def read_runtime_maafw_version(runtime_path: Path) -> str | None:
    """原生库里内嵌的版本串，规范化成 PEP 440；不是恰好一个或解析不了时 None。"""

    try:
        data = (runtime_path / PROJECT_MAAFW_DLL_NAME).read_bytes()
    except OSError:
        return None

    found = {
        match.group(1).decode("ascii", errors="ignore")
        for match in _MAAFW_DLL_VERSION_RE.finditer(data)
    }
    if len(found) != 1:
        return None
    try:
        return str(Version(found.pop()))
    except InvalidVersion:
        return None


def _runtime_loadable_on_host(runtime_path: Path) -> bool:
    """原生库的 PE 架构与本机一致；读不出来（非 PE、读失败）不猜，算一致。"""

    found = detect_pe_architecture(runtime_path / PROJECT_MAAFW_DLL_NAME)
    return found is None or found == host_architecture()


def project_runtime_loadable_on_host(project_path: Path) -> bool | None:
    """项目自带的 MaaFramework 在本机能不能加载。

    Returns:
        True / False；项目没自带原生库、或读不出它的架构时 None（不猜）。
    """

    runtime = project_maafw_runtime_path(project_path)
    if runtime is None:
        return None
    found = detect_pe_architecture(runtime / PROJECT_MAAFW_DLL_NAME)
    if found is None:
        return None
    return found == host_architecture()


#: 导入表里这些名字不在原生库目录里也不算缺：API set 由系统解析，VC / UCRT 运行库装在系统里
#: （运行 MAS 的 Python 自己也带一份）。缺了它们重下发行包也补不回来。
_SYSTEM_IMPORT_PREFIXES = (
    "api-ms-",
    "ext-ms-",
    "msvcp",
    "vcruntime",
    "concrt",
    "vccorlib",
    "vcomp",
    "ucrtbase",
)


def runtime_missing_dependencies(runtime_path: Path) -> list[str] | None:
    """原生库目录里 ``MaaFramework.dll`` 顺着导入表要用、目录里又没有的 DLL。

    从主库出发，只沿着目录里有的那些 DLL 往下查；系统目录里有的、API set 与 VC 运行库
    （:data:`_SYSTEM_IMPORT_PREFIXES`）不算缺。差量更新把 runner 换到只有几个 DLL 的目录时
    （MAA_bbb v1.13.20），这里会列出 ``opencv_world4_maa.dll`` 之类。

    Returns:
        缺的 DLL 名（空表即完整）；不是 Windows、没有主库、导入表读不出时 None（不下结论）。
    """

    if sys.platform != "win32":
        return None
    try:
        present = {
            item.name.casefold(): item
            for item in Path(runtime_path).iterdir()
            if item.is_file()
        }
    except OSError:
        return None
    if PROJECT_MAAFW_DLL_NAME.casefold() not in present:
        return None
    system_dirs = [
        Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32",
        Path(sys.executable).parent,
    ]
    pending = [PROJECT_MAAFW_DLL_NAME.casefold()]
    seen: set[str] = set()
    missing: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        imports = pe_imported_dlls(present[name])
        if imports is None:
            return None
        for dependency in imports:
            key = dependency.casefold()
            if key in present:
                pending.append(key)
            elif not key.startswith(_SYSTEM_IMPORT_PREFIXES) and not any(
                (directory / dependency).is_file() for directory in system_dirs
            ):
                missing.add(dependency)
    return sorted(missing, key=str.casefold)


# 子进程里只做一件事：按 runner 的 ``Library.open`` 同样的方式（绝对路径的 WinDLL，
# 依赖从 DLL 所在目录找）加载主库。加载失败退出码 3，并把原因打到 stdout。
_NATIVE_LOAD_PROBE = (
    "import ctypes, sys\n"
    "try:\n"
    "    ctypes.WinDLL(sys.argv[1])\n"
    "except OSError as error:\n"
    "    print(error)\n"
    "    sys.exit(3)\n"
)
_NATIVE_LOAD_FAILED_EXIT = 3
_NATIVE_LOAD_TIMEOUT_SECONDS = 60

NATIVE_LOAD_OK = "ok"
NATIVE_LOAD_FAILED = "failed"
NATIVE_LOAD_UNKNOWN = "unknown"


def probe_native_runtime_load(runtime_path: Path) -> tuple[str, str]:
    """在独立子进程里真加载一次 ``runtime_path`` 下的 ``MaaFramework.dll``。

    不在本进程里加载：载进来就卸不掉，还会锁住文件。

    Returns:
        ``(结论, 说明)``：结论是 :data:`NATIVE_LOAD_OK` / :data:`NATIVE_LOAD_FAILED`（子进程
        明确报加载失败，说明是系统给的原因）/ :data:`NATIVE_LOAD_UNKNOWN`（不是 Windows、
        子进程起不来、超时、异常退出——不下结论）。
    """

    if sys.platform != "win32":
        return NATIVE_LOAD_UNKNOWN, "不是 Windows"
    dll = Path(runtime_path) / PROJECT_MAAFW_DLL_NAME
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _NATIVE_LOAD_PROBE, str(dll)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=_NATIVE_LOAD_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return NATIVE_LOAD_UNKNOWN, f"{type(exc).__name__}: {exc}"
    if completed.returncode == _NATIVE_LOAD_FAILED_EXIT:
        reason = (completed.stdout or "").strip().rstrip("。.") or "原因未知"
        return NATIVE_LOAD_FAILED, reason
    if completed.returncode != 0:
        return (
            NATIVE_LOAD_UNKNOWN,
            f"退出码 {completed.returncode}：{(completed.stderr or '').strip()[-500:]}",
        )
    return NATIVE_LOAD_OK, ""


def project_runtime_broken(project_path: Path) -> bool:
    """runner 要用的那份原生库**确定**用不了：依赖缺了（:func:`runtime_missing_dependencies`），
    而且在子进程里真加载也失败。

    导入表的判断只用来挑出可疑的副本（几毫秒）；真加载（一两秒）只在可疑时才做，用来排除
    误判——否则一次误判就会让更新器每次运行都按全量包重装一遍。判断不了一律 False。
    """

    runtime = project_maafw_runtime_path(project_path)
    if runtime is None or not runtime_missing_dependencies(runtime):
        return False
    verdict, _detail = probe_native_runtime_load(runtime)
    return verdict == NATIVE_LOAD_FAILED


def project_runtime_complete(project_path: Path) -> bool | None:
    """runner 要用的那份原生库依赖齐不齐（见 :func:`runtime_missing_dependencies`）。

    Returns:
        True / False；没自带原生库或判断不了时 None（不猜）。
    """

    runtime = project_maafw_runtime_path(project_path)
    if runtime is None:
        return None
    missing = runtime_missing_dependencies(runtime)
    if missing is None:
        return None
    return not missing


def project_runtime_usable_on_host(project_path: Path) -> bool | None:
    """项目自带的 MaaFramework 在本机能不能用：架构对得上**而且**依赖齐。

    任一项确定不行就是 False；都判断不了时 None。同版本载荷谁顶替谁（``payloads``）按它判。
    """

    loadable = project_runtime_loadable_on_host(project_path)
    if loadable is False:
        return False
    complete = project_runtime_complete(project_path)
    if complete is False:
        return False
    if loadable is None and complete is None:
        return None
    return True


# 架构不符报错（describe_runtime_architecture_mismatch 的各种文案、「只支持 x64」提示）
# 里一定有其一；宿主侧靠它认出「重试也没用」，别只改文案不改这里。
ARCHITECTURE_MISMATCH_MARKERS = (
    "架构，本机是 ",
    "架构的 MaaFramework，本机是 ",
    UNSUPPORTED_ARCHITECTURE_MARKER,
)


def describe_runtime_architecture_mismatch(
    runtime_path: Path | None,
    *,
    project_path: Path | None = None,
    source_path: Path | None = None,
) -> str | None:
    """项目自带的原生库架构与本机不符时给出可读原因。

    不符时 ``Library.open`` 必然失败，但原生层报的错难以定位到「装错了包」。
    提前判断只是把同一个失败说清楚，不会挡下任何原本能跑的情况。

    典型场景：arm64 机器上装了 win-x86_64 的发行包（或反之）——MaaFramework
    的项目普遍两种都发，选错了很难自己看出来。另一种是 MAS 自己造成的：旧版在
    来源 ``runtimes/`` 同时带 win-arm64 与 win-x64 时按名字选中 arm64，副本里只剩
    arm64。给了 ``project_path``（副本）且原生库在它的 ``runtimes/`` 下时按这种情况
    说；再给了 ``source_path``（导入来源 ``Info.Path``）就看来源里有没有本机能用的，
    有就只让重新导入，没有就让换包。这里只说明、不动副本与载荷。
    """

    if runtime_path is None:
        return None
    dll = runtime_path / PROJECT_MAAFW_DLL_NAME
    found = detect_pe_architecture(dll)
    if found is None:
        return None  # 读不出来就不猜，交给原生层去报
    expected = host_architecture()
    if found == expected:
        return None
    source_loadable = (
        project_runtime_loadable_on_host(source_path)
        if source_path is not None and source_path.is_dir()
        else None
    )
    if source_loadable is True:
        return (
            f"项目副本里只带了 {found} 架构的 MaaFramework，本机是 {expected}"
            "（旧版 MAS 在来源目录同时带多种架构时选错了）。来源目录里有 "
            f"{expected} 版，请在托管页重新导入项目"
        )
    if source_loadable is False:
        return (
            f"项目自带的 MaaFramework 是 {found} 架构，本机是 {expected}，来源目录里"
            f"也只有 {found} 版——请换成 {expected} 的发行包，再在托管页重新导入"
        )
    if project_path is not None and _is_relative_to(
        runtime_path, project_path / "runtimes"
    ):
        return (
            f"项目副本里只带了 {found} 架构的 MaaFramework，本机是 {expected}"
            "（旧版 MAS 在来源目录同时带多种架构时会选错），请在托管页重新导入项目；"
            f"若来源目录本身只有 {found} 版，请换成 {expected} 的发行包"
        )
    return (
        f"项目自带的 MaaFramework 是 {found} 架构，本机是 {expected}——"
        "多半是下载了不匹配的发行包，请换成对应架构的包"
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
    except (OSError, ValueError):
        return False
    return True


def describe_plugin_architecture_mismatch(plugins_dir: Path) -> str | None:
    """项目自带的原生插件目录里没有一个本机能加载时给出可读原因（导入时提示用）。

    与 runner 目录模式的筛选同一个判据：PE 架构读得出且与本机不符的 DLL 会被跳过，
    读不出的照旧尝试。所以只有「读得出架构的全都不符、也没有读不出的」才说——那时
    插件一个都不会加载。没有 DLL、或目录读不了时不说。
    """

    try:
        dlls = [item for item in plugins_dir.rglob("*.dll") if item.is_file()]
    except OSError:
        return None
    found: set[str] = set()
    for dll in dlls:
        architecture = detect_pe_architecture(dll)
        if architecture is None:
            return None
        found.add(architecture)
    expected = host_architecture()
    if not found or expected in found:
        return None
    return (
        f"项目自带的原生插件（{plugins_dir.name}/）是 {' / '.join(sorted(found))} 架构，"
        f"本机是 {expected}——多半是下载了不匹配的发行包，请换成 {expected} 的发行包"
        "重新导入"
    )


def describe_project_runtime_architecture_mismatch(
    project_path: Path, *, source_path: Path | None = None
) -> str | None:
    """运行前自检用：项目（副本）自带的原生库与本机架构不符时的原因，见
    :func:`describe_runtime_architecture_mismatch`；对得上或没自带时 None。"""

    return describe_runtime_architecture_mismatch(
        project_maafw_runtime_path(project_path),
        project_path=project_path,
        source_path=source_path,
    )


def probe_bundled_maafw_version(project_path: Path) -> str | None:
    """读出项目自带原生库的版本，规范化成 PEP 440。

    ``v5.13.0-beta.2`` -> ``5.13.0b2``，正好对得上 PyPI 上的预发布版本号。
    只在原生库里恰好存在唯一一个版本串时才采信——多于一个说明这个提取方式
    对该构建不成立，宁可返回 None 走原有兜底。
    """

    runtime_path = project_maafw_runtime_path(project_path)
    if runtime_path is None:
        return None
    return read_runtime_maafw_version(runtime_path)


__all__ = [
    "ARCHITECTURE_MISMATCH_MARKERS",
    "NATIVE_LOAD_FAILED",
    "NATIVE_LOAD_OK",
    "NATIVE_LOAD_UNKNOWN",
    "PROJECT_MAAFW_DLL_NAME",
    "describe_plugin_architecture_mismatch",
    "describe_project_runtime_architecture_mismatch",
    "describe_runtime_architecture_mismatch",
    "host_runtime_rid_dirs",
    "probe_bundled_maafw_version",
    "probe_native_runtime_load",
    "project_maafw_runtime_path",
    "project_runtime_broken",
    "project_runtime_complete",
    "project_runtime_loadable_on_host",
    "project_runtime_usable_on_host",
    "read_runtime_maafw_version",
    "runtime_identifier_matches_host",
    "runtime_missing_dependencies",
]
