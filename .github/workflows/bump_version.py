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

    # 开发者确定下一个版本后，统一更新四处版本号
    python .github/workflows/bump_version.py --set v5.5.1
"""

import argparse
import json
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


def write_versions(version: str) -> None:
    """把四处版本号写成 ``version``，并在 version_info 顶部备好新版本段。"""

    version_json = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    version_info = version_json.get("version_info", {})

    section = version_info.pop(version, {})
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


def command_set(version: str) -> None:
    """手动把版本号设置为指定值。"""

    parse_version(version)
    current = read_versions()["res/version.json"]
    if current == version:
        print(f"版本号已经是 {version}，无需改动")
        return

    write_versions(version)
    print(f"版本号由 {current} 设置为 {version}")


def main() -> None:
    configure_stdio()

    parser = argparse.ArgumentParser(description="维护 AUTO-MAS 的四处版本号")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="校验四处版本号是否一致")
    group.add_argument(
        "--set", metavar="VERSION", dest="set_version", help="手动设置版本号"
    )
    arguments = parser.parse_args()

    if arguments.check:
        command_check()
    else:
        command_set(arguments.set_version)


if __name__ == "__main__":
    main()
