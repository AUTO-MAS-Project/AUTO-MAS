---
name: mas-schema-naming
description: Define canonical naming for new backend config groups and API contracts, including endpoint-local and shared models, while preserving established business field names.
---

# MAS Schema Naming

约束**新增**后端配置分组与共享语义命名；默认不批量重命名既有遗留模块。公开配置模型字段统一 `PascalCase`，新脚本配置用 `Info`/`Run`/`Emulator` 分组，用户配置用 `Info`/`Data`/`Notify` 及领域专属分组。

## 共享语义标准命名表

语义相同时必须复用下表名称，禁止同义漂移（如 `RootPath` 替代 `Path`）或跨组错放：

| 语义 | 标准名 | 分组 | 语义 | 标准名 | 分组 |
| --- | --- | --- | --- | --- | --- |
| 脚本显示名 | `Name` | `Info` | 用户显示名 / ID | `Name` / `Id` | `User.Info` |
| 脚本路径 | `Path` | `Info` | 用户启用状态 | `Status` | `User.Info` |
| 模拟器 ID / 索引 | `Id` / `Index` | `Emulator` | 剩余天数 / 备注 / 标签 | `RemainedDay` / `Notes` / `Tag` | `User.Info` |
| 切换策略 | `TaskTransitionMethod` | `Run` | 上次代理日期 / 次数 | `LastProxyDate` / `ProxyTimes` | `User.Data` |
| 每日代理上限 | `ProxyTimesLimit` | `Run` | 人工核查结果 | `IfPassCheck` | `User.Data` |
| 重试次数 / 超时 | `RunTimesLimit` / `RunTimeLimit` | `Run` | 通知总开关 / 统计 | `Enabled` / `IfSendStatistic` | `User.Notify` |
| 邮件开关 / 收件人 | `IfSendMail` / `ToAddress` | `User.Notify` | Server 酱开关 / Key | `IfServerChan` / `ServerChanKey` | `User.Notify` |

## 规则

- 领域专属字段留在专属分组，不强套共享名，也不在同一分组加同义字段。
- 规范化既有公开字段时，迁移期保持旧输入读取兼容、新响应写标准名，待消费方全迁完再删旧名。
