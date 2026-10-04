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


import asyncio
import os
from contextlib import suppress
from pathlib import Path
from typing import Any

from app.models.emulator import DeviceInfo, DeviceRef, DeviceStatus
from app.utils import get_logger

logger = get_logger("星穹铁道模拟器登录")


async def login(
    emulator_info: DeviceInfo,
    package_name: str,
    id: str,
    password: str,
    device_ref: DeviceRef | None = None,
) -> bool:
    """
    模拟器登录星穹铁道

    Args:
        emulator_info: 模拟器信息
        package_name: 星穹铁道包名
        id: 账号ID
        password: 账号密码
        device_ref: 设备在 Emulator 2.0 里的归属；官方模拟器实例改在独立子进程里跑
            （见 :func:`_login_in_subprocess`），其余模拟器照旧在 MAS 进程里跑

    Returns:
        bool: 登录是否成功
    """

    if emulator_info.status != DeviceStatus.ONLINE:
        logger.warning(f"模拟器{emulator_info.title}不在线，无法登录")
        return False

    logger.info(f"开始登录: {emulator_info.title} - {package_name}")

    from app.core import Config, MaaFWManager

    if id == "":
        logger.info("未输入账号，将跳过账号切换，等待游戏加载")
        pipeline_override = {
            "等待加载完成[StarRailEmulator]": {
                "action": {"param": {"package": package_name}}
            }
        }
    elif (package_name == "com.miHoYo.hkrpg" and "*" in id) or password == "":
        logger.info("账号密码不完整，禁用通过输入账号密码登录")
        pipeline_override = {
            "切换账号[StarRailEmulator]": {
                "action": {"param": {"package": package_name}}
            },
            "启动游戏[StarRailEmulator]": {
                "action": {"param": {"package": package_name}}
            },
            "Bilibili隐私政策[StarRailEmulator]": {
                "enabled": Config.get("Function", "IfAgreeBilibili")
            },
            "下滑账号列表[StarRailEmulator]": {"on_error": []},
            "下滑账号列表-B服[StarRailEmulator]": {"on_error": []},
            "识别登录下拉框禁用[StarRailEmulator]": {"on_error": []},
            "选中账号[StarRailEmulator]": {
                "recognition": {
                    "param": {"expected": [f"{id[:3]}[a-zA-Z0-9 *]*{id[-2:]}"]}
                }
            },
            "验证当前账号[StarRailEmulator]": {
                "recognition": {
                    "param": {"expected": [f"{id[:3]}[a-zA-Z0-9 *]*{id[-2:]}"]}
                }
            },
            "选中账号-B服[StarRailEmulator]": {
                "recognition": {
                    "param": {
                        "expected": [id.split("|")[0].strip() if "|" in id else id],
                        "model": "en_us" if id.isascii() else "zh_cn",
                    }
                }
            },
        }
    else:
        pipeline_override = {
            "切换账号[StarRailEmulator]": {
                "action": {"param": {"package": package_name}}
            },
            "启动游戏[StarRailEmulator]": {
                "action": {"param": {"package": package_name}}
            },
            "Bilibili隐私政策[StarRailEmulator]": {
                "enabled": Config.get("Function", "IfAgreeBilibili")
            },
            "选中账号[StarRailEmulator]": {
                "recognition": {
                    "param": {"expected": [f"{id[:3]}[a-zA-Z0-9 *]*{id[-2:]}"]}
                }
            },
            "验证当前账号[StarRailEmulator]": {
                "recognition": {
                    "param": {"expected": [f"{id[:3]}[a-zA-Z0-9 *]*{id[-2:]}"]}
                }
            },
            "选中账号-B服[StarRailEmulator]": {
                "recognition": {
                    "param": {
                        "expected": [id.split("|")[0].strip() if "|" in id else id],
                        "model": "en_us" if id.isascii() else "zh_cn",
                    }
                }
            },
            "输入账号[StarRailEmulator]": {"action": {"param": {"input_text": id}}},
            "输入密码[StarRailEmulator]": {
                "action": {"param": {"input_text": password}}
            },
            "输入账号-B服[StarRailEmulator]": {
                "action": {
                    "param": {
                        "input_text": id.split("|")[1].strip() if "|" in id else id
                    }
                }
            },
            "输入密码-B服[StarRailEmulator]": {
                "action": {"param": {"input_text": password}}
            },
        }

    entry = "切换账号[StarRailEmulator]" if id else "等待加载完成[StarRailEmulator]"
    if device_ref is not None and device_ref.emulator_type == "avd":
        return await _login_in_subprocess(
            emulator_info, device_ref, entry, pipeline_override, id, password
        )

    try:
        tasker = await MaaFWManager.get_adb_tasker(emulator_info)
    except Exception as e:
        logger.warning(f"获取模拟器{emulator_info.title}的ADB控制器时出现异常: {e}")
        return False

    try:
        await MaaFWManager.do_job(
            tasker.post_task(
                (
                    "切换账号[StarRailEmulator]"
                    if id
                    else "等待加载完成[StarRailEmulator]"
                ),
                pipeline_override,
            )
        )
        logger.success(f"模拟器{emulator_info.title}登录成功")
        await asyncio.sleep(10)  # 等待资源释放
        return True
    except Exception as e:
        error_msg = str(e)
        if id:
            error_msg = error_msg.replace(id, "id***")
        if password:
            error_msg = error_msg.replace(password, "password***")
        logger.warning(f"模拟器{emulator_info.title}切换账号时出现异常: {error_msg}")
        return False
    except asyncio.CancelledError:
        with suppress(Exception):
            await MaaFWManager.do_job(tasker.post_stop())
        raise


def login_secrets(id: str, password: str) -> list[str]:
    """登录子进程的日志与结果里要打码的值：账号、密码，以及 B 服「显示名|账号」的两段。"""
    values = [id, password]
    if "|" in id:
        values += [part.strip() for part in id.split("|")]
    return [value for value in values if value]


def build_login_job(
    device: Any,
    entry: str,
    pipeline_override: dict,
    secrets: list[str],
    *,
    resource_dir: Path,
    user_dir: Path,
) -> dict[str, Any]:
    """登录子进程的任务描述（经 stdin 传，不进命令行）。不写 MaaFW 日志文件：override 里有密码。"""
    return {
        "adb_path": str(device.adb_path),
        "address": device.address,
        "screencap_methods": int(device.screencap_methods),
        "input_methods": int(device.input_methods),
        "config": device.config,
        "resource_dir": str(resource_dir),
        "user_dir": str(user_dir),
        "logging": False,
        "mode": "task",
        "entry": entry,
        "pipeline_override": pipeline_override,
        "secrets": secrets,
    }


async def _login_in_subprocess(
    emulator_info: DeviceInfo,
    device_ref: DeviceRef,
    entry: str,
    pipeline_override: dict,
    id: str,
    password: str,
) -> bool:
    """官方模拟器实例：在独立子进程里跑登录任务。

    MaaFramework 在 MAS 进程里起的 adb 继承 MAS 的环境，只能落到 5037（会和雷电 / MuMu 自带的旧版
    adb 互杀 server），又没法逐条命令加 ``-P``；子进程带 ``ANDROID_ADB_SERVER_PORT=<脚本专用端口>``，
    它起的 adb 都走那里。解释器、maa binding、资源与 ``pipeline_override`` 都和进程内同一份；
    账号密码经 stdin 传入，日志与结果里一律打码。
    """
    from app.core import MaaFWManager
    from app.core.maafw_adb_subprocess import mask, run_adb_job
    from app.utils import resource_path
    from app.utils.emulator2.avd import host
    from app.utils.emulator2.avd.components import (
        root_from_manager_exe,
        script_adb_env,
    )

    secrets = login_secrets(id, password)
    try:
        device = await MaaFWManager.convert_adb(emulator_info, device_ref)
    except Exception as e:
        logger.warning(f"获取模拟器{emulator_info.title}的ADB设备时出现异常: {e}")
        return False
    root = root_from_manager_exe(device_ref.manager_path)
    env = dict(os.environ)
    env.update(script_adb_env(root))
    # 脚本专用 adb server 先由 MAS 以脱离方式起好，子进程里的 adb 不去顺手拉起（会继承输出管道）
    with suppress(Exception):
        await host.ensure_script_adb_server(root)
    job = build_login_job(
        device,
        entry,
        pipeline_override,
        secrets,
        resource_dir=resource_path("MaaFW"),
        user_dir=Path.cwd() / "debug" / "maafw-adb-job",
    )
    logger.info(
        f"模拟器{emulator_info.title}是官方模拟器实例，在独立进程里登录"
        f"（adb server 端口 {env['ANDROID_ADB_SERVER_PORT']}）"
    )
    try:
        outcome = await run_adb_job(
            job,
            env=env,
            # run_adb_job 已打过码，这里再打一次：日志出口不信任上游
            on_log=lambda line: logger.info(f"[登录进程] {mask(line, secrets)}"),
        )
    except Exception as e:
        logger.warning(
            f"模拟器{emulator_info.title}登录进程出现异常: {type(e).__name__}"
        )
        return False
    if outcome.ok:
        logger.success(f"模拟器{emulator_info.title}登录成功")
        return True
    logger.warning(
        f"模拟器{emulator_info.title}切换账号时出现异常: "
        f"{outcome.result.get('error') or f'登录进程退出码 {outcome.returncode}'}"
    )
    return False
