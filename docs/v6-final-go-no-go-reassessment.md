# v6 最终收口 GO/NO-GO 复评

> 复评时间：2026-07-23（基于当前未提交工作树状态，非旧 HEAD b5e872815）
> 工作树：`AUTO-MAS-workspace\worktrees\all-plugins-integration`（分支 `integration/dev-v2-dev-all-plugins`）
> 对照基线：`docs/v6-glm-master/FINAL_GO_NO_GO.md`（基于旧 HEAD）
> 复评性质：代码层 observed + 部分未实测项明确标注

本复评对照旧审计的 10 个领域，逐条核实【当前未提交工作树】下的真实状态。旧审计多项发现已在未提交工作中修复。

---

## 总判定

**当前状态：仍为 NO-GO（不可正式发布），但代码层 P0/P1 阻断已大幅收敛。**

长期目标未完成的硬阻断（从 3 个降至 2 个）：
1. **配置旧基类仍未退出正式运行链（P0）**：当前启动仍先执行 `Config.init_config()`，随后才初始化 `ConfigService`；生产配置根仍由 `ConfigBase` / `ConfigItem` / `MultipleConfig` 承载，`app/configuration/v2` 下只有框架和示例根。现有 `_authoritative_load()` / `_migrate_legacy_to_v2()` 是 legacy 对象上的 TOML 投影与回填，不是原生 Config v2 authoritative，也不能作为 A 测放行依据。
2. **无签名正式安装包**：所有候选仍 NotSigned，需 SignPath CI 触发（无法在本地完成）。
3. **无真实设备/Windows GUI 手测证据**：49 项验收与 50 张手测卡仍 blocked。

---

## 按领域复评

### 1. Config

| 判定 | **NO-GO：authoritative 仍是 legacy-first 投影链，旧配置基类尚未退出正式运行路径** |
|---|---|
| 旧 P1-SEC-01 DPAPI 无 entropy | **已修复**（observed）：`app/utils/security.py:31-39` 引入 `DPAPI_APPLICATION_ENTROPY`、版本化 `DPAPI:v1:` 前缀、`dpapi_decrypt_with_status` 迁移检测 |
| 旧 P1-SEC-02 EncryptValidator 静默替换 | **已修复**（observed）：`app/models/ConfigBase.py:302-361` `normalize()` 在 persisted 失败时抛 `EncryptedConfigValueError`，不静默替换 |
| 旧 P1-CFG-01 shadow→authoritative 丢失 | **仍未关闭，提升为 A 测 P0 门禁**：启动顺序是 legacy 先加载，`ConfigBase.save()` 也是 legacy JSON 先写、v2 observer 后通知；`_authoritative_load()` 还允许逐根 legacy fallback，可能形成混合权威。必须完成原生生产根、全根 generation/CURRENT 原子提交、启动前 r6 原始字节快照和 fail-closed authoritative 后才能放行 |
| 命名空间遗留 | **已清理**（本轮）：`v2/examples/reference_config.py`、`v2/support/logger.py`、`v2/manager.py` 三处 `config_framework_v2` → `app.configuration` |
| 说明 | Config v2 框架与 shadow 观测链已存在，但生产原生根迁移尚未发生；当前 `authoritative` 环境变量路径必须视为实验性且 fail-closed 禁用。DPAPI 设备验证只是后续门禁之一，不能替代架构迁移 |

### 2. WebSocket

| 判定 | **条件性 GO（代码层），NO-GO（运行时未验证）** |
|---|---|
| 旧 P1-WS-01 连接替换竞态 | **已修复**（observed）：`app/core/ws/manager.py:52,134-149,397-408` 锁+身份校验+`_is_current`+来源绑定发送 |
| 全栈能力 | **已实现**（observed）：鉴权（loopback+subprotocol HMAC）、重连、背压（4MiB/64条/5s）、关闭（drain+inflight）、兼容链路（旧 `send_websocket_message` 委托） |
| soak 验证 | **未验证**：30min/10k+ 真实 Electron soak 未执行 |

### 3. 插件

| 判定 | **NO-GO（wheelhouse drift）** |
|---|---|
| 旧 P0-REL-01 wheelhouse drift | **仍存在，且旧记录再次过期**：正式 wheelhouse 仍为 `automas-script-hsr` 0.1.2、SRA 0.1.2、M7A 0.1.3、meta 0.1.3；当前独立 HSR 源码已推进到 core/SRA 0.1.4、M7A/meta 0.1.5。新的 r3 scratch 候选已构建但仍在安全审查，尚未获准替换正式 wheelhouse，也尚未重生成 runtime-lock/snapshot |
| 旧 P1-PLG-01 19 插件未安装 | **未变**：site-packages 仅 4 dist-info，需运行时安装 |

### 4. UI

| 判定 | **条件性 GO（代码层）** |
|---|---|
| 旧 P0-SEC-02 iframe sandbox | **已修复**（observed）：`PluginPageHost.vue:10-19` sandbox 已加，跨源场景合理 |
| 旧 P0-SEC-03 Vue 全局暴露 | **已修复**（本轮）：`pluginFrontendLoader.ts:97-107` 改用 `Object.defineProperty` 不可枚举/不可写/不可配置，一次性设置 |
| 旧 P0-PERF-01 manualChunks | **已修复**（observed）：`vite.config.ts:73-81` 已配置 |
| 旧 P0-PERF-02 启动打点 | **已修复**（本轮）：`useAppLifecycle.ts` 新增 `performance.now()` 打点（lifecycle-init/connect-attempt/ws-first-open） |
| 预存 typecheck 错误 | 2 个预存错误（`emulatorApiContract.test.ts`、`vite.config.ts replaceAll` lib target），非本轮引入 |

### 5. 启动

| 判定 | **条件性 GO（打点已注入），NO-GO（未实测）** |
|---|---|
| 旧 P0-PERF-02 启动打点缺失 | **已修复**（本轮）：打点已注入，需真实冷启动测量量化 5100ms 预算 |

### 6. CI

| 判定 | **GO（代码层）** |
|---|---|
| 旧 P1-CI-01 Action SHA pin | **已修复**（observed）：全部 40 位 SHA pin，`ACTION_PINS.md` 维护对照表 |
| 旧 P1-CI-02 SignPath slug | **已修复**（observed）：两处 `project-slug: AUTO_MAA` 一致 |
| 旧 P1-CI-03 permissions 最小化 | **已修复**（observed）：每 job 显式最小权限 |

### 7. wheelhouse

| 判定 | **NO-GO（blocker）** |
|---|---|
| 旧 P0-REL-01 snapshot drift | **仍存在**：需授权后重新生成 `res/integration-snapshot.json` |

### 8. 签名

| 判定 | **NO-GO** |
|---|---|
| 旧 P0-REL-03 NotSigned | **未变**：需 SignPath CI workflow_dispatch 触发后验证 |

### 9. 离线安装

| 判定 | **条件性 GO（闭包完整），NO-GO（未实测安装）** |
|---|---|
| 证据 | environment.zip SHA 通过，离线闭包完整；未执行真实离线安装测试 |

### 10. 真实设备

| 判定 | **NO-GO（全部 blocked）** |
|---|---|
| 证据 | 49 项验收 blocked，50 张手测卡 blocked，8 张关键手测卡（MC-001/002/018/028/031/039/043/050）必须回填 |

---

## 复评汇总矩阵

| 领域 | 旧判定 | 复评判定 | 变化 |
|---|---|---|---|
| Config | NO-GO | NO-GO | 安全加固不等于权威迁移；生产原生根为 0，启动和保存仍是 legacy-first，需先完成 fail-closed、全根代际事务及旧类退出 |
| WebSocket | NO-GO | 条件性 GO（代码层） | P1-WS-01 已修复，全栈已实现；soak 未验证 |
| 插件 | NO-GO | NO-GO | wheelhouse drift 形态变化：数量/SHA 自洽，但 HSR 四包版本落后源码 |
| UI | 条件性 GO | 条件性 GO | P0-SEC-03/PERF-02 本轮修复；P0-SEC-02/PERF-01 已修复 |
| 启动 | NO-GO | 条件性 GO（打点已注入） | P0-PERF-02 已修复；需实测 |
| CI | NO-GO | GO（代码层） | P1-CI-01/02/03 全部已修复 |
| wheelhouse | NO-GO | NO-GO | snapshot drift 形态变化：内部自洽，HSR 四包版本落后源码 |
| 签名 | NO-GO | NO-GO | 需 SignPath CI |
| 离线安装 | 条件性 GO | 条件性 GO | 未变 |
| 真实设备 | NO-GO | NO-GO | 未变 |

---

## 本轮（2026-07-23）新增修复清单

以下 6 项为本轮在未提交工作树上完成的代码级修复：

| 修复 | 文件 | 内容 |
|---|---|---|
| Config v2 命名空间 1 | `app/configuration/v2/examples/reference_config.py` | `from config_framework_v2` → `from app.configuration` |
| Config v2 命名空间 2 | `app/configuration/v2/support/logger.py` | logger 命名空间 → `app.configuration` |
| Config v2 命名空间 3 | `app/configuration/v2/manager.py:149-157` | ContextVar 名称 → `app_configuration_*` |
| P0-SEC-03 Vue 全局暴露 | `frontend/src/plugin/pluginFrontendLoader.ts:97-107` | `Object.defineProperty` 不可枚举/不可写/不可配置，一次性 |
| P0-PERF-02 启动打点 | `frontend/src/composables/useAppLifecycle.ts` | `performance.now()` 埋点 lifecycle-init/connect-attempt/ws-first-open |
| P1-CFG-01 authoritative 模式 | `main.py`、`app/core/config_service.py`、`app/models/ConfigBase.py` | 现有 `_authoritative_load()` + `_migrate_legacy_to_v2()` 仍依赖 legacy 对象；源码实证显示 legacy 先加载、JSON 先写，不能声明 v2 TOML 已成为唯一权威源 |

| authoritative 模式测试 | `tests/configuration/test_config_v2_exp_alpha.py` | 116 个配置测试可作为当前投影/兼容路径回归证据，但其中 toy-root `TestAuthoritativeMode` 不能证明八个真实生产根、跨根原子提交、r6 原始字节迁移或旧基类退出 |
| 8 张关键手测卡 | `docs/v6-final-manual-test-cards.md` | MC-001/002/018/028/031/039/043/050 完整步骤、期望结果、证据清单 |
| 离线首次启动验证脚本 | `scripts/verify_offline_first_start.ps1` | 目录结构/wheelhouse/health/配置创建/日志网络错误检查 |
| r6 升级回滚验证脚本 | `scripts/verify_r6_upgrade_rollback.ps1` | r6 备份/v2 迁移验证/配置值一致性/回滚测试/明文密钥检查 |

验证：
- `uv run python -m py_compile app/core/config_service.py`：0 错误
- `uv run pytest tests/configuration/ -v`：历史记录为 116 passed in 1.58s；仅证明当时测试集合通过，不等于 authoritative 发布门禁通过
- `yarn typecheck`：通过（仅剩 2 个预存错误，非本轮引入）

---

## 长期目标完成条件核查

用户定义的完成条件：
1. ❌ **配置旧基类完全退出正式运行链** — 未实现。当前生产根仍由旧类承载，legacy JSON 仍先加载/先保存；禁止仅凭环境变量或设备 round-trip 将默认模式切到 `authoritative`。
2. ❌ **所有功能门禁通过** — ❌ wheelhouse drift blocker 未解，真实设备验收全 blocked。
3. ❌ **正式安装包和证据齐全** — ❌ 无签名安装包，无真实 Windows GUI/设备手测证据。

**结论：长期目标未完成。** 除签名安装包和设备手测外，仍有 Config v2 原生根迁移、全根原子持久化、旧基类退出、HSR 新 wheel 复核与正式 wheelhouse/runtime-lock/snapshot 重建等源码与发布硬阻断。

---

## 后续最小完成路径

### A. Config v2 authoritative 实现门禁（设备验证之前）
1. ⬜ authoritative 对未完成原生迁移的根 fail-closed，禁止逐根 legacy fallback
2. ✅ `_migrate_legacy_to_v2()` 实现 r6 升级迁移
3. ⬜ 以 generation/CURRENT 一次提交全部必需根，持久化成功后才更新 live state 和 WS outbox
4. ✅ 降级恢复（v2 TOML 读取失败时保留 legacy JSON 值）
5. ⬜ 使用脱敏的真实 r6 八根 fixture 验证原始字节快照、升级、崩溃恢复、上一代回滚和旧类零运行引用；现有 116 tests 不是该门禁
6. ⬜ 上述源码门禁通过后，再在真实 Windows DPAPI 环境验证：
   - v2 TOML 启动读取正确性
   - r6 JSON → v2 TOML 迁移 round-trip 一致性
   - DPAPI 密文在 v2 TOML 中的持久化与解密
   - 降级恢复（删除 v2 TOML 后回退到 JSON）
7. ⬜ 只有源码、fixture 与设备门禁全部通过后，才允许从 `shadow` 切换到 native `authoritative`

### B. wheelhouse snapshot 重新生成
1. 用户授权后运行 `scripts/verify_wheelhouse_snapshot.py` 重新生成 `res/integration-snapshot.json`。
2. 确认 `core_distribution_version` 5.4.0b1 vs 6.0.0a1 的版本预期。

### C. 签名与安装包
1. SignPath CI workflow_dispatch 触发签名。
2. 验证 Authenticode Status/Subject/Thumbprint。

### D. 真实设备手测
1. 回填 8 张关键手测卡（MC-001/002/018/028/031/039/043/050）—— 模板已就绪：`docs/v6-final-manual-test-cards.md`。
2. 离线首次启动验证 —— 脚本已就绪：`scripts/verify_offline_first_start.ps1`。
3. r6 覆盖升级与回滚验证 —— 脚本已就绪：`scripts/verify_r6_upgrade_rollback.ps1`。
4. 失败隔离、卸载验证 —— 需后续补充。

### E. WebSocket soak
1. 30min/10k+ 真实 Electron soak，复核 4MiB/64条/5s 参数。
