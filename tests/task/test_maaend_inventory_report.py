"""MaaEnd 协议空间材料记录按材料合并成一行合计，上游状态保持原样。"""

from tests.runtime_support import RuntimeStub as SimpleNamespace

from app.task.MaaEnd.AutoProxy import AutoProxyTask


def _proxy(*, push_log_mode: str = "逐条") -> AutoProxyTask:
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.user_state = lambda user: user
    proxy.callbacks = SimpleNamespace()
    proxy.cur_user_item = SimpleNamespace(push_log=[], push_log_mode=push_log_mode)
    proxy.push_log_enabled = push_log_mode != "关闭"
    proxy.task_name_map = {"协议空间": "ProtocolSpace"}
    proxy.inventory_status_messages = {
        "快子遴捡晶格 未达标，准备刷取协议空间",
        "快子遴捡晶格 协议空间目标已切换，开始刷取",
    }
    return proxy


def test_gains_merge_per_material(tmp_path):
    proxy = _proxy()
    path = tmp_path / "run.log"
    path.write_text(
        "[2026-11-02 14:20:00.000] 任务开始: 协议空间\n"
        "[2026-11-02 14:42:00.000] 快子遴捡晶格 未达标，准备刷取协议空间\n"
        "[2026-11-02 14:46:00.000] 获得以下物品：快子遴捡晶格 ×6\n"
        "[2026-11-02 14:46:01.000] 获得以下物品：行动资历 ×480\n"
        "[2026-11-02 14:48:00.000] 获得以下物品：快子遴捡晶格 ×6\n"
        "[2026-11-02 14:48:01.000] 获得以下物品：行动资历 ×480\n"
        "[2026-11-02 14:52:00.000] 获得以下物品：超距辉映管 ×1\n"
        "[2026-11-02 15:00:00.000] 理智不足，结束任务\n"
        "[2026-11-02 15:01:00.000] 任务完成: 协议空间\n",
        encoding="utf-8",
    )

    lines = proxy._collect_inventory_report([path])

    assert lines == [
        "[14:42:00] 上游报告：快子遴捡晶格 未达标，准备刷取协议空间",
        "[14:46:00] 本次获得：快子遴捡晶格 ×12（2 次）",
        "[14:46:01] 本次获得：行动资历 ×960（2 次）",
        "[14:52:00] 本次获得：超距辉映管 ×1（1 次）",
        "[15:00:00] 上游报告：理智不足，结束任务",
    ]
    assert [entry[1] for entry in proxy.cur_user_item.push_log] == [
        line.split("] ", 1)[1] for line in lines
    ]


def test_push_log_off_keeps_report_lines(tmp_path):
    proxy = _proxy(push_log_mode="关闭")
    path = tmp_path / "run.log"
    path.write_text(
        "[2026-11-02 14:20:00.000] 任务开始: 协议空间\n"
        "[2026-11-02 14:46:00.000] 获得以下物品：快子遴捡晶格 ×6\n"
        "[2026-11-02 14:46:01.000] 获得以下物品：快子遴捡晶格 ×6\n",
        encoding="utf-8",
    )

    lines = proxy._collect_inventory_report([path])

    assert lines == ["[14:46:00] 本次获得：快子遴捡晶格 ×12（2 次）"]
    assert proxy.cur_user_item.push_log == []


def test_unparsable_gain_line_stays_verbatim(tmp_path):
    proxy = _proxy()
    path = tmp_path / "run.log"
    path.write_text(
        "[2026-11-02 14:20:00.000] 任务开始: 协议空间\n"
        "[2026-11-02 14:46:00.000] 获得以下物品：快子遴捡晶格 ×6、行动资历 ×480\n"
        "[2026-11-02 14:50:00.000] 获得以下物品：快子遴捡晶格 ×6（背包已满）\n",
        encoding="utf-8",
    )

    lines = proxy._collect_inventory_report([path])

    assert lines == [
        "[14:46:00] 本次获得：快子遴捡晶格 ×6（1 次）",
        "[14:46:00] 本次获得：行动资历 ×480（1 次）",
        "[14:50:00] 本次获得：快子遴捡晶格 ×6（背包已满）",
    ]
