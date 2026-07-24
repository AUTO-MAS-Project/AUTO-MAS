"""authoritative_api_cert 测试套件配置。"""
import sys
from pathlib import Path

# 确保工作树根目录在 sys.path 中
WORKTREE = Path(__file__).resolve().parents[3]
if str(WORKTREE) not in sys.path:
    sys.path.insert(0, str(WORKTREE))