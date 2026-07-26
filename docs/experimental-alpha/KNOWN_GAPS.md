# AUTO-MAS v6 Experimental Alpha 已知缺口与发布阻断项

> 标注规则：`observed` 表示已从当前源码或构建契约静态确认；`inferred` 表示由设计推导；`unverified` 表示尚无当前候选包的可复现实测。旧报告、其他提交或聊天结论不能替代当前证据。

## 本候选身份（alpha.11）

- 候选版本：`v6.0.0-alpha.NEXUS-OVERDRIVE.20260726.11`（snapshot_id `nexus-overdrive-all-plugins-v6.0.0-alpha.20260726.r11-portable-v11`）。
- 包型：`observed`：仅 Full 绿色免安装包；不提供安装器，不接受 Lite 包替代。
- Config v2 / WS v2：`observed`：Config v2 authoritative 是默认且唯一的生产配置权威源（进程默认模式与无效环境变量回退均为 `authoritative`），正式运行链不再构造 legacy `AppConfig`/`ConfigBase` 对象图，legacy JSON-first 保存显式失败；首启从不可变 r6 原始字节快照一次性迁移，之后只加载已校验的 CURRENT generation，不回退可变 legacy JSON；`off`/`shadow`/`canary` 仅保留用于受控回滚与诊断。WebSocket 主链路为 `{id,type,data}` 协议并保留兼容桥。`unverified`：真机旧 profile 的首次迁移、r6 回滚 bundle 导出与旧 WS 链完全退出均未在 Alpha 验证。
- 真实设备：`unverified`：所有真实游戏启动、模拟器控制、账号登录和自动化执行均未自动验证；源码调用链不等于真实运行成功。

## 送测前的阻断项

| ID | 项目 | 当前状态 | 为什么阻断 |
| --- | --- | --- | --- |
| GAP-01 | 具体 Alpha 便携包、版本、哈希和来源记录 | `pending` | 没有同一次构建的发行清单与 SHA-256，不能确认被测文件。 |
| GAP-02 | Full 便携包的实际构建结果 | `pending` | 源码中的构建流程不等于可运行产物。 |
| GAP-03 | Authenticode 签名状态 | `unverified` | 本草案不声明已签名；必须检查实际 executable。 |
| GAP-04 | 全新 Windows 安装和离线首启 | `unverified` | 结构检查不能代替真实 UI、断网和首次初始化。 |
| GAP-05 | r6 升级、回滚、卸载边界 | `unverified` | 不得在冻结 r6 目录上试错；需要隔离副本与可恢复备份。 |
| GAP-06 | 当前源码对应的全插件黑盒认证 | `pending` | 必须确认报告、日志、wheel 与当前构建输入一致。 |

## 运行时与功能风险

| ID | 范围 | 标注 | 测试前应如何处理 |
| --- | --- | --- | --- |
| GAP-07 | Config v2 authoritative 的首启迁移与崩溃恢复（原「authoritative 切换」，切换本身已完成） | `observed`：authoritative 已是默认且唯一的生产配置权威源，首启从不可变 r6 原始快照一次性迁移，之后只加载已校验的 CURRENT generation；`unverified`：真机旧 profile 首迁尚缺 GUI 回归证据，真实崩溃恢复与 r6 回滚 bundle 导出亦未实测 | 按手测卡在隔离副本上验证首启迁移结果与 r6 回滚 bundle 导出，不得以静态检查代替真机记录；崩溃后不得自行挑选孤儿 generation，需操作者显式确认 generation 与 manifest 哈希。 |
| GAP-08 | REST/WS/插件桥接在长期运行、异常重连和多客户端条件下的行为 | `unverified` | 保留前后端日志、请求/响应证据和重现步骤。 |
| GAP-09 | 插件实际加载、更新、失败隔离与热重载 | `unverified` | 先用隔离测试配置；故障插件不得污染稳定用户数据。 |
| GAP-10 | MaaFW 项目导入和真实 Agent/游戏执行 | `unverified` | 只在明确授权的人工测试环境执行；保留项目样本与日志。 |
| GAP-11 | HSR/SRA/M7A 动态数据、培养目标和托管更新 | `unverified` | 先检查配置界面和干运行/预览；真实脚本执行另行记录。 |
| GAP-12 | 游戏/模拟器发现、控制和运行结果 | `unverified` | 需要真实设备与实际模拟器手测；不得从静态代码推定成功。 |
| GAP-13 | 启动耗时、资源占用、DPI/多显示器表现 | `unverified` | 需要真实 Windows 性能基线和截图；不可沿用旧版本数据。 |
| GAP-14 | 应用更新下载与安装器拉起（`app/services/update.py`） | `observed`：下载不支持断点续传；安装器拉起后本地安装包不保留，失败后无本地包可直接重试 | 更新失败时保留下载日志并重新完整下载；弱网环境不要反复触发更新。 |
| GAP-15 | HSR/MaaEnd/MaaFW 运行链的宿主侧自动化测试 | `observed`：宿主侧无对应后端自动化测试，回归依赖真机 | 相关代码或依赖变更后，必须按手测卡在真实设备回归；不得以静态检查代替。 |
| GAP-16 | 插件市场安装/卸载通道 | `observed`：仅走 WebSocket 通道，无 HTTP 回退 | WS 断开或被代理拦截时安装/卸载不可用；保留连接日志，重连后再重试。 |
| GAP-17 | MAA/M9A/MaaEnd/general 任务管理器的配置副本 | `observed`：authoritative 模式下仍构造游离 `MultipleConfig` 内存副本（不落盘）；四个 manager 在 authoritative 下均无注册方且与 native 根 API 不兼容（调用即失败），属 legacy 死代码而非执行链 | 不要以内存副本推断磁盘配置状态；第三方插件不得将 `manager_factory` 指向 `app.task.{MAA,M9A,MaaEnd,general}.manager`；配置一致性以 authoritative 存储为准并按手测卡验证。 |
| GAP-18 | #302 MaaEnd 新登录接入 | `observed`：新登录本体未落地，后端仍走 Id+Password（`app/task/MaaEnd/AutoProxy.py`、`ManualReview.py`）；已落地的是 Skyland token 敏感字段保存协议（前后端字段与 DPAPI 加密闭环） | 不得以「敏感字段协议已完成」宣称 #302 登录接入完成；新登录落地前按现有 Id+Password 链手测。 |
| GAP-19 | MaaEnd adapter wheel 的构建可复现性 | `observed`：`plugins/wheels/manifest.json` 记录 `dirty: true`，wheel 无法仅凭 commit `2acb9ee8` 复现（含未提交的 ADB/Win32 兼容修复）；现有校验器无法发现此类缺口 | 重建该 wheel 必须使用保存的源树副本；升级该插件版本时优先补一次干净提交再出 wheel。 |
| GAP-20 | Python 侧 wheelhouse 校验器强度 | `observed`：`scripts/verify_wheelhouse_snapshot.py` 只校验计数、顶层摘要与 pyproject pin，不校验单 wheel sha256、manifest↔lock 逐条一致与 entry point 内容；完整校验依赖 TS 侧 `yarn validate:wheelhouse:integration` | 发布链任何环节不得只跑 Python 校验器就宣称 wheelhouse 通过；两个校验器必须都跑。 |
| GAP-21 | 插件事件总线的任务日志载荷 | `observed`：WS 推送的 `task.log.updated` 已按 512K 字符尾部窗口截断，但插件事件总线 `_emit_task_log` 的 `data["log"]` 仍携带完整日志；若未来插件桥把该事件转发上 WS，超限问题会在该路径复现 | 插件侧消费任务日志时注意载荷可能极大；桥接该事件上 WS 前必须先加截断。 |

## Alpha 的明确边界

- `observed`：构建契约为 Alpha 使用独立应用标识、独立安装目录名和 `manual-only` 更新策略。
- `observed`：离线首启脚本包含结构与端口预检，并要求人工完成 UI 初始化；它不是 GUI 自动化证明。
- `inferred`：若 Full 环境、snapshot、wheelhouse 和 runtime lock 均完整，离线首启具备可测试前提；实际可用性仍为 `unverified`。
- `unverified`：任何第三方插件、账号、游戏、模拟器或在线服务在测试者环境中的可用性。

## 解除规则

每个缺口只能由与候选包同源的文件、哈希、命令输出和人工记录解除。若源树、wheelhouse、runtime lock、安装器或版本发生变化，相关结论必须回退为 `pending` 或 `stale`，并按 [CI_GATES.json](CI_GATES.json) 和 [MANUAL_TEST_CARDS.md](MANUAL_TEST_CARDS.md) 重验。
