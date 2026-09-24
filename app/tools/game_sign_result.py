from collections.abc import Mapping

SKLAND_GAME_MAPPING = {
    "arknights": "明日方舟",
    "endfield": "终末地",
}


def build_skland_sign_results(
    raw_result: object,
    *,
    account_name: str,
    account_uid: str,
) -> list[dict[str, object]]:
    """将森空岛返回值归一化为游戏社区签到结果。"""
    results: list[dict[str, object]] = []
    status_mapping = {
        "成功": "成功",
        "重复": "已签到",
        "失败": "失败",
    }

    if not isinstance(raw_result, dict):
        return [
            {
                "account": f"{account_name}/森空岛",
                "account_uid": account_uid,
                "game": "森空岛",
                "platform": "森空岛",
                "status": "失败",
                "reward": "",
                "reason": "森空岛未返回可识别的签到结果",
            }
        ]

    if any(game_key in raw_result for game_key in SKLAND_GAME_MAPPING):
        for game_key, game_name in SKLAND_GAME_MAPPING.items():
            game_result = raw_result.get(game_key, {})
            if not isinstance(game_result, dict):
                results.append(
                    {
                        "account": f"{account_name}/森空岛",
                        "account_uid": account_uid,
                        "game": game_name,
                        "platform": "森空岛",
                        "status": "失败",
                        "reward": "",
                        "reason": f"{game_name}角色列表响应格式无效",
                    }
                )
                continue
            reward_map = game_result.get("奖励") or {}
            if not isinstance(reward_map, dict):
                reward_map = {}
            failures = game_result.get("失败", [])
            if game_result.get("总计") == 0 and failures:
                reason = str(failures[0])
                results.append(
                    {
                        "account": f"{account_name}/森空岛",
                        "account_uid": account_uid,
                        "game": game_name,
                        "platform": "森空岛",
                        "status": "失败",
                        "reward": "",
                        "reason": reason,
                    }
                )
                continue
            for source_status, status in status_mapping.items():
                for item in game_result.get(source_status, []):
                    account_label = item if isinstance(item, str) else str(item)
                    reward = str(reward_map.get(account_label) or "")
                    results.append(
                        {
                            "account": account_label,
                            "account_uid": account_uid,
                            "game": game_name,
                            "platform": "森空岛",
                            "status": status,
                            "reward": reward,
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


def merge_community_sign_result(
    game_result: Mapping[str, object],
    community_result: Mapping[str, object],
    *,
    include_reward: bool = True,
) -> dict[str, object]:
    """合并同一账号的游戏签到和社区打卡，失败与奖励均不能被覆盖。"""
    result = dict(game_result)
    signed_statuses = {"成功", "已签到"}
    game_status = str(game_result.get("status") or "失败")
    community_status = str(community_result.get("status") or "失败")
    if game_status in signed_statuses and community_status in signed_statuses:
        result["status"] = (
            "成功" if "成功" in (game_status, community_status) else "已签到"
        )
    else:
        reasons = [
            str(
                game_result.get("reason")
                or ("游戏签到失败" if game_status not in signed_statuses else "")
            ).strip()
        ]
        if community_status not in signed_statuses:
            reason = str(community_result.get("reason") or "签到失败")
            reasons.append(f"社区打卡：{reason}")
            if game_status in signed_statuses:
                reasons.insert(0, "游戏签到已完成")
                result["status"] = community_status
        else:
            reasons.append("社区打卡已完成")
        result["reason"] = "；".join(reason for reason in reasons if reason)
        result.pop("_completed", None)
    if include_reward:
        result["reward"] = "、".join(
            str(reward)
            for reward in (game_result.get("reward"), community_result.get("reward"))
            if reward
        )
    return result
