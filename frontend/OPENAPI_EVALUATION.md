# OpenAPI 生成器评估（G00）

2026-10-21：本轮暂缓替换生成器，B05 继续使用现有客户端和 Vue Query。
临时新客户端未进入生产入口，未修改 `src/api`、依赖清单或锁文件。

原生成器已[公告停止维护](https://github.com/ferdikoomen/openapi-typescript-codegen)，
后续迁移仍有必要；本结论只针对这次治理的实施顺序。

## 固定输入与工具

- 后端提交：`9d27abe9d21382f632300e254e66685161aee2b5`。B00–B04 未改变后端。
- 从隔离 E2E 后端的 `/openapi.json` 导出，SHA-256：
  `3082fcb60e5b07a17886ab869d998d0342458633fe244d7a05ba7c0aa99b3778`。
- Node `24.19.0`、Yarn `4.18.1`、TypeScript `5.9.2`、Axios `1.15.2`。
- 对比 `openapi-typescript-codegen@0.29.0` 与 `@hey-api/openapi-ts@0.99.0`。
  后者要求 Node >=22.18.0，现有 Windows 构建的 22.18.0 满足要求。
- 新生成器插件：`@hey-api/typescript`、`@hey-api/client-axios`、
  `@hey-api/sdk`、`@tanstack/vue-query`；生成时关闭格式化与 lint。

依赖只安装在 Git 忽略的临时项目。两个候选配置各连续生成两次，17 个 TS 文件
逐文件 SHA-256 均相同，均为 LF。现有换行后处理在这些样本中没有额外工作。
同一输入的旧输出为 1131 文件、39787 行，新默认输出为 17 文件、52602 行；
文件布局变化不算手写实现减少。

## 代表性实测

使用本机临时 HTTP 服务和真实生成客户端发请求，不调用真实脚本或用户配置。

| 对照项 | 结果 |
| --- | --- |
| 设备选项读取 | 两客户端 JSON 参数相同；配置 ID 保持原值 |
| 脚本字段补丁 | `Info.Name`、路径 `null` 和省略字段传输相同，没有补齐整份配置 |
| 添加用户业务失败 | HTTP 200 / `code: 400` 均保留响应，仍须业务层判成功 |
| 非 2xx 错误 | 旧客户端抛 `ApiError.body/status`；新客户端显式 `throwOnError: true` 后抛 `AxiosError.response.data/status` |
| 新 SDK 默认错误 | 不抛异常，返回带 `error` 的对象；现有 catch 不能原样迁移 |
| 动态地址 | `client.setConfig({ baseURL })` 后请求使用新地址；需替换现有 `OpenAPI.BASE` 读写点 |
| 取消 | AbortSignal 使 Axios 拒绝，并观察到服务端连接关闭 |
| 枚举与可空 | 字符串枚举值保持；默认输出改为字面量联合，旧的运行时 `ScriptCreateIn.type` 访问需要迁移；可省略和可空分别表达 |
| 日志 | 新旧传输均不代替业务日志；现有 API 包装层的日志仍有实际消费者 |

默认插件把设备选项的 POST 读取生成 mutation。按官方
[操作分类 hook](https://heyapi.dev/docs/openapi/typescript/configuration/parser#operations-1)
仅将 `/api/info/combox/emulator/devices` 分类为 query 后，生成的 Query options
可按 body 区分 A/B、合并同键并发请求、将 Query 的取消信号传至底层 HTTP。
此定向配置也完成双次生成和 TypeScript 编译。

但 HTTP 200 的业务失败仍被生成 Query 记为成功。原始设备类型、魔改 AVD 标记、
页面本地展示规则及成功写入后的失效范围，仍需要领域层组合。
[Query 插件](https://heyapi.dev/docs/openapi/typescript/plugins/tanstack-query)
能生成传输与 key 的样板，不能取代这些规则。

## 迁移成本与决定

当前手写源码有 164 个文件、218 条 `@/api` 导入语句（含类型，不等于调用数）。
除服务类调用改为函数和 `{ body }` 参数外，响应包装、错误类型、可取消 Promise、
枚举值入口以及缩略词类型命名均有变化，例如 `MaaFWConfig` → `MaaFwConfig`。
不能只替换生成命令后继续使用原包装层。

本轮共享查询的主要维护成本是组合设备信息、取消与写后失效。迁移生成器后这些
手写规则依然存在，还会同时触及大量现有调用者。因此先完成 B05 的单缓存试点，
暂缓生成器迁移，避免在保存与恢复路径重构期间增加另一组兼容改动。

重新启动迁移时：固定版本和输入，列出真正的 POST 读取白名单；统一动态地址和
HTTP 错误读取；逐模块替换服务调用、参数、响应及枚举引用；最后一次性移除旧
生成器和临时兼容层。不得长期维护两套生产客户端。

## 验证与边界

- 新默认配置、定向 Query 配置及旧客户端均通过 TypeScript 严格编译。
- 本地传输对照 12 次请求通过；定向 Query 的并发合并、A/B key、业务失败保留和
  实际取消检查通过。
- 原生产前端的 lint、typecheck、构建及现有 96 项测试在 B04 通过。
  没有替换整仓生产客户端，因此不宣称完成新 SDK 的整仓构建或迁移验收。
- 原始契约、临时安装、两轮输出、编译产物及探针只保存在
  `.dev/frontend-governance/`，不提交、不被生产代码引用。

复现实验时，在上述后端提交的隔离数据环境导出契约并核对哈希；建立独立临时
Yarn 4 项目，固定以上版本，调用 `createClient({ input, output, plugins })`。
第二组额外配置 `parser.hooks.operations.getKind`，仅对上述读取返回 `['query']`。
比较两轮文件哈希，再对各输出运行：

```powershell
corepack yarn tsc --target ES2022 --module commonjs --moduleResolution node --esModuleInterop --skipLibCheck --strict --outDir compiled out-one/index.ts out-one/@tanstack/vue-query.gen.ts
```
