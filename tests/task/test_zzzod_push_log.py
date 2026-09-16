import unittest

from app.log_box.logtype import LogType
from app.task.ZzzOd.push_log import make_zzzod_resolve

# 结果元组含采集时间戳；(日志类型, 文本, 时间戳)
T = 1000.0


class ZzzodResolveTest(unittest.TestCase):
    """make_zzzod_resolve 后处理纯逻辑：账号段归属、终态聚合、剩余体力独立行。"""

    def test_battery_is_standalone_trailing_line(self) -> None:
        # 体力刷本带电量：节点行照常输出（不带后缀），电量在报告末尾独立成行
        resolve = make_zzzod_resolve({"体力刷本", "每日签到"}, {})
        results = [
            (LogType.NORMAL, "SEG:1", T),
            (LogType.NORMAL, "OK:每日签到", T),
            (LogType.NORMAL, "OK:体力刷本|🔋120", T),
        ]
        self.assertEqual(
            [text for _, text, _ in resolve(results)],
            ["✅ 成功: 每日签到", "✅ 成功: 体力刷本", "🔋 剩余体力: 120"],
        )

    def test_multi_account_battery_follows_account(self) -> None:
        # 多账号段：节点行与剩余体力行都带账号前缀，各自归属；同账号取最后一次
        resolve = make_zzzod_resolve({"体力刷本", "每日签到"}, {1: "寒风", 2: "凰北月"})
        results = [
            (LogType.NORMAL, "SEG:1", T),
            (LogType.NORMAL, "OK:体力刷本|🔋32", T),
            (LogType.NORMAL, "SEG:2", T),
            (LogType.NORMAL, "OK:体力刷本|🔋120", T),
            (LogType.NORMAL, "OK:每日签到", T),
        ]
        self.assertEqual(
            [text for _, text, _ in resolve(results)],
            [
                "【寒风】✅ 成功: 体力刷本",
                "【凰北月】✅ 成功: 体力刷本",
                "【凰北月】✅ 成功: 每日签到",
                "【寒风】🔋 剩余体力: 32",
                "【凰北月】🔋 剩余体力: 120",
            ],
        )

    def test_fail_reason_and_aux_command_filter(self) -> None:
        # 失败带原因经（原因）渲染；辅助指令（不在应用名集合）不进报告
        resolve = make_zzzod_resolve({"影院约会"}, {})
        results = [
            (LogType.NORMAL, "SEG:1", T),
            (LogType.NORMAL, "OK:返回大世界", T),
            (LogType.NORMAL, "FAIL:影院约会|超时", T),
        ]
        self.assertEqual(
            [text for _, text, _ in resolve(results)],
            ["❌ 失败: 影院约会（超时）"],
        )

    def test_notify_fail_is_summary_signal_dropped(self) -> None:
        # 「通知」失败 = 上游「本轮存在失败」汇总信号（消息已发出），剔除不展示；
        # 真实失败节点照常输出；「通知」成功仍正常展示
        resolve = make_zzzod_resolve({"丽都城募", "通知"}, {})
        results = [
            (LogType.NORMAL, "SEG:1", T),
            (LogType.NORMAL, "FAIL:丽都城募|找不到 丽都城募", T),
            (LogType.NORMAL, "FAIL:通知|失败", T),
            (LogType.NORMAL, "OK:通知", T),
        ]
        self.assertEqual(
            [text for _, text, _ in resolve(results)],
            ["❌ 失败: 丽都城募（找不到 丽都城募）", "✅ 成功: 通知"],
        )

    def test_retry_round_keeps_last_state_and_battery(self) -> None:
        # MAS 重试轮：同节点与同账号电量都取最后一次
        resolve = make_zzzod_resolve({"体力刷本"}, {1: "寒风"})
        results = [
            (LogType.NORMAL, "SEG:1", 1.0),
            (LogType.NORMAL, "OK:体力刷本|🔋10", 2.0),
            (LogType.NORMAL, "SEG:1", 3.0),
            (LogType.NORMAL, "OK:体力刷本|🔋99", 4.0),
        ]
        self.assertEqual(
            resolve(results),
            [
                (LogType.NORMAL, "✅ 成功: 体力刷本", 4.0),
                (LogType.NORMAL, "🔋 剩余体力: 99", 4.0),
            ],
        )


if __name__ == "__main__":
    unittest.main()
