"""将锁定的插件发行包安装到隔离测试目录，供主仓回归、接口生成及词表审计使用。"""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """使用 uv 校验发行文件摘要；宿主运行依赖和 SDK 由现有锁定环境及源码提供。"""
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--target",
            str(root / ".test-plugins"),
            "--no-deps",
            "--require-hashes",
            "--only-binary",
            ":all:",
            "--requirement",
            str(root / "tests/requirements-plugins.txt"),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
