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
from contextlib import suppress


from app.models.emulator import DeviceInfo, DeviceStatus
from app.utils import get_logger

logger = get_logger("星穹铁道模拟器登录")


async def login(
    emulator_info: DeviceInfo, package_name: str, id: str, password: str
) -> bool:
    """
    模拟器登录星穹铁道

    Args:
        emulator_info: 模拟器信息
        package_name: 星穹铁道包名
        id: 账号ID
        password: 账号密码

    Returns:
        bool: 登录是否成功
    """

    if emulator_info.status != DeviceStatus.ONLINE:
        logger.error(f"模拟器{emulator_info.title}不在线，无法登录")
        return False

    logger.info(f"开始登录: {emulator_info.title} - {package_name}")

    from app.core import Config, MaaFWManager

    if (package_name == "com.miHoYo.hkrpg" and "*" in id) or password == "":
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
                    "param": {"expected": [f"^{id[:3]}[a-zA-Z0-9 *]*{id[-2:]}$"]}
                }
            },
            "验证当前账号[StarRailEmulator]": {
                "recognition": {
                    "param": {"expected": [f"^{id[:3]}[a-zA-Z0-9 *]*{id[-2:]}$"]}
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
                    "param": {"expected": [f"^{id[:3]}[a-zA-Z0-9 *]*{id[-2:]}$"]}
                }
            },
            "验证当前账号[StarRailEmulator]": {
                "recognition": {
                    "param": {"expected": [f"^{id[:3]}[a-zA-Z0-9 *]*{id[-2:]}$"]}
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

    try:
        tasker = await MaaFWManager.get_adb_tasker(emulator_info)
    except Exception as e:
        logger.error(f"获取模拟器{emulator_info.title}的ADB控制器时出现异常: {e}")
        return False

    try:
        await MaaFWManager.do_job(
            tasker.post_task("切换账号[StarRailEmulator]", pipeline_override)
        )
        logger.success(f"模拟器{emulator_info.title}登录成功")
        del tasker
        await asyncio.sleep(10)  # 等待资源释放
        return True
    except Exception as e:
        errorMsg = str(e)
        if id:
            errorMsg = errorMsg.replace(id, "id***")
        if password:
            errorMsg = errorMsg.replace(password, "password***")
        logger.error(f"模拟器{emulator_info.title}切换账号时出现异常: {errorMsg}")
        del tasker
        return False
    except asyncio.CancelledError:
        with suppress(Exception):
            await MaaFWManager.do_job(tasker.post_stop())
            del tasker
        raise
