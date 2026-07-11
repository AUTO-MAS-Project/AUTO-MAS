#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright 漏 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


from __future__ import annotations

import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

for stream in (sys.stdout, sys.stderr):
    with suppress(Exception):
        stream.reconfigure(encoding="utf-8", errors="replace")

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from environment import prefer_active_venv_site_packages  # type: ignore[no-redef]

    # 桌面插件目录也可能安装 MaaFW。先把项目 Runner venv 放到 sys.path 最前，
    # 避免共享插件依赖覆盖项目 requirements 声明的 MaaFW 版本。
    prefer_active_venv_site_packages()
    from run_plan import MaaFWRunPlan  # type: ignore[no-redef]
    from runner import MaaFWDeviceConfig, MaaFWRunResult, MaaFWRunner  # type: ignore[no-redef]
else:
    from .environment import prefer_active_venv_site_packages

    prefer_active_venv_site_packages()
    from .run_plan import MaaFWRunPlan
    from .runner import MaaFWDeviceConfig, MaaFWRunResult, MaaFWRunner


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _emit_log(message: str) -> None:
    _emit({"type": "log", "message": message})


def main() -> int:
    if len(sys.argv) != 2:
        _emit({"type": "error", "message": "runner worker requires one job json path"})
        return 64

    job_path = Path(sys.argv[1])
    runner: MaaFWRunner | None = None
    try:
        payload = json.loads(job_path.read_text(encoding="utf-8"))
        plan = MaaFWRunPlan.model_validate(payload["plan"])
        device_config = MaaFWDeviceConfig.model_validate(payload["deviceConfig"])
        runner = MaaFWRunner(plan, send_log=_emit_log)
        result = runner.run(device_config)
        _emit({"type": "result", "data": result.model_dump(mode="json")})
        return 0 if result.success else 2
    except BaseException as exc:  # noqa: BLE001 - keep worker boundary explicit.
        result = MaaFWRunResult(
            success=False,
            projectName="",
            controllerName="",
            resourceName="",
            errorMessage=str(exc),
        )
        with suppress(Exception):
            _emit({"type": "result", "data": result.model_dump(mode="json")})
        _emit({"type": "error", "message": str(exc)})
        return 1
    finally:
        if runner is not None:
            with suppress(Exception):
                runner.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
