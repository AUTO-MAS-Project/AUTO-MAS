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

"""版本号维护脚本。

仓库里有四处版本号，必须始终一致：

- ``res/version.json`` 的 ``version``
- ``frontend/package.json`` 的 ``version``
- ``app/core/config.py`` 中 ``AppConfig.VERSION``
- ``pyproject.toml`` 的 ``[project] version``（PEP 440 写法，如 ``5.5.0b3``）

用法::

    # 校验四处是否一致，CI 与本地都可用
    python .github/workflows/bump_version.py --check

    # 发版成功后推进开发版本号，由 build-app.yml 调用
    python .github/workflows/bump_version.py --after-release v5.5.0-beta.3 \
        --released-info <已发布版本的 res/version.json>

    # 手动指定版本号，用于 v5.5.1 这类特殊修复版
    python .github/workflows/bump_version.py --set v5.5.1
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

VERSION_JSON = REPO_ROOT / "res" / "version.json"
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
CONFIG_PY = REPO_ROOT / "app" / "core" / "config.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# vX.Y.Z 或 vX.Y.Z-beta.N
VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$")
# PEP 440 写法：X.Y.Z 或 X.Y.ZbN
PEP440_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:b(\d+))?$")

PACKAGE_VERSION_RE = re.compile(
    r'(?m)^(?P<head>\s*"version"\s*:\s*")(?P<version>[^"]*)(?P<tail>")'
)
CONFIG_VERSION_RE = re.compile(
    r'(?m)^(?P<head>\s*VERSION\s*=\s*")(?P<version>[^"]*)(?P<tail>")'
)
PYPROJECT_VERSION_RE = re.compile(
    r'(?m)^(?P<head>version\s*=\s*")(?P<version>[^"]*)(?P<tail>")'
)

# append-version-contributor.yml 在条目末尾追加的 " by [@login](url)" 署名，可以有多个。
CONTRIBUTOR_SUFFIX_RE = re.compile(r"\s+by \[@[^\]]+\]\([^)]*\)")


def configure_stdio() -> None:
    """强制 UTF-8 输出，避免 Windows 上默认编码写不出中文提示。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def die(message: str) -> None:
    """打印错误并以非零状态退出。"""

    print(f"错误：{message}", file=sys.stderr)
    raise SystemExit(1)


def parse_version(version: str) -> Tuple[int, int, int, Optional[int]]:
    """把 ``vX.Y.Z[-beta.N]`` 解析为四元组，``beta`` 为 ``None`` 表示正式版。"""

    matched = VERSION_RE.match(version)
    if matched is None:
        die(f"版本号 {version!r} 不符合 vX.Y.Z 或 vX.Y.Z-beta.N 的格式")

    major, minor, patch, beta = matched.groups()
    return int(major), int(minor), int(patch), None if beta is None else int(beta)


def to_pep440(version: str) -> str:
    """把 ``v5.6.0-beta.1`` 转成 pyproject.toml 用的 ``5.6.0b1``。"""

    major, minor, patch, beta = parse_version(version)
    base = f"{major}.{minor}.{patch}"
    return base if beta is None else f"{base}b{beta}"


def from_pep440(version: str) -> str:
    """把 ``5.6.0b1`` 还原成 ``v5.6.0-beta.1``，仅用于一致性比对。"""

    matched = PEP440_RE.match(version)
    if matched is None:
        die(f"pyproject.toml 的版本号 {version!r} 不符合 PEP 440 的 X.Y.Z[bN] 格式")

    major, minor, patch, beta = matched.groups()
    base = f"v{major}.{minor}.{patch}"
    return base if beta is None else f"{base}-beta.{beta}"


def next_version(released: str) -> Optional[str]:
    """算出发布 ``released`` 之后开发分支该用的版本号。

    - 预发布版 ``vX.Y.Z-beta.N`` → ``vX.Y.Z-beta.(N+1)``
    - 正式版 ``vX.Y.0`` → ``vX.(Y+1).0-beta.1``
    - 修复版 ``vX.Y.Z``（Z 不为 0）→ ``None``，下一个版本号由维护者决定
    """

    major, minor, patch, beta = parse_version(released)
    if beta is not None:
        return f"v{major}.{minor}.{patch}-beta.{beta + 1}"
    if patch != 0:
        return None
    return f"v{major}.{minor + 1}.0-beta.1"


def read_literal(path: Path, pattern: re.Pattern) -> str:
    """按正则取出文件里唯一的版本号字面量。"""

    text = path.read_text(encoding="utf-8")
    matches = pattern.findall(text)
    if len(matches) != 1:
        die(
            f"{path.relative_to(REPO_ROOT).as_posix()} 中匹配到 "
            f"{len(matches)} 处版本号，预期 1 处"
        )
    return pattern.search(text).group("version")


def read_versions() -> Dict[str, str]:
    """读出四处版本号，统一成 ``vX.Y.Z[-beta.N]`` 形式返回。"""

    version_json = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    return {
        "res/version.json": version_json["version"],
        "frontend/package.json": read_literal(PACKAGE_JSON, PACKAGE_VERSION_RE),
        "app/core/config.py": read_literal(CONFIG_PY, CONFIG_VERSION_RE),
        "pyproject.toml": from_pep440(read_literal(PYPROJECT, PYPROJECT_VERSION_RE)),
    }


def replace_literal(path: Path, pattern: re.Pattern, version: str) -> None:
    """把文件里唯一的版本号字面量替换成 ``version``。"""

    text = path.read_text(encoding="utf-8")
    updated, count = pattern.subn(
        lambda matched: matched.group("head") + version + matched.group("tail"), text
    )
    if count != 1:
        die(
            f"{path.relative_to(REPO_ROOT).as_posix()} 中替换到 "
            f"{count} 处版本号，预期 1 处"
        )
    path.write_text(updated, encoding="utf-8", newline="\n")


def strip_contributors(item: str) -> str:
    """去掉条目末尾的贡献者署名，比对条目是否同一条时用。"""

    return CONTRIBUTOR_SUFFIX_RE.sub("", item).strip()


def take_unreleased_entries(
    version_info: Dict[str, dict], released_info: Dict[str, dict]
) -> Dict[str, list]:
    """把已发布快照里没有的条目从各版本段中取出，按分类归拢返回。

    发版到推进版本号之间合入的 PR，条目会写进当时还是最新的、但已经发布出去的版本段。
    留在原处既与归档语义不符，也会被 app/services/update.py 的「只取高于当前版本的段」
    过滤掉，停在该版本的用户在更新提示里看不到这些条目。
    """

    released_items = {
        strip_contributors(item)
        for section in released_info.values()
        for items in section.values()
        if isinstance(items, list)
        for item in items
        if isinstance(item, str)
    }

    taken: Dict[str, list] = {}
    for section in version_info.values():
        for category in list(section):
            items = section[category]
            if not isinstance(items, list):
                continue

            kept = []
            for item in items:
                released = (
                    not isinstance(item, str)
                    or strip_contributors(item) in released_items
                )
                if released:
                    kept.append(item)
                else:
                    taken.setdefault(category, []).append(item)

            if items and not kept:
                del section[category]
            else:
                section[category] = kept

    return {category: items for category, items in taken.items() if items}


def write_versions(
    version: str,
    *,
    reset_history: bool,
    released_info: Optional[Dict[str, dict]] = None,
) -> int:
    """把四处版本号写成 ``version``，并在 version_info 顶部备好新版本段。

    返回从已发布版本段迁移到新版本段的条目数。
    """

    version_json = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    version_info = version_json.get("version_info", {})

    if reset_history and released_info is None:
        print("没有已发布版本的更新条目可比对，保留 version_info 历史段落")
        reset_history = False

    pending = (
        take_unreleased_entries(version_info, released_info)
        if released_info is not None
        else {}
    )

    if reset_history:
        version_json["version_info"] = {version: pending}
    else:
        section = version_info.pop(version, {})
        for category, items in pending.items():
            section.setdefault(category, []).extend(items)
        version_json["version_info"] = {version: section, **version_info}

    version_json["version"] = version
    VERSION_JSON.write_text(
        json.dumps(version_json, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    replace_literal(PACKAGE_JSON, PACKAGE_VERSION_RE, version)
    replace_literal(CONFIG_PY, CONFIG_VERSION_RE, version)
    replace_literal(PYPROJECT, PYPROJECT_VERSION_RE, to_pep440(version))

    return sum(len(items) for items in pending.values())


def set_output(**outputs: str) -> None:
    """写 GitHub Actions 的 step output，本地运行时忽略。"""

    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return

    with Path(output_path).open("a", encoding="utf-8") as file:
        for key, value in outputs.items():
            file.write(f"{key}={value}\n")


def command_check() -> None:
    """校验四处版本号是否一致。"""

    versions = read_versions()
    if len(set(versions.values())) != 1:
        details = "\n".join(
            f"- {path}: {version}" for path, version in versions.items()
        )
        die(f"四处版本号不一致：\n{details}")

    current = next(iter(versions.values()))
    parse_version(current)
    print(f"版本号一致：{current}")


def command_after_release(released: str, released_info_path: Optional[str]) -> None:
    """发版成功后推进开发分支的版本号。"""

    parse_version(released)
    current = read_versions()["res/version.json"]

    if current != released:
        reason = f"当前版本号为 {current}，与刚发布的 {released} 不一致，跳过"
        print(reason)
        set_output(changed="false", skip_reason=reason)
        return

    upcoming = next_version(released)
    if upcoming is None:
        reason = f"{released} 是修复版，下一个版本号由维护者决定，跳过"
        print(reason)
        set_output(changed="false", skip_reason=reason)
        return

    released_info = None
    if released_info_path is not None:
        released_json = json.loads(Path(released_info_path).read_text(encoding="utf-8"))
        released_info = released_json.get("version_info", {})

    _, _, _, beta = parse_version(released)
    moved = write_versions(
        upcoming, reset_history=beta is None, released_info=released_info
    )
    print(f"版本号由 {released} 推进至 {upcoming}")
    if moved:
        print(f"发版后合入的 {moved} 条更新条目已迁入 {upcoming} 段")
    set_output(
        changed="true",
        previous_version=released,
        next_version=upcoming,
        moved_entries=str(moved),
    )


def command_set(version: str) -> None:
    """手动把版本号设置为指定值。"""

    parse_version(version)
    current = read_versions()["res/version.json"]
    if current == version:
        print(f"版本号已经是 {version}，无需改动")
        set_output(changed="false", skip_reason=f"版本号已经是 {version}")
        return

    write_versions(version, reset_history=False)
    print(f"版本号由 {current} 设置为 {version}")
    set_output(changed="true", previous_version=current, next_version=version)


def main() -> None:
    configure_stdio()

    parser = argparse.ArgumentParser(description="维护 AUTO-MAS 的四处版本号")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="校验四处版本号是否一致")
    group.add_argument(
        "--after-release", metavar="TAG", help="按刚发布的版本号推进开发版本号"
    )
    group.add_argument(
        "--set", metavar="VERSION", dest="set_version", help="手动设置版本号"
    )
    parser.add_argument(
        "--released-info",
        metavar="PATH",
        help=(
            "已发布版本的 res/version.json 路径，仅配合 --after-release 使用。"
            "发版到推进版本号之间合入的更新条目会据此迁入新版本段；"
            "缺少它时不会清空 version_info 历史段落。"
        ),
    )
    arguments = parser.parse_args()

    if arguments.released_info is not None and arguments.after_release is None:
        parser.error("--released-info 只能配合 --after-release 使用")

    if arguments.check:
        command_check()
    elif arguments.after_release is not None:
        command_after_release(arguments.after_release, arguments.released_info)
    else:
        command_set(arguments.set_version)


if __name__ == "__main__":
    main()
