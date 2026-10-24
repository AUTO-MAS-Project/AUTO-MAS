# 接入与结果语义

## 选择已有入口

先沿用户操作追到实际业务请求或现有结果信号，再查同一路径是否已经观察。优先搜索：

```powershell
rg -n 'observeFeature|beginAnalyticsOperation|beginMainFeature|recordAnalyticsEvent' frontend/src frontend/electron
rg -n '<业务方法或事件名>' frontend/src frontend/electron app
```

这些命令需要在仓库根目录用 PowerShell 7 执行。搜索是定位工具，不能代替运行验证。

| 已有责任边界 | 接入方式 |
| --- | --- |
| 共用配置保存、任务请求、队列/计划管理 | 复用对应 composable，不在组件再发同一事件 |
| 单次生成 API 操作 | 业务 API/composable 使用 `observeFeature`，返回原可取消 Promise |
| 多步交互、扫码、导出、导入 | 开始前创建一次 operation，唯一终态处 finish |
| 实际结果由主进程掌握 | `beginMainFeature`；不要绕到 renderer 或辅助窗口再猜测 |
| 后台任务受理和完成分开 | 受理处记录请求结果，完成处消费已有权威结果并可靠关联 |
| 新页面 | 更新 `src/router/analytics.ts` 与页面/来源有限词表，不记录 route params/query |
| Python 产生结果 | 优先复用现有领域结果及本机 WS 边界，由统一采集层发送；不在 Python 新开直传 Aptabase 通道 |

共享的 `apiOutcome` 仅按现有约定把业务 code 映射为 success/blocked/failure；不是所有 code=200 的接口都已经完成动作。`commandOutcome` 只用于返回 success/cancelled 的相应命令契约。阅读真实接口后再选映射。

## 增加事件或维度

1. 检查是否能复用同一产品含义的事件族；增加一个有限操作类别通常比造一套相同事件更合适。
2. 定义结果所有者和固定属性。新字段必须有可以解释的分析用途；不上传为了“以后可能用”而收集的内容。
3. 扩展契约和实际校验：
   - 常规 feature 事件在 `electron/services/analyticsFeaturePolicy.ts` 定义；类型由该纯常量模块映射，主校验在 `analyticsPolicy.ts` 合入。
   - 核心事件在 `src/types/analytics.d.ts` 和 `electron/services/analyticsPolicy.ts` 同时更新。
   - 主进程独占事件加入 `mainOnlyFeatureEvents` 或现有主进程独占分支，确保 renderer 路径被拒绝。
4. 在真实调用边界接入，覆盖同类实际入口；不要只新增类型、枚举、文档或一个永远没有调用者的 helper。
5. 为新值增加归一化和 unknown；新增脚本类型需核对核心/feature 词表、`analyticsScriptType` 与现有注册表，保留 MaaFW flavor 的独立类型语义。
6. 更新 `analytics.md`、相关覆盖台账及发生变化的三语采集说明，随后验证字段拒绝和真实接线。

新增字段会改变精确字段数量校验。不要给原事件悄悄塞属性、把对象展开进 props，或要求主进程忽略额外字段。若变更历史含义，应明确调整口径/事件，不能让同名数据的前后意义不一致。

## Renderer 单次 API 示例

以下示意已有模板导入类别的用法；先确认实际业务是否已走相同观察，避免重复：

```ts
return observeFeature(
  'adapter_setup_finished',
  { script_type: 'General', operation_kind: 'template', engine_kind: 'unknown' },
  () => Service.importScriptFromWebApiScriptsImportWebPost(input),
  result => apiOutcome(result)
)
```

示例方法名须与当前生成客户端核对，不凭示例新增接口。外层继续执行原有状态更新、提示和异常处理。统计不读取模板、名称、正则或日志内容。不要改写为“等待上报后再返回接口结果”。

如果业务契约还需要 `ok`、`cancelled`、`taskId` 等确认，必须按该结构映射：例如创建任务 code=200 且带实际任务标识只是 accepted，不能叫任务 success。标识只用于本机确认，不加入事件属性。

## 多步和主进程示例

```ts
const operation = beginAnalyticsOperation('update_install_requested')
try {
  const result = await Service.installUpdateApiUpdateInstallPost()
  operation.finish({
    choice: 'install_now',
    request_outcome: result.code === 200 ? 'accepted' : 'rejected',
  })
  // 继续原来的界面/业务处理。
} catch (error) {
  operation.finish({ choice: 'install_now', request_outcome: 'unknown' })
  // 保留原先处理方式；原本抛错的仍抛原错。
}
```

安装接口创建后台任务即返回，因此此处不能命名 installed。主进程的明确业务操作使用对应的 `beginMainFeature` 并在实际结果处 finish，不在 renderer 重复观察同一结果。

`finish()` 一次保护不能替代“哪个操作”的归属判断。不要让旧回调通过全局的当前 operation 去结束后来新建的会话。重试、替换、导航、关闭和卸载时要明确旧操作是结束、丢弃还是继续等实际结果。

## 结果映射

| 信号 | 可以声称什么 | 必须避免 |
| --- | --- | --- |
| 用户点确认/取消/稍后 | 固定选择类别 | 当成后台执行已成功或失败 |
| 任务加入队列、后台任务已创建 | accepted/rejected/unknown | 成功完成、安装器已运行 |
| 明确的领域返回已持久化/已完成 | success/failure | 被随后音效或页面刷新失败反转 |
| 前段已完成、后段失败 | partial 或两个分别确认的事件 | 将已发生的副作用折为全部 failure |
| 明确用户取消 | cancelled、未请求或选择类别 | 网络错误一律 cancelled |
| 超时、断网、缺少完成帧 | unknown、observation_unknown 等现有口径 | 断言后台已经失败 |
| busy/重复操作直接跳过 | 丢弃或有业务用途的 skipped/blocked | 复用上次的成功结果 |
| 恢复快照/已有绑定/配置回填 | 更新本地视图 | 当成新运行、新绑定、新采用 |

网络异常的 unknown 不等于确认失败。对照具体事件契约选合法值，不能因为 feature schema 允许某个词就忽略业务含义。

## 字段和关联

- 从入口取得 script_type 等固定类别，不能拿用户 UID 查脚本 UID 缓存；修正统计时不替换原业务 target ID。
- 数量用现有数量桶，耗时由现有 operation 或 `analyticsDuration`/`durationBucket` 归桶。不要上传日期集合、精确时刻、速率序列、下载字节或任意版本文本。
- 自定义名称/来源/枚举扩展先归一化到内置有限词表。对象 ID 即使哈希后仍不外发。
- 有界缓存只利用已有成功读取/写入；缺失分类保留 unknown。不额外查询用户、脚本或配置来丰富统计。
- 并发写、取消与重连应捕获操作自己的上下文、类别和快照。缺少可靠关联的完成帧宁可不计，不分配给最新请求。
- 不新增高频心跳和全局自动请求/点击拦截器。共用并发、超时、速率预算和现有采样；不能用换事件名绕过预算。

## 开关与传输的修改边界

`analyticsService.ts` 负责环境、配置确认和固定传输，`analytics.ts` 负责代次、会话、采样、频率与取消，`ipc/analyticsHandlers.ts` 负责窗口/frame/应用来源。日常业务接入直接复用这些机制。

禁止为了“方便看到结果”去掉开发隔离、允许辅助窗口发送任意事件、创建第二个 SDK 实例、复用生产账户做批量伪造数据，或修改服务器文件。生产验收与真实业务操作必须有相应授权，并按验证层级据实报告。
