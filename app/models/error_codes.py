#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3
#   of the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""界面文案用的稳定错误码。

失败响应里的 message 是后端拼好的中文，不随界面语言变化；errorCode 不随语言变化，
前端按 `t('apiErrors.' + errorCode, errorParams)` 取当前语言的文案，message 只作兜底
（未知错误、日志、取不到词条时）。

命名：`<域><动作><Outcome>`，camelCase，只用 ASCII 字母数字。Outcome 限定：

    Failed      通用失败，只展示
    NotFound    目标不存在，提示刷新列表
    Invalid     参数或格式不合法，高亮输入项
    Busy        正在执行中，提示稍后重试
    Expired     时效性失效，引导重新获取
    Unavailable 依赖不可用，提示检查环境
    Rejected    业务规则拒绝，要展示原因

码值一经发布不能改名（改了旧版前端的词表就查不到、会静默回退中文）；确需调整时新旧
并存一个版本。新增码时同时在三语词表 `apiErrors` 下加同名词条。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.schema import OutBase


class ErrorCode:
    """已发布错误的码值。新增时按域分组，并同步补三语词条。"""

    # 脚本与账号
    SCRIPT_LOAD_FAILED = "scriptLoadFailed"
    SCRIPT_SAVE_FAILED = "scriptSaveFailed"
    SCRIPT_ADD_FAILED = "scriptAddFailed"
    SCRIPT_DELETE_FAILED = "scriptDeleteFailed"
    SCRIPT_MOD_AVD_BINDING_REJECTED = "scriptModAvdBindingRejected"
    USER_ADD_FAILED = "userAddFailed"
    USER_SAVE_FAILED = "userSaveFailed"
    USER_LIST_FAILED = "userListFailed"

    # 设置与通知
    SETTINGS_LOAD_FAILED = "settingsLoadFailed"
    SETTINGS_SAVE_FAILED = "settingsSaveFailed"
    SETTING_NOTIFY_CHANNEL_MISSING = "settingNotifyChannelMissing"
    SETTING_NOTIFY_SEND_FAILED = "settingNotifySendFailed"

    # 模拟器
    EMULATOR_OPERATE_FAILED = "emulatorOperateFailed"

    # 队列与计划
    QUEUE_ITEM_ADD_FAILED = "queueItemAddFailed"
    QUEUE_ITEM_UPDATE_FAILED = "queueItemUpdateFailed"
    QUEUE_ITEM_DELETE_FAILED = "queueItemDeleteFailed"
    PLAN_ADD_FAILED = "planAddFailed"
    PLAN_UPDATE_FAILED = "planUpdateFailed"
    PLAN_DELETE_FAILED = "planDeleteFailed"

    # 游戏社区签到
    GAME_SIGN_BUSY = "gameSignBusy"
    GAME_SIGN_FAILED = "gameSignFailed"

    # 更新
    UPDATE_DOWNLOAD_BUSY = "updateDownloadBusy"
    UPDATE_NO_ACTIVE_DOWNLOAD = "updateNoActiveDownload"
    UPDATE_SOURCE_SWITCH_UNAVAILABLE = "updateSourceSwitchUnavailable"
    UPDATE_DOWNLOAD_CANCEL_FAILED = "updateDownloadCancelFailed"
    UPDATE_SOURCE_SWITCH_FAILED = "updateSourceSwitchFailed"


def fail(
    error_code: str,
    message: str,
    *,
    code: int = 500,
    status: str = "error",
    params: Optional[Dict[str, Any]] = None,
) -> OutBase:
    """构造带稳定错误码的失败响应；message 仍写中文，供兜底与日志使用。"""

    return OutBase(
        code=code,
        status=status,
        message=message,
        errorCode=error_code,
        errorParams=params,
    )
