"""r6 配置升级、崩溃恢复与可逆回滚黑盒认证 harness。

本包为 AUTO-MAS v6 Experimental Alpha 的 Config v2 authoritative 模式提供
独立、只读、scratch-based 的端到端黑盒认证。所有测试在 tempfile 临时目录中
运行，绝不读取真实用户 config/。

覆盖矩阵：
- MIGRATION_CORPUS_MATRIX: 9 类输入语料 → 升级 / 持久化 / 重启 / 回滚
- RECOVERY_MATRIX: 各 FAULT_POINTS 崩溃中断后恢复
- ROLLBACK_MATRIX: 锁 / 级联删除 / 重排 / 跨根事务故障注入
- NATIVE_TRANSPORT_MATRIX: NativeConfigFacade scripts/users/queue/plan/settings/webhook 投影
- ENCRYPTION_BOUNDARY: 密文落盘 vs API 明文投影边界
"""
