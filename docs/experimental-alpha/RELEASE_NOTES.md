# AUTO-MAS v6 Experimental Alpha 发布说明（候选草案）

> 状态：`unverified`。尚未绑定某个特定便携包；请以该包的 `alpha-release-manifest.json`、哈希清单和 CI 运行记录补全版本与构建来源。不得将本草案当作已完成发布或已通过全量测试的证明。

## 发布定位

这是一个独立安装、手工分发、手工更新的 Experimental Alpha 候选包：

- 不覆盖冻结 r6，也不替代稳定发布渠道。
- 使用 Alpha 专属应用标识、安装目录和可执行文件名。
- 不提供常规自动更新承诺；更新路径为 `manual-only`。
- 仅在 Full 环境、随包 wheelhouse、runtime lock、来源记录与构建清单完整时才具备送测资格。

## alpha.10 候选变更摘要

本草案对应候选身份 `v6.0.0-alpha.NEXUS-OVERDRIVE.20260726.11`（snapshot_id `nexus-overdrive-all-plugins-v6.0.0-alpha.20260726.r11-portable-v11`）。相对前一候选，身份字段已在 `app/core/config.py`、`frontend/package.json`、`res/version.json` 和 `res/integration-snapshot.json` 四处同步刷新。具体便携包的版本、SHA-256 和来源记录仍以同一次构建的 `alpha-release-manifest.json` 为准。

能力边界声明：

- **全功能绿色免安装 Alpha**：仅 Full 便携 ZIP，随包携带完整离线 wheelhouse、runtime-lock、integration-snapshot 与来源记录；不提供安装器，不接受 Lite 包替代。
- **Config v2 authoritative 是默认且唯一的生产配置权威源**：进程默认模式与无效环境变量回退均为 `authoritative`，正式运行链不再构造 legacy `AppConfig`/`ConfigBase` 对象图，legacy JSON-first 保存会显式失败；`off`/`shadow`/`canary`/`authoritative` 四种显式模式仅保留用于受控回滚与诊断。首启从冻结的 r6 原始字节快照（`config/.config-v2-original/`）一次性迁移，之后每次启动只加载已校验的 CURRENT generation，不回退到可变的 legacy JSON。敏感字段 DPAPI 应用绑定加密，写入为原子 generation 事务；随时可导出完整八根 r6 格式 JSON 回滚 bundle 到 `config/.config-v2-r6-rollback/` 作为退路，且不覆盖 live config 或已有 bundle。`unverified`：真机旧 profile 的首次迁移与崩溃恢复仍缺人工记录。
- **WS v2 主链路与兼容桥并存**：WebSocket 主链路为 `{id,type,data}` 协议并保留兼容桥；不宣称旧 WS 链已完全退出。
- **真实游戏/模拟器/Agent 未自动验证**：所有真实设备、模拟器控制、账号登录和自动化执行均标记为 `unverified`；源码调用链、interface 解析和 dry-run 不等于真实运行成功。

## 候选范围（非验收结论）

本 Alpha 的候选范围包括以下集成方向。每项是否已随具体产物交付、是否可在真实环境运行，均需由该产物的测试证据确认：

- Config v2 的 authoritative 生产运行链，以及 r6 原始快照首启迁移与 r6 回滚 bundle 导出边界。
- REST、WebSocket 与插件前后端桥接的兼容链。
- 官方和本地插件的随包发现、配置、生命周期与失败隔离。
- 新版前端、插件 UI 扩展和脚本管理搜索。
- MaaFW ProjectInterface 适配，以及 HSR、SRA、M7A 的专项配置入口。
- 游戏与模拟器管理入口。
- 随包优先的离线 wheelhouse、runtime lock、来源追溯和 Alpha 安装器链。

上表只是送测范围，不等同于“全部可用”。没有自动化记录或人工手测回填的功能应标为 `unverified`。

## 发布前必须附上的事实

在向测试者发出候选包前，发布者必须补齐而不是口头说明下列项目：

| 项目 | 必须给出的证据 | 当前草案状态 |
| --- | --- | --- |
| 版本与提交 | `alpha-release-manifest.json`、包内来源记录、CI 提交号 | `pending` |
| Full 便携包完整性 | SHA-256 清单与对应文件 | `pending` |
| Full 环境与 wheelhouse | `runtime-lock.json`、wheel manifest、布局检查日志 | `pending` |
| 前端质量门禁 | lint、typecheck、test、build 的实际日志 | `pending` |
| 插件兼容 | 当前源码对应的黑盒/生命周期证据 | `pending` |
| 离线首启 | 结构预检输出和人工离线记录 | `unverified` |
| 真实 Windows 解压运行 | 全新目录、升级/回滚边界的人工记录 | `unverified` |
| 签名 | 对可执行文件的实际签名验证输出 | `unverified` |

## 不在本次 Alpha 承诺之内

- 正式稳定性、无缺陷保证或正式发布资格。
- 自动更新、官方更新通道接入或不受控镜像分发。
- 未经真实设备验证的游戏启动、模拟器控制、账号登录或自动化执行。
- 覆盖 r6 安装目录的升级；这属于禁止的测试路径。

详见 [KNOWN_GAPS.md](KNOWN_GAPS.md) 和 [MANUAL_TEST_CARDS.md](MANUAL_TEST_CARDS.md)。
