from app.log_box.logtype import LogType
from app.task.OkNte.push_log import oknte_resolve


def test_oknte_resolve_merges_status_and_stamina() -> None:
    results = [
        (LogType.NORMAL, "✅ 成功: 节点A"),
        (LogType.NORMAL, "⏭ 跳过: 节点B"),
        (LogType.NORMAL, "❌ 失败: 节点A"),
        (LogType.NORMAL, "CUR:90"),
        (LogType.NORMAL, "TGT:60"),
    ]

    assert oknte_resolve(results) == [
        (LogType.NORMAL, "⏭ 跳过: 节点B"),
        (LogType.NORMAL, "❌ 失败: 节点A"),
        (LogType.NORMAL, "⚡️ 剩余体力: 30"),
    ]


def test_oknte_resolve_ignores_invalid_skip_items() -> None:
    assert oknte_resolve([(LogType.NORMAL, "SKIP:'节点A', 123")]) == [
        (LogType.NORMAL, "⏭ 跳过: 节点A")
    ]
