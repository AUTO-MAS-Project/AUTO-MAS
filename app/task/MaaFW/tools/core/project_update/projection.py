"""按 ProjectInterface 白名单把一个 MaaFW 发行包投影成只含内置运行所需文件的树。

内置运行从不启动项目自带的界面程序（MFW.exe / MFAAvalonia / MXU），去掉的就是它们：
外壳程序、.NET 托管库、界面用的运行时、缓存与日志。一份发行包里要落盘的是：
interface.json 及其 ``import``、resource 声明的目录、controller 的附加资源、languages
文件、agent 与 pretask 引用的文件所在目录、依赖清单（requirements.txt 之类），以及
**项目自带的运行时原样带走**——MaaFramework 原生库目录（``maafw/`` 或
``runtimes/<rid>/native``）与 agent 自带的 Python 解释器目录（``python/``）。另外带上
interface 里各层级的 ``icon``（用户页展示项目 / 任务图标）与顶层 ``welcome`` 及其
正文引用的图片（给说明页备着）——小文件，找不到就静默跳过。

**白名单之外的顶层条目，小的留下、大的不要。** 五个真实发行包量下来，agent 在运行时读的
数据经常不在 interface 里：MaaEnd 的 ``data/``（5.6 MB，地图导航、物品识别）、``locales/``
里 languages 没声明的那 37 个文件；M9A 的 ``data/activity``（agent 热更新的活动表）；
MaaYYs 的 ``assets/答案.csv``（逢魔答题）与 ``resource_pack`` 里没声明的子目录。把它们
去掉，副本上的运行就和路径模式不一样。而大的顶层条目（MFAAvalonia 的 ``libs/`` 141 MB、
M9A 的 ``temp_res`` 185 MB、PyQt 外壳的 ``PySide6/``）都是外壳运行时。所以每个没被完整
声明的顶层条目，剩余部分 ≤ 64 MB 就以"保留根"的口径带走（里面照常按分类表剔除），
更大的才丢；根目录上没声明的可执行文件与库（``.exe`` / ``.dll`` / ``.pyd`` …）一律不要，
它们只可能是外壳。外壳若是冻结的 Python 程序（MFW.exe 旁边直接放着 ``python312.dll``），
它的二进制依赖包（``numpy/``、``backports/``、``numpy.libs/`` …）也散在根目录，同样不要：
agent 子进程的 ``PYTHONPATH`` 就是项目根，这些没有 ``__init__.py`` 的半截包会变成命名空间包
盖住真正的模块——Maa_bbb 的副本上 pip 就是这样被 ``backports.zstd`` 打崩的。

原样带走的运行时目录里只剔 ``__pycache__``：CPython 发行版本来就有叫 ``build`` /
``debug`` / ``logs`` 的目录（``pip/_internal/operations/build`` 少了 pip 就起不来），
无源码的 ``.pyc`` 模块也得留着，分类表在这里不适用。

运行时为什么原样带走而不是靠运行池重建：真机上两个项目两种死法——M9A 的 agent
写死 Python >=3.13,<3.14，用宿主 3.12 建的隔离 venv 起来即退；MaaYYs 的 Go agent.exe
启动时从 <项目>/maafw 加载 MaaFramework，找不到直接 fatal。项目自带的 DLL 可能是
自定义构建、site-packages 里可能有 requirements.txt 没写的东西，"按版本从运行池
重建一份等价环境"这条路验证不完。带走之后 runner 与 agent 用的就是发行包里的那份，
与路径模式完全一致；运行池只在项目本来就没自带时兜底——也与路径模式一致。分类表只在两处起作用：白名单目标
内部（比如 agent 目录里的 ``__pycache__``），以及保守模式下的整棵根。

三条与旧 Project Store 投影不同的取舍：

- **不改写 interface JSON。** 文件逐字节照抄，差量包里的哈希才对得上；assets 布局
  里声明路径逃出 ``assets/`` 的直接拒绝，不做路径重写。
- **不带 ABI / requirements 闸门。** 缺自带 Python 由 ``agent_env/planner.py`` 落到
  隔离 venv，这里只把"自带解释器被投影掉了"记进警告。
- **差量包用叠加视图算白名单。** 包里有 interface 就用包里的，没有就用项目现有的；
  引用的文件先在包里找、再在项目里找；不查存在性——新版本新增的目录在包里就是新的。
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import json5

from .blob_store import LINK_MIN_BYTES, RuntimeBlobStore, place_fresh

MAX_REPORT_ITEMS = 128

# 白名单之外的顶层条目：剩余部分不超过这个大小就留下（数据文件级别），再大就是外壳运行时。
UNDECLARED_KEEP_LIMIT = 64 * 1024 * 1024
# 根目录上没声明的这些后缀只可能是外壳或外壳的运行时（m9a.exe、MaaEnd.exe、qt6core.dll…）。
UNDECLARED_BINARY_SUFFIXES = {
    ".exe",
    ".dll",
    ".pyd",
    ".so",
    ".dylib",
    ".pdb",
    ".node",
    ".lib",
}
# 目录里有这些就是 .NET 外壳的托管库目录，不看大小直接不要。
DOTNET_SHELL_FILE_PREFIXES = (
    "avalonia",
    "mfaavalonia",
    "microsoft.extensions.",
    "system.",
)

EXCLUDED_DIRECTORY_REASONS: dict[str, str] = {
    ".git": "source-control",
    ".github": "source-control",
    ".idea": "editor-state",
    ".vscode": "editor-state",
    "ui": "ui-shell",
    "gui": "ui-shell",
    "frontend": "ui-shell",
    "web": "ui-shell",
    "webui": "ui-shell",
    "electron": "ui-shell",
    "mfaavalonia": "ui-shell",
    "mxu": "ui-shell",
    "mfw": "ui-shell",
    "maapicli": "ui-shell",
    "node_modules": "ui-runtime",
    "pyside6": "ui-runtime",
    "pyside2": "ui-runtime",
    "pyqt6": "ui-runtime",
    "pyqt5": "ui-runtime",
    "shiboken6": "ui-runtime",
    "shiboken2": "ui-runtime",
    # 发行包自带的原生库目录：副本里由运行池按投影标记的版本提供，整目录不进。
    "maafw": "embedded-runtime",
    "runtime": "embedded-runtime",
    "runtimes": "embedded-runtime",
    "python": "embedded-python",
    "python-runtime": "embedded-python",
    "python_runtime": "embedded-python",
    "python-embed": "embedded-python",
    "python_embed": "embedded-python",
    ".venv": "embedded-python",
    "venv": "embedded-python",
    "__pycache__": "cache",
    ".cache": "cache",
    "cache": "cache",
    "debug": "cache",
    "logs": "cache",
    "log": "cache",
    ".pytest_cache": "cache",
    ".mypy_cache": "cache",
    ".ruff_cache": "cache",
    ".tox": "cache",
    ".nox": "cache",
    ".mas-update": "updater-shell",
    ".mas-update-cache": "updater-shell",
    "update": "updater-shell",
    "updates": "updater-shell",
    "updater": "updater-shell",
    "temp": "temporary",
    "tmp": "temporary",
    ".tmp": "temporary",
    "backup": "temporary",
    "backups": "temporary",
    "build": "build-output",
    "dist": "build-output",
}
EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp", ".log"}
KNOWN_RUNTIME_FILE_NAMES = {
    "maaframework.dll",
    "maaframework.so",
    "maaframework.dylib",
    "maapicli",
    "maapicli.exe",
    "maatoolkit.dll",
    "python.exe",
    "pythonw.exe",
}
KNOWN_RUNTIME_STEMS = {"maaframework", "maatoolkit", "maaadbcontrolunit", "maahttp"}
# 按内容共用（硬链接）的判定：≥ 64 KB 且不在排除表。不再按后缀白名单——被白名单挡掉的
# 恰是 MaaEnd 的导航网格 .gz、agent .exe、大 JSON / 图片（第二份副本多占 139 MB）。
# 实测五个项目运行期对出厂文件的原地覆盖只有 config/ 下的几百字节小文件，agent 热更新
# 一律「临时文件 + os.replace」（换目录项、不写穿 inode）。可写的东西靠四层挡住：尺寸
# （< 64 KB 永远私有）、下面这张排除表、运行期新建即新 inode、事后写穿巡检学到的
# ``privatePaths``。
SHARED_EXCLUDED_ROOT_DIRS = frozenset(
    {
        "config",
        "debug",
        "logs",
        "temp",
        "cache",
        ".pycache",
        ".mas-update",
        ".mas-update-cache",
    }
)
SHARED_EXCLUDED_SUFFIXES = frozenset({".lock", ".sha256", ".pth", ".log", ".tmp"})


def is_shared_path(
    relative: str | Path, size: int, private_paths: Iterable[str] = ()
) -> bool:
    """这个项目相对路径的文件能否按内容与其它副本 / 载荷共用（硬链接）。

    ``relative`` 相对项目根（投影后的坐标系）；``private_paths`` 是谱系学到的
    「会被原地写」的路径（posix，大小写不敏感）。
    """

    if size < LINK_MIN_BYTES:
        return False
    parts = PurePosixPath(Path(relative).as_posix()).parts
    if not parts:
        return False
    if parts[0].casefold() in SHARED_EXCLUDED_ROOT_DIRS:
        return False
    if PurePosixPath(parts[-1]).suffix.casefold() in SHARED_EXCLUDED_SUFFIXES:
        return False
    if any(part.casefold().endswith(".dist-info") for part in parts[:-1]):
        return False
    folded = "/".join(parts).casefold()
    return not any(
        folded == str(item).replace("\\", "/").strip("/").casefold()
        for item in private_paths
    )


KNOWN_UI_SHELL_STEMS = {"mfaavalonia", "mxu", "mfw", "maapicli"}
SHELL_SUFFIXES = {".bat", ".cmd", ".exe", ".ps1", ".sh"}
DEPENDENCY_DIR_NAMES = {"agent", "agents", "lock", "locks", "plugins", "requirements"}
DEPENDENCY_FILE_PATTERNS = (
    "requirements*.txt",
    "constraints*.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "environment.yml",
    "environment.yaml",
    "conda-lock.yml",
    "conda-lock.yaml",
    "*.lock",
)
PYTHON_INTERPRETER_NAMES = {
    "python",
    "python.exe",
    "python3",
    "python3.exe",
    "pythonw",
    "pythonw.exe",
    "py",
    "py.exe",
}
# 与 ``detect_maafw_project_shell_hint`` 同一套家族名，报告里直接回填。
SHELL_FAMILY_NAMES = {
    "mfaavalonia": "MFAAvalonia",
    "mxu": "MXU",
    "cfa": "CFA",
    "mfw": "MFW",
    "maapicli": "MaaPiCli",
}
SHELL_REASONS = {
    "ui-shell",
    "ui-runtime",
    "embedded-runtime",
    "embedded-python",
    "updater-shell",
}

ROOT = Path(".")


class ProjectionError(RuntimeError):
    """投影无法进行：发行包不合规，或声明的路径不存在。原因原样给用户看。"""


@dataclass(frozen=True)
class TargetMode:
    """一个白名单目标的口径。

    ``complete``：整棵子树都要（resource 目录）；否则只是"保留根"，里面按分类表剔除。
    ``allow_excluded_root``：目标本身的名字可以撞上分类表（resource 目录真有叫
    ``runtime`` 的），只豁免这个前缀，里面照常剔除。
    """

    complete: bool
    allow_excluded_root: bool
    # 项目自带的运行时目录（原生库 / 解释器）原样带走：分类表在里面不起作用，
    # 只剔 ``__pycache__``。
    verbatim_runtime: bool = False


@dataclass(frozen=True)
class RequiredPath:
    path: Path
    label: str
    is_directory: bool
    python_interpreter: bool = False
    missing: bool = False


@dataclass
class ProjectionRules:
    """白名单目标 + 分类表 = "某个相对路径要不要"。

    ``source_root`` 是用户指向的目录，``interface_base`` 是 interface.json 所在目录
    （release 布局二者相同，assets 布局后者是 ``source_root/assets``）。输出路径一律
    相对 ``interface_base``，这就是 assets 布局的"提升"。
    """

    source_root: Path
    interface_base: Path
    targets: dict[Path, TargetMode]
    required: list[RequiredPath]
    agents: list[dict[str, Any]]
    conservative: bool
    warnings: list[str] = field(default_factory=list)
    # 导入时声明了但发行包里没有的 resource（名字）：副本里不可用，其余照常导入。
    unavailable_resources: list[str] = field(default_factory=list)

    @property
    def base_relative(self) -> Path:
        relative = self.interface_base.relative_to(self.source_root)
        return relative if relative.parts else ROOT

    def output_path(self, relative: Path) -> Path:
        """源相对路径 → 副本相对路径。assets 布局把 ``assets/x`` 提升为 ``x``。"""

        base = self.base_relative
        if base == ROOT:
            return relative
        try:
            promoted = relative.relative_to(base)
        except ValueError as exc:
            raise ProjectionError(
                f"路径逃出 interface 所在目录，无法提升：{relative.as_posix()}"
            ) from exc
        return promoted if promoted.parts else ROOT

    def is_shared_file(
        self, relative: Path, size: int, private_paths: Iterable[str] = ()
    ) -> bool:
        """这个文件可以按内容与其它副本共用（硬链接），谓词见 :func:`is_shared_path`。

        ``relative`` 是投影后的（项目根相对）路径；与白名单目标无关——导入、更新落地、
        视图物化共用同一个谓词。
        """

        return is_shared_path(relative, size, private_paths)

    def keeps(self, relative: Path, *, is_directory: bool = False) -> bool:
        """这个源相对路径要不要进副本。"""

        for target, mode in self.targets.items():
            if not _is_relative_to(relative, target):
                continue
            target_is_directory = target == ROOT or (relative != target or is_directory)
            if (
                target_exclusion_reason(
                    relative,
                    target=target,
                    mode=mode,
                    target_is_directory=target_is_directory,
                    is_directory=is_directory,
                )
                is None
            ):
                return True
        return False


@dataclass
class ProjectionPlan:
    rules: ProjectionRules
    copied_files: set[Path]
    copied_directories: set[Path]
    excluded_reasons: dict[str, str]
    source_tree_bytes: int
    projected_bytes: int
    # 给界面看的信息：来源自带 MaaFramework 的实测版本（PEP 440）与 agent 自带解释器的
    # 大版本（如 "3.13"）。两者都随目录原样进副本，运行时读的是目录里的东西，不是这里。
    bundled_maafw_version: str | None = None
    bundled_python_version: str | None = None

    def report(self) -> dict[str, Any]:
        """给界面看的精简报告。数字在这里算好，前端不重算。"""

        saved = max(0, self.source_tree_bytes - self.projected_bytes)
        percent = (
            round(saved * 100 / self.source_tree_bytes, 2)
            if self.source_tree_bytes
            else 0.0
        )
        families: set[str] = set()
        reason_counts: dict[str, int] = {}
        for path, reason in self.excluded_reasons.items():
            if reason in SHELL_REASONS:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                for part in Path(path).parts:
                    family = SHELL_FAMILY_NAMES.get(part.casefold().split(".", 1)[0])
                    if family:
                        families.add(family)
        excluded_items = sorted(self.excluded_reasons.items())
        return {
            "sourceSizeBytes": self.source_tree_bytes,
            "payloadSizeBytes": self.projected_bytes,
            "savedBytes": saved,
            "savedPercent": percent,
            "copiedFileCount": len(self.copied_files),
            "excludedCount": len(self.excluded_reasons),
            "excludedReasons": dict(excluded_items[:MAX_REPORT_ITEMS]),
            "excludedTruncated": len(excluded_items) > MAX_REPORT_ITEMS,
            "shellFamilies": sorted(families),
            "shellReasonCounts": dict(sorted(reason_counts.items())),
            "conservative": self.rules.conservative,
            "interfaceBase": self.rules.base_relative.as_posix(),
            "agents": [dict(agent) for agent in self.rules.agents],
            "warnings": list(self.rules.warnings),
            "unavailableResources": list(self.rules.unavailable_resources),
            "bundledMaaFWVersion": self.bundled_maafw_version or "",
            "bundledPythonVersion": self.bundled_python_version or "",
        }


# --------------------------------------------------------------------------
# 分类表
# --------------------------------------------------------------------------


def exclusion_reason(path: Path, *, is_directory: bool = False) -> str | None:
    """按分类表判断一个相对路径为什么不该进副本；None 表示没有理由。"""

    parts = path.parts if is_directory else path.parts[:-1]
    for part in parts:
        normalized = part.casefold()
        reason = EXCLUDED_DIRECTORY_REASONS.get(normalized)
        if reason:
            return reason
        family = normalized.split(".", 1)[0]
        if family in KNOWN_UI_SHELL_STEMS:
            return "ui-shell"
        if family in KNOWN_RUNTIME_STEMS:
            return "embedded-runtime"
    if is_directory:
        return None
    name = path.name.casefold()
    suffix = path.suffix.casefold()
    family = name.split(".", 1)[0]
    if family in KNOWN_UI_SHELL_STEMS:
        return "ui-shell"
    if family in KNOWN_RUNTIME_STEMS:
        return "embedded-runtime"
    if suffix in EXCLUDED_FILE_SUFFIXES:
        return "cache-or-temporary"
    if name in KNOWN_RUNTIME_FILE_NAMES or (
        name.startswith("python") and suffix in {".dll", ".exe", ".so", ".dylib"}
    ):
        return "embedded-runtime"
    stem = path.stem.casefold()
    if suffix in SHELL_SUFFIXES and (
        "update" in stem
        or "updater" in stem
        or stem.endswith(("gui", "ui", "launcher"))
    ):
        return "ui-or-updater-shell"
    return None


def target_exclusion_reason(
    path: Path,
    *,
    target: Path,
    mode: TargetMode,
    target_is_directory: bool,
    is_directory: bool = False,
) -> str | None:
    """在某个白名单目标之下判断 ``path``。

    显式声明的完整目标（resource 目录）可以叫 ``runtime`` / ``python`` 这种在发行包
    顶层视为外壳的名字——声明比猜测更可信，只豁免目标前缀本身，里面照常剔除。
    """

    if not mode.complete or not mode.allow_excluded_root or target == ROOT:
        return exclusion_reason(path, is_directory=is_directory)
    inner = path.relative_to(target) if target_is_directory else Path(path.name)
    if mode.verbatim_runtime:
        # 原样带走的运行时目录：CPython 发行版里本来就有 build / debug / logs 这些
        # 名字（pip/_internal/operations/build 少了 pip 就起不来），无源码的 .pyc
        # 模块也得留着；只有 __pycache__ 是能重建的缓存。
        parts = inner.parts if is_directory else inner.parts[:-1]
        if any(part.casefold() == "__pycache__" for part in parts):
            return "cache"
        return None
    return exclusion_reason(inner, is_directory=is_directory)


# --------------------------------------------------------------------------
# 文件视图：单目录（导入）或叠加（差量包在前、项目在后）
# --------------------------------------------------------------------------


class _FileView:
    def __init__(self, roots: tuple[Path, ...]) -> None:
        self.roots = roots

    def locate(self, relative: Path) -> Path | None:
        for root in self.roots:
            candidate = root / relative
            if candidate.exists():
                return candidate
        return None

    def exists(self, relative: Path) -> bool:
        return self.locate(relative) is not None

    def is_file(self, relative: Path) -> bool:
        located = self.locate(relative)
        return located is not None and located.is_file()

    def read_text(self, relative: Path) -> str:
        located = self.locate(relative)
        if located is None or not located.is_file():
            raise OSError(f"not a file: {relative.as_posix()}")
        return located.read_text(encoding="utf-8-sig")

    def is_dir(self, relative: Path) -> bool:
        located = self.locate(relative)
        return located is not None and located.is_dir()

    def read_json(self, relative: Path, label: str) -> dict[str, Any]:
        located = self.locate(relative)
        if located is None or not located.is_file():
            raise ProjectionError(f"{label} 不存在：{relative.as_posix()}")
        return read_json_object(located, label)

    def size(self, relative: Path) -> int:
        located = self.locate(relative)
        try:
            return located.stat().st_size if located is not None else 0
        except OSError:
            return 0

    def walk_files(self, relative: Path) -> list[Path]:
        """叠加视图里某目录下的全部文件（相对根路径），同名以靠前的根为准。"""

        seen: dict[str, Path] = {}
        for root in self.roots:
            directory = root / relative
            if not directory.is_dir():
                continue
            for path in directory.rglob("*"):
                if path.is_file():
                    rel = relative / path.relative_to(directory)
                    seen.setdefault(rel.as_posix(), rel)
        return list(seen.values())

    def iter_entries(self, relative: Path) -> list[Path]:
        """列出叠加视图里某目录下的直接条目（相对根路径），不重复。"""

        seen: dict[str, Path] = {}
        for root in self.roots:
            directory = root / relative
            if not directory.is_dir():
                continue
            for entry in directory.iterdir():
                seen.setdefault(entry.name, relative / entry.name)
        return list(seen.values())


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    """interface 文件：先 json，失败再退 json5——带注释的 JSONC 也能读。"""

    text = path.read_text(encoding="utf-8-sig")
    try:
        payload = json.loads(text)
    except ValueError:
        try:
            payload = json5.loads(text)
        except Exception as exc:  # noqa: BLE001 - 解析器异常类型不统一
            raise ProjectionError(f"{label} 不是合法 JSON：{path}（{exc}）") from exc
    if not isinstance(payload, dict):
        raise ProjectionError(f"{label} 顶层必须是 JSON object：{path}")
    return payload


# --------------------------------------------------------------------------
# interface 发现与路径解析
# --------------------------------------------------------------------------


def discover_project_interface(source_root: Path) -> tuple[Path, Path]:
    """返回 ``(interface_base, interface_path)``；先看根，再看 ``assets/``。"""

    root = source_root.resolve()
    for base, name in (
        (root, "interface.json"),
        (root, "interface.jsonc"),
        (root / "assets", "interface.json"),
        (root / "assets", "interface.jsonc"),
    ):
        candidate = base / name
        if candidate.is_file():
            return base, candidate
    raise ProjectionError("目录里没有 interface.json（根目录或 assets/ 下都没有）")


def _normalize_declared_path(raw: str, base_relative: Path, label: str) -> Path:
    """把 interface 里写的路径归一成相对 ``source_root`` 的纯路径，不许逃出去。"""

    value = str(raw).strip().strip('"').strip("'").replace("\\", "/")
    value = value.replace("${PROJECT_DIR}", "{PROJECT_DIR}")
    if value.startswith("{PROJECT_DIR}"):
        value = value[len("{PROJECT_DIR}") :].lstrip("/")
    pure = PurePosixPath(value or ".")
    if pure.is_absolute() or (len(value) > 1 and value[1] == ":"):
        raise ProjectionError(f"{label} 必须是项目内的相对路径：{raw}")
    parts: list[str] = list(base_relative.parts)
    for part in pure.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ProjectionError(f"{label} 逃出了项目目录：{raw}")
            parts.pop()
            continue
        parts.append(part)
    return Path(*parts) if parts else ROOT


def collect_ui_asset_paths(data: Any) -> list[str]:
    """interface 里所有层级的 ``icon`` 字符串，加上顶层 ``welcome``。"""

    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "icon" and isinstance(value, str) and value.strip():
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    if isinstance(data, dict):
        found.extend(_welcome_entries(data.get("welcome")))
    return found


#: 协议里「支持文件路径、URL 或直接文本」的说明类字段：description 在各层级都有，
#: contact / license 只在顶层。
_DOCUMENT_KEYS = frozenset({"description"})
_ROOT_DOCUMENT_KEYS = ("contact", "license")
# 说明文字往往就是一段正文；只有像文件路径的值（单行、不太长、带扩展名）才去查盘，
# 免得把一整段文字拼成超长路径去 stat。
_DOCUMENT_PATH_RE = re.compile(r"^[^\r\n<>|\"*?]{1,200}\.[A-Za-z0-9]{1,8}$")


def collect_document_paths(data: Any) -> list[str]:
    """interface 里 description（各层级）与顶层 contact / license 中像文件路径的值。

    「关于」页、任务说明会按项目根去读这些文件；以前只靠「顶层小目录一并带走」捡到，
    放进大目录里的就丢了。是不是真文件由调用方查。
    """

    found: list[str] = []

    def add(value: Any) -> None:
        for item in value if isinstance(value, list) else [value]:
            text = _text(item)
            if text and _DOCUMENT_PATH_RE.match(text):
                found.append(text)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _DOCUMENT_KEYS:
                    add(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    if isinstance(data, dict):
        for key in _ROOT_DOCUMENT_KEYS:
            add(data.get(key))
    return found


def _welcome_entries(value: Any) -> list[str]:
    """顶层 ``welcome`` 的各条内容：单个字符串（旧写法）或字符串数组（PI v2.10.2）。"""

    items = value if isinstance(value, list) else [value]
    return [text for text in (_text(item) for item in items) if text]


# welcome（README）里以 Markdown / HTML 写法引用的本地图片。只认这两种写法，
# 只取相对路径；远程 URL、data: URI 由 _normalize_ui_asset_path 过滤。
_WELCOME_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))(?:\s+\"[^\"]*\")?\s*\)"
    r"|<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


def collect_welcome_image_paths(text: str) -> list[str]:
    """welcome 文件正文里引用的图片路径，按出现顺序去重。"""

    found: list[str] = []
    for match in _WELCOME_IMAGE_RE.finditer(text):
        raw = next((group for group in match.groups() if group), "").strip()
        if raw and raw not in found:
            found.append(raw)
    return found


def _normalize_ui_asset_path(raw: str, base_relative: Path) -> Path | None:
    """界面素材路径：允许 ``/assets/logo.png`` 这种以 / 开头的项目根相对写法；
    远程 URL、data: URI、逃出项目的一律当没有。"""

    value = str(raw).strip().replace("\\", "/")
    if not value or value.startswith(("http://", "https://", "data:")):
        return None
    if len(value) > 1 and value[1] == ":":
        return None
    try:
        return _normalize_declared_path(value.lstrip("/"), base_relative, "icon")
    except ProjectionError:
        return None


#: 一眼就是脚本 / 可执行文件的后缀：agent 参数里带这种后缀的路径几乎肯定是入口文件，
#: 找不到就该让导入失败；其余带斜杠的参数（``cmd /c``、``--opt=a/b``）只能当自由文本。
_SCRIPT_SUFFIXES = frozenset(
    {".py", ".pyw", ".js", ".mjs", ".cjs", ".exe", ".cmd", ".bat", ".ps1", ".sh"}
)


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'")


def looks_like_script_file(value: str) -> bool:
    """参数是不是一个脚本 / 可执行文件路径（按后缀判断）。"""

    return Path(_strip_quotes(value)).suffix.casefold() in _SCRIPT_SUFFIXES


def looks_like_local_path(value: str) -> bool:
    normalized = _strip_quotes(value)
    if not normalized or normalized.startswith(("-", "http://", "https://")):
        return False
    if normalized.startswith(
        ("{PROJECT_DIR}", "${PROJECT_DIR}", "./", "../", ".\\", "..\\")
    ):
        return True
    if "/" in normalized or "\\" in normalized:
        return True
    return Path(normalized).suffix.casefold() in _SCRIPT_SUFFIXES


def is_python_interpreter_path(path: Path) -> bool:
    return path.name.casefold() in PYTHON_INTERPRETER_NAMES


def classify_agent(
    declared_type: str, child_exec: str, child_args: list[str]
) -> tuple[str, bool]:
    """返回 ``(classification, opaque)``。opaque 为真时投影退回保守模式。"""

    kind = declared_type.casefold()
    executable = Path(child_exec.replace("\\", "/")).name.casefold()
    suffixes = {Path(item.replace("\\", "/")).suffix.casefold() for item in child_args}
    if kind in {"custom", "command", "shell", "opaque"}:
        return kind or "opaque", True
    if (
        is_python_interpreter_path(Path(executable))
        or ".py" in suffixes
        or ".pyw" in suffixes
    ):
        return "python", False
    if executable in {"node", "node.exe", "deno", "deno.exe", "bun", "bun.exe"} or (
        ".js" in suffixes or ".mjs" in suffixes
    ):
        return "javascript", False
    if executable in {
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "sh",
        "bash",
    }:
        return "command", True
    if child_exec and (
        "/" in child_exec or "\\" in child_exec or Path(child_exec).suffix
    ):
        return "native", False
    if child_exec:
        return "external", True
    return "opaque", True


def _retention_root(relative: Path, view: _FileView) -> Path:
    """agent / pretask 引用的文件所在目录整个保留（按分类表剔除）。"""

    if view.is_dir(relative):
        return relative
    parent = relative.parent
    return parent if parent != ROOT else relative


#: 分类表里按「内嵌解释器」处理的目录名（python / venv / .venv / python-embed …）。
EMBEDDED_PYTHON_DIR_NAMES = frozenset(
    name
    for name, reason in EXCLUDED_DIRECTORY_REASONS.items()
    if reason == "embedded-python"
)


def _is_python_interpreter_dir(view: _FileView, relative: Path) -> bool:
    """目录里真有一个 Python 解释器（发行版 / 嵌入式包 / venv），而不只是叫这个名字。

    特征：根上的 ``python.exe`` / ``pythonw.exe`` / ``python`` / ``python3`` /
    ``pyvenv.cfg`` / ``python3.dll`` / ``python3XY.dll``，或 venv 布局的
    ``Scripts/python.exe``、``bin/python``。只放 ``.py`` 源码的 ``python/``（MaaFramework
    官方 Demo 的 agent 就在 ``python/demo3_agent.py``）不是解释器。
    """

    if not view.is_dir(relative):
        return False
    for name in (
        "python.exe",
        "pythonw.exe",
        "python",
        "python3",
        "pyvenv.cfg",
        "python3.dll",
        "Scripts/python.exe",
        "bin/python",
        "bin/python3",
    ):
        if view.is_file(relative / name):
            return True
    return any(
        _PYTHON_DLL_RE.match(entry.name) and view.is_file(entry)
        for entry in view.iter_entries(relative)
    )


def _python_named_source_prefix(view: _FileView, relative: Path) -> Path | None:
    """``relative``（目录）路径上名字像内嵌解释器、其实只是源码目录的最外层前缀。

    分类表只看名字，会把 ``python/demo3_agent.py`` 所在的整个 ``python/`` 当解释器
    剔掉，声明的 agent 入口就成了「运行必需却被投影排除」。返回 None 表示路径上没有
    这种段（或那一段真是解释器目录，照旧按解释器处理）。
    """

    prefix = ROOT
    for part in relative.parts:
        prefix = prefix / part
        if part.casefold() in EMBEDDED_PYTHON_DIR_NAMES:
            if _is_python_interpreter_dir(view, prefix):
                return None
            return prefix
    return None


# --------------------------------------------------------------------------
# 白名单目标收集
# --------------------------------------------------------------------------


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def build_projection_rules(
    source_root: Path,
    *,
    strict: bool = True,
    overlay_root: Path | None = None,
) -> ProjectionRules:
    """从 interface 声明算出白名单。

    ``strict``：导入时为真——声明的路径必须存在，缺了就是发行包不合规。差量落地时
    为假——新版本新增的目录本来就还不在项目里。
    ``overlay_root``：差量包的 payload 根，排在项目目录前面参与查找。
    """

    source_root = source_root.resolve()
    roots: tuple[Path, ...] = (
        (overlay_root.resolve(), source_root)
        if overlay_root is not None
        else (source_root,)
    )
    view = _FileView(roots)
    # interface 在哪一层？叠加视图里以包内的为准，包里没有再看项目。
    interface_base: Path | None = None
    interface_relative: Path | None = None
    for root in roots:
        try:
            base, path = discover_project_interface(root)
        except ProjectionError:
            continue
        interface_base = base.relative_to(root)
        interface_relative = path.relative_to(root)
        break
    if interface_base is None or interface_relative is None:
        raise ProjectionError("目录里没有 interface.json（根目录或 assets/ 下都没有）")
    base_relative = interface_base if interface_base.parts else ROOT

    targets: dict[Path, TargetMode] = {}
    required: list[RequiredPath] = []
    warnings: list[str] = []
    agents: list[dict[str, Any]] = []
    unavailable_resources: list[str] = []
    opaque_found = False

    def add_target(
        relative: Path,
        *,
        complete: bool,
        required_label: str | None,
        allow_excluded_root: bool = False,
        required_path: Path | None = None,
        python_interpreter: bool = False,
        verbatim_runtime: bool = False,
    ) -> None:
        exists = view.exists(relative)
        if not exists:
            if python_interpreter:
                # 自带解释器不在了（本来就没发，或已被上一次投影去掉）：planner 会
                # 落到隔离 venv，这不是错误，记一笔就行。
                required.append(
                    RequiredPath(
                        path=required_path or relative,
                        label=required_label or "agent interpreter",
                        is_directory=False,
                        python_interpreter=True,
                        missing=True,
                    )
                )
                return
            if required_label and strict:
                raise ProjectionError(
                    f"{required_label} 声明的路径不存在：{relative.as_posix()}"
                )
            if required_label:
                warnings.append(
                    f"{required_label} 声明的路径当前不存在：{relative.as_posix()}"
                )
            else:
                warnings.append(f"可选路径不存在，未保留：{relative.as_posix()}")
            if not strict:
                # 差量落地：目标还没到，但白名单要先立起来，包里带来的文件才能进。
                previous = targets.get(relative, TargetMode(False, False))
                targets[relative] = TargetMode(
                    previous.complete or complete,
                    previous.allow_excluded_root or allow_excluded_root,
                    previous.verbatim_runtime or verbatim_runtime,
                )
            return
        previous = targets.get(relative, TargetMode(False, False))
        targets[relative] = TargetMode(
            previous.complete or complete,
            previous.allow_excluded_root or allow_excluded_root,
            previous.verbatim_runtime or verbatim_runtime,
        )
        if required_label:
            exact = required_path or relative
            required.append(
                RequiredPath(
                    path=exact,
                    label=required_label,
                    is_directory=view.is_dir(exact),
                    python_interpreter=python_interpreter,
                )
            )

    def declare(raw: str, label: str, *, must_exist: bool) -> Path | None:
        relative = _normalize_declared_path(raw, base_relative, label)
        if must_exist and strict and not view.exists(relative):
            raise ProjectionError(f"{label} 声明的路径不存在：{raw}")
        return relative

    def declare_executable(raw: str, label: str) -> Path:
        relative = _normalize_declared_path(raw, base_relative, label)
        if view.exists(relative):
            return relative
        if not relative.suffix:
            with_exe = relative.with_name(relative.name + ".exe")
            if view.is_file(with_exe):
                return with_exe
        return relative

    def add_retention_target(
        referenced: Path, *, required_label: str | None, required_path: Path
    ) -> None:
        """agent / pretask 引用的文件：所在目录整个保留（按分类表剔除）。

        所在目录（或它的上级）叫 ``python`` 这类名字、其实只是源码目录时，声明比猜测
        更可信：把它当显式目标、豁免名字本身（与 resource 目录叫 ``runtime`` 同一口径），
        里面照常按分类表剔除。
        """

        retention = _retention_root(referenced, view)
        directory = retention if view.is_dir(retention) else retention.parent
        python_source = _python_named_source_prefix(view, directory) is not None
        add_target(
            retention,
            complete=python_source,
            required_label=required_label,
            required_path=required_path,
            allow_excluded_root=python_source,
        )

    visited: set[Path] = set()

    def visit_interface(relative: Path, scope: str) -> None:
        nonlocal opaque_found
        if relative in visited:
            return
        visited.add(relative)
        data = view.read_json(relative, "ProjectInterface")
        add_target(relative, complete=True, required_label="ProjectInterface")

        raw_imports = data.get("import")
        if raw_imports is not None:
            if not isinstance(raw_imports, list) or not all(
                isinstance(item, str) and item.strip() for item in raw_imports
            ):
                raise ProjectionError("ProjectInterface 的 import 必须是字符串数组")
            for raw_import in raw_imports:
                imported = declare(
                    raw_import, "ProjectInterface import", must_exist=False
                )
                if imported is None:
                    continue
                if strict and not view.is_file(imported):
                    # 发行包漏打包了 import 文件（MPA v3.10.46、MSBA v3.7.41）：与加载器
                    # 同一口径，跳过这一个文件继续导入，其中声明的任务 / 选项不可用。
                    warnings.append(
                        f"ProjectInterface import 声明的文件不存在：{raw_import}；"
                        "发行包漏打包了这个文件，其中声明的任务与选项在副本里不可用，"
                        "其余照常导入"
                    )
                    continue
                if view.is_file(imported):
                    visit_interface(imported, imported.as_posix())
                else:
                    add_target(
                        imported,
                        complete=True,
                        required_label="ProjectInterface import",
                    )

        for index, resource in enumerate(_as_list(data.get("resource"))):
            if not isinstance(resource, dict):
                continue
            name = _text(resource.get("name")) or f"resource[{index}]"
            raw_paths = resource.get("path")
            values = (
                [raw_paths] if isinstance(raw_paths, str) else list(raw_paths or [])
            )
            for raw_path in values:
                if not isinstance(raw_path, str):
                    raise ProjectionError(f"resource {name} 的 path 必须是字符串")
                relative_path = declare(raw_path, f"resource {name}", must_exist=False)
                if strict and not view.exists(relative_path):
                    # 发行包声明了却没打进包的资源（MaaDuDuL v1.1.7 的 resource/zh_hant）：
                    # 只是这一个资源用不了，不该让整个项目导入不了。选中它运行时由
                    # runner 的「资源目录不存在」报清楚。
                    if name not in unavailable_resources:
                        unavailable_resources.append(name)
                    warnings.append(
                        f"resource {name} 声明的路径不存在：{raw_path}；"
                        "该资源在副本里不可用（选中它运行会报资源目录不存在），其余照常导入"
                    )
                    continue
                if relative_path is not None:
                    add_target(
                        relative_path,
                        complete=True,
                        required_label=f"resource {name}",
                        allow_excluded_root=True,
                    )

        for index, controller in enumerate(_as_list(data.get("controller"))):
            if not isinstance(controller, dict):
                continue
            key = (
                "attach_resource_path"
                if "attach_resource_path" in controller
                else "attachResourcePath"
            )
            raw_value = controller.get(key)
            if raw_value is None:
                continue
            values = (
                [raw_value] if isinstance(raw_value, str) else list(raw_value or [])
            )
            for raw_path in values:
                if not isinstance(raw_path, str):
                    raise ProjectionError(
                        f"controller[{index}].{key} 必须是字符串或字符串数组"
                    )
                relative_path = declare(
                    raw_path, f"controller[{index}].{key}", must_exist=True
                )
                if relative_path is not None:
                    add_target(
                        relative_path,
                        complete=True,
                        required_label=f"controller[{index}].{key}",
                        allow_excluded_root=True,
                    )

        # 界面素材：只在文件确实在时保留，缺了不记警告——发行包里 icon 指向不存在
        # 的文件很常见，那是上游的事，不该把投影报告刷满。
        for raw_asset in collect_ui_asset_paths(data):
            asset_relative = _normalize_ui_asset_path(raw_asset, base_relative)
            if asset_relative is not None and view.is_file(asset_relative):
                add_target(asset_relative, complete=True, required_label=None)

        # description / contact / license 写成文件路径时（docs/about.md），同样只在文件
        # 确实在时显式带上。
        for raw_document in collect_document_paths(data):
            document_relative = _normalize_ui_asset_path(raw_document, base_relative)
            if document_relative is not None and view.is_file(document_relative):
                add_target(document_relative, complete=True, required_label=None)

        # welcome 正文里引用的图片：说明页会按项目根去取，缺了就是一排裂图。先按
        # welcome 文件所在目录解析（Markdown 的习惯），再退到项目根；都不在就算了。
        # 数组写法（PI v2.10.2）逐条处理。
        for welcome_raw in _welcome_entries(data.get("welcome")):
            welcome_relative = _normalize_ui_asset_path(welcome_raw, base_relative)
            if welcome_relative is None or not view.is_file(welcome_relative):
                continue
            try:
                welcome_text = view.read_text(welcome_relative)
            except (OSError, UnicodeDecodeError):
                welcome_text = ""
            for raw_image in collect_welcome_image_paths(welcome_text):
                for anchor in (welcome_relative.parent, base_relative):
                    image_relative = _normalize_ui_asset_path(raw_image, anchor)
                    if image_relative is not None and view.is_file(image_relative):
                        add_target(image_relative, complete=True, required_label=None)
                        break

        languages = data.get("languages")
        if isinstance(languages, dict):
            for language, raw_path in languages.items():
                if not isinstance(raw_path, str):
                    raise ProjectionError(f"languages.{language} 必须是字符串路径")
                relative_path = declare(
                    raw_path, f"languages.{language}", must_exist=True
                )
                if relative_path is not None:
                    add_target(
                        relative_path,
                        complete=True,
                        required_label=f"languages.{language}",
                    )

        for index, agent in enumerate(_as_list(data.get("agent"))):
            if not isinstance(agent, dict):
                continue
            child_exec = _text(agent.get("child_exec")) or _text(agent.get("childExec"))
            raw_args = agent.get("child_args")
            if raw_args is None:
                raw_args = agent.get("childArgs")
            child_args = (
                [item for item in raw_args if isinstance(item, str)]
                if isinstance(raw_args, list)
                else []
            )
            declared_type = _text(agent.get("type")) or _text(agent.get("kind"))
            classification, opaque = classify_agent(
                declared_type, child_exec, child_args
            )
            opaque_found = opaque_found or opaque
            discovered: list[str] = []
            if child_exec and looks_like_local_path(child_exec):
                label = f"agent[{index}].child_exec"
                exec_relative = declare_executable(child_exec, label)
                interpreter = classification == "python" and is_python_interpreter_path(
                    exec_relative
                )
                if view.exists(exec_relative):
                    discovered.append(exec_relative.as_posix())
                    # 自带解释器所在目录原样带走：里面的 site-packages 就是这个项目
                    # 实际跑起来的环境，运行池重建的不等价（版本、自定义构建、
                    # requirements 没写的包）。其它 agent 文件所在目录只是保留根。
                    if interpreter:
                        add_target(
                            _retention_root(exec_relative, view),
                            complete=True,
                            required_label=label,
                            required_path=exec_relative,
                            allow_excluded_root=True,
                            python_interpreter=True,
                            verbatim_runtime=True,
                        )
                    else:
                        add_retention_target(
                            exec_relative,
                            required_label=label,
                            required_path=exec_relative,
                        )
                    _add_root_python_siblings(
                        exec_relative, view, targets, base_relative
                    )
                elif interpreter:
                    add_target(
                        exec_relative,
                        complete=False,
                        required_label=label,
                        python_interpreter=True,
                    )
                elif strict:
                    raise ProjectionError(f"{label} 声明的路径不存在：{child_exec}")
                else:
                    warnings.append(f"{label} 声明的路径当前不存在：{child_exec}")
            for arg_index, raw_arg in enumerate(child_args):
                if not looks_like_local_path(raw_arg):
                    continue
                label = f"agent[{index}].child_args[{arg_index}]"
                if looks_like_script_file(raw_arg):
                    # 脚本 / 可执行文件路径就是 agent 的入口，缺了必然跑不起来：照旧严格。
                    arg_relative = declare(raw_arg, label, must_exist=True)
                    if arg_relative is None:
                        continue
                else:
                    # 其余带斜杠的参数是自由文本：``cmd /c``、``--opt=a/b``、URL 片段都会被
                    # looks_like_local_path 当成路径。归一不了（绝对路径、逃出项目根）只能
                    # 说明它不是要带走的项目文件，不能让导入失败。
                    try:
                        arg_relative = _normalize_declared_path(
                            raw_arg, base_relative, label
                        )
                    except ProjectionError:
                        warnings.append(
                            f"{label} 像路径但不在项目内，按普通参数原样保留：{raw_arg}"
                        )
                        continue
                if view.exists(arg_relative):
                    discovered.append(arg_relative.as_posix())
                    add_retention_target(
                        arg_relative,
                        required_label=label,
                        required_path=arg_relative,
                    )
                    _add_root_python_siblings(
                        arg_relative, view, targets, base_relative
                    )
                else:
                    warnings.append(f"{label} 声明的路径当前不存在：{raw_arg}")
            agents.append(
                {
                    "index": index,
                    "scope": scope,
                    "declaredType": declared_type or None,
                    "childExec": child_exec or None,
                    "classification": classification,
                    "opaque": opaque,
                    "projectPaths": discovered,
                }
            )

        for index, pretask in enumerate(_as_list(data.get("pretask"))):
            if not isinstance(pretask, dict):
                continue
            raw_exec = pretask.get("exec")
            if not isinstance(raw_exec, str) or not looks_like_local_path(raw_exec):
                continue
            label = f"pretask[{index}].exec"
            exec_relative = declare_executable(raw_exec, label)
            if view.exists(exec_relative):
                add_retention_target(
                    exec_relative,
                    required_label=label,
                    required_path=exec_relative,
                )
            elif strict:
                raise ProjectionError(f"{label} 声明的路径不存在：{raw_exec}")
            else:
                warnings.append(f"{label} 声明的路径当前不存在：{raw_exec}")

        # pretask 参数里引用的项目文件（"exec": "python", "args": ["./scripts/p.py"]）：
        # 所在目录整个保留。参数也可能只是自由文本，找不到只记警告，不让导入失败。
        for index, pretask in enumerate(_as_list(data.get("pretask"))):
            if not isinstance(pretask, dict):
                continue
            raw_args = pretask.get("args")
            if not isinstance(raw_args, list):
                continue
            for arg_index, raw_arg in enumerate(raw_args):
                if not isinstance(raw_arg, str) or not looks_like_local_path(raw_arg):
                    continue
                label = f"pretask[{index}].args[{arg_index}]"
                try:
                    arg_relative = _normalize_declared_path(
                        raw_arg, base_relative, label
                    )
                except ProjectionError:
                    warnings.append(
                        f"{label} 像路径但不在项目内，按普通参数原样保留：{raw_arg}"
                    )
                    continue
                if arg_relative in (ROOT, base_relative):
                    # "{PROJECT_DIR}" 本身：不是要带走的某个文件，整棵根不能因此进白名单。
                    continue
                if view.exists(arg_relative):
                    # 不记进「运行必需」：参数是给 pretask 程序的自由文本，被分类表剔掉
                    # （例如放在 build/ 下）也只是回到以前的行为，不该让导入失败。
                    add_retention_target(
                        arg_relative,
                        required_label=None,
                        required_path=arg_relative,
                    )
                else:
                    warnings.append(f"{label} 声明的路径当前不存在：{raw_arg}")

    visit_interface(interface_relative, interface_relative.as_posix())

    # 依赖清单：根目录与 interface 所在目录都看一眼。
    for base in {ROOT, base_relative}:
        for entry in view.iter_entries(base):
            name = entry.name
            if name.casefold() in DEPENDENCY_DIR_NAMES and view.is_dir(entry):
                add_target(entry, complete=False, required_label=None)
            elif view.is_file(entry) and any(
                fnmatch.fnmatchcase(name, pattern)
                for pattern in DEPENDENCY_FILE_PATTERNS
            ):
                add_target(entry, complete=False, required_label=None)

    # 项目自带的 MaaFramework 原生库目录原样带走：runner 优先加载它（与路径模式一致），
    # 非 Python 的 agent 更是启动时就从 <项目>/maafw 加载。
    runtime_relative = _bundled_native_runtime_dir(roots, base_relative)
    for candidate in {runtime_relative, base_relative / "maafw"}:
        if candidate is None or not view.is_dir(candidate):
            continue
        if candidate in (ROOT, base_relative):
            # 原生库直接放在包根目录（MRA / MaaTOT / MALW 的 PiCLI 包、MAAAE、MAG、MAH、
            # MMleo、MaaEOV）：根目录不能当成原样带走的运行时目录——以前那样做，根目录
            # 退回分类表，恰好剔掉 MaaFramework / MaaToolkit / MaaAdbControlUnit、留下其余
            # 原生库（运行时退到运行池的库、与自带版本混载），整个根目录还失去了 64 MB
            # 限制（MAAAE 带走 134 MB 的外壳 libs/）。改为只把根上的原生库文件逐个原样带走。
            for native_file in _root_native_runtime_files(view, candidate):
                add_target(
                    native_file,
                    complete=True,
                    required_label="bundled native runtime",
                    allow_excluded_root=True,
                    verbatim_runtime=True,
                )
            continue
        add_target(
            candidate,
            complete=True,
            required_label="bundled native runtime",
            allow_excluded_root=True,
            verbatim_runtime=True,
        )
    if (
        runtime_relative is None
        and strict
        and any(agent.get("classification") != "python" for agent in agents)
    ):
        warnings.append(
            "agent 不是 Python，但项目里没有自带的 MaaFramework 原生库目录；"
            "agent 若要从项目目录加载库，运行时会失败。"
        )

    _adopt_small_undeclared_entries(view, base_relative, targets, warnings)

    conservative = opaque_found
    if conservative:
        targets[ROOT] = TargetMode(complete=False, allow_excluded_root=False)
        warnings.append(
            "agent 是 custom / command / 不透明形态，投影退回保守模式：保留整棵目录，只去掉分类表命中的外壳与缓存。"
        )

    # 声明路径逃出 interface 所在目录的，assets 布局提升后会指向不存在的位置。
    if base_relative != ROOT:
        for target in targets:
            if target != ROOT and not _is_relative_to(target, base_relative):
                raise ProjectionError(
                    f"interface 在 {base_relative.as_posix()}/ 下，但声明的路径 "
                    f"{target.as_posix()} 在它之外；这种布局无法提升为内嵌副本"
                )

    rules = ProjectionRules(
        source_root=source_root,
        interface_base=source_root / base_relative,
        targets=targets,
        required=required,
        agents=agents,
        conservative=conservative,
        warnings=warnings,
        unavailable_resources=unavailable_resources,
    )
    return rules


def _add_root_python_siblings(
    relative: Path,
    view: _FileView,
    targets: dict[Path, TargetMode],
    base_relative: Path,
) -> None:
    """根目录直接放 ``main.py`` 的项目，把同级 ``*.py`` 与惯例目录一并保留。"""

    if relative.parent != base_relative and relative.parent != ROOT:
        return
    if relative.suffix.casefold() not in {".py", ".pyw"}:
        return
    for entry in view.iter_entries(relative.parent):
        if view.is_file(entry) and entry.suffix.casefold() in {".py", ".pyw"}:
            targets.setdefault(entry, TargetMode(False, False))
    for folder_name in ("src", "lib", "modules", relative.stem):
        folder = relative.parent / folder_name
        if view.is_dir(folder):
            targets.setdefault(folder, TargetMode(False, False))


# --------------------------------------------------------------------------
# 完整投影（导入）与复制
# --------------------------------------------------------------------------


def _scan_tree(root: Path) -> tuple[set[Path], set[Path], dict[Path, int]]:
    directories: set[Path] = {ROOT}
    files: set[Path] = set()
    sizes: dict[Path, int] = {}
    for current_raw, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        current = Path(current_raw)
        if current.is_symlink() or current.is_junction():
            raise ProjectionError(f"目录里有符号链接，拒绝投影：{current}")
        for directory_name in list(directory_names):
            directory = current / directory_name
            # Windows 的 junction 不算 symlink，os.walk(followlinks=False) 照样走进去，
            # 指回上级的 junction 会无限嵌套；一并拒绝。
            if directory.is_symlink() or directory.is_junction():
                raise ProjectionError(f"目录里有符号链接，拒绝投影：{directory}")
            directories.add(directory.relative_to(root))
        for file_name in file_names:
            file_path = current / file_name
            if file_path.is_symlink():
                raise ProjectionError(f"目录里有符号链接，拒绝投影：{file_path}")
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(root)
            files.add(relative)
            sizes[relative] = file_path.stat().st_size
    return directories, files, sizes


def _relative_parents(path: Path) -> set[Path]:
    parents: set[Path] = set()
    current = path.parent
    while current != ROOT:
        parents.add(current)
        current = current.parent
    parents.add(ROOT)
    return parents


def _is_relative_to(path: Path, parent: Path) -> bool:
    if parent == ROOT:
        return True
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def build_projection_plan(source_root: Path) -> ProjectionPlan:
    """导入用：算白名单、扫整棵树、决定每个文件去留。"""

    rules = build_projection_rules(source_root, strict=True)
    root = rules.source_root
    all_directories, all_files, sizes = _scan_tree(root)

    copied_files: set[Path] = set()
    copied_directories: set[Path] = {ROOT}
    for target, mode in rules.targets.items():
        target_absolute = root / target
        if target_absolute.is_file():
            if (
                target_exclusion_reason(
                    target, target=target, mode=mode, target_is_directory=False
                )
                is None
            ):
                copied_files.add(target)
                copied_directories.update(_relative_parents(target))
            continue
        for directory in all_directories:
            if not _is_relative_to(directory, target):
                continue
            if (
                target_exclusion_reason(
                    directory,
                    target=target,
                    mode=mode,
                    target_is_directory=True,
                    is_directory=True,
                )
                is None
            ):
                copied_directories.add(directory)
                copied_directories.update(_relative_parents(directory))
        for file_path in all_files:
            if not _is_relative_to(file_path, target):
                continue
            if (
                target_exclusion_reason(
                    file_path, target=target, mode=mode, target_is_directory=True
                )
                is None
            ):
                copied_files.add(file_path)
                copied_directories.update(_relative_parents(file_path))

    # 声明为必需的路径必须真的留下来；唯一的例外是被投影掉的自带 Python 解释器。
    for requirement in rules.required:
        retained = (
            requirement.path in copied_directories
            if requirement.is_directory
            else requirement.path in copied_files
        )
        if retained:
            continue
        if requirement.python_interpreter:
            rules.warnings.append(
                f"{requirement.label} 的自带 Python 解释器"
                f"{'不存在' if requirement.missing else '已被投影去掉'}"
                f"（{requirement.path.as_posix()}），运行时将使用该项目的隔离 venv。"
            )
            continue
        reason = exclusion_reason(
            requirement.path, is_directory=requirement.is_directory
        )
        raise ProjectionError(
            f"{requirement.label} 是运行必需的，却被投影排除了："
            f"{requirement.path.as_posix()}（{reason or 'not-retained'}）"
        )

    excluded_reasons = {
        path.as_posix(): (
            exclusion_reason(path) or "not-required-by-runtime-projection"
        )
        for path in all_files - copied_files
    }

    # 提升后的输出路径不能撞车（assets/x 与根上的 x 同名）。
    owners: dict[Path, Path] = {}
    for source_relative in copied_files:
        output = rules.output_path(source_relative)
        owner = owners.setdefault(output, source_relative)
        if owner != source_relative:
            raise ProjectionError(
                f"提升 assets/ 后路径撞车：{owner.as_posix()} 与 {source_relative.as_posix()}"
            )

    return ProjectionPlan(
        rules=rules,
        copied_files=copied_files,
        copied_directories=copied_directories,
        excluded_reasons=excluded_reasons,
        source_tree_bytes=sum(sizes.values()),
        projected_bytes=sum(sizes[path] for path in copied_files),
        bundled_maafw_version=probe_bundled_maafw_version(root),
        bundled_python_version=probe_bundled_python_version(root, rules),
    )


_PYTHON_DLL_RE = re.compile(r"^python3(\d{1,2})\.dll$", re.IGNORECASE)


def _looks_like_dotnet_shell_dir(view: _FileView, directory: Path) -> bool:
    for entry in view.iter_entries(directory):
        name = entry.name.casefold()
        if name.endswith(".dll") and name.startswith(DOTNET_SHELL_FILE_PREFIXES):
            return True
    return False


def _looks_like_frozen_python_package_dir(view: _FileView, directory: Path) -> bool:
    """冻结的 Python 程序散在根目录的二进制依赖包：``numpy.libs``、``*.dist-info``，
    或者目录里带 ``.pyd``。纯 Python 的包（有 ``__init__.py``）不算——冻结程序把
    源码都收进了自己的归档，根上还剩纯 Python 包的只能是项目自己的东西。"""

    name = directory.name.casefold()
    if name.endswith((".libs", ".dist-info")):
        return True
    return any(path.suffix.casefold() == ".pyd" for path in view.walk_files(directory))


def _adopt_small_undeclared_entries(
    view: _FileView,
    base_relative: Path,
    targets: dict[Path, TargetMode],
    warnings: list[str],
) -> None:
    """白名单之外的顶层条目：剩余部分 ≤ 64 MB 的以"保留根"口径带走，更大的丢。

    "剩余部分"只算还没被任何目标覆盖、也没被分类表命中的文件——``resource_pack`` 里
    声明过的子目录不重复算。根目录上没声明的可执行文件与库一律不要；外壳是冻结的
    Python 程序时（根上直接放着没人声明的 ``python3xx.dll``），它散在根目录的二进制
    依赖包也不要——agent 的 ``PYTHONPATH`` 是项目根，半截包会盖住真正的模块。
    """

    def covered(relative: Path) -> bool:
        return any(
            mode.complete and _is_relative_to(relative, target)
            for target, mode in targets.items()
            if target != ROOT
        )

    entries = sorted(view.iter_entries(base_relative))
    frozen_shell = any(
        view.is_file(entry) and _PYTHON_DLL_RE.match(entry.name) and not covered(entry)
        for entry in entries
    )
    frozen_packages: list[str] = []
    for entry in entries:
        if entry in targets and targets[entry].complete:
            continue
        is_dir = view.is_dir(entry)
        reason = exclusion_reason(entry, is_directory=is_dir)
        if (
            reason == "embedded-python"
            and is_dir
            and not _is_python_interpreter_dir(view, entry)
        ):
            # 叫 python / venv 却没有解释器的目录只是项目源码（agent 会 import 的
            # 辅助脚本），按名字当解释器丢掉就和路径模式不一样了。名字本身豁免，
            # 里面照常按分类表剔除。
            remainder = sum(
                view.size(path)
                for path in view.walk_files(entry)
                if exclusion_reason(path.relative_to(entry)) is None
            )
            if remainder <= UNDECLARED_KEEP_LIMIT:
                targets[entry] = TargetMode(True, True)
            continue
        if reason is not None:
            continue
        if not is_dir:
            if entry.suffix.casefold() in UNDECLARED_BINARY_SUFFIXES:
                continue
            if view.size(entry) <= UNDECLARED_KEEP_LIMIT:
                targets.setdefault(entry, TargetMode(False, False))
            continue
        if _looks_like_dotnet_shell_dir(view, entry):
            continue
        if frozen_shell and _looks_like_frozen_python_package_dir(view, entry):
            frozen_packages.append(entry.name)
            continue
        remainder = sum(
            view.size(path)
            for path in view.walk_files(entry)
            if not covered(path) and exclusion_reason(path) is None
        )
        if remainder > UNDECLARED_KEEP_LIMIT:
            if entry in targets:
                warnings.append(
                    f"目录 {entry.as_posix()}/ 里没被 interface 引用的部分有 "
                    f"{remainder / 2**20:.0f} MB，只带入被引用的文件"
                )
            else:
                warnings.append(
                    f"未声明的目录 {entry.as_posix()}/ 有 {remainder / 2**20:.0f} MB，"
                    "按外壳运行时处理，未带入副本"
                )
            continue
        previous = targets.get(entry, TargetMode(False, False))
        targets[entry] = TargetMode(
            False, previous.allow_excluded_root, previous.verbatim_runtime
        )
    if frozen_packages:
        warnings.append(
            "根目录上的 "
            + "、".join(frozen_packages)
            + " 是冻结 Python 外壳自带的依赖包，未带入副本"
        )


#: MaaFramework 发行的原生库里不以 Maa 开头的那几个（MaaFramework 自己的 bin 目录、PyPI
#: maafw 包的 maa/bin 里都是这一套）：OCR / 推理 / 图像库带 ``_maa`` 后缀，另有
#: DirectML 与手柄控制器用的 ViGEmClient。
_MAAFW_RUNTIME_EXTRA_STEMS = frozenset({"directml", "vigemclient"})
_NATIVE_LIBRARY_SUFFIXES = frozenset({".dll", ".so", ".dylib"})


def _is_maafw_runtime_library(name: str) -> bool:
    """文件名是不是 MaaFramework 运行时的原生库（而不是外壳 / 界面的）。

    认的是 MaaFramework 自己发布的那套：``Maa*``（MaaFramework、MaaToolkit、MaaUtils、
    MaaAgentClient / Server、各 ``Maa*ControlUnit``；Linux / macOS 带 ``lib`` 前缀）、
    ``*_maa``（opencv_world4_maa、onnxruntime_maa、fastdeploy_ppocr_maa）、DirectML、
    ViGEmClient。外壳放在根上的 MaaPiCli.exe、MFAAvalonia.dll、libSkiaSharp.dll、
    Node 绑定 MaaNode.node 都不算。
    """

    path = PurePosixPath(name.casefold())
    if path.suffix not in _NATIVE_LIBRARY_SUFFIXES:
        return False
    stem = path.name.split(".", 1)[0]
    stem = stem.removeprefix("lib") if path.suffix != ".dll" else stem
    if stem.startswith("maa") and stem != "maapicli":
        return True
    return stem.endswith("_maa") or stem in _MAAFW_RUNTIME_EXTRA_STEMS


def _root_native_runtime_files(view: _FileView, directory: Path) -> list[Path]:
    """``project_maafw_runtime_path`` 认定的运行时目录是包根时，其中的 MaaFramework 原生库文件。"""

    return sorted(
        entry
        for entry in view.iter_entries(directory)
        if view.is_file(entry) and _is_maafw_runtime_library(entry.name)
    )


def _bundled_native_runtime_dir(
    roots: tuple[Path, ...], base_relative: Path
) -> Path | None:
    """项目自带 MaaFramework 原生库所在目录（相对 ``source_root``）；没有就 None。

    查找逻辑与 runner 同一套（``project_maafw_runtime_path``：先 ``maafw/``，再
    ``runtimes/<rid>/native``，再有界搜索），叠加视图里先看包、再看项目。MFAAvalonia
    布局下找到的是 ``runtimes/win-x64/native``，那里除了 MaaFramework 还有外壳自己的
    原生库；整目录带走，几十 MB，换来的是 runner 用的就是发行包里那份库。
    """

    from app.task.MaaFW.tools.core.runner.environment import (
        project_maafw_runtime_path,
    )

    for root in roots:
        base = root / base_relative if base_relative.parts else root
        found = project_maafw_runtime_path(base)
        if found is None:
            continue
        try:
            return found.resolve().relative_to(root.resolve())
        except ValueError:
            continue
    return None


def probe_bundled_python_version(root: Path, rules: ProjectionRules) -> str | None:
    """agent 自带解释器的大版本（如 ``3.13``）。

    只看解释器目录里 ``python3XY.dll`` 的文件名，不执行任何东西；没有自带解释器
    （裸写 python、或解释器已被上一次投影去掉）返回 None。
    """

    for agent in rules.agents:
        if agent.get("classification") != "python":
            continue
        for raw in agent.get("projectPaths") or []:
            relative = Path(str(raw))
            if not is_python_interpreter_path(relative):
                continue
            try:
                names = os.listdir(root / relative.parent)
            except OSError:
                continue
            for name in names:
                match = _PYTHON_DLL_RE.match(name)
                if match:
                    return f"3.{int(match.group(1))}"
    return None


def probe_bundled_maafw_version(root: Path) -> str | None:
    """来源（或更新包）自带 MaaFramework 原生库的版本；探测逻辑与 runner 共用。"""

    from app.task.MaaFW.tools.core.runner.environment import (
        probe_bundled_maafw_version as _probe,
    )

    return _probe(root)


def materialize_projection(
    plan: ProjectionPlan,
    target_dir: Path,
    *,
    progress: Callable[[int, int], None] | None = None,
    blob_store: RuntimeBlobStore | None = None,
    private_paths: Iterable[str] = (),
) -> dict[str, int]:
    """把 plan 里要留的文件复制到 ``target_dir``（assets 布局在这里被提升）。

    给了 ``blob_store`` 时，满足共用谓词（:func:`is_shared_path`：≥ 64 KB 且不在排除表、
    不在谱系 ``private_paths`` 里）的文件按内容与其它副本共用（硬链接）。
    ``progress(done_bytes, total_bytes)`` 按已复制字节回调（按文件数算的话一个几百 MB
    的模型会让进度条先冲到 90% 再卡住）；每个文件复制完调一次，最后一次 done == total。
    返回共用统计：``sharedFiles`` / ``sharedBytes``。
    """

    target = target_dir.resolve()
    target.mkdir(parents=True, exist_ok=True)
    rules = plan.rules
    for relative_directory in sorted(
        plan.copied_directories, key=lambda path: (len(path.parts), path.as_posix())
    ):
        if relative_directory == ROOT:
            continue
        try:
            output_directory = rules.output_path(relative_directory)
        except ProjectionError:
            # 提升后的根之外的目录（例如 assets 布局里根上的 README 所在目录）不需要建。
            continue
        if output_directory == ROOT:
            continue
        (target / output_directory).mkdir(parents=True, exist_ok=True)

    ordered = sorted(plan.copied_files, key=lambda path: path.as_posix())
    total_bytes = max(plan.projected_bytes, 0)
    done_bytes = 0
    shared_files = 0
    shared_bytes = 0
    private = tuple(private_paths)
    for index, relative_file in enumerate(ordered, start=1):
        source = rules.source_root / relative_file
        output_relative = rules.output_path(relative_file)
        destination = target / output_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            size = source.stat().st_size
        except OSError:
            size = 0
        if blob_store is not None and rules.is_shared_file(
            output_relative, size, private
        ):
            placed = blob_store.place(source, destination)
            if placed.action == "linked":
                shared_files += 1
                shared_bytes += placed.size
        else:
            # 与载荷 / 视图同一口径：独占新建，绝不往已存在的目标里写。
            place_fresh(source, destination, link=False, make_parent=False)
        if progress is not None:
            # 计划里的字节数是建计划时统计的，复制期间文件可能变；最后一个文件一律报满
            done_bytes = (
                total_bytes
                if index == len(ordered)
                else min(done_bytes + size, total_bytes)
            )
            progress(done_bytes, total_bytes)
    return {"sharedFiles": shared_files, "sharedBytes": shared_bytes}


# --------------------------------------------------------------------------
# 更新落地：给 build_package_plan 用的过滤谓词
# --------------------------------------------------------------------------


def package_projection_rules(payload_root: Path, project_root: Path) -> ProjectionRules:
    """更新包落地时的白名单：包内 interface 优先，其次项目现有的；不查存在性。

    只支持 release 布局的包（interface.json 在包根）：内嵌副本本身就是提升后的
    release 布局，assets 布局的源码 zip 从来不是更新器的输入。
    """

    rules = build_projection_rules(
        project_root, strict=False, overlay_root=payload_root
    )
    if rules.base_relative != ROOT:
        raise ProjectionError(
            "更新包的 interface.json 不在包根（assets 布局），内嵌副本不接受这种更新包"
        )
    return rules


def filter_package_entries(
    rules: ProjectionRules,
    entries: Iterable[str],
) -> tuple[set[str], dict[str, str]]:
    """把包内相对路径分成「要落盘」与「不要（附原因）」两组。"""

    kept: set[str] = set()
    dropped: dict[str, str] = {}
    for entry in entries:
        # 包内条目与白名单目标同一坐标系：都相对根。
        relative = Path(entry)
        if rules.keeps(relative):
            kept.add(entry)
        else:
            dropped[entry] = (
                exclusion_reason(relative) or "not-required-by-runtime-projection"
            )
    return kept, dropped


__all__ = [
    "EXCLUDED_DIRECTORY_REASONS",
    "MAX_REPORT_ITEMS",
    "SHARED_EXCLUDED_ROOT_DIRS",
    "SHARED_EXCLUDED_SUFFIXES",
    "ProjectionError",
    "ProjectionPlan",
    "ProjectionRules",
    "RequiredPath",
    "TargetMode",
    "build_projection_plan",
    "build_projection_rules",
    "classify_agent",
    "discover_project_interface",
    "exclusion_reason",
    "filter_package_entries",
    "is_python_interpreter_path",
    "is_shared_path",
    "looks_like_local_path",
    "materialize_projection",
    "package_projection_rules",
    "read_json_object",
    "target_exclusion_reason",
]
