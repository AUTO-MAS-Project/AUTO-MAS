"""Test runner for taskmanager_native_candidate test suite.

Run with: python scripts/taskmanager_native_candidate/run_tests.py
"""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    tests_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "tests"
        / "taskmanager_native_candidate"
    )

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(tests_dir),
        "-v",
        "--tb=short",
        "--color=yes",
    ]

    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd, cwd=str(tests_dir.parent.parent))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())