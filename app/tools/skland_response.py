def is_skland_already_signed(response: dict) -> bool:
    """判断森空岛签到响应是否表示今日已签到。"""
    message = str(response.get("message", ""))
    return response.get("code") == 10001 or any(
        marker in message
        for marker in ("请勿重复签到", "Please do not sign in again!")
    )
