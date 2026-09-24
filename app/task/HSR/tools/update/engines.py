"""M7A 与 SRA 的更新契约描述。

两个引擎的版本探测方式、发行资产命名和可用下载源都不一样，差异全部收敛在
这里，其余更新模块只依赖 :class:`EngineSpec`。

契约由 ``scripts/hsr_update_contract_check.py`` 实测核对过：Mirror 酱两个 rid
都是单平台（带 ``os``/``arch`` 一律 404），M7A 的 ``update.7z`` 是单根
``update/`` 且不含任何用户状态，SRA 发行包是扁平布局。改这里之前先把那份脚本
跑一遍。
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

HSREngine = Literal["M7A", "SRA"]

# 下载源标识。与 ``HSRConfig`` 的 ``Update.M7ASource`` / ``Update.SRASource``
# 选项字符串一一对应，顺序即 OptionsValidator 的选项顺序（首项是回退值）。
SourceId = Literal["AutoSite", "GitHub", "MirrorChyan"]

_STATION_BASE = "https://download.auto-mas.top/d"

# ``SRA-cli.exe --version`` 输出裸版本号（实测 0.09 秒返回、rc=0、不触发 UAC），
# 但也可能带上程序名前缀，取最后一个像版本号的 token。
_VERSION_TOKEN = re.compile(r"\d+(?:\.\d+)+(?:[-.][0-9A-Za-z.]+)?")


@dataclass(frozen=True)
class EngineSpec:
    """一个外部引擎的更新契约。"""

    engine: HSREngine
    display_name: str
    mirrorchyan_rid: str
    github_repo: str
    executable: str
    #: 该引擎允许的下载源，首项即 OptionsValidator 的默认/回退值。
    sources: tuple[SourceId, ...]
    #: GitHub 资产名匹配。M7A 的资产名不带版本号，SRA 的带，故用模板函数。
    _asset_patterns: tuple[tuple[str, str], ...]

    def station_url(self, tag: str) -> str | None:
        """自建站直链。只有 SRA 上了站。"""

        if "AutoSite" not in self.sources:
            return None
        return (
            f"{_STATION_BASE}/{self.mirrorchyan_rid}/{self.mirrorchyan_rid}-{tag}.zip"
        )

    def asset_patterns(self, tag: str) -> tuple[tuple[str, str], ...]:
        """返回 ``(kind, 资产名)`` 候选，按优先级排列。

        ``kind`` 供上层判断是否需要 7z 解包；真正的取舍在
        :func:`select_asset_name`，这里只做模板展开。
        """

        return tuple(
            (kind, name.format(tag=tag)) for kind, name in self._asset_patterns
        )


M7A = EngineSpec(
    engine="M7A",
    display_name="三月七助手",
    mirrorchyan_rid="March7thAssistant",
    github_repo="moesnow/March7thAssistant",
    executable="March7th Assistant.exe",
    sources=("GitHub", "MirrorChyan"),
    # update.7z 约 170MB、解压 565MB；full.zip 约 750MB 但 stdlib 就能解。
    _asset_patterns=(
        ("7z", "update.7z"),
        ("zip", "March7thAssistant_full.zip"),
    ),
)

SRA = EngineSpec(
    engine="SRA",
    display_name="StarRailAssistant",
    mirrorchyan_rid="StarRailAssistant",
    github_repo="Shasnow/StarRailAssistant",
    executable="SRA-cli.exe",
    # 自建站免 CDK、不限流、字节与 GitHub 一致，故排首位作默认值。
    sources=("AutoSite", "GitHub", "MirrorChyan"),
    # 只取 Full：它是三个源唯一共有的变体，也是唯一不制造混合版本的选择。
    _asset_patterns=(("zip", "StarRailAssistant_{tag}.zip"),),
)

_SPECS: dict[str, EngineSpec] = {"M7A": M7A, "SRA": SRA}


def get_spec(engine: str) -> EngineSpec:
    spec = _SPECS.get(str(engine or "").strip().upper())
    if spec is None:
        raise ValueError(f"未知的 HSR 引擎：{engine!r}")
    return spec


def select_asset_name(
    spec: EngineSpec,
    tag: str,
    *,
    can_extract_7z: bool,
) -> tuple[str, str]:
    """挑选要下载的资产，返回 ``(kind, 资产名)``。

    M7A 优先 ``update.7z``（体积只有全量包的四分之一），但它需要 7z 解包器；
    没有解包器时退回 stdlib 能解的 ``full.zip``。SRA 只有一个候选。
    """

    candidates = spec.asset_patterns(tag)
    for kind, name in candidates:
        if kind == "7z" and not can_extract_7z:
            continue
        return kind, name
    # 全部候选都要 7z 而又没有解包器时，退到最后一个（必为 zip 形态）。
    return candidates[-1]


def read_installed_version(spec: EngineSpec, root: Path) -> str | None:
    """读取已安装版本，读不到返回 ``None``（当作未知，不阻止更新）。

    统一返回带 ``v`` 前缀的形式，与 Mirror 酱 / GitHub 的 tag 对齐。
    """

    if spec.engine == "M7A":
        raw = _read_m7a_version(root)
    else:
        raw = _probe_sra_version(root / spec.executable)
    if not raw:
        return None
    return raw if raw.startswith("v") else f"v{raw}"


def _read_m7a_version(root: Path) -> str | None:
    marker = root / "assets" / "config" / "version.txt"
    try:
        text = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    match = _VERSION_TOKEN.search(text)
    return match.group(0) if match else None


def _probe_sra_version(executable: Path) -> str | None:
    """跑 ``SRA-cli.exe --version``。

    argparse 的 ``action='version'`` 在 ``parse_known_args()`` 里就触发，早于
    SRA 自己的提权分支，因此不会弹 UAC——实测 0.09 秒返回。仍设超时兜底，
    免得异常构建把任务卡死。
    """

    if not executable.is_file():
        return None
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            # 实测 0.09 秒返回。给 10 秒是为了容忍首次运行时的杀毒扫描，再长就
            # 没意义了——读不到版本号只会让更新按「未知版本」处理，不是硬失败。
            timeout=10,
            cwd=str(executable.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    match = _VERSION_TOKEN.search(f"{completed.stdout}\n{completed.stderr}")
    return match.group(0) if match else None


def find_seven_zip(root: Path) -> Path | None:
    """M7A 安装目录自带的 7z 解包器（实测为 7-Zip 23.01）。

    只在 M7A 自己的目录里找：这是它官方更新器用的同一个二进制，我们不额外
    引入 ``py7zr`` 之类的依赖。找不到就让调用方退回 zip 资产。
    """

    candidate = root / "assets" / "binary" / "7za.exe"
    return candidate if candidate.is_file() else None


__all__ = [
    "M7A",
    "SRA",
    "EngineSpec",
    "HSREngine",
    "SourceId",
    "find_seven_zip",
    "get_spec",
    "read_installed_version",
    "select_asset_name",
]
