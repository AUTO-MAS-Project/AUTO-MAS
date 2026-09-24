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


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新日志与版本号的唯一入口。

日常开发不再改 `CHANGELOG.md`：每个 PR 在 `changelog.d/` 下放一个碎片文件，
文件名 `<PR 号或分支名>.<分类>.md`，内容是一句面向用户的话。发版时由 `release`
把全部碎片编译进 `CHANGELOG.md` 顶部的新版本段、推进版本号、删除碎片，并开出发版 PR。
`CHANGELOG.md` 顶部第一个 `## [vX.Y.Z]` 标题就是仓库当前的版本号，其余五处版本号与
`res/version.json` 全部由本脚本从它生成，不要手改：

- `res/version.json`   —— 整份生成（前端编译期注入、发布 CI 生成 Release 正文都读它）
- `frontend/package.json`
- `app/core/config.py`
- `pyproject.toml`     —— PEP 440 写法，如 5.5.0b3
- `uv.lock`            —— 其中 auto-mas 包自身的版本，同样是 PEP 440 写法

用法::

    python scripts/changelog.py add fix "修复了什么"      # 新建一个碎片（贡献者用）
    python scripts/changelog.py check                     # 校验格式、碎片、版本号（CI 用）
    python scripts/changelog.py release --kind beta       # 编译碎片、推进版本号（发版工作流用）
    python scripts/changelog.py release-note              # 渲染 Release 正文（构建工作流用）
    python scripts/changelog.py guard                     # 构建前守门：版本号已推进且碎片已清空
    python scripts/changelog.py sync                      # 从 CHANGELOG.md 同步到各处生成物
    python scripts/changelog.py current                   # 打印当前版本号

版本号只有 `vX.Y.Z` 与 `vX.Y.Z-beta.N` 两种形态：预发布号里的 X.Y.Z 就是它将成为的正式号，
转正与最后一个 beta 同号，正式版热修出 Z+1 的补丁版，N 只增不减。`release --kind` 按这套
规则从最新 tag 推出下一个版本号，不接受倒退。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/AUTO-MAS-Project/AUTO-MAS"
GITHUB_REPO = "AUTO-MAS-Project/AUTO-MAS"
# 未发布版本的对比链接指向开发分支
DEVELOPMENT_BRANCH = "dev"

CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
VERSION_JSON_PATH = REPO_ROOT / "res" / "version.json"
PACKAGE_JSON_PATH = REPO_ROOT / "frontend" / "package.json"
APP_CONFIG_PATH = REPO_ROOT / "app" / "core" / "config.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
UV_LOCK_PATH = REPO_ROOT / "uv.lock"
FRAGMENT_DIR = REPO_ROOT / "changelog.d"

UNRELEASED = "未发布"

# 分类的固定顺序。中间六类是 Keep a Changelog 的标准分类（用中文标题，因为条目本身是
# 中文、而且这些标题会直接显示在应用内的更新提示里）；首尾三类是本项目的扩展。
# 这不是白名单——表外的新分类照常保留，只是排在这些之后。
CATEGORY_ORDER = [
    "破坏性变更",  # 本项目扩展：需要用户动手确认的改动，置顶最醒目
    "本次亮点",  # 本项目扩展：这一版最值得看的三五条
    "新增",  # Added
    "变更",  # Changed
    "弃用",  # Deprecated
    "移除",  # Removed
    "修复",  # Fixed
    "安全",  # Security
    "开发流程",  # 本项目扩展：只影响贡献者、不影响用户的改动
]

# 碎片文件名后缀 -> 分类。贡献者只需要选后缀，不用记中文分类名。
FRAGMENT_TYPES = {
    "breaking": "破坏性变更",
    "feat": "新增",
    "change": "变更",
    "deprecate": "弃用",
    "remove": "移除",
    "fix": "修复",
    "security": "安全",
    "dev": "开发流程",
}
FRAGMENT_NAME = re.compile(
    r"^(?P<identifier>[A-Za-z0-9][A-Za-z0-9._-]*)\.(?P<type>"
    + "|".join(FRAGMENT_TYPES)
    + r")\.md$"
)
# 目录里允许存在、但不是碎片的文件
FRAGMENT_IGNORED = {"README.md", ".gitkeep"}
LOGIN = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
LOGIN_PATTERN = re.compile(rf"^{LOGIN}$")
FRAGMENT_AUTHOR = re.compile(rf"^author:\s*@?(?P<login>{LOGIN})\s*$")

# 改了这些路径的 PR 被视为用户可见，必须带碎片（除非打了 skip-changelog 标签）
USER_VISIBLE_PREFIXES = ("app/", "frontend/src/", "frontend/electron/", "main.py")
# 普通 PR 完全不许碰的文件：它们只由发版 PR 更新
PROTECTED_FILES = ("CHANGELOG.md", "res/version.json")

# 提交标题带这些前缀的直推提交，发版时不当作「漏了碎片」点名
NON_USER_FACING_PREFIXES = ("chore", "docs", "doc", "ci", "test", "style", "build")

VERSION_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")
PRE_RELEASE_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?$")
PRE_RELEASE_ABBR = {"alpha": "a", "beta": "b", "rc": "rc"}
PHASE_RANK = {"alpha": 0, "beta": 1, "rc": 2, None: 3}

RELEASE_HEADING = re.compile(
    rf"^## \[(?P<version>[^\]]+)\] - (?P<date>{UNRELEASED}|\d{{4}}-\d{{2}}-\d{{2}})$"
)
# 底部的版本对比链接，由 render_changelog 重新生成，解析时跳过
LINK_DEFINITION = re.compile(r"^\[[^\]]+\]:\s+\S+$")
# 一个署名；碎片正文里出现它就是手写了署名
SIGNATURE = re.compile(r" by \[@(?P<login>[^\]]+)\]\((?P<url>[^)]*)\)")
# 条目末尾的整串署名：第一个必带 ` by `，后面的可以只用空格连着——旧机器人给多人条目
# 补署名时写的就是 ` by [@a](..) [@b](..)`，已发布段里有几十条，两种写法都要认
SIGNATURE_TAIL = re.compile(
    r" by \[@[^\]]+\]\([^)]*\)(?:(?: by)? \[@[^\]]+\]\([^)]*\))*$"
)
SIGNATURE_LOGIN = re.compile(r"\[@(?P<login>[^\]]+)\]\([^)]*\)")

# 发版日期按北京时间取，维护者与用户都在这个时区；不用 zoneinfo 是因为 Windows 上
# 没有 tzdata 包时它会直接抛错。
RELEASE_TIMEZONE = timezone(timedelta(hours=8))

CHANGELOG_PREAMBLE = """# 更新日志

本项目所有值得注意的变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/spec/v2.0.0.html)。

<!--
  本文件由 scripts/changelog.py 在发版时从 changelog.d/ 里的碎片编译生成，平时不要手改，
  也不要手改 res/version.json 等生成物。

  - 要登记一条更新日志，在 changelog.d/ 下新建一个碎片文件，见 changelog.d/README.md，
    或运行 `python scripts/changelog.py add <分类> "<一句话>"`。一条 PR 只放一个碎片。
  - 文件顶部第一个 `## [vX.Y.Z]` 标题就是仓库当前的版本号。发版 PR 由「准备发版」工作流
    创建，是唯一会改动本文件与各处版本号的地方。
  - 条目写成一行，从用户视角描述这次改动带来了什么；署名在发版时按碎片的提交作者自动补，
    不要手写。

  分类含义（中间六类来自 Keep a Changelog）：

  - 破坏性变更：需要用户动手确认或会改变既有行为的改动，在更新提示里最醒目地展示。
  - 本次亮点：这一版最值得一看的三五条，由维护者在发版 PR 里挑选。
  - 新增：新添加的功能。
  - 变更：对现有功能的变更，含优化与调整。
  - 弃用：已经不建议使用、即将移除的功能。
  - 移除：已经移除的功能。
  - 修复：对 bug 的修复。
  - 安全：对安全性的改进。
  - 开发流程：只影响贡献者、用户看不见的改动。
-->
"""


class ChangelogError(Exception):
    """CHANGELOG.md 或碎片不符合约定的格式。"""


Sections = Dict[str, Dict[str, List[str]]]
Dates = Dict[str, str]


def read_text(path: Path) -> str:
    """用 utf-8-sig 读，顺手吃掉记事本保存出来的 BOM，免得报成「无法识别的内容」。"""

    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    """始终以 LF 写出，避免 Windows 上写成 CRLF 与 .gitattributes 冲突。"""

    path.write_text(content, encoding="utf-8", newline="\n")


def parse_changelog(text: str) -> Tuple[str, Sections, Dates]:
    """把 CHANGELOG.md 解析成 (当前版本号, {版本: {分类: [条目]}}, {版本: 日期})。

    第一个 `## [...]` 之前的内容是文件头说明，整段由 render_changelog 重新生成，
    这里一律跳过，所以文件头里可以写任意散文与注释。
    """

    sections: Sections = {}
    dates: Dates = {}
    current_version: str | None = None
    current_category: str | None = None
    seen_release = False

    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip()
        stripped = line.strip()

        is_release_heading = stripped.startswith("## ")
        if not seen_release and not is_release_heading:
            continue

        if is_release_heading:
            seen_release = True
            matched = RELEASE_HEADING.match(stripped)
            if matched is None:
                raise ChangelogError(
                    f"第 {number} 行：版本标题必须形如 "
                    f"`## [v5.5.0-beta.3] - 2026-08-31` 或 `## [v5.5.0-beta.3] - {UNRELEASED}`，"
                    f"实际是 {stripped!r}"
                )
            version = matched.group("version")
            date = matched.group("date")
            if not VERSION_PATTERN.match(version):
                raise ChangelogError(
                    f"第 {number} 行：版本号必须形如 `v5.5.0-beta.3`，实际是 {version!r}"
                )
            if version in sections:
                raise ChangelogError(f"第 {number} 行：版本 {version} 重复出现")
            if date == UNRELEASED and sections:
                raise ChangelogError(
                    f"第 {number} 行：只有文件顶部的第一个版本可以标 {UNRELEASED}"
                )
            sections[version] = {}
            dates[version] = date
            current_version = version
            current_category = None
            continue

        if not stripped:
            continue

        # 底部的版本对比链接由 render 重新生成，解析时忽略
        if LINK_DEFINITION.match(stripped):
            continue

        if stripped.startswith("<!--") or stripped.startswith("# "):
            raise ChangelogError(
                f"第 {number} 行：版本段里不能写注释或一级标题，"
                "它们不会被保留，sync 会把它们删掉"
            )

        if stripped.startswith("### "):
            if current_version is None:
                raise ChangelogError(f"第 {number} 行：分类出现在任何版本标题之前")
            category = stripped[4:].strip()
            if not category:
                raise ChangelogError(f"第 {number} 行：分类名为空")
            if category in sections[current_version]:
                raise ChangelogError(
                    f"第 {number} 行：版本 {current_version} 下分类 {category} 重复出现"
                )
            sections[current_version][category] = []
            current_category = category
            continue

        if stripped.startswith("- "):
            if current_version is None or current_category is None:
                raise ChangelogError(f"第 {number} 行：条目不在任何分类下")
            if line != stripped:
                raise ChangelogError(
                    f"第 {number} 行：条目不能缩进，嵌套列表转不成 version.json"
                )
            entry = stripped[2:].strip()
            if not entry:
                raise ChangelogError(f"第 {number} 行：条目内容为空")
            items = sections[current_version][current_category]
            if entry in items:
                raise ChangelogError(
                    f"第 {number} 行：{current_version} / {current_category} 下条目重复：{entry[:40]}…"
                )
            items.append(entry)
            continue

        raise ChangelogError(
            f"第 {number} 行：无法识别的内容 {stripped[:60]!r}。"
            "条目必须写成单独一行、以 `- ` 开头。"
        )

    if not sections:
        raise ChangelogError("CHANGELOG.md 里没有任何 `## [vX.Y.Z] - 日期` 版本段")

    return next(iter(sections)), sections, dates


def order_categories(categories: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """已知分类按固定顺序排前面，未知分类保持原有相对顺序排在后面。"""

    known = [name for name in CATEGORY_ORDER if name in categories]
    unknown = [name for name in categories if name not in CATEGORY_ORDER]
    return {name: categories[name] for name in known + unknown}


def render_links(sections: Sections, dates: Dates) -> List[str]:
    """按 Keep a Changelog 的做法，在文件底部给每个版本生成对比链接。

    未发布版本对到开发分支；最老的那一版没有可比对象，指向它自己的 Release 页。
    """

    versions = list(sections)
    lines: List[str] = []
    for index, version in enumerate(versions):
        previous = versions[index + 1] if index + 1 < len(versions) else None
        if previous is None:
            target = f"{REPO_URL}/releases/tag/{version}"
        elif dates[version] == UNRELEASED:
            target = f"{REPO_URL}/compare/{previous}...{DEVELOPMENT_BRANCH}"
        else:
            target = f"{REPO_URL}/compare/{previous}...{version}"
        lines.append(f"[{version}]: {target}")
    return lines


def render_section(categories: Dict[str, List[str]]) -> List[str]:
    """渲染一个版本段的正文（不含版本标题），发版 PR 正文与 Release 正文复用。"""

    lines: List[str] = []
    for category, items in order_categories(categories).items():
        lines.append(f"### {category}")
        lines.append("")
        lines.extend(f"- {item}" for item in items)
        lines.append("")
    return lines


def render_changelog(sections: Sections, dates: Dates) -> str:
    lines = [CHANGELOG_PREAMBLE.rstrip("\n"), ""]
    for version, categories in sections.items():
        lines.append(f"## [{version}] - {dates[version]}")
        lines.append("")
        lines.extend(render_section(categories))
    lines.extend(render_links(sections, dates))
    return "\n".join(lines).rstrip("\n") + "\n"


def render_version_json(current_version: str, sections: Sections) -> str:
    """生成 res/version.json。

    只写版本与分类条目，不写日期——这份 JSON 的结构是已发布客户端解析更新提示的契约，
    发布 CI 会把它整个塞进 Release 正文首行的 HTML 注释里。
    """

    payload = {
        "version": current_version,
        "version_info": {
            version: order_categories(categories)
            for version, categories in sections.items()
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=4) + "\n"


# ---------------------------------------------------------------------------
# 版本号
# ---------------------------------------------------------------------------


def to_pep440(version: str) -> str:
    """v5.5.0-beta.3 -> 5.5.0b3；正式版 v5.4.0 -> 5.4.0。"""

    matched = PRE_RELEASE_PATTERN.match(version)
    if matched is None:
        raise ChangelogError(
            f"版本号 {version} 无法转换成 PEP 440 写法，"
            "只支持 vX.Y.Z 与 vX.Y.Z-(alpha|beta|rc).N"
        )
    major, minor, patch, phase, ordinal = matched.groups()
    base = f"{major}.{minor}.{patch}"
    if phase is None:
        return base
    return f"{base}{PRE_RELEASE_ABBR[phase]}{ordinal}"


def version_key(version: str) -> Optional[Tuple[int, int, int, int, int]]:
    """把 tag 变成可排序的元组；不是 vX.Y.Z[-phase.N] 形态的 tag 返回 None，调用方跳过。

    排序与 SemVer / PEP 440 一致：alpha < beta < rc < 正式版，同级按数值比。
    """

    matched = PRE_RELEASE_PATTERN.match(version)
    if matched is None:
        return None
    major, minor, patch, phase, ordinal = matched.groups()
    return (int(major), int(minor), int(patch), PHASE_RANK[phase], int(ordinal or 0))


def is_prerelease(version: str) -> bool:
    key = version_key(version)
    return key is not None and key[3] != PHASE_RANK[None]


def latest_version(versions: Iterable[str]) -> Optional[str]:
    """一组 tag 里最新的那个；不合形态的（如 v5.4.0-dev-xxx）忽略。"""

    parsed = [(version_key(v), v) for v in versions]
    valid = [(key, v) for key, v in parsed if key is not None]
    if not valid:
        return None
    return max(valid)[1]


def next_version(
    kind: str,
    latest: Optional[str],
    explicit: Optional[str] = None,
) -> str:
    """按发版类型从最新 tag 推出下一个版本号。

    - beta：最新是 beta 则 N+1；最新是正式版则下一个次版本的 beta.1。
    - stable：最新必须是 beta，转正同号。
    - patch：最新必须是正式版，Z+1。
    - explicit：用给定的版本号，但必须大于当前分支可达的最新 tag（在 release 线上打补丁时，
      dev 上更新的 tag 不算；与任何已有 tag 重号由 release 另行拒绝）。
    """

    if kind == "explicit":
        if not explicit:
            raise ChangelogError("--kind explicit 必须同时给 --version")
        if version_key(explicit) is None:
            raise ChangelogError(
                f"版本号 {explicit} 不合形态，应为 vX.Y.Z 或 vX.Y.Z-beta.N"
            )
        if latest is not None and version_key(explicit) <= version_key(latest):  # type: ignore[operator]
            raise ChangelogError(f"版本号 {explicit} 没有大于最新 tag {latest}")
        return explicit

    if latest is None:
        raise ChangelogError(
            "找不到任何形如 vX.Y.Z 的 tag，请用 --kind explicit 指定版本号"
        )

    major, minor, patch, phase_rank, ordinal = version_key(latest)  # type: ignore[misc]
    latest_is_final = phase_rank == PHASE_RANK[None]
    latest_is_beta = phase_rank == PHASE_RANK["beta"]

    if kind == "beta":
        if latest_is_beta:
            return f"v{major}.{minor}.{patch}-beta.{ordinal + 1}"
        if latest_is_final:
            return f"v{major}.{minor + 1}.0-beta.1"
        raise ChangelogError(
            f"最新 tag {latest} 既不是 beta 也不是正式版，请用 --kind explicit 指定版本号"
        )
    if kind == "stable":
        if latest_is_final:
            raise ChangelogError(
                f"最新 tag {latest} 已经是正式版；正式版的热修请用 --kind patch"
            )
        return f"v{major}.{minor}.{patch}"
    if kind == "patch":
        if not latest_is_final:
            raise ChangelogError(
                f"最新 tag {latest} 是预发布版，补丁版只能从正式版出；转正请用 --kind stable"
            )
        return f"v{major}.{minor}.{patch + 1}"
    raise ChangelogError(f"未知的发版类型 {kind}")


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------


def git(*args: str, root: Path = REPO_ROOT) -> str:
    """跑一条 git 命令并返回 stdout；失败抛 ChangelogError。"""

    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    except FileNotFoundError as error:
        raise ChangelogError("找不到 git 命令") from error
    except subprocess.CalledProcessError as error:
        raise ChangelogError(
            f"git {' '.join(args)} 失败：{error.stderr.strip() or error.stdout.strip()}"
        ) from error
    return completed.stdout


def git_available(root: Path = REPO_ROOT) -> bool:
    try:
        git("rev-parse", "--is-inside-work-tree", root=root)
    except ChangelogError:
        return False
    return True


def reachable_tags(ref: str = "HEAD", root: Path = REPO_ROOT) -> List[str]:
    """从 ref 可达的 v* tag。release 分支上只会看到自己这条线的 tag。"""

    output = git("tag", "--list", "v*", "--merged", ref, root=root)
    return [line.strip() for line in output.splitlines() if line.strip()]


def all_tags(root: Path = REPO_ROOT) -> List[str]:
    output = git("tag", "--list", "v*", root=root)
    return [line.strip() for line in output.splitlines() if line.strip()]


def changed_files(
    base: str, head: str = "HEAD", root: Path = REPO_ROOT
) -> List[Tuple[str, str]]:
    """base...head 之间的 (状态, 路径)。重命名按新路径记为 R。"""

    output = git("diff", "--name-status", "--no-renames", f"{base}...{head}", root=root)
    result: List[Tuple[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        result.append((status[:1], path.strip().replace("\\", "/")))
    return result


def show_file(ref: str, path: str, root: Path = REPO_ROOT) -> Optional[str]:
    try:
        return git("show", f"{ref}:{path}", root=root)
    except ChangelogError:
        return None


# ---------------------------------------------------------------------------
# 碎片
# ---------------------------------------------------------------------------


class Fragment:
    """一个碎片：文件、标识、分类、正文，以及可选的署名覆盖。"""

    __slots__ = ("path", "identifier", "category", "text", "author")

    def __init__(
        self,
        path: Path,
        identifier: str,
        category: str,
        text: str,
        author: Optional[str] = None,
    ) -> None:
        self.path = path
        self.identifier = identifier
        self.category = category
        self.text = text
        self.author = author


def parse_fragment(path: Path, content: str) -> Fragment:
    """碎片 = 文件名决定分类 + 正文一行。可选的首行 `author: 登录名` 覆盖自动署名。"""

    matched = FRAGMENT_NAME.match(path.name)
    if matched is None:
        raise ChangelogError(
            f"{path.name}：碎片文件名必须形如 `<PR 号或分支名>.<分类>.md`，"
            f"分类取 {'、'.join(FRAGMENT_TYPES)} 之一"
        )
    author: Optional[str] = None
    body: List[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        author_match = FRAGMENT_AUTHOR.match(stripped)
        if author_match and not body:
            if author is not None:
                raise ChangelogError(f"{path.name}：author 只能写一次")
            author = author_match.group("login")
            continue
        body.append(stripped)
    if not body:
        raise ChangelogError(f"{path.name}：碎片正文为空")
    if len(body) > 1:
        raise ChangelogError(
            f"{path.name}：碎片正文只能有一行，一条 PR 把全部改动概括成一句话"
        )
    text = body[0]
    if text.startswith("- "):
        text = text[2:].strip()
    if not text:
        raise ChangelogError(f"{path.name}：碎片正文为空")
    if SIGNATURE.search(text):
        raise ChangelogError(
            f"{path.name}：不要手写 ` by [@用户]` 署名，发版时会按提交作者自动补"
        )
    if text.startswith("#"):
        raise ChangelogError(f"{path.name}：碎片正文不能是标题，只写一句话")
    return Fragment(
        path=path,
        identifier=matched.group("identifier"),
        category=FRAGMENT_TYPES[matched.group("type")],
        text=text,
        author=author,
    )


def list_fragments(directory: Path = FRAGMENT_DIR) -> List[Fragment]:
    """读出目录里全部碎片；README 与 .gitkeep 以外的非碎片文件直接报错。"""

    if not directory.is_dir():
        return []
    fragments: List[Fragment] = []
    for path in sorted(directory.iterdir()):
        if path.name in FRAGMENT_IGNORED or path.name.startswith("."):
            continue
        if path.is_dir():
            raise ChangelogError(f"changelog.d/{path.name}：碎片目录下不能有子目录")
        fragments.append(parse_fragment(path, read_text(path)))
    return fragments


def default_identifier(root: Path = REPO_ROOT) -> str:
    """开 PR 前还不知道 PR 号，用分支名代替；在 dev / main / 游离 HEAD 上就用时间戳。"""

    branch = ""
    if git_available(root):
        try:
            branch = git("rev-parse", "--abbrev-ref", "HEAD", root=root).strip()
        except ChangelogError:
            branch = ""
    if branch in ("", "HEAD", "dev", "main", "master"):
        return datetime.now(RELEASE_TIMEZONE).strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-.")
    return slug or datetime.now(RELEASE_TIMEZONE).strftime("%Y%m%d-%H%M%S")


def signature(login: str) -> str:
    return f" by [@{login}](https://github.com/{login})"


def split_signatures(entry: str) -> Tuple[str, List[str]]:
    """把条目拆成 (正文, [署名登录名])。

    只认条目末尾那一串署名，正文中间提到某人的链接不算；末尾那串里第一个带 ` by `，
    后面的可以只用空格连着（旧机器人的多人写法），否则转正合并时跨 beta 段按正文去重
    对不上、贡献者名单也会漏人。
    """

    stripped = entry.rstrip()
    matched = SIGNATURE_TAIL.search(stripped)
    if matched is None:
        return stripped, []
    logins = [m.group("login") for m in SIGNATURE_LOGIN.finditer(matched.group(0))]
    return stripped[: matched.start()].rstrip(), logins


def join_signatures(text: str, logins: Sequence[str]) -> str:
    seen: List[str] = []
    for login in logins:
        if login not in seen:
            seen.append(login)
    return text + "".join(signature(login) for login in seen)


NOREPLY_EMAIL = re.compile(
    r"^(?:\d+\+)?(?P<login>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)@users\.noreply\.github\.com$"
)


def resolve_login_via_api(repo: str, sha: str, token: Optional[str]) -> Optional[str]:
    """用 commits API 把提交解析成 GitHub 登录名；网络或权限问题一律返回 None。"""

    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/commits/{sha}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "auto-mas-changelog",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    author = payload.get("author") or {}
    login = author.get("login")
    return str(login) if login else None


def fragment_author(
    fragment: Fragment,
    repo: str = GITHUB_REPO,
    token: Optional[str] = None,
    root: Path = REPO_ROOT,
    resolve_online: bool = True,
) -> Optional[str]:
    """碎片的署名 = 最近一次把它加进仓库的那个提交的作者。

    squash 合并时就是 PR 作者，rebase 合并保留原作者，直推就是推的人。不读
    Co-authored-by，否则 AI 助手会被签进更新日志。noreply 邮箱直接拆出登录名，
    其余经 commits API 解析；解析不到时，git 作者名长得像登录名才拿来用，否则不署名。
    """

    if fragment.author:
        return fragment.author
    if not git_available(root):
        return None
    relative = fragment.path.resolve().relative_to(root.resolve()).as_posix()
    output = git(
        "log",
        "--diff-filter=A",
        "--format=%H%x00%an%x00%ae",
        "--",
        relative,
        root=root,
    ).strip()
    if not output:
        return None
    # git log 最新在前，取第一行：碎片发版后会被删除，同名文件可能被后来的 PR 再次
    # 新增，要署最近一次新增它的人，而不是历史上第一个用过这个文件名的人
    sha, name, email = output.splitlines()[0].split("\x00")
    noreply = NOREPLY_EMAIL.match(email.strip())
    if noreply:
        return noreply.group("login")
    if resolve_online:
        login = resolve_login_via_api(repo, sha, token)
        if login:
            return login
    # 退回 git 作者名，但只有长得像登录名的才用：squash 提交里的作者名往往是显示名
    # （中文昵称、带空格的全名），签进去会渲染成 https://github.com/<昵称> 这种坏链接，
    # 不如不署名，让发版 PR 的「解析不到作者」提示把它点出来
    name = name.strip()
    return name if LOGIN_PATTERN.match(name) else None


# ---------------------------------------------------------------------------
# 生成物同步
# ---------------------------------------------------------------------------


def substitute_once(text: str, pattern: re.Pattern[str], value: str, where: str) -> str:
    """把唯一一处版本号替换掉；命中数不是 1 就直接报错，避免改错地方。"""

    matches = pattern.findall(text)
    if len(matches) != 1:
        raise ChangelogError(
            f"{where}：预期恰好命中 1 处版本号，实际 {len(matches)} 处"
        )
    return pattern.sub(lambda m: f'{m.group(1)}"{value}"', text, count=1)


PACKAGE_JSON_VERSION = re.compile(r'(?m)^(\s*"version"\s*:\s*)"[^"]*"')
APP_CONFIG_VERSION = re.compile(r'(?m)^(\s*VERSION\s*=\s*)"[^"]*"')
PYPROJECT_VERSION = re.compile(r'(?m)^(version\s*=\s*)"[^"]*"')
UV_LOCK_VERSION = re.compile(
    r'(?m)^(\[\[package\]\]\nname = "auto-mas"\nversion = )"[^"]*"'
)
# (相对路径, 正则)：普通 PR 不许改动这四处的版本号取值
VERSION_FIELDS = (
    ("frontend/package.json", PACKAGE_JSON_VERSION),
    ("app/core/config.py", APP_CONFIG_VERSION),
    ("pyproject.toml", PYPROJECT_VERSION),
    ("uv.lock", UV_LOCK_VERSION),
)


def extract_version_field(text: str, pattern: re.Pattern[str]) -> Optional[str]:
    matched = pattern.search(text)
    if matched is None:
        return None
    return text[matched.end(1) :].split('"', 2)[1]


def build_expected() -> Dict[Path, str]:
    """算出每个生成物应有的完整内容。"""

    current_version, sections, dates = parse_changelog(read_text(CHANGELOG_PATH))
    pep440_version = to_pep440(current_version)

    return {
        CHANGELOG_PATH: render_changelog(sections, dates),
        VERSION_JSON_PATH: render_version_json(current_version, sections),
        PACKAGE_JSON_PATH: substitute_once(
            read_text(PACKAGE_JSON_PATH),
            PACKAGE_JSON_VERSION,
            current_version,
            "frontend/package.json",
        ),
        APP_CONFIG_PATH: substitute_once(
            read_text(APP_CONFIG_PATH),
            APP_CONFIG_VERSION,
            current_version,
            "app/core/config.py",
        ),
        PYPROJECT_PATH: substitute_once(
            read_text(PYPROJECT_PATH),
            PYPROJECT_VERSION,
            pep440_version,
            "pyproject.toml",
        ),
        UV_LOCK_PATH: substitute_once(
            read_text(UV_LOCK_PATH),
            UV_LOCK_VERSION,
            pep440_version,
            "uv.lock",
        ),
    }


def sync_generated() -> List[str]:
    changed: List[str] = []
    for path, expected in build_expected().items():
        if read_text(path) != expected:
            write_text(path, expected)
            changed.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
    return changed


def command_sync() -> int:
    changed = sync_generated()
    if changed:
        print("已更新：")
        for name in changed:
            print(f"  - {name}")
    else:
        print("各处版本号与生成物均已同步，无需改动")
    return 0


# ---------------------------------------------------------------------------
# check / guard
# ---------------------------------------------------------------------------


def check_generated() -> List[str]:
    """返回与 CHANGELOG.md 不一致的生成物列表。"""

    stale: List[str] = []
    for path, expected in build_expected().items():
        if read_text(path) != expected:
            stale.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
    return stale


def check_version_floor(current_version: str, root: Path = REPO_ROOT) -> Optional[str]:
    """仓库里的版本号不能小于当前分支可达的最新 tag；返回作为基准的 tag。

    没有 git 或没有任何 tag 时跳过（本地 zip 包、浅克隆的 fork 都可能这样）。
    """

    if not git_available(root):
        return None
    try:
        latest = latest_version(reachable_tags("HEAD", root))
    except ChangelogError:
        return None
    if latest is None:
        return None
    current_key = version_key(current_version)
    if current_key is None:
        raise ChangelogError(f"当前版本号 {current_version} 不合形态")
    if current_key < version_key(latest):  # type: ignore[operator]
        raise ChangelogError(
            f"仓库里的版本号 {current_version} 小于已发布的 tag {latest}。"
            "这通常是合并时把别人的版本提升冲掉了，请以 dev 为准重新解决冲突。"
        )
    return latest


def check_pull_request(
    base: str,
    kind: str,
    skip_changelog: bool,
    maintenance: bool,
    dev_ref: Optional[str],
    root: Path = REPO_ROOT,
) -> List[str]:
    """PR 级别的规则，返回违规说明列表。

    kind：normal（普通 PR）、release（发版 PR）、sync（dev→main 之类的同步 PR）。
    """

    problems: List[str] = []
    changes = changed_files(base, "HEAD", root)
    paths = {path for _, path in changes}

    if dev_ref:
        # 目标是 release/* 的 PR，不论类型，都不得带入 dev 独有的提交（#673 那种事故的判据）。
        # 放在类型分流之前：发版 PR 被误改目标到 release/* 时同样要拦。
        pr_commits = set(git("rev-list", f"{base}..HEAD", root=root).split())
        dev_only = set(git("rev-list", f"{base}..{dev_ref}", root=root).split())
        leaked = sorted(pr_commits & dev_only)
        if leaked:
            problems.append(
                f"这个 PR 会把 {len(leaked)} 个只在 {dev_ref} 上的提交带进 {base}。"
                "release 分支只接受从 dev cherry-pick 出来的修复，"
                "请基于 release 分支重新开分支并 cherry-pick"
            )

    if kind == "sync":
        return problems

    if kind == "release":
        if list_fragments(root / "changelog.d"):
            problems.append(
                "发版 PR 合并时 changelog.d/ 必须已经清空，请重新运行「准备发版」"
            )
        current_version, _, _ = parse_changelog(read_text(root / "CHANGELOG.md"))
        base_text = show_file(base, "CHANGELOG.md", root)
        if base_text:
            # 过渡期目标分支顶部可能已经手工预留了同号的「未发布」段，所以只要求不倒退
            base_version, _, _ = parse_changelog(base_text)
            if version_key(current_version) < version_key(base_version):  # type: ignore[operator]
                problems.append(
                    f"发版 PR 的版本号 {current_version} 比 {base} 上的 {base_version} 还旧"
                )
        latest = latest_version(reachable_tags("HEAD", root))
        if latest is not None and version_key(current_version) <= version_key(latest):  # type: ignore[operator]
            problems.append(
                f"发版 PR 的版本号 {current_version} 没有比最新 tag {latest} 新"
            )
        return problems

    # normal
    fragment_dir = root / "changelog.d"
    added = [
        path
        for status, path in changes
        if status == "A"
        and path.startswith("changelog.d/")
        and FRAGMENT_NAME.match(path.rsplit("/", 1)[-1])
    ]
    touched_others = [
        path
        for status, path in changes
        if status != "A"
        and path.startswith("changelog.d/")
        and path.rsplit("/", 1)[-1] not in FRAGMENT_IGNORED
    ]
    if touched_others and not maintenance:
        problems.append(
            "不要修改或删除已有的碎片，它们属于别的 PR：" + "、".join(touched_others)
        )

    if not maintenance:
        for protected in PROTECTED_FILES:
            if protected in paths:
                problems.append(
                    f"普通 PR 不能改 {protected}，它只由发版 PR 更新；"
                    "更新日志请写成 changelog.d/ 下的碎片"
                )
        for relative, pattern in VERSION_FIELDS:
            if relative not in paths:
                continue
            before = show_file(base, relative, root)
            after_path = root / relative
            after = read_text(after_path) if after_path.exists() else None
            if before is None or after is None:
                continue
            if extract_version_field(before, pattern) != extract_version_field(
                after, pattern
            ):
                problems.append(
                    f"普通 PR 不能改 {relative} 里的版本号，版本号只由发版 PR 推进"
                )

    user_visible = any(
        path.startswith(USER_VISIBLE_PREFIXES) or path in USER_VISIBLE_PREFIXES
        for path in paths
    )
    needs_fragment = user_visible and not skip_changelog and not maintenance
    if needs_fragment and not added:
        problems.append(
            "这个 PR 改了用户可见的代码，但没有新增更新日志碎片。"
            '请运行 `python scripts/changelog.py add <分类> "<一句话>"`；'
            "确实没有用户可见改动的话，给 PR 打 skip-changelog 标签"
        )
    if len(added) > 1:
        problems.append(
            "一条 PR 只放一个碎片，把全部改动概括成一句话：" + "、".join(added)
        )
    for path in added:
        # 目录里的碎片已经被 list_fragments 整体校验过；这里只确认新加的确实在目录里
        if not (fragment_dir / path.rsplit("/", 1)[-1]).exists():
            problems.append(f"{path} 在工作区里不存在")

    return problems


def command_check(arguments: argparse.Namespace) -> int:
    stale = check_generated()
    if stale:
        print("以下文件与 CHANGELOG.md 不一致：", file=sys.stderr)
        for name in stale:
            print(f"  - {name}", file=sys.stderr)
        print(
            "\n请运行 `python scripts/changelog.py sync` 重新生成后提交。",
            file=sys.stderr,
        )
        return 1

    fragments = list_fragments()
    current_version, _, _ = parse_changelog(read_text(CHANGELOG_PATH))
    floor = check_version_floor(current_version)

    problems: List[str] = []
    if arguments.pr_base:
        problems = check_pull_request(
            base=arguments.pr_base,
            kind=arguments.pr_kind,
            skip_changelog=arguments.skip_changelog,
            maintenance=arguments.maintenance,
            dev_ref=arguments.dev_ref,
        )
    if problems:
        print("更新日志检查未通过：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"版本号一致: {current_version}")
    if floor:
        print(f"最新已发布 tag: {floor}")
    print(f"待发布碎片: {len(fragments)} 个")
    return 0


def command_guard() -> int:
    """构建发布前的守门：版本号必须已经比最新 tag 新，碎片必须已经清空。"""

    current_version, _, _ = parse_changelog(read_text(CHANGELOG_PATH))
    latest = latest_version(reachable_tags("HEAD")) if git_available() else None
    problems: List[str] = []
    if latest is not None and version_key(current_version) <= version_key(latest):  # type: ignore[operator]
        problems.append(
            f"仓库版本号 {current_version} 没有比最新 tag {latest} 新，"
            "请先运行「准备发版」并合并发版 PR"
        )
    if latest is not None and current_version in all_tags():
        problems.append(f"tag {current_version} 已经存在，不能重复发布")
    fragments = list_fragments()
    if fragments:
        problems.append(
            f"changelog.d/ 里还有 {len(fragments)} 个未编译的碎片，"
            "说明发版 PR 之后又合并了改动；请重新运行「准备发版」"
        )
    if problems:
        print("发布守门未通过：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"可以发布 {current_version}")
    return 0


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------


def merge_entries(target: Dict[str, List[str]], source: Dict[str, List[str]]) -> None:
    """把 source 的条目并进 target：同文本去重、署名取并集、分类照旧。"""

    for category, items in source.items():
        bucket = target.setdefault(category, [])
        index = {split_signatures(item)[0]: i for i, item in enumerate(bucket)}
        for item in items:
            text, logins = split_signatures(item)
            if text in index:
                existing_text, existing_logins = split_signatures(bucket[index[text]])
                bucket[index[text]] = join_signatures(
                    existing_text, [*existing_logins, *logins]
                )
            else:
                index[text] = len(bucket)
                # 重新拼一次署名：旧机器人写的 ` by [@a](..) [@b](..)` 借此归一成每个都带 by
                bucket.append(join_signatures(text, logins))


def unconfirmed_commits(
    since: Optional[str], root: Path = REPO_ROOT
) -> List[Tuple[str, str]]:
    """上个 tag 以来改了用户可见代码、却没带碎片、也不是 chore/docs 类的提交。

    这是直推修复的兜底：漏写只会被点名，不会静默消失。
    """

    if since is None or not git_available(root):
        return []
    shas = git("rev-list", "--no-merges", f"{since}..HEAD", root=root).split()
    result: List[Tuple[str, str]] = []
    for sha in shas:
        subject = git("log", "-1", "--format=%s", sha, root=root).strip()
        prefix = re.match(r"^([A-Za-z]+)", subject)
        if prefix and prefix.group(1).lower() in NON_USER_FACING_PREFIXES:
            continue
        files = git(
            "show", "--name-only", "--format=", "--diff-filter=ACMR", sha, root=root
        ).split("\n")
        files = [f.strip().replace("\\", "/") for f in files if f.strip()]
        if any(f.startswith("changelog.d/") for f in files):
            continue
        # 只动了版本文件的提交（发版 PR、版本修正）不算用户可见改动
        bookkeeping = set(PROTECTED_FILES) | {
            relative for relative, _ in VERSION_FIELDS
        }
        if set(files) <= bookkeeping:
            continue
        if not any(
            f.startswith(USER_VISIBLE_PREFIXES) or f in USER_VISIBLE_PREFIXES
            for f in files
        ):
            continue
        result.append((sha[:9], subject))
    return result


def compile_release(
    sections: Sections,
    dates: Dates,
    fragments: Sequence[Fragment],
    target: str,
    date: str,
    authors: Dict[str, Optional[str]],
    tagged: Iterable[str],
) -> Tuple[Sections, Dates]:
    """把碎片编译进新的版本段，返回新的 (sections, dates)。

    - 顶部若有 `未发布` 段，其条目并入新段（过渡期兼容手工预留的版本段）。
    - 目标版本已经有段但还没打 tag 时（发版 PR 合并后又来了改动），在原段上追加。
    - 转正时把同号的全部 beta 段合并进来，并从文件里移除。
    """

    sections = {
        v: {c: list(items) for c, items in cats.items()} for v, cats in sections.items()
    }
    dates = dict(dates)
    tagged_set = set(tagged)

    pending: Dict[str, List[str]] = {}
    first = next(iter(sections))
    if dates[first] == UNRELEASED:
        if first != target:
            print(
                f"提示：顶部手工预留的 {first} 未发布段已并入 {target}，"
                "版本号以 tag 推算的结果为准",
                file=sys.stderr,
            )
        merge_entries(pending, sections.pop(first))
        dates.pop(first)

    if target in sections:
        if target in tagged_set:
            raise ChangelogError(f"版本 {target} 已经发布过，不能再往里加条目")
        merge_entries(pending, sections.pop(target))
        dates.pop(target)

    target_key = version_key(target)
    if target_key is None:
        raise ChangelogError(f"版本号 {target} 不合形态")

    if not is_prerelease(target):
        # 转正：同号的 beta 段按从旧到新的顺序并入，读起来才是时间顺序
        cycle = [
            v
            for v in sections
            if (key := version_key(v)) is not None
            and key[:3] == target_key[:3]
            and key[3] != PHASE_RANK[None]
        ]
        rolled: Dict[str, List[str]] = {}
        for v in reversed(cycle):
            merge_entries(rolled, sections.pop(v))
            dates.pop(v)
        merge_entries(rolled, pending)
        pending = rolled

    fresh: Dict[str, List[str]] = {}
    for fragment in fragments:
        login = authors.get(fragment.path.name)
        entry = join_signatures(fragment.text, [login]) if login else fragment.text
        fresh.setdefault(fragment.category, []).append(entry)
    merge_entries(pending, fresh)

    if not pending:
        raise ChangelogError(
            "没有任何可发布的内容：changelog.d/ 为空，顶部也没有未发布条目"
        )

    for older in sections:
        if version_key(older) is not None and version_key(older) >= target_key:  # type: ignore[operator]
            raise ChangelogError(
                f"CHANGELOG.md 里已经有不小于 {target} 的版本 {older}，版本号不能倒退"
            )

    new_sections: Sections = {target: order_categories(pending)}
    new_sections.update(sections)
    new_dates: Dates = {target: date}
    new_dates.update(dates)
    return new_sections, new_dates


def render_pr_body(
    version: str,
    previous: Optional[str],
    kind: str,
    categories: Dict[str, List[str]],
    unconfirmed: Sequence[Tuple[str, str]],
) -> str:
    lines = [f"## Release {version}", ""]
    lines.append(
        "由「准备发版」工作流生成。这是唯一允许修改 `CHANGELOG.md` 与版本号的 PR，"
        "合并后请手动运行「构建并发布应用程序」。"
    )
    lines.append("")
    lines.append("合并前请在本 PR 里完成：")
    lines.append("")
    lines.append(
        "- [ ] 在 `CHANGELOG.md` 新版本段里补「本次亮点」（三五条即可，可不补）"
    )
    if kind == "stable":
        lines.append("- [ ] 删掉周期内引入又修掉的问题，稳定通道用户没装过 beta")
        lines.append(
            "- [ ] 同一件事写了简写和详写两遍的，保留详写；同专项多条可合成一句"
        )
    if unconfirmed:
        lines.append("- [ ] 下面「待确认」的提交若用户可见，直接在新版本段里补一条")
    lines.append("- [ ] 改完运行 `python scripts/changelog.py sync` 并提交")
    lines.append("")
    if previous:
        lines.append(f"自 `{previous}` 以来的改动：")
        lines.append("")
    lines.extend(render_section(categories))
    if unconfirmed:
        lines.append("### 待确认：改了用户可见代码但没有碎片的提交")
        lines.append("")
        for sha, subject in unconfirmed:
            lines.append(f"- `{sha}` {subject}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def command_release(arguments: argparse.Namespace) -> int:
    text = read_text(CHANGELOG_PATH)
    current_version, sections, dates = parse_changelog(text)
    fragments = list_fragments()

    if not git_available():
        raise ChangelogError("release 需要在 git 仓库里运行")
    reachable = reachable_tags("HEAD")
    every = all_tags()
    latest = latest_version(reachable)
    target = next_version(arguments.kind, latest, arguments.version)
    if target in every:
        raise ChangelogError(f"tag {target} 已经存在，请换一个版本号")

    date = arguments.date or datetime.now(RELEASE_TIMEZONE).strftime("%Y-%m-%d")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    authors = {
        fragment.path.name: fragment_author(
            fragment,
            repo=arguments.repo,
            token=token,
            resolve_online=not arguments.offline,
        )
        for fragment in fragments
    }
    unresolved = [name for name, login in authors.items() if not login]
    if unresolved:
        print(
            "以下碎片解析不到作者，将不带署名：" + "、".join(unresolved),
            file=sys.stderr,
        )

    new_sections, new_dates = compile_release(
        sections, dates, fragments, target, date, authors, every
    )
    unconfirmed = unconfirmed_commits(latest)

    if arguments.dry_run:
        print(f"将发布 {target}（{arguments.kind}），基于 {latest or '无 tag'}")
        print("\n".join(render_section(new_sections[target])))
        for sha, subject in unconfirmed:
            print(f"待确认: {sha} {subject}")
        return 0

    write_text(CHANGELOG_PATH, render_changelog(new_sections, new_dates))
    for fragment in fragments:
        fragment.path.unlink()
    changed = sync_generated()

    body = render_pr_body(
        target, latest, arguments.kind, new_sections[target], unconfirmed
    )
    if arguments.body_file:
        write_text(Path(arguments.body_file), body)
    if arguments.summary_file:
        summary = {
            "version": target,
            "previous_tag": latest,
            "kind": arguments.kind,
            "date": date,
            "fragments": len(fragments),
            "unconfirmed": [
                {"sha": sha, "subject": subject} for sha, subject in unconfirmed
            ],
            "changed_files": changed,
        }
        write_text(
            Path(arguments.summary_file),
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        )
    if arguments.github_output:
        with open(arguments.github_output, "a", encoding="utf-8") as output:
            output.write(f"version={target}\n")
            output.write(f"previous_tag={latest or ''}\n")
            output.write(f"kind={arguments.kind}\n")

    print(f"已编译 {len(fragments)} 个碎片到 {target}，基于 {latest or '无 tag'}")
    for name in changed:
        print(f"  - {name}")
    if unconfirmed:
        print("待确认的提交：")
        for sha, subject in unconfirmed:
            print(f"  - {sha} {subject}")
    return 0


# ---------------------------------------------------------------------------
# release-note
# ---------------------------------------------------------------------------


def select_note_versions(sections: Sections, version: str) -> List[str]:
    """Release 正文首行 JSON 里要带哪些版本段。

    老客户端按「比本机新」过滤这份 JSON 并逐段显示，所以：
    - 公测版带本周期全部 beta 段，加上一个正式周期的整条线（X.Y.0 汇总与其补丁），
      切通道、跳版都能看全；
    - 正式版带本次汇总，加上一个正式周期的整条线，不带 beta 段（否则重复显示）；
    - 补丁版带本次，加同一 X.Y 下更早的补丁段与 X.Y.0 汇总段。
    """

    key = version_key(version)
    if key is None:
        raise ChangelogError(f"版本号 {version} 不合形态")
    ordered = [v for v in sections if version_key(v) is not None]
    older = [v for v in ordered if version_key(v) <= key]  # type: ignore[operator]
    finals = [v for v in older if not is_prerelease(v)]

    def whole_line(anchor: Optional[str]) -> List[str]:
        """anchor 所在 X.Y 线上的全部正式版段：X.Y.0 汇总加它之后的补丁。"""

        if anchor is None:
            return []
        line = version_key(anchor)[:2]  # type: ignore[index]
        return [v for v in finals if version_key(v)[:2] == line]  # type: ignore[index]

    selected: List[str] = []
    if is_prerelease(version):
        selected.extend(
            v
            for v in older
            if is_prerelease(v) and version_key(v)[:3] == key[:3]  # type: ignore[index]
        )
        # 上一个正式周期整条线都带上：只带最后一个补丁段会丢掉 X.Y.0 汇总与更早的补丁
        selected.extend(whole_line(next(iter(finals), None)))
    elif key[2] == 0:
        selected.append(version)
        selected.extend(whole_line(next((v for v in finals if v != version), None)))
    else:
        selected.extend(v for v in finals if version_key(v)[:2] == key[:2])  # type: ignore[index]
        if not selected or selected[0] != version:
            selected.insert(0, version)
    # 去重并保持文件顺序（新在前）
    seen: List[str] = []
    for v in ordered:
        if v in selected and v not in seen:
            seen.append(v)
    return seen


def render_release_note(sections: Sections, version: str) -> str:
    """Release 正文：首行 JSON（老客户端契约）+ 本版可见正文 + 贡献者 + 对比链接。"""

    if version not in sections:
        raise ChangelogError(f"CHANGELOG.md 里没有版本 {version}")
    selected = select_note_versions(sections, version)
    payload = {v: order_categories(sections[v]) for v in selected}
    lines = [
        "<!--" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "-->"
    ]
    lines.append(f"## {version}")
    lines.append("")
    lines.extend(render_section(sections[version]))

    contributors: List[str] = []
    for items in sections[version].values():
        for item in items:
            for login in split_signatures(item)[1]:
                if login not in contributors:
                    contributors.append(login)
    if contributors:
        lines.append("### 贡献者")
        lines.append("")
        lines.append(
            " ".join(
                f"[@{login}](https://github.com/{login})" for login in contributors
            )
        )
        lines.append("")

    ordered = [v for v in sections if version_key(v) is not None]
    key = version_key(version)
    if is_prerelease(version) or key[2] != 0:  # type: ignore[index]
        previous = next((v for v in ordered if version_key(v) < key), None)  # type: ignore[operator]
    else:
        previous = next(
            (v for v in ordered if not is_prerelease(v) and version_key(v) < key),  # type: ignore[operator]
            None,
        )
    if previous:
        lines.append(
            f"**完整对比**：[{previous}...{version}]({REPO_URL}/compare/{previous}...{version})"
        )
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def command_release_note(arguments: argparse.Namespace) -> int:
    current_version, sections, _ = parse_changelog(read_text(CHANGELOG_PATH))
    version = arguments.version or current_version
    note = render_release_note(sections, version)
    if arguments.output:
        write_text(Path(arguments.output), note)
        print(f"已写出 {version} 的 Release 正文到 {arguments.output}")
    else:
        sys.stdout.write(note)
    return 0


# ---------------------------------------------------------------------------
# add / current
# ---------------------------------------------------------------------------


def command_add(arguments: argparse.Namespace) -> int:
    text = " ".join(arguments.text).strip()
    if text.startswith("- "):
        text = text[2:].strip()
    if not text:
        raise ChangelogError("碎片内容为空")
    if "\n" in text:
        raise ChangelogError("碎片只能写一行")
    if SIGNATURE.search(text):
        raise ChangelogError("不要手写 ` by [@用户]` 署名，发版时会按提交作者自动补")

    identifier = arguments.id or default_identifier()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", identifier):
        raise ChangelogError(f"标识 {identifier!r} 只能含字母、数字、. _ -")

    FRAGMENT_DIR.mkdir(exist_ok=True)
    existing = [f for f in list_fragments() if f.identifier == identifier]
    if existing:
        raise ChangelogError(
            f"已经有碎片 {existing[0].path.name}，一条 PR 只放一个碎片，请直接编辑它"
        )
    path = FRAGMENT_DIR / f"{identifier}.{arguments.type}.md"
    content = text + "\n"
    if arguments.author:
        content = f"author: {arguments.author.lstrip('@')}\n" + content
    write_text(path, content)
    parse_fragment(path, content)
    print(
        f"已创建 {path.relative_to(REPO_ROOT).as_posix()}（分类：{FRAGMENT_TYPES[arguments.type]}）"
    )
    return 0


def command_current(_: argparse.Namespace) -> int:
    current_version, _, _ = parse_changelog(read_text(CHANGELOG_PATH))
    print(current_version)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="新建一个更新日志碎片")
    add.add_argument("type", choices=sorted(FRAGMENT_TYPES), help="分类后缀")
    add.add_argument("text", nargs="+", help="一句面向用户的话")
    add.add_argument("--id", help="文件名前缀，默认取 PR 号或当前分支名")
    add.add_argument("--author", help="替别人提交时指定署名登录名")

    check = subparsers.add_parser("check", help="校验格式、碎片与版本号（CI 用）")
    check.add_argument(
        "--pr-base", help="PR 的目标分支引用，如 origin/dev；给了才做 PR 级检查"
    )
    check.add_argument(
        "--pr-kind",
        choices=["normal", "release", "sync"],
        default="normal",
        help="normal 普通 PR、release 发版 PR、sync 同步 PR",
    )
    check.add_argument(
        "--skip-changelog", action="store_true", help="PR 带 skip-changelog 标签"
    )
    check.add_argument(
        "--maintenance",
        action="store_true",
        help="PR 带 changelog-maintenance 标签：允许维护者直接整理 CHANGELOG.md",
    )
    check.add_argument(
        "--dev-ref", help="目标是 release/* 时给 dev 的引用，用于查带错提交"
    )

    release = subparsers.add_parser("release", help="编译碎片、推进版本号")
    release.add_argument(
        "--kind", choices=["beta", "stable", "patch", "explicit"], default="beta"
    )
    release.add_argument("--version", help="--kind explicit 时的版本号")
    release.add_argument("--date", help="发布日期 YYYY-MM-DD，默认北京时间今天")
    release.add_argument("--repo", default=GITHUB_REPO, help="解析署名用的 owner/repo")
    release.add_argument(
        "--offline", action="store_true", help="不访问 GitHub API 解析署名"
    )
    release.add_argument("--dry-run", action="store_true", help="只打印结果，不改文件")
    release.add_argument("--summary-file", help="把结果摘要写成 JSON")
    release.add_argument("--body-file", help="把发版 PR 正文写成 Markdown")
    release.add_argument("--github-output", help="把 version 等写进 GITHUB_OUTPUT")

    note = subparsers.add_parser("release-note", help="渲染 Release 正文")
    note.add_argument("--version", help="默认当前版本")
    note.add_argument("--output", help="写到文件而不是标准输出")

    subparsers.add_parser("guard", help="构建发布前守门")
    subparsers.add_parser("sync", help="从 CHANGELOG.md 同步各处生成物")
    subparsers.add_parser("current", help="打印当前版本号")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    handlers = {
        "add": command_add,
        "check": command_check,
        "release": command_release,
        "release-note": command_release_note,
        "guard": lambda _: command_guard(),
        "sync": lambda _: command_sync(),
        "current": command_current,
    }
    try:
        return handlers[arguments.command](arguments)
    except ChangelogError as error:
        print(f"更新日志有误：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Windows 上被管道接走时 stdout 默认不是 UTF-8，打印中文会直接崩。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
