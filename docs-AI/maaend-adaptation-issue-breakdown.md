# AUTO-MAS 对 MaaEnd 专项适配 Issue 拆分方案（Plan v2 对齐）

本文基于以下材料整理：

- `docs-AI/maaend-adaptation-plan-v2.md`
- 当前 `AUTO-MAS-Lite` 的实际代码结构

目标：按 **复用 MAA 思路、最小改动、可持续维护** 的原则，更新 MaaEnd 适配 issue 拆分与依赖关系。

## 当前状态（截至 2026-03-12）

- 已完成：I01、I02、I03、I04、I05、I06、I07、I08、I09、I10
- 进行中：I11
- 未开始：I12-I13

## 1. 拆分原则（v2）

### 1.1 外部配置优先，AUTO-MAS 只做必要管理

MaaEnd 接入遵循 MAA 现有模式：

1. 从 AUTO-MAS 启动外部配置流程
2. 由 MaaEnd 维护具体任务与选项
3. AUTO-MAS 回读关键字段并调度执行
4. 执行后进入历史/通知/WebSocket 闭环

### 1.2 最小改动优先

- 不重建 MaaEnd 全量任务/选项元数据模型
- 不在首期实现复杂动态任务编排 UI
- 优先复用 MAA/General 既有链路（配置、调度、日志、通知）

### 1.3 一项 issue 对应一个审阅面

每个 issue 只覆盖一类变更面，避免“模型/API/执行器/前端”混改导致审阅困难。

## 2. 建议 Project 结构

### Epic A. 规格与后端基础

- I00 规格冻结：MaaEnd MVP 与字段清单
- I01 后端模型：MaaEndConfig / MaaEndUserConfig 接入
- I02 API 与 OpenAPI：Schema / Scripts API / SDK 联合类型扩展
- I03 外部配置接入：启动 MaaEnd 配置流程并回读关键字段

### Epic B. 执行链路接入

- I04 运行期参数注入：桥接 AUTO-MAS 与 MaaEnd 配置文件
- I05 TaskManager 接入：新增 MaaEndManager 骨架与类型分发
- I06 生命周期实现：check / prepare / final
- I07 执行与日志判定：main 阶段、失败归因、重试策略
- I08 可观测性接入：WebSocket / 历史 / 通知

### Epic C. 前端接入（最小可用）

- I09 前端基础接入：类型、列表、路由、创建入口
- I10 MaaEndScriptEdit：脚本级最小配置页
- I11 MaaEndUserEdit：用户级最小配置能力（非全量动态编排）

### Epic D. 联调、回归与发布

- I12 端到端联调与混排回归
- I13 文档、灰度与发布收口

## 3. Issue 总览（v2）

| ID | Issue 标题 | 主要范围 | 前置依赖 | 建议负责人 |
| --- | --- | --- | --- | --- |
| I00 | 冻结 MaaEnd MVP 规格与字段清单 | 规格/设计 | 无 | Tech Lead |
| I01 | 新增 MaaEndConfig / MaaEndUserConfig 并接入配置树 | 后端模型 | I00 | Backend |
| I02 | 扩展 Schema、Scripts API 与 OpenAPI 以支持 MaaEnd | API/模型 | I01 | Backend |
| I03 | 外部配置接入：启动 MaaEnd 并回读关键字段 | 后端服务 | I01 | Backend |
| I04 | 实现运行期参数注入与配置桥接 | 后端执行准备 | I03 | Backend |
| I05 | 新增 MaaEndManager 骨架并接入 TaskManager 分发 | 调度/执行器 | I02, I04 | Backend |
| I06 | 完成 MaaEndManager 的 check/prepare/final 链路 | 执行器 | I05 | Backend |
| I07 | 完成 main 阶段、日志判定、失败归因与重试 | 执行器 | I06 | Backend |
| I08 | 接入历史记录、通知与 WebSocket 状态广播 | 可观测性 | I07 | Backend |
| I09 | 前端接入 MaaEnd 类型、入口、路由与列表映射 | 前端基础 | I02 | Frontend |
| I10 | 实现 MaaEndScriptEdit（最小配置） | 前端脚本页 | I09 | Frontend |
| I11 | 实现 MaaEndUserEdit（最小用户配置） | 前端用户页 | I03, I09 | Frontend |
| I12 | 完成端到端联调与三类型混排回归 | QA/联调 | I08, I10, I11 | QA + 全员 |
| I13 | 补齐文档、灰度策略与发布清单 | 文档/发布 | I12 | PM + Dev |

## 4. 关键 issue 说明（v2 变更点）

### I03 外部配置接入（重定义）

`类型`：feature  
`目标`：对齐 MAA，把 MaaEnd 配置编辑能力留在外部配置器，AUTO-MAS 只负责触发与回读。

`主要内容`

- 提供启动 MaaEnd 配置流程的后端能力
- 回读并持久化最小关键字段（控制器、资源、预设、必要运行参数）
- 保证回读幂等，不引入任务/选项硬编码

`非目标`

- 不做 `interface/tasks/preset` 全量元数据建模
- 不做复杂动态任务表单生成

`验收标准`

- 可从 AUTO-MAS 发起一次 MaaEnd 配置流程
- 可回读并保存关键字段，重启后可复现
- 不影响 MAA/General 现有链路

### I04 运行期参数注入与配置桥接

`类型`：feature  
`目标`：将 AUTO-MAS 管理的最小参数注入到 MaaEnd 运行期配置，形成执行前桥接。

`主要内容`

- 基于回读结果生成/覆盖运行期必要字段
- 输出到 MaaEnd 约定配置位置
- 保持配置覆盖规则简单可追踪

`验收标准`

- 可稳定生成可执行配置
- 注入逻辑可复现、可排障
- 不引入新的全量任务模型依赖

### I10 MaaEndScriptEdit（最小配置）

`类型`：feature  
`目标`：提供脚本级必要配置编辑能力，避免前端过度设计。

`主要内容`

- 安装路径、运行参数、日志判定规则等最小字段编辑
- 保留与后端字段一一对应
- 日志监控默认路径对齐为 `Info.Path/debug/go-service.log`
- 不实现全量任务编排 UI

### I11 MaaEndUserEdit（最小用户配置）

`类型`：feature  
`目标`：聚焦“选择/启用用户配置”而非重建 MaaEnd 内部任务系统。

`主要内容`

- 用户级启停、顺序、基础运行参数
- 与 I03 回读结果联动展示必要信息
- 仅提供最小可用交互，不引入高耦合动态表单

## 5. 建议执行顺序（v2）

1. I00
2. I01
3. I02
4. I03
5. I04 + I05
6. I06
7. I07
8. I08
9. I09
10. I10（已完成）+ I11
11. I12
12. I13

## 6. 标签与优先级建议

建议标签：

- `epic:maaend-adaptation`
- `area:backend`
- `area:frontend`
- `area:qa`
- `type:spec`
- `type:feature`
- `type:test`
- `type:docs`
- `priority:p0`
- `priority:p1`

建议优先级：

- `P0`：I00-I08
- `P1`：I09-I11
- `P0`：I12
- `P1`：I13

## 7. 建卡模板（建议）

```md
## 目标

## 范围

## 非目标

## 涉及模块

## 前置依赖

## 验收标准

## 审阅重点
```

---

此版为 **plan-v2 对齐版本**，后续若需要同步到 GitHub Project，可直接按本文件的 issue 粒度建卡。

