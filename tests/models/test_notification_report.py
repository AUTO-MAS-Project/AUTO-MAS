"""通知节点模型的状态约束和既有文本识别边界。"""

import pytest

from app.models.notification.report import Node


def test_node_contract_keeps_legacy_recognition_boundary():
    node = Node(status="success", name="邮件", account="实例 1")
    assert Node.from_text(node.text) == node
    assert Node.from_text("✅ 成功：邮件") is None
    assert Node.from_text("⚠️ 节点采集失败") is None
    with pytest.raises(ValueError):
        Node(status="unknown", name="邮件")
