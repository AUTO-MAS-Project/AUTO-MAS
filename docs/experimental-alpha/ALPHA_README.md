# AUTO-MAS v6 Experimental Alpha 随包说明

> 文档状态：草案。它描述 Alpha 候选包应附带的边界和验证方式，**不是**某个已构建产物的验收记录。版本、SHA-256、签名状态、测试结果和下载位置必须以同一次构建生成的 `alpha-release-manifest.json`、`SHA256SUMS` 与 CI 日志为准；本文件不代填这些数据。

## 这是什么

AUTO-MAS v6 Experimental Alpha 是用于受控 A 测的独立候选包，不是正式稳定版，也不进入常规自动更新渠道。

- 发布通道：`experimental-alpha`。
- 更新策略：`manual-only`；测试者不得把它当作常规在线更新客户端使用。
- 预期可执行文件名：`AUTO-MAS-v6-Experimental-Alpha.exe`。
- 预期安装目录名：`AUTO-MAS v6 Experimental Alpha`。
- 本阶段包型：仅 Full 绿色免安装包；安装器延后，不接受 Lite 包替代。

这些标识的目的，是把 Alpha 与现有稳定安装区分开。它们不能代替对实际产物的检查。

## 本候选身份（alpha.10）

本草案对应候选身份 `v6.0.0-alpha.NEXUS-OVERDRIVE.20260726.11`，snapshot_id 为 `nexus-overdrive-all-plugins-v6.0.0-alpha.20260726.r11-portable-v11`。身份字段已同步写入 `app/core/config.py`、`frontend/package.json` 顶层 `version`、`res/version.json` 与 `res/integration-snapshot.json`。具体便携包的版本、SHA-256 和来源记录仍以同一次构建的 `alpha-release-manifest.json` 为准；本节身份字段只是源码侧声明，不代填实际产物哈希。

本候选的能力边界：

- **全功能绿色免安装 Alpha**：仅 Full 便携 ZIP 形态，随包携带完整离线 wheelhouse、runtime-lock、integration-snapshot 与来源记录；不接受 Lite 包替代，不提供安装器。
- **Config v2 authoritative 是默认且唯一的生产配置权威源**：进程默认模式与无效环境变量回退均为 `authoritative`；该模式下正式运行链选用 `NativeConfigFacade`，不再构造 legacy `AppConfig`/`ConfigBase` 对象图，legacy JSON-first 保存与旧的 legacy 投影加载都会显式失败，不存在混合权威。`off`/`shadow`/`canary`/`authoritative` 四种显式模式仅保留用于受控回滚与诊断，不是默认路径。首启在任何 plugins/core 导入前，把 r6 八个 JSON 根的**原始字节**冻结为不可变快照（`config/.config-v2-original/`），并仅在没有已提交 generation 时从该快照一次性迁移；此后每次启动都加载已校验的 CURRENT generation，不回退到可变的 legacy JSON。敏感字段以 DPAPI 应用绑定加密保存（密文带 `DPAPI:v1:` 前缀），写入为原子 generation 事务。需要回到 r6 时，可随时导出完整八根 r6 格式 JSON 回滚 bundle 到 `config/.config-v2-r6-rollback/`（含 manifest 与每根 sha256），该导出从不覆盖 live config 或已有 bundle。`unverified`：真机旧 profile 的首次迁移与崩溃恢复尚无 GUI 回归记录。
- **WS v2 主链路与兼容桥并存**：WebSocket 主链路为 `{id,type,data}` 协议并保留兼容桥；不宣称旧 WS 链已完全退出。
- **真实游戏/模拟器/Agent 未自动验证**：所有真实设备、模拟器控制、账号登录和自动化执行均标记为 `unverified`。源码中的调用链、interface 解析和 dry-run 不等于真实运行成功；任何“可用”结论必须由人工手测卡回填。

## 安装边界（必须遵守）

1. 只使用由本次 Alpha 构建给出的 Full 便携 ZIP，并先核对同目录的 SHA-256 清单和发行清单。
2. 选择一个新的、专用于 A 测的目录；不得选择、覆盖或就地升级冻结 r6 的安装目录。
3. 不移动、删除、覆盖或重命名冻结 r6 产物；r6 升级/回滚仅能按手测卡在隔离副本和已备份用户数据上验证。
4. Alpha 的升级、更新、卸载和回滚边界尚需真实 Windows 手测记录。没有记录时，一律视为 `unverified`。

## 产物完整性与来源

合格候选包应随构建提供下列可核对材料；缺少任一项时，不应作为 A 测包分发：

- `alpha-release-manifest.json`：便携包的文件名、SHA-256、构建输入摘要及发行身份，并明确标记 `portable-only`。
- `SHA256SUMS`：与发行清单一致的产物哈希。
- 包内 `resources/integration-snapshot/evidence/EVIDENCE_INDEX.json` 与外部 `evidence/EVIDENCE_INDEX.json`：对 `app.asar`、snapshot、wheel 声明、安全验证脚本及六份随包说明的逐项 SHA-256/大小索引；两份 index 必须相同。index 不包含自身，也不代替 ZIP 的外层哈希。
- 包内 `resources/integration-snapshot/source-provenance.json`：源码输入树与构建 Git 提交的可追溯记录。
- 包内 `resources/integration-snapshot/plugins/wheels/manifest.json` 与 `runtime-lock.json`：随包 wheelhouse 的声明。
- 本目录的已知缺口、离线首启说明和人工手测卡。

发布者应先用 `SHA256SUMS` 校验 ZIP、最终 manifest 和外部 evidence index，再比对 manifest 与两份 index，最后读取包内来源记录。来源记录存在只表示可追溯性门禁被设计；是否与本次产物匹配，必须由实际构建日志和哈希复核。

## 签名与安全提示

本草案不宣称可执行文件已经完成 Authenticode 签名。签名状态目前为 `unverified`，必须针对**实际解压的可执行文件**运行签名检查并附证据。若签名缺失、无效或待定，应在 A 测招募说明中明确提示，且不得把该状态表述为“已验证发布者”。

请仅从受控 A 测分发位置取得文件；不要从转存、聊天附件或未知镜像执行程序。

## 应从哪里开始

1. 阅读 [RELEASE_NOTES.md](RELEASE_NOTES.md) 和 [KNOWN_GAPS.md](KNOWN_GAPS.md)。
2. 在隔离目录完成 [OFFLINE_FIRST_START.md](OFFLINE_FIRST_START.md) 的前置检查。
3. 按 [MANUAL_TEST_CARDS.md](MANUAL_TEST_CARDS.md) 回填真实 Windows 结果和日志。
4. 仅当相应 CI 门禁已有实际证据时，才把 [CI_GATES.json](CI_GATES.json) 中的 `pending`/`unverified` 改为结果状态。
