"""pytest 配置 for taskmanager_native_candidate 测试套件。"""

import sys
from pathlib import Path

import pytest

# 将候选代码路径加入 sys.path
for parent in Path(__file__).resolve().parents:
    candidate_root = parent / "_alpha_build" / "a1" / "taskmanager-native-candidate-20260723"
    if candidate_root.is_dir():
        sys.path.insert(0, str(candidate_root))
        break
