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


"""模块规模门禁（#859）：app/api/scripts.py 只放端点，规模只降不升。

上限取当前实测值的绝对值；每次把业务搬回 app/task/<Xxx>/ 之后，
在同一个 PR 里把对应常量调小，形成棘轮。调大上限必须在 PR diff 里留痕并由评审确认。

用法：python scripts/check_module_size.py，超出上限时退出码 1。
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 文件 -> (最大行数, 最大端点数量)；端点数量为 None 表示只卡行数。
# 数值为 2026-10-03 origin/dev 实测值，只降不升：app/core/config.py 的 5372
# 已包含 #949 在 init_config 开头加的启动钩子（dev 现值 5320 + 52），合并后
# 即成为 dev 的新基线。
LIMITS: dict[str, tuple[int, int | None]] = {
    "app/api/scripts.py": (3757, 102),
    "app/core/config.py": (5372, None),
}

ROUTER_DECORATOR = re.compile(
    r"^\s*@router\.(get|post|put|delete|patch)\(", re.MULTILINE
)


def main() -> int:
    failures: list[str] = []

    for relative_path, (max_lines, max_endpoints) in LIMITS.items():
        path = REPO_ROOT / relative_path
        if not path.is_file():
            failures.append(f"{relative_path}: 文件不存在")
            continue

        text = path.read_text(encoding="utf-8")
        lines = len(text.splitlines())
        checks = [(lines, max_lines, "行数")]
        if max_endpoints is not None:
            endpoints = len(ROUTER_DECORATOR.findall(text))
            checks.append((endpoints, max_endpoints, "端点数量"))

        for actual, limit, label in checks:
            if actual > limit:
                failures.append(f"{relative_path}: {label} {actual} 超过上限 {limit}")
            else:
                print(f"OK   {relative_path}: {label} {actual} <= {limit}")

    if failures:
        print("")
        print("模块规模超限（#859：app/api/scripts.py 只放端点，规模只降不升）：")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
