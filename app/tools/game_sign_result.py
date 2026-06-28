SKLAND_GAME_MAPPING = {
    "arknights": "明日方舟",
    "endfield": "终末地",
}


def build_skland_sign_results(
    raw_result: dict,
    *,
    account_name: str,
    account_uid: str,
) -> list[dict]:
    """将森空岛返回值归一化为游戏社区签到结果。"""
    results = []
    status_mapping = {
        "成功": "成功",
        "重复": "已签到",
        "失败": "失败",
    }

    if any(game_key in raw_result for game_key in SKLAND_GAME_MAPPING):
        for game_key, game_name in SKLAND_GAME_MAPPING.items():
            game_result = raw_result.get(game_key, {})
            for source_status, status in status_mapping.items():
                for item in game_result.get(source_status, []):
                    results.append(
                        {
                            "account": item if isinstance(item, str) else str(item),
                            "account_uid": account_uid,
                            "game": game_name,
                            "platform": "森空岛",
                            "status": status,
                            "reward": "",
                            "reason": "签到失败" if status == "失败" else "",
                        }
                    )
        return results

    failures = raw_result.get("失败", [])
    reason = str(failures[0]) if failures else "未返回可识别的签到结果"
    return [
        {
            "account": f"{account_name}/森空岛",
            "account_uid": account_uid,
            "game": "森空岛",
            "platform": "森空岛",
            "status": "失败",
            "reward": "",
            "reason": reason,
        }
    ]
