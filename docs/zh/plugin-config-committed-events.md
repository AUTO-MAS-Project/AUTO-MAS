# 配置提交后事件

本项由用户批准从插件迁移基线独立实现，关联 #1387。

- 保留 `ConfigNode.connect`：事务内校验、引用维护、配置联动仍能共同回滚。
- 新增 `ConfigCommittedEvent`：外层内存提交成功后，每次事务发布一份摘要；嵌套事务合并，初始化和回滚不发布。
- 摘要只有事件 ID、进程内递增 revision、节点/根 ID、类型和变更路径，不携带明文密钥、字段值或可变配置对象。它不是落盘确认；YAML 仍走原有防抖与 `flush()`。
- 每个观察者按提交顺序消费，异常只记录并继续；异步回调不持有配置事务锁，慢观察者不阻塞其他观察者。
- 国际化通知、运行期系统设置与设备去广告策略转入提交后阶段；初始化系统设置沿用原入口。策略消费者读取当前已提交值，连续提交允许应用最新策略。
- 插件通过注入的 `self.config_events.connect(callback)` 订阅，不依赖全局配置管理器。禁用、重载、启用失败和退出时注销并等待在途回调收尾；旧实例不能重新订阅。
- 宿主可 `await config_manager.committed.drain()` 等待当前观察队列，进程关闭用 `shutdown()` 取消观察者并等待清理。

示例：

```python
async def on_enable(self):
    self.config_events.connect(self.on_config_committed)

async def on_config_committed(self, event):
    for change in event.changes:
        if change.config_uid == self.config.uid:
            # 按 changed_paths 刷新插件自己的外部资源。
            ...
```

本项不修改配置格式、字段校验、事务内信号或落盘方式，不引入外部消息服务。异步 Trigger 的执行所有权由另一独立分支处理。
