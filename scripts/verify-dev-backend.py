"""以目标解释器只读核对锁定依赖、平台与开发目录边界。"""

from __future__ import annotations

import argparse
import os
import platform
import struct
import subprocess
import sys
import sysconfig
from importlib import metadata
from pathlib import Path


def disjoint(first: Path, second: Path) -> bool:
    """确认两个规范化目录不相等且互不包含。"""
    return not (first.is_relative_to(second) or second.is_relative_to(first))


def check_paths(repo: Path, venv: Path, external: Path, test: bool) -> None:
    """拒绝发行、共享测试环境与工作树的目录重叠。"""
    worktree_list = subprocess.check_output(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain", "-z"]
    )
    worktrees = [
        Path(os.fsdecode(field.removeprefix(b"worktree "))).resolve()
        for field in worktree_list.split(b"\0")
        if field.startswith(b"worktree ")
    ]
    if not worktrees or any(not disjoint(root, external) for root in worktrees):
        raise ValueError("请将测试包或共享环境放在所有当前工作树之外。")
    if not venv.is_relative_to(external) or venv == external:
        raise ValueError("虚拟环境路径不在所选测试目录内，请检查链接或联接点。")
    if test:
        packaged_parent = any(
            (parent / "AUTO-MAS.exe").exists()
            or (parent / ".automas-dev-install").exists()
            for parent in (external, *external.parents)
        )
        if packaged_parent:
            raise ValueError("共享测试环境不能位于发行包的目录内。")
    else:
        for name in (
            "config",
            "data",
            "debug",
            "history",
            "list",
            "plugins",
            "script",
            "temp",
            ".automas-dev-electron",
        ):
            if (repo / name).resolve().parent != repo:
                raise ValueError(f"开发目录 {name} 指向工作树外，拒绝启动。")


def check_requirements(repo: Path, venv: Path, uv: Path, test: bool) -> None:
    """比较锁文件导出的当前平台依赖版本与实际环境，只读且离线。"""
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("UV_")}
    group = (
        ["--no-default-groups", "--group", "dev"] if test else ["--no-default-groups"]
    )
    lines = subprocess.check_output(
        [
            str(uv),
            "export",
            "--locked",
            "--offline",
            "--no-cache",
            "--no-python-downloads",
            "--python",
            sys.executable,
            "--no-emit-project",
            "--no-hashes",
            "--no-header",
            "--no-annotate",
            *group,
            "-q",
        ],
        cwd=repo,
        env=env,
        encoding="utf-8",
    ).splitlines()
    site = Path(sysconfig.get_path("purelib")).resolve()
    if not site.is_relative_to(venv):
        raise ValueError("Python 包目录不在目标虚拟环境内。")
    present = {
        canonicalize_name(dist.metadata["Name"]): dist.version
        for dist in metadata.distributions(path=[str(site)])
    }
    failures = []
    for line in filter(None, map(str.strip, lines)):
        if line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        specs = list(requirement.specifier)
        if requirement.url or len(specs) != 1 or specs[0].operator != "==":
            raise ValueError(f"只支持有精确版本的锁定包：{requirement.name}")
        actual = present.get(canonicalize_name(requirement.name))
        if actual is None or actual not in requirement.specifier:
            failures.append(
                f"{requirement.name}{requirement.specifier}（实际：{actual or '未安装'}）"
            )
    if failures:
        raise ValueError("与当前锁文件不兼容：\n  " + "\n  ".join(sorted(failures)))


def pe_architecture(path: Path) -> str:
    """从发布的 Windows 程序读取架构，不运行程序。"""
    with path.open("rb") as binary:
        if binary.read(2) != b"MZ":
            raise ValueError(f"无效的 Windows 程序：{path}")
        binary.seek(60)
        binary.seek(struct.unpack("<I", binary.read(4))[0])
        if binary.read(4) != b"PE\0\0":
            raise ValueError(f"无效的 Windows 程序头：{path}")
        machine = struct.unpack("<H", binary.read(2))[0]
    return {0x8664: "x64", 0xAA64: "arm64"}.get(machine, f"0x{machine:04x}")


def main() -> int:
    """根据 Check、Start 或 Test 的目标执行只读预检。"""
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("repo", "venv", "uv"):
        parser.add_argument(f"--{arg}", required=True, type=Path)
    for arg in ("platform", "architecture", "version"):
        parser.add_argument(f"--{arg}", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pool-root", type=Path)
    target.add_argument("--app-root", type=Path)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    try:
        repo = args.repo.resolve(strict=True)
        venv = args.venv.resolve(strict=True)
        external = (args.pool_root or args.app_root).resolve(strict=True)
        if args.test != bool(args.pool_root):
            raise ValueError("共享池路径仅用于 Test。")
        check_paths(repo, venv, external, args.test)
        if Path(sys.prefix).resolve() != venv or sys.prefix == sys.base_prefix:
            raise ValueError("执行的 Python 不是所选虚拟环境的解释器。")
        arch = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(
            platform.machine().lower(), platform.machine().lower()
        )
        if (
            platform.python_version() != args.version
            or sys.platform != args.platform
            or arch != args.architecture
            or struct.calcsize("P") != 8
        ):
            raise ValueError(
                f"Python {platform.python_version()}/{sys.platform}/{arch} "
                f"不匹配 {args.version}/{args.platform}/{args.architecture}。"
            )
        if args.app_root:
            for path in (
                external / "AUTO-MAS.exe",
                external / "resources/auto-mas-runtime.exe",
            ):
                if (
                    not path.resolve().is_relative_to(external)
                    or pe_architecture(path) != arch
                ):
                    raise ValueError(f"测试包的程序路径或架构不匹配：{path}")
        check_requirements(repo, venv, args.uv, args.test)
    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        ModuleNotFoundError,
        struct.error,
    ) as error:
        print(f"开发后端预检失败：{error}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"环境兼容，解释器：{sys.executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
