# AUTO-MAS v6 Experimental Alpha 已知缺口与发布阻断项

> 标注规则：`observed` 表示已从当前源码或构建契约静态确认；`inferred` 表示由设计推导；`unverified` 表示尚无当前候选包的可复现实测。旧报告、其他提交或聊天结论不能替代当前证据。

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
| GAP-07 | Config v2 的 authoritative 切换 | `observed`：Alpha 设计允许兼容/影子链；`unverified`：真实配置升级与崩溃恢复 | 只按手测卡验证导入和回滚，不宣称旧配置运行链已退出。 |
| GAP-08 | REST/WS/插件桥接在长期运行、异常重连和多客户端条件下的行为 | `unverified` | 保留前后端日志、请求/响应证据和重现步骤。 |
| GAP-09 | 插件实际加载、更新、失败隔离与热重载 | `unverified` | 先用隔离测试配置；故障插件不得污染稳定用户数据。 |
| GAP-10 | MaaFW 项目导入和真实 Agent/游戏执行 | `unverified` | 只在明确授权的人工测试环境执行；保留项目样本与日志。 |
| GAP-11 | HSR/SRA/M7A 动态数据、培养目标和托管更新 | `unverified` | 先检查配置界面和干运行/预览；真实脚本执行另行记录。 |
| GAP-12 | 游戏/模拟器发现、控制和运行结果 | `unverified` | 需要真实设备与实际模拟器手测；不得从静态代码推定成功。 |
| GAP-13 | 启动耗时、资源占用、DPI/多显示器表现 | `unverified` | 需要真实 Windows 性能基线和截图；不可沿用旧版本数据。 |

## Alpha 的明确边界

- `observed`：构建契约为 Alpha 使用独立应用标识、独立安装目录名和 `manual-only` 更新策略。
- `observed`：离线首启脚本包含结构与端口预检，并要求人工完成 UI 初始化；它不是 GUI 自动化证明。
- `inferred`：若 Full 环境、snapshot、wheelhouse 和 runtime lock 均完整，离线首启具备可测试前提；实际可用性仍为 `unverified`。
- `unverified`：任何第三方插件、账号、游戏、模拟器或在线服务在测试者环境中的可用性。

## 解除规则

每个缺口只能由与候选包同源的文件、哈希、命令输出和人工记录解除。若源树、wheelhouse、runtime lock、安装器或版本发生变化，相关结论必须回退为 `pending` 或 `stale`，并按 [CI_GATES.json](CI_GATES.json) 和 [MANUAL_TEST_CARDS.md](MANUAL_TEST_CARDS.md) 重验。
