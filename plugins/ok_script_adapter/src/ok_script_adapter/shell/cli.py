#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ok-script 控制台壳命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .manifest import OkProjectInspectError, inspect_ok_project, save_manifest
from .runtime import (
    AUTO_PROTOCOL,
    SUPPORTED_PROTOCOLS,
    OkConfigStore,
    OkShellRunner,
    OkShellRuntimeError,
)

EXIT_OK = 0
EXIT_PROJECT_ERROR = 3
EXIT_RUN_ERROR = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ok-script-shell",
        description="通过控制台解析、配置并运行 ok-script 衍生项目",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="解析项目 Manifest")
    _add_project_arguments(inspect_parser)
    inspect_parser.add_argument("--save", type=Path, help="保存 Manifest JSON")

    tasks_parser = subparsers.add_parser("tasks", help="列出项目任务")
    _add_project_arguments(tasks_parser)

    config_parser = subparsers.add_parser("config", help="查看或修改 JSON 配置")
    _add_project_arguments(config_parser)
    config_subparsers = config_parser.add_subparsers(
        dest="config_command",
        required=True,
    )
    config_subparsers.add_parser("list", help="列出配置文件")
    config_get = config_subparsers.add_parser("get", help="读取配置")
    config_get.add_argument("name")
    config_set = config_subparsers.add_parser("set", help="写入配置")
    config_set.add_argument("name")
    input_group = config_set.add_mutually_exclusive_group()
    input_group.add_argument("--json", dest="json_text", help="JSON 对象文本")
    input_group.add_argument("--file", type=Path, help="从文件读取 JSON 对象")
    config_set.add_argument(
        "--replace",
        action="store_true",
        help="替换整个配置，不与已有配置合并",
    )

    run_parser = subparsers.add_parser("run", help="运行一个项目任务")
    _add_project_arguments(run_parser)
    run_parser.add_argument("task", help="任务类名、标签或序号")
    run_parser.add_argument(
        "--protocol",
        choices=(AUTO_PROTOCOL, *SUPPORTED_PROTOCOLS),
        default=AUTO_PROTOCOL,
    )
    run_parser.add_argument("--timeout", type=_positive_float)
    run_parser.add_argument("--no-exit", action="store_true")
    run_parser.add_argument("--events", type=Path, help="追加保存 JSONL 运行事件")
    return parser


def _add_project_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project", type=Path, help="ok-script 衍生项目根目录")
    parser.add_argument("--python", type=Path, help="覆盖项目 Python 解释器")


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须大于 0")
    return parsed


def _read_config_input(args: argparse.Namespace) -> dict[str, Any]:
    if args.file is not None:
        try:
            text = args.file.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise OkShellRuntimeError(f"JSON 输入文件读取失败: {exc}") from exc
    elif args.json_text is not None:
        text = args.json_text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        raise OkShellRuntimeError("请使用 --json、--file 或标准输入提供 JSON 对象")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OkShellRuntimeError(f"JSON 输入无效: {exc}") from exc
    if not isinstance(data, dict):
        raise OkShellRuntimeError("JSON 输入顶层必须是对象")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = inspect_ok_project(
            args.project,
            python_executable=args.python,
        )
        if args.command == "inspect":
            if args.save is not None:
                save_manifest(manifest, args.save)
            print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))
            return EXIT_OK

        if args.command == "tasks":
            print(
                json.dumps(
                    [task.to_dict() for task in manifest.tasks],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return EXIT_OK

        if args.command == "config":
            store = OkConfigStore(manifest.config_dir)
            if args.config_command == "list":
                print(json.dumps(list(store.list()), ensure_ascii=False, indent=2))
            elif args.config_command == "get":
                print(json.dumps(store.read(args.name), ensure_ascii=False, indent=2))
            else:
                path = store.write(
                    args.name,
                    _read_config_input(args),
                    merge=not args.replace,
                )
                print(path)
            return EXIT_OK

        runner = OkShellRunner(manifest, event_path=args.events)
        result = runner.run(
            args.task,
            protocol=args.protocol,
            exit_after=not args.no_exit,
            timeout=args.timeout,
        )
        if result.timed_out:
            print("任务运行超时", file=sys.stderr)
            return EXIT_RUN_ERROR
        if result.return_code != 0:
            print(
                f"任务进程异常退出: {result.return_code}",
                file=sys.stderr,
            )
            return EXIT_RUN_ERROR
        return EXIT_OK
    except OkProjectInspectError as exc:
        print(f"项目解析失败: {exc}", file=sys.stderr)
        return EXIT_PROJECT_ERROR
    except OkShellRuntimeError as exc:
        print(f"ok-script 控制台壳错误: {exc}", file=sys.stderr)
        return EXIT_RUN_ERROR
    except KeyboardInterrupt:
        print("任务已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
