#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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

from functools import cache

from app.core import Config
from app.core.notify import (
    DispatchResult,
    NotifyTarget,
    dispatch,
    global_target,
    statistic_targets,
    user_target,
)
from app.models.config import MaaUserConfig
from app.models.notification import (
    NotificationImage,
    NotifyPayload,
    image_reference,
)
from app.task.notify_core import push_proxy_result
from app.utils import get_logger
from app.utils.paths import resource_path

logger = get_logger("MAA 通知工具")

# MAA 的签名只空一行, 与其余脚本不同
SIGNATURE_SEP = "\n"

# 喜报图片同时提供本地资源和官网 URL；缺少本地文件时，仍可在支持 URL 的表达中展示。
SIX_STAR_IMAGE_ID = "maa-six-star"
SIX_STAR_IMAGE_URL = "https://api.auto-mas.top/file/Resource/six_star.png"


@cache
def _six_star_image() -> bytes | None:
    try:
        return resource_path("images", "notification", "six_star.png").read_bytes()
    except OSError as exc:
        logger.warning(f"读取喜报配图失败，通知将使用可用的替代图片来源: {exc}")
        return None


def _statistic_text(message: dict) -> str:
    """拼装掉落、招募与养成达成统计的纯文本正文。"""

    formatted = []
    if "drop_statistics" in message:
        for stage, items in message["drop_statistics"].items():
            formatted.append(f"掉落统计（{stage}）:")
            for item, quantity in items.items():
                formatted.append(f"  {item}: {quantity}")
    drop_text = "\n".join(formatted)

    formatted = ["招募统计:"]
    if "recruit_statistics" in message:
        for star, count in message["recruit_statistics"].items():
            formatted.append(f"  {star}: {count}")
    recruit_text = "\n".join(formatted)

    # 本轮有干员达成养成目标时附一行；无则不占位
    cultivate_text = (
        f"养成达成: {message['cultivate_achievement']}\n"
        if message.get("cultivate_achievement")
        else ""
    )

    return (
        f"开始时间: {message['start_time']}\n"
        f"结束时间: {message['end_time']}\n"
        f"理智剩余: {message.get('sanity', '未知')}\n"
        f"回复时间: {message.get('sanity_full_at', '未知')}\n"
        f"MAA执行结果: {message['maa_result']}\n"
        f"{cultivate_text}"
        f"{recruit_text}\n"
        f"{drop_text}"
    )


def _six_star_targets(user_config: MaaUserConfig | None) -> list[NotifyTarget]:
    """公招六星喜报的推送目标, 全局与用户各有独立开关。"""

    targets = []
    if Config.get("Notify", "IfSendSixStar"):
        targets.append(global_target())
    if (
        user_config is not None
        and user_config.get("Notify", "Enabled")
        and user_config.get("Notify", "IfSendSixStar")
    ):
        targets.append(user_target(user_config))
    return targets


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    user_config: MaaUserConfig | None,
    task_info: object | None = None,
) -> DispatchResult:
    """通过所有渠道推送通知; 返回分发的实际尝试/成功/失败结果。"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果":
        return await push_proxy_result(
            title=title,
            message=message,
            task_info=task_info,
            result_template="MAA_result.html",
            signature_sep=SIGNATURE_SEP,
        )

    if mode == "统计信息":
        template = Config.notify_env.get_template("MAA_statistics.html")

        return await dispatch(
            NotifyPayload(
                title=title,
                text=_statistic_text(message),
                html=template.render(message),
                signature_sep=SIGNATURE_SEP,
            ),
            statistic_targets(user_config),
        )

    if mode == "公招六星":
        # 喜报正文是固定文案, message 只用于渲染 HTML
        template = Config.notify_env.get_template("MAA_six_star.html")

        image = _six_star_image()

        return await dispatch(
            NotifyPayload(
                title=title,
                text="好羡慕~",
                markdown=f"好羡慕~\n\n![喜报]({image_reference(SIX_STAR_IMAGE_ID)})",
                html=template.render(message),
                signature_sep=SIGNATURE_SEP,
                images=(
                    NotificationImage(
                        id=SIX_STAR_IMAGE_ID,
                        data=image,
                        url=SIX_STAR_IMAGE_URL,
                        alt="喜报",
                    ),
                ),
            ),
            _six_star_targets(user_config),
        )

    return DispatchResult()
