"""将锁定的插件发行包安装到隔离测试目录，供主仓回归、接口生成及词表审计使用。"""

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """使用 uv 校验发行文件摘要；宿主运行依赖和 SDK 由现有锁定环境及源码提供。"""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        type=Path,
        default=root / "tests/requirements-plugins.txt",
        help="带摘要的发行包清单，可指定尚未发布的本地配套 wheel 清单",
    )
    args = parser.parse_args()
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
            str(args.requirements.resolve()),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
