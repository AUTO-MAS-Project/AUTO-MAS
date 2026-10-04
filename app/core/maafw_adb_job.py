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

"""在独立子进程里对一台 ADB 设备跑一次 MaaFramework 任务（魔改 AVD 实例用）。

MaaFramework 在 MAS 进程里起的 adb 继承 MAS 的环境，只能落到 5037，又没法逐条命令加 ``-P``；
放进子进程，由父进程给它设 ``ANDROID_ADB_SERVER_PORT=<脚本专用端口>``，它起的 adb 就都走那里。

**以脚本方式执行**（``python <本文件>``），不经 ``app`` 包导入：不拉起 MAS 的配置、日志与事件循环，
只依赖标准库与 ``maa``。任务描述是一份 JSON，从 **stdin** 读（里面可能有账号密码，不能进命令行）：

``{"adb_path", "address", "screencap_methods", "input_methods", "config", "resource_dir",
"user_dir", "logging", "mode": "task" | "screencap", "entry", "pipeline_override", "secrets": [...]}``

输出：每行 ``LOG <文本>``（已把 ``secrets`` 里的值换成 ``***``），最后一行 ``RESULT <json>``。
退出码：0 成功，1 任务失败，2 连接 / 初始化失败，3 任务描述有误。
MaaFramework 自己的标准输出关掉（它会把 ``pipeline_override`` 原文、含密码打出来）；
``logging`` 为假时也不写 ``maafw.log``。
"""

import json
import sys
import time
from pathlib import Path

EXIT_OK, EXIT_TASK_FAILED, EXIT_INIT_FAILED, EXIT_BAD_JOB = 0, 1, 2, 3


def mask(text: str, secrets: list[str]) -> str:
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "***")
    return text


def main() -> int:
    try:
        job = json.loads(sys.stdin.read())
    except ValueError as e:
        print(
            f"RESULT {json.dumps({'ok': False, 'error': f'bad job: {e}'})}", flush=True
        )
        return EXIT_BAD_JOB
    secrets = [str(s) for s in job.get("secrets") or [] if s]

    def log(text: str) -> None:
        print(f"LOG {mask(str(text), secrets)}", flush=True)

    def result(code: int, **fields) -> int:
        fields = {
            k: mask(v, secrets) if isinstance(v, str) else v for k, v in fields.items()
        }
        print(f"RESULT {json.dumps(fields, ensure_ascii=False)}", flush=True)
        return code

    from maa.controller import AdbController
    from maa.custom_action import CustomAction
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.toolkit import Toolkit

    user_dir = Path(job["user_dir"])
    user_dir.mkdir(parents=True, exist_ok=True)
    Toolkit.init_option(
        user_dir,
        {"logging": bool(job.get("logging")), "save_draw": False, "stdout_level": 0},
    )
    controller = AdbController(
        job["adb_path"],
        job["address"],
        int(job["screencap_methods"]),
        int(job["input_methods"]),
        job.get("config") or {},
    )
    started = time.perf_counter()
    if not controller.post_connection().wait().succeeded:
        return result(EXIT_INIT_FAILED, ok=False, error="连接设备失败")
    log(f"已连接 {job['address']}（{time.perf_counter() - started:.2f} 秒）")

    if job.get("mode") == "screencap":
        times = []
        for _ in range(int(job.get("shots") or 10)):
            begin = time.perf_counter()
            if not controller.post_screencap().wait().succeeded:
                return result(EXIT_TASK_FAILED, ok=False, error="截图失败")
            times.append((time.perf_counter() - begin) * 1000)
        image = controller.cached_image
        times.sort()
        return result(
            EXIT_OK,
            ok=True,
            shape=list(image.shape) if image is not None else None,
            screencap_ms={
                "n": len(times),
                "p50": round(times[len(times) // 2], 2),
                "max": round(times[-1], 2),
            },
        )

    resource = Resource()

    class _NoOp(CustomAction):
        def run(self, context, argv) -> bool:
            return True

    # MAS 资源里的两个自定义动作（app/core/maa_manager.py），这里同样是空动作
    resource.register_custom_action("DisableLog", _NoOp())
    resource.register_custom_action("EnableLog", _NoOp())
    if not resource.post_bundle(job["resource_dir"]).wait().succeeded:
        return result(EXIT_INIT_FAILED, ok=False, error="加载 MaaFW 资源失败")
    tasker = Tasker()
    tasker.bind(resource, controller)
    if not tasker.inited:
        return result(EXIT_INIT_FAILED, ok=False, error="无法初始化 MaaFW tasker")
    log(f"开始任务 {job['entry']}")
    task_job = tasker.post_task(job["entry"], job.get("pipeline_override") or {})
    task_job.wait()
    if task_job.failed:
        return result(EXIT_TASK_FAILED, ok=False, error="任务执行失败")
    return result(EXIT_OK, ok=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 - 一行结果交回父进程，不带堆栈（可能含任务参数）
        print(
            f"RESULT {json.dumps({'ok': False, 'error': f'{type(e).__name__}'})}",
            flush=True,
        )
        sys.exit(EXIT_INIT_FAILED)
