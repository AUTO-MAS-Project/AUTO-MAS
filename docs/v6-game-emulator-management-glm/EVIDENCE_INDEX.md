# 证据索引 — 游戏/模拟器管理（Subagent C）

> Subagent C 维护。索引所有测试、审计、手测相关证据文件的绝对路径。
> 工作树：`AUTO-MAS-workspace/worktrees/all-plugins-integration` @ `integration/dev-v2-dev-all-plugins` (HEAD `b5e872815a3ea5eef81fc3fd34eb0dc71db32d4e`)
> 生成时间：2026-07-23 (Asia/Shanghai)
>
> 标注规则：`observed` = 直接读取确认；`inferred` = 基于代码推断；`proposed` = 提议但未实现；`unverified` = 未验证

---

## 1. 证据根目录

所有 Subagent C 证据文件位于：

```
D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration\_alpha_build\a1\glm-game-emulator-management-20260723\subagent-C\
```

---

## 2. 基线证据 (baseline/)

| 文件 | 内容 | 退出码 | 标注 |
|------|------|--------|------|
| `baseline/emulator-vue-stats.txt` | `Emulator.vue` 行数统计：1540 总行 / 812 script / 365 template / 361 style / 10 any | — | `observed` |
| `baseline/yarn-lint.log` | `yarn lint` 基线：5 prettier errors, 1 warning | 1 | `observed` |
| `baseline/yarn-lint-exitcode.txt` | 退出码记录 | 1 | `observed` |
| `baseline/yarn-typecheck.log` | `yarn typecheck` 基线：`vite.config.ts(11,33)` replaceAll 错误 | 2 | `observed` |
| `baseline/yarn-typecheck-exitcode.txt` | 退出码记录 | 2 | `observed` |
| `baseline/yarn-test-baseline.log` | `yarn test --run` 基线：33 文件 295 用例全过, 1.97s | 0 | `observed` |
| `baseline/yarn-test-baseline-exitcode.txt` | 退出码记录 | 0 | `observed` |
| `baseline/yarn-test.log` | 同 baseline 测试日志 | 0 | `observed` |
| `baseline/yarn-test-exitcode.txt` | 退出码记录 | 0 | `observed` |
| `baseline/yarn-test-full.log` | 全量测试日志 | 0 | `observed` |
| `baseline/yarn-test-full-exitcode.txt` | 退出码记录 | 0 | `observed` |
| `baseline/yarn-web-build.log` | `yarn web` dev server 日志（首次） | — | `observed` |
| `baseline/yarn-web-build-2.log` | `yarn web` dev server 日志（第二次，端口 5174） | — | `observed` |

---

## 3. 测试运行证据 (test-runs/)

| 文件 | 内容 | 退出码 | 标注 |
|------|------|--------|------|
| `test-runs/emulator-tests-run-1.log` | emulator 测试首轮：5 failed | 1 | `observed` |
| `test-runs/emulator-tests-run-1-exitcode.txt` | 退出码记录 | 1 | `observed` |
| `test-runs/emulator-tests-run-2.log` | emulator 测试第二轮：3 文件 53 用例全过 | 0 | `observed` |
| `test-runs/emulator-tests-run-2-exitcode.txt` | 退出码记录 | 0 | `observed` |
| `test-runs/yarn-test-after-emulator.log` | 新增 emulator 测试后定向运行 | 0 | `observed` |
| `test-runs/yarn-test-after-emulator-exitcode.txt` | 退出码记录 | 0 | `observed` |
| `test-runs/yarn-test-final.log` | 全量 `yarn test --run` 最终：36 文件 349 用例全过, 1.87s | 0 | `observed` |
| `test-runs/yarn-test-final-exitcode.txt` | 退出码记录 | 0 | `observed` |

---

## 4. 测试文件证据

测试文件位于工作树源码目录（非 `_alpha_build`）：

| 文件 | 用例数 | 覆盖维度 | 标注 |
|------|--------|----------|------|
| `frontend/src/views/emulator/__tests__/fakeEmulatorApi.ts` | (夹具) | 与 `@/api` Service 形状一致的可控 stub | `observed` |
| `frontend/src/views/emulator/__tests__/fakeEmulatorService.ts` | (夹具) | 与 `LegacyEmulatorService` 契约一致的 fake provider | `observed` |
| `frontend/src/views/emulator/__tests__/emulatorApiContract.test.ts` | 21 | FE-CONTRACT-01..11 | `observed` pass |
| `frontend/src/views/emulator/__tests__/emulatorPolling.test.ts` | 20 | FE-POLL / FE-BOSS / FE-DELETE / FE-STATUS / FE-EMPTY / FE-PATH | `observed` pass |
| `frontend/src/views/emulator/__tests__/providerContractMatrix.test.ts` | 13 | BE-CONTRACT-01..08 | `observed` pass |

绝对路径前缀：
```
D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration\
```

---

## 5. 源码证据（只读，不可改）

以下源码文件作为测试设计和审计的输入，仅读取未修改：

| 文件 | 行数 | 用途 | 标注 |
|------|------|------|------|
| `frontend/src/views/Emulator.vue` | 1540 | 前端模拟器管理主组件 | `observed` |
| `app/api/emulator.py` | — | 8 个 API 端点 | `observed` |
| `app/core/emulator_manager.py` | — | EmulatorManager 后端管理器 | `observed` |
| `app/plugins/emulator_compat.py` | — | LegacyEmulatorService host fallback | `observed` |
| `app/models/emulator.py` | — | DeviceStatus IntEnum / DeviceBase ABC | `observed` |
| `app/utils/emulator/tools.py` | — | search_all_emulators 注册表枚举 | `observed` |
| `app/models/config.py` | — | MAA/SRC/M9A 用 Emulator.Id/Index；MaaEnd/General 用 Game.EmulatorId/EmulatorIndex | `observed` |
| `app/task/MAA/manager.py` | — | MAA 脚本 emulator 获取与收尾 | `observed` |
| `app/task/MaaEnd/manager.py` | — | MaaEnd 脚本 emulator 获取与收尾 | `observed` |
| `app/task/SRC/manager.py` | — | SRC 脚本 emulator 获取与收尾 | `observed` |
| `app/task/M9A/manager.py` | — | M9A 脚本 emulator 获取与收尾 | `observed` |
| `app/task/general/adapter.py` | — | General 脚本 schema options 构建 | `observed` |
| `frontend/src/views/EditView/Script/MAAScriptEdit.vue` | — | MAA 脚本编辑页模拟器选择器 | `observed` |
| `frontend/src/views/EditView/Script/MaaEndScriptEdit.vue` | — | MaaEnd 脚本编辑页模拟器选择器 | `observed` |
| `frontend/src/views/EditView/Script/SRCScriptEdit.vue` | — | SRC 脚本编辑页模拟器选择器 | `observed` |
| `frontend/src/views/EditView/Script/GeneralScriptEdit.vue` | — | General 脚本编辑页模拟器选择器 | `observed` |
| `frontend/src/views/EditView/Script/MaaFWScriptEdit.vue` | — | MaaFW 脚本编辑页 composable 模式 | `observed` |

---

## 6. 交付物文件

| 文件 | 内容 | 标注 |
|------|------|------|
| `docs/v6-game-emulator-management-glm/TEST_MATRIX.md` | 测试矩阵：基线摘要、FE/BE 测试矩阵、A11Y 审计、PERF 审计、LINK 联动矩阵、测试运行记录、barrier | `observed` |
| `docs/v6-game-emulator-management-glm/MANUAL_TEST_CARDS.md` | 14 张 Windows 手测卡（GM-001 ~ GM-014） | `unverified` (待用户手测) |
| `docs/v6-game-emulator-management-glm/KNOWN_GAPS.md` | 已知缺陷（A 后端 + C 测试与可用性） | `observed` / `inferred` |
| `docs/v6-game-emulator-management-glm/FUNCTION_MATRIX.md` | 功能矩阵（B 前端 + A 后端 + C 脚本联动） | `observed` |
| `docs/v6-game-emulator-management-glm/EVIDENCE_INDEX.md` | 本文件：证据索引 | `observed` |

绝对路径前缀：
```
D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration\
```

---

## 7. 测试运行记录汇总

| 时间 (Asia/Shanghai) | 命令 | 退出码 | 结果 | 日志文件 |
| --- | --- | --- | --- | --- |
| 2026-07-23 12:28 | `yarn lint` | 1 | 5 errors, 1 warning (基线) | `baseline/yarn-lint.log` |
| 2026-07-23 12:28 | `yarn typecheck` | 2 | `vite.config.ts` replaceAll | `baseline/yarn-typecheck.log` |
| 2026-07-23 12:28 | `yarn test --run` | 0 | 33 文件 295 用例, 1.97s (基线) | `baseline/yarn-test-baseline.log` |
| 2026-07-23 12:49 | `yarn test --run src/views/emulator/__tests__/` | 1 | 5 failed (首轮) | `test-runs/emulator-tests-run-1.log` |
| 2026-07-23 12:50 | `yarn test --run src/views/emulator/__tests__/` | 0 | 3 文件 53 用例 (修复后) | `test-runs/emulator-tests-run-2.log` |
| 2026-07-23 12:55 | `yarn test --run src/views/emulator/__tests__/` | 0 | 3 文件 54 用例 (final) | `test-runs/` |
| 2026-07-23 12:56 | `yarn test --run` | 0 | 36 文件 349 用例, 1.87s (全量最终) | `test-runs/yarn-test-final.log` |
| 2026-07-23 12:57 | `yarn lint` (新增测试后) | 0 | 0 errors, 0 warnings (emulator 相关) | `test-runs/` |

---

## 8. 未解决的 barrier

| Barrier | 影响 | 处置 | 标注 |
|---------|------|------|------|
| `yarn typecheck` 基线失败 (`vite.config.ts` replaceAll) | 无法用 typecheck 作为前端门禁 | 未修复，超出 Subagent C 可写范围；建议 UI 重构组或 A 处理 | `observed` |
| `yarn web`/`yarn build` chunk 大小未获取 | PERF-01 无法填入实际数字 | `yarn web` 启动 dev server 而非生产构建；需执行 `yarn build` | `unverified` |
| Python 提权未申请 | 未运行 `tests/emulator/`、`tests/api/test_emulator_api.py` | 后端测试由 A 创建并报告 58 passed；C 未独立验证 | `unverified` |
| Emulator 专区尚未释放 (B 未实装前端重构) | 无法做组件挂载测试 | 全部用 fake/契约骨架替代；B 实装后迁移 | `observed` |
| 所有 GM-001 ~ GM-014 手测卡 | 真实设备/GUI 行为未验证 | 标 `unverified`，待用户手测回填 | `unverified` |

---

## 9. Subagent A 交叉引用

Subagent A 的证据文件位于：
```
D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration\_alpha_build\a1\glm-game-emulator-management-20260723\subagent-A\
```

| 文件 | 内容 | 标注 |
|------|------|------|
| `pytest-run-final.log` | 后端 pytest 58 passed | `observed` (from A 报告) / `unverified` (C 未独立运行) |

Subagent A 修改的后端文件清单见 `KNOWN_GAPS.md` 第 6 节和 `FUNCTION_MATRIX.md` B10 节。

---

## 10. Subagent B 交叉引用

Subagent B 的前端只读研究产出位于 `docs/v6-game-emulator-management-glm/`：

| 文件 | 内容 | 标注 |
|------|------|------|
| `FUNCTION_MATRIX.md` 前端部分（第 1~6 节） | 功能清单、API 端点使用矩阵、组件使用矩阵、状态变量矩阵、优先级汇总、测试矩阵输入 | `observed` |
| `UI_INFORMATION_ARCHITECTURE.md` | UI 信息架构 | `observed` |
| `CURRENT_BEHAVIOR_MAP.md` | 当前行为映射 | `observed` |
| `API_PROVIDER_CONTRACT.md` | API/Provider 契约 | `observed` |

---

> 本索引完毕。所有证据文件路径均为 Windows 绝对路径。
