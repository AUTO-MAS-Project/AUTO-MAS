# 前端测试指南

测试提交、PR 验证与清理原则以[开发文档站规范](https://doc.auto-mas.top/developer/development-specifications.html#测试提交与维护规范)和 [mas-testing](../.agents/skills/mas-testing/SKILL.md#先判断是否值得长期保留)为准。长期测试优先保留便宜、稳定、能守住公共边界或高损失故障的用例；一次性页面探针留在本地，不扩充长期测试集。

## 长期单元测试覆盖边界

| 边界 | 重点防范的问题 |
| --- | --- |
| 配置文件与保存队列 | 并发覆盖、写入失败卡死队列、损坏配置被覆盖、旧配置被误重导 |
| WebSocket 与任务快照 | 重连状态错乱、关闭后旧请求复活连接、订阅串台、失败无限重试 |
| Runtime 协议与后端生命周期 | 分片解析失败、握手不匹配、误判就绪、退出遗留进程、启动备份无法恢复 |
| 初始化与更新编排 | 未停机更新、失败无法重试、取消后继续执行、退出时重启后端 |
| Runtime 文件更新 | 未验哈希安装、并发或取消后替换、失败破坏旧文件与备份 |
| 诊断包与全局词表 | 混入无关专项目录、泄露凭据/用户路径、缺词条或非法转义 |

## 编写与维护约定

- 新增长期用例前明确其守护边界、对应故障及替代的人工校对；同故障只留代表性用例，不按参数或文案堆叠。
- 直接调用真实被测模块，只隔离网络、进程与 IPC 边界；不联网、不碰真实用户数据。
- 不读取源码做字符串断言（全局词表扫描等无法模块调用的契约除外）；删除用例时同步清理无引用夹具，不用 `skip` 隐藏失败。

## E2E 与桌宠窗口测试

- **渲染层 E2E**：从 `frontend/` 先跑 `yarn e2e:check` 再跑 `yarn e2e`（可按需 `--grep '@queue|@scheduler|@history|@settings|@recovery'` 或 `--grep '@i18n|@webhook'`）。所有流程均开启页面未捕获异常与 Vue 全局错误检查；完整指南见 [docs/testing/e2e.md](../docs/testing/e2e.md)。
- **桌宠窗口 E2E**：在 Windows 图形会话下运行 `yarn e2e --grep '@mascot'`。流程会编译主进程、导入临时 v1 桌宠包并验证点击、拖拽、播放与资源释放（使用临时目录，不读取本机配置；测试期间勿手动拖动弹窗）。

## 常用验证命令

在 `frontend/` 下使用 PowerShell 7 执行：

```powershell
yarn test                    # 单元测试（需限并发时加 --maxWorkers=4）
yarn lint --max-warnings 1   # 静态检查
yarn typecheck               # Vue 渲染层类型检查
```
