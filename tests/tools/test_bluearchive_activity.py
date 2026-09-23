#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""碧蓝档案活动排期判定的纯逻辑回归测试。

只覆盖判定本身：调度侧据此在「活动期间配置」与「默认配置」之间二选一，
判错会让用户在活动期间跑到日常配置（或反过来），因此边界必须写死。
接口取数失败退回默认行为属于功能边界，不在本文件覆盖。
"""

from app.tools.bluearchive_activity import collect_activities, has_running_activity_in

## 判定函数只认这两个字段，时间一律是 Unix 秒
NOW = 1_700_000_000


def activity(start: float, end: float, item_type: str = "Event") -> dict:
    """构造一条 Kivo 时间轴条目"""

    return {"type": item_type, "start_time": start, "end_time": end}


class TestHasRunningActivityIn:
    """时间轴 → 当前是否有进行中的活动"""

    def test_running_activity_is_detected(self) -> None:
        assert has_running_activity_in([activity(NOW - 100, NOW + 100)], NOW) is True

    def test_upcoming_activity_is_not_running(self) -> None:
        assert has_running_activity_in([activity(NOW + 100, NOW + 200)], NOW) is False

    def test_ended_activity_is_not_running(self) -> None:
        assert has_running_activity_in([activity(NOW - 200, NOW - 100)], NOW) is False

    def test_start_boundary_counts_as_running(self) -> None:
        assert has_running_activity_in([activity(NOW, NOW + 100)], NOW) is True

    def test_end_boundary_does_not_count_as_running(self) -> None:
        assert has_running_activity_in([activity(NOW - 100, NOW)], NOW) is False

    def test_one_running_activity_is_enough(self) -> None:
        timeline = [
            activity(NOW - 500, NOW - 400),
            activity(NOW + 100, NOW + 200),
            activity(NOW - 100, NOW + 100),
        ]
        assert has_running_activity_in(timeline, NOW) is True

    def test_other_types_are_ignored(self) -> None:
        """卡池、掉落加倍、维护等分类不算活动"""

        timeline = [
            activity(NOW - 100, NOW + 100, item_type="Gacha"),
            activity(NOW - 100, NOW + 100, item_type="Campaign"),
        ]
        assert has_running_activity_in(timeline, NOW) is False

    def test_items_without_numeric_time_are_skipped(self) -> None:
        timeline = [
            {"type": "Event", "start_time": "2026-01-01", "end_time": None},
            {"type": "Event"},
            activity(NOW + 100, NOW + 200),
        ]
        assert has_running_activity_in(timeline, NOW) is False

    def test_empty_timeline(self) -> None:
        assert has_running_activity_in([], NOW) is False


def titled_activity(
    start: float, end: float, title: str = "活动", item_type: str = "Event"
) -> dict:
    """构造一条带标题的时间轴条目（界面要展示活动名）"""

    return {"type": item_type, "title": title, "start_time": start, "end_time": end}


class TestCollectActivities:
    """挑出进行中的活动与下一个未开始的活动"""

    def test_running_and_upcoming(self) -> None:
        timeline = [
            titled_activity(NOW - 100, NOW + 100, title="进行中"),
            titled_activity(NOW + 200, NOW + 300, title="下一个"),
        ]

        running, upcoming = collect_activities(timeline, NOW)

        assert running is not None and running.name == "进行中"
        assert upcoming is not None and upcoming.name == "下一个"

    def test_no_running_returns_next(self) -> None:
        running, upcoming = collect_activities(
            [titled_activity(NOW + 200, NOW + 300, title="下一个")], NOW
        )

        assert running is None
        assert upcoming is not None and upcoming.name == "下一个"

    def test_running_prefers_earliest_end(self) -> None:
        """同时有几场进行中时取最早结束的那场，与首页卡片的取值口径一致"""
        timeline = [
            titled_activity(NOW - 50, NOW + 300, title="晚结束"),
            titled_activity(NOW - 200, NOW + 100, title="早结束"),
        ]

        running, _ = collect_activities(timeline, NOW)

        assert running is not None and running.name == "早结束"

    def test_upcoming_prefers_earliest_start(self) -> None:
        timeline = [
            titled_activity(NOW + 500, NOW + 600, title="更晚"),
            titled_activity(NOW + 200, NOW + 300, title="更早"),
        ]

        _, upcoming = collect_activities(timeline, NOW)

        assert upcoming is not None and upcoming.name == "更早"

    def test_same_title_keeps_latest_end(self) -> None:
        """同一活动被拆成多条（活动本体与介绍 PV）时保留结束最晚的那条"""

        timeline = [
            titled_activity(NOW - 100, NOW + 50, title="活动"),
            titled_activity(NOW - 100, NOW + 300, title="活动"),
        ]

        running, _ = collect_activities(timeline, NOW)

        assert running is not None and running.end_time == NOW + 300

    def test_items_without_title_are_skipped(self) -> None:
        """没有名字的条目界面无法展示，按不存在处理"""

        running, upcoming = collect_activities(
            [{"type": "Event", "start_time": NOW - 100, "end_time": NOW + 100}], NOW
        )

        assert running is None and upcoming is None

    def test_other_types_are_ignored(self) -> None:
        timeline = [
            titled_activity(NOW - 100, NOW + 100, title="卡池", item_type="Gacha")
        ]

        running, upcoming = collect_activities(timeline, NOW)

        assert running is None and upcoming is None

    def test_end_boundary_moves_to_upcoming(self) -> None:
        """刚好结束的活动不再算进行中，也不该被当成下一个"""

        running, upcoming = collect_activities(
            [titled_activity(NOW - 100, NOW, title="刚结束")], NOW
        )

        assert running is None and upcoming is None

    def test_empty_timeline(self) -> None:
        assert collect_activities([], NOW) == (None, None)
