"""MAA 配置 diff 透传的最小回归测试(纯逻辑)。"""

from app.task.MAA.AutoProxy import _merge_maa_changes, _merge_task_queue


def test_scalar_change_merged():
    archive = {"a": 1}
    assert _merge_maa_changes(archive, {"a": 1}, {"a": 2})
    assert archive == {"a": 2}


def test_new_key_merged():
    archive = {}
    assert _merge_maa_changes(archive, {}, {"b": "x"})
    assert archive == {"b": "x"}


def test_deletion_not_transferred():
    archive = {"a": 1, "b": 2}
    assert not _merge_maa_changes(archive, {"a": 1, "b": 2}, {"a": 1})
    assert archive == {"a": 1, "b": 2}


def test_nested_dict_merged():
    archive = {"Configurations": {"Default": {"k": 1}}}
    baseline = {"Configurations": {"Default": {"k": 1}}}
    current = {"Configurations": {"Default": {"k": 9}}}
    assert _merge_maa_changes(archive, baseline, current)
    assert archive["Configurations"]["Default"]["k"] == 9


def test_task_queue_aligned_by_task_type_and_name():
    # 托管注入改变队列顺序, 基线索引与存档索引不同, 必须按标识对齐
    baseline = {
        "TaskQueue": [
            {"TaskType": "StartUp", "Name": "开始唤醒", "IsEnable": True},
            {"TaskType": "Mall", "Name": "信用收支", "CreditFightLastTime": "旧"},
        ]
    }
    current = {
        "TaskQueue": [
            {"TaskType": "StartUp", "Name": "开始唤醒", "IsEnable": True},
            {
                "TaskType": "Mall",
                "Name": "信用收支",
                "CreditFightLastTime": "2026-09-07 00:00:00",
            },
        ]
    }
    archive = {
        "TaskQueue": [
            {"TaskType": "Mall", "Name": "信用收支", "CreditFight": True},
            {"TaskType": "StartUp", "Name": "开始唤醒"},
        ]
    }
    assert _merge_maa_changes(archive, baseline, current)
    mall = next(i for i in archive["TaskQueue"] if i["TaskType"] == "Mall")
    assert mall["CreditFightLastTime"] == "2026-09-07 00:00:00"
    assert mall["CreditFight"] is True  # 存档原有字段不丢


def test_task_queue_synthetic_task_skipped():
    # 基线中的托管合成任务在存档中不存在, 变更跳过
    baseline = {
        "TaskQueue": [{"TaskType": "DepotMaintain", "Name": "库存保持", "X": 1}]
    }
    current = {"TaskQueue": [{"TaskType": "DepotMaintain", "Name": "库存保持", "X": 2}]}
    archive = {"TaskQueue": []}
    assert not _merge_maa_changes(archive, baseline, current)
    assert archive["TaskQueue"] == []


def test_task_queue_new_element_skipped():
    baseline = {"TaskQueue": []}
    current = {"TaskQueue": [{"TaskType": "Mall", "Name": "信用收支"}]}
    archive = {"TaskQueue": []}
    assert not _merge_maa_changes(archive, baseline, current)
    assert archive["TaskQueue"] == []


def test_task_queue_archive_missing_subtree_skipped():
    # 存档缺 TaskQueue 子树时不整棵写入运行期内容
    baseline = {"TaskQueue": [{"TaskType": "Mall", "Name": "信用收支", "T": "旧"}]}
    current = {"TaskQueue": [{"TaskType": "Mall", "Name": "信用收支", "T": "新"}]}
    archive = {}
    assert not _merge_maa_changes(archive, baseline, current)
    assert archive == {}


def test_structure_type_mismatch_skipped():
    # MAA 把某 dict 键改成 list 属结构演化, 跟随整体替换
    archive = {"a": {"b": 1}}
    baseline = {"a": {"b": 1}}
    current = {"a": [1]}
    assert _merge_maa_changes(archive, baseline, current)
    assert archive == {"a": [1]}


def test_top_level_type_mismatch_skipped():
    # 顶层结构不匹配(写盘半截被截断)整体跳过
    assert not _merge_maa_changes({}, {"a": 1}, [1])
    assert not _merge_maa_changes([], {}, [])


def test_merge_idempotent():
    archive = {"a": 1}
    baseline = {"a": 1}
    current = {"a": 2}
    assert _merge_maa_changes(archive, baseline, current)
    assert not _merge_maa_changes(archive, baseline, current)
    assert archive == {"a": 2}


def test_merge_task_queue_direct():
    archive = [
        {"TaskType": "Mall", "Name": "信用收支", "VisitFriendsLastTime": "旧"},
        {"TaskType": "StartUp", "Name": "开始唤醒"},
    ]
    baseline = [
        {"TaskType": "StartUp", "Name": "开始唤醒"},
        {"TaskType": "Mall", "Name": "信用收支", "VisitFriendsLastTime": "旧"},
    ]
    current = [
        {"TaskType": "StartUp", "Name": "开始唤醒"},
        {"TaskType": "Mall", "Name": "信用收支", "VisitFriendsLastTime": "新"},
    ]
    assert _merge_task_queue(archive, baseline, current)
    assert archive[0]["VisitFriendsLastTime"] == "新"
    assert _merge_task_queue(archive, baseline, current) is False  # 幂等
