# Emulator 专区测试矩阵 (TEST_MATRIX)

> Subagent C 维护。覆盖前端、后端、contract、可访问性、性能、手测六大维度。
> 所有真实设备/GUI 项必须由用户手测回填，未回填的标 `unverified`。
>
> 工作树：`AUTO-MAS-workspace/worktrees/all-plugins-integration` @ `integration/dev-v2-dev-all-plugins` (HEAD `b5e872815a3ea5eef81fc3fd34eb0dc71db32d4e`)
> 生成时间：2026-07-23 (Asia/Shanghai)

## 0. 基线摘要 (observed)

| 指标 | 数值 | 来源 |
| --- | --- | --- |
| `frontend/src/views/Emulator.vue` 总行数 | 1540 | `baseline/emulator-vue-stats.txt` |
| `<script setup>` 行数 | 812 (1..812) | 同上 |
| `<template>` 行数 | 365 (814..1178) | 同上 |
| `<style scoped>` 行数 | 361 (1180..1540) | 同上 |
| `any` 出现次数 | 10 | 同上 |
| 现有 emulator 相关 Vitest 测试 | 0 → 3 文件 54 用例 | 本任务新增 |
| `yarn lint` 基线 | exit 1 (5 prettier errors, 1 warning) | `baseline/yarn-lint.log` |
| `yarn lint` (新增测试后) | exit 0 | `test-runs/` |
| `yarn typecheck` 基线 | exit 2 (`vite.config.ts` replaceAll) | `baseline/yarn-typecheck.log` |
| `yarn test` 基线 | 33 文件 295 用例 全过, 1.97s | `baseline/yarn-test-baseline.log` |
| `yarn test` (新增后) | 36 文件 349 用例 全过, 1.87s | `test-runs/yarn-test-final.log` |
| 后端 `tests/emulator/**` | 不存在 | `tests/` 目录 |
| 后端 `tests/api/test_emulator_api.py` | 不存在 | 同上 |

> 注：`yarn typecheck` 在 `vite.config.ts(11,33)` 报 `replaceAll` 不可用，是工作树既有问题，与 Emulator 专区无关，未由本任务修复（超出 Subagent C 可写范围）。

## 1. 前端 deterministic 测试 (FE-*, Vitest + fake)

测试文件位于 `frontend/src/views/emulator/__tests__/`：

| 文件 | 用例数 | 覆盖维度 |
| --- | --- | --- |
| `fakeEmulatorApi.ts` | (夹具) | 与 `@/api` Service 形状一致的可控 stub |
| `fakeEmulatorService.ts` | (夹具) | 与 `LegacyEmulatorService` 契约一致的 fake provider |
| `emulatorApiContract.test.ts` | 21 | FE-CONTRACT-01..11 |
| `emulatorPolling.test.ts` | 20 | FE-POLL / FE-BOSS / FE-DELETE / FE-STATUS / FE-EMPTY / FE-PATH |
| `providerContractMatrix.test.ts` | 13 | BE-CONTRACT-01..08 |

### 1.1 FE-CONTRACT-* (API 契约)

| ID | 用例 | 状态 |
| --- | --- | --- |
| FE-CONTRACT-01 | getEmulator 全量/单点返回；addEmulator uid 自增；updateEmulator 写回 Info 子字段；deleteEmulator 清理 index/data/devices；searchEmulators 返回副本 | observed pass |
| FE-CONTRACT-02 | 业务失败 (code !== 200) 不改设备状态；覆盖只影响指定方法 | observed pass |
| FE-CONTRACT-03 | setThrow 抛异常后状态保持一致，无半成品写入 | observed pass |
| FE-CONTRACT-04 | 旧响应覆盖保护：后发起的 status 拿到更新数据（fake 同步，真实场景需 epoch 守卫） | observed pass (fake 层) / inferred (前端需补 epoch) |
| FE-CONTRACT-05 | 搜索结果按 path 去重由后端完成；前端导入两次产生独立 uid | observed pass |
| FE-CONTRACT-06 | 导入流程：add 后 update 写入搜索结果字段 | observed pass |
| FE-CONTRACT-07 | 并发 update 串行化，各字段互不覆盖 | observed pass |
| FE-CONTRACT-08 | deleteEmulator 后 devicesData 清理 | observed pass |
| FE-CONTRACT-09 | operate 结束/抛异常后 inFlightOperate 清空 | observed pass |
| FE-CONTRACT-10 | OPEN→ONLINE+adb_address；CLOSE→OFFLINE+清空 adb_address；不波及其他 index | observed pass |
| FE-CONTRACT-11 | 所有调用记录到 calls；reset 清除覆盖 | observed pass |

### 1.2 FE-POLL-* / FE-CLEANUP-* (轮询与生命周期)

| ID | 用例 | 状态 |
| --- | --- | --- |
| FE-POLL-01 | setInterval 在 5000ms 触发 | observed pass |
| FE-POLL-02 | 重复 setInterval 前 clearInterval 不叠加 | observed pass |
| FE-POLL-03 | 空列表不发起轮询请求（早退） | observed pass |
| FE-POLL-04 | unmount 后 clearInterval 不再触发回调 | observed pass |
| FE-POLL-05 | per-device in-flight 防重入：同 deviceKey 未完成时再次调用被忽略 | observed pass |
| FE-POLL-06 | route.path 切换触发 start/stop | observed pass |

### 1.3 FE-BOSS-* (老板键)

| ID | 用例 | 状态 |
| --- | --- | --- |
| FE-BOSS-01 | 录制期间 keydown 收集 Ctrl+Shift+Q，keyup 提交 | observed pass |
| FE-BOSS-02 | 未录制主键时 keyup 不提交 | observed pass |
| FE-BOSS-03 | 老板键替换而非追加（长度始终 1 或 0） | observed pass |
| FE-BOSS-MUMU | type=mumu 时不渲染输入框，显示提示；显示强力关闭开关 | observed pass |
| FE-BOSS-ESC | Esc/失焦停止录制 → 见手测卡 GM-009 | unverified |

### 1.4 FE-DELETE-* (删除)

| ID | 用例 | 状态 |
| --- | --- | --- |
| FE-DELETE-01 | a-popconfirm confirm 才调用 handleDelete | observed pass |
| FE-DELETE-02 | 删除当前激活 Tab 自动跳转相邻 Tab | observed pass |

### 1.5 FE-STATUS-* (设备状态映射)

| ID | 用例 | 状态 |
| --- | --- | --- |
| FE-STATUS-01 | 每个状态有唯一 text/color 组合 | observed pass |
| FE-STATUS-02 | ONLINE/STARTING 可关闭，其他不可关闭 | observed pass |
| FE-STATUS-03 | OFFLINE/ERROR/NOT_FOUND/UNKNOWN 可启动，ONLINE/STARTING/CLOSING 不可 | observed pass |
| FE-STATUS-04 | ERROR 与 NOT_FOUND 都用 error 色但 text 不同（色盲可读） | observed pass |

### 1.6 FE-EMPTY-* / FE-PATH-*

| ID | 用例 | 状态 |
| --- | --- | --- |
| FE-EMPTY-01 | emulatorIndex 为空显示空态大按钮 | observed pass |
| FE-EMPTY-02 | devicesData 为空显示「暂无设备信息」+ 启动按钮 | observed pass |
| FE-PATH-01 | 路径被后端纠正时提示文案含 `->` | observed pass |

## 2. 后端 contract 测试 (BE-CONTRACT-*, fake provider)

| ID | 用例 | 状态 |
| --- | --- | --- |
| BE-CONTRACT-01 | host fallback：provider.kind=host 经 host 路径；plugin installed=false 抛 pluginError | observed pass |
| BE-CONTRACT-02 | real plugin provider：installed=true 经 plugin 路径；支持 list_options/list_device_options | observed pass |
| BE-CONTRACT-03 | 失败恢复：operate 抛错后 status 仍可查询；search_installed 抛错后 get_config 仍可用 | observed pass |
| BE-CONTRACT-04 | 未知 provider：kind=unknown 抛错且不写入任何状态 | observed pass |
| BE-CONTRACT-05 | 超时：operateDelayMs > 0 时 operate 在超时前未完成，推进后完成 | observed pass (fake timers) |
| BE-CONTRACT-06 | 取消：markCancelled 加入 cancelled 集合；取消后 status 不反映 operate 变迁 | observed pass (fake) |
| BE-CONTRACT-07 | reorder 顺序与传入一致，丢失项被过滤 | observed pass |
| BE-CONTRACT-08 | status(null) 全量；status(emulatorId) 单点 | observed pass |

> 真实后端 `LegacyEmulatorService` 的 host fallback 行为（plugin 未注册时回退而非抛错）由 Subagent A 在 `tests/emulator/**` 覆盖；本矩阵只验证 fake 契约形状。

## 3. 可访问性审计 (A11Y-*)

详见 `MANUAL_TEST_CARDS.md` 的可访问性部分。审计清单：

| ID | 项目 | 状态 |
| --- | --- | --- |
| A11Y-01 | 可见焦点（focus-visible 不被全局 outline:none 抹掉） | inferred (Emulator.vue 未显式禁用，但需手测确认) |
| A11Y-02 | 键盘顺序（Tab 顺序符合视觉顺序） | unverified |
| A11Y-03 | 图标按钮名称（FolderOpenOutlined / PlayCircleOutlined / EyeOutlined 等需 aria-label） | inferred (当前 Emulator.vue 的图标按钮未设 aria-label) |
| A11Y-04 | 状态不只靠颜色（ERROR/NOT_FOUND 用 text 区分） | observed pass (FE-STATUS-04) |
| A11Y-05 | 对比度（light/dark 双主题） | unverified |
| A11Y-06 | 140% 缩放无溢出 | unverified |
| A11Y-07 | 表格横向溢出（a-table scroll x: 'max-content'） | inferred (代码已设) |
| A11Y-08 | 危险操作确认（删除走 a-popconfirm） | observed pass |

## 4. 性能审计 (PERF-*)

详见 `MANUAL_TEST_CARDS.md` 与 `KNOWN_GAPS.md`。

| ID | 项目 | before | proposed after | 状态 |
| --- | --- | --- | --- | --- |
| PERF-01 | 页面首开 chunk 大小 | 待 `yarn web` build 输出 | — | inferred (build 在跑) |
| PERF-02 | 轮询请求数 | 每 5s × N 个模拟器串行 getStatus | 批量 status(null) 一次 | proposed |
| PERF-03 | 定时器清理 | onUnmounted stopPolling + route watch | 已实现 | observed pass |
| PERF-04 | 模板内对象重复创建 | a-table columns 每次渲染重建 | 提取常量 | proposed |
| PERF-05 | 长列表/多开设备 | a-table 无虚拟滚动 | 虚拟滚动或分页 | proposed (设备数 > 50 时) |

## 5. 手测卡 (MANUAL-*)

详见 `MANUAL_TEST_CARDS.md`，GM-001 到 GM-014。所有真实设备项标 `unverified` 直到用户回填。

## 6. 联动矩阵 (LINK-*)

详见 `FUNCTION_MATRIX.md` 的联动部分。

| ID | 脚本 | 消费字段 | 状态 |
| --- | --- | --- | --- |
| LINK-MAA | MAA | `Emulator.Id` / `Emulator.Index` | observed (代码) |
| LINK-MaaEnd | MaaEnd | `Game.EmulatorId` / `Game.EmulatorIndex` (ADB 模式) | observed (代码) |
| LINK-SRC | SRC | `Emulator.Id` / `Emulator.Index` | observed (代码) |
| LINK-M9A | M9A | `Emulator.Id` / `Emulator.Index` | observed (代码) |
| LINK-General | General | `Game.EmulatorId` / `Game.EmulatorIndex` (Type=Emulator) | observed (代码) |
| LINK-MaaFW | MaaFW | `Emulator.Id` / `Emulator.Index` (前端) | observed (前端) / inferred (后端走 plugin) |
| LINK-OkScript | OK Script | 不直接消费 emulator id (plugin 内部) | observed (前端无引用) |
| LINK-Okww | Okww | 不直接消费 emulator id (plugin 内部) | observed (前端无引用) |

## 7. 测试运行记录

| 时间 (Asia/Shanghai) | 命令 | 退出码 | 结果 | 日志 |
| --- | --- | --- | --- | --- |
| 2026-07-23 12:28 | `yarn lint` | 1 | 5 errors, 1 warning (基线) | `baseline/yarn-lint.log` |
| 2026-07-23 12:28 | `yarn typecheck` | 2 | vite.config.ts replaceAll | `baseline/yarn-typecheck.log` |
| 2026-07-23 12:28 | `yarn test --run` | 0 | 33 文件 295 用例 | `baseline/yarn-test-baseline.log` |
| 2026-07-23 12:49 | `yarn test --run src/views/emulator/__tests__/` | 1 | 5 failed (首轮) | `test-runs/emulator-tests-run-1.log` |
| 2026-07-23 12:50 | `yarn test --run src/views/emulator/__tests__/` | 0 | 3 文件 53 用例 | `test-runs/emulator-tests-run-2.log` |
| 2026-07-23 12:55 | `yarn test --run src/views/emulator/__tests__/` | 0 | 3 文件 54 用例 | `test-runs/` (final) |
| 2026-07-23 12:56 | `yarn test --run` | 0 | 36 文件 349 用例, 1.87s | `test-runs/yarn-test-final.log` |
| 2026-07-23 12:57 | `yarn lint` (新增后) | 0 | 0 errors, 0 warnings (emulator 相关) | `test-runs/` |

## 8. 已知 barrier

| Barrier | 影响 | 处置 |
| --- | --- | --- |
| `yarn typecheck` 基线失败 (vite.config.ts replaceAll) | 无法用 typecheck 作为前端门禁 | 未修复，超出 Subagent C 可写范围；建议 UI 重构组或 A 处理 |
| `yarn web`/`yarn build` 较慢 | 未拿到 chunk 大小数字 | 持续运行中，结果补到 `baseline/yarn-web-build-2.log` |
| Python 提权未申请 | 未运行 `tests/emulator/`、`tests/api/test_emulator_api.py` | 后端测试目录本就不存在；若 A 创建后需由 A 或主控授权运行 |
| Emulator 专区尚未释放 (B 未实装前端) | 无法做组件挂载测试 | 全部用 fake/契约骨架替代；B 实装后迁移 |
