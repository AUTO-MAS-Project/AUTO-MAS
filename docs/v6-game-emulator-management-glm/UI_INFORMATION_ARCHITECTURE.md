# UI 信息架构设计 — 游戏/模拟器管理 v6 重构

> Subagent B 前端只读研究产出（Emulator 专区未释放，本文件为设计稿，不含 `frontend/src/**` 实现）
> 工作树：`D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration`
> 证据基线：`_alpha_build/a1/glm-game-emulator-management-20260723/subagent-B/behavior-baseline.md`
> 标注规则：`observed` = 现状已确认；`inferred` = 基于代码推断；`proposed` = 重构设计建议；`unverified` = 需后续验证

---

## 目录

1. [设计目标与约束](#1-设计目标与约束)
2. [模块边界设计](#2-模块边界设计)
3. [组件树与 props/emits](#3-组件树与-propsemits)
4. [类型方案（消除 any）](#4-类型方案消除-any)
5. [页面状态机](#5-页面状态机)
6. [轮询与防竞态](#6-轮询与防竞态)
7. [操作按钮状态机](#7-操作按钮状态机)
8. [老板键录制方案](#8-老板键录制方案)
9. [路径选择方案](#9-路径选择方案)
10. [自动搜索导入方案](#10-自动搜索导入方案)
11. [插件兼容方案](#11-插件兼容方案)
12. [响应式与可访问性](#12-响应式与可访问性)
13. [WS 通知订阅设计](#13-ws-通知订阅设计)
14. [与现有代码的边界](#14-与现有代码的边界)

---

## 1. 设计目标与约束

### 1.1 设计目标（proposed）

| 目标 | 说明 | 对应问题 |
|------|------|----------|
| 消除假成功 | `/operate` 返回 200 不代表操作成功，需通过 WS `emulator.notice` 反馈真实结果 | Q1/Q2 |
| 消除竞态 | 轮询、保存、手动加载均需 epoch/AbortController 防竞态 | Q3/Q4/Q6 |
| 类型安全 | 全部 `any` 替换为 OpenAPI 生成类型 | Q11 |
| v6 规范统一 | 使用 v6 token、v6 状态组件，移除本地 CSS 变量与渐变标题 | Q12/Q14/Q15/Q16 |
| 操作互斥合理 | per-device 互斥，不跨设备锁死 | 新增 |
| 老板键录制健壮 | Esc 取消、blur 停止、IME 处理、主键校验 | Q7a–Q7f |
| 路径校验前置 | `file-exists` IPC 预校验 + 后端纠正回显 | Q8a–Q8c |
| 搜索导入健壮 | 去重、type 合法性过滤、导入后聚焦 | Q9a–Q9d |
| 响应式达标 | 960×900 最小窗口、100/125/140% 缩放自适应 | Q13 |
| 低性能降级 | `data-perf-mode='low'` + `prefers-reduced-motion` 感知 | 新增 |

### 1.2 硬约束（observed）

- **不得修改** `frontend/src/api/**`（OpenAPI 生成）、lockfile、package.json。
- **不得修改** UI 重构组独占文件：`AppLayout.vue`、`TitleBar.vue`、`styles/**`、`theme/**`、`components/v6/**`、`composables/useTheme.ts`、`composables/useAppBackground.ts`。只复用其现有接口和 token。
- keep-alive 仅含 `Scheduler`，Emulator 页面不缓存（observed，`AppLayout.vue`）。
- 后端 `DeviceStatus.CLOSEING=3` 拼写错误属历史遗留，前端不修正（observed）。
- 后端 `/operate` 为 fire-and-forget（`asyncio.create_task`），前端不能依赖其返回值判断成功（observed）。

---

## 2. 模块边界设计

### 2.1 现状问题（observed）

当前 `Emulator.vue`（1539 行）将全部逻辑集中在单文件 `<script setup>` 中：
- 列表加载、Tab 管理、轮询、配置编辑、即时保存、设备操作、老板键录制、路径选择、搜索导入——全部耦合。
- 无 composable 抽离，状态变量 20+ 个直接散落在组件作用域。
- 测试困难：无法对单个逻辑单元独立测试。

### 2.2 提议模块划分（proposed）

```
frontend/src/
├── views/
│   └── Emulator.vue                          # 页面编排层（薄壳，<200 行）
│
├── composables/
│   ├── useEmulatorManagement.ts              # 列表/选择/加载/刷新/轮询生命周期
│   ├── useEmulatorConfig.ts                  # 配置表单编辑/即时保存/防竞态
│   ├── useEmulatorOperations.ts              # open/close/show + WS 通知订阅
│   ├── useEmulatorDiscovery.ts               # 自动搜索/去重/导入/过滤
│   └── useBossKeyRecorder.ts                 # 老板键录制状态机
│
└── components/emulator/
    ├── EmulatorToolbar.vue                   # 顶部工具栏（搜索/添加）
    ├── EmulatorConfigPanel.vue               # 配置表单（a-descriptions）
    ├── EmulatorDeviceTable.vue               # 设备列表表
    ├── EmulatorDeviceActions.vue             # 设备操作按钮组（per-device）
    ├── EmulatorDiscoveryModal.vue            # 搜索结果模态框
    └── EmulatorPathPicker.vue                # 路径选择器（含 file-exists 校验）
```

### 2.3 各模块职责（proposed）

#### `Emulator.vue`（页面编排层）
- 职责：路由监听、页面级状态机调度、组合各 composable、渲染顶层组件树。
- 不含：具体 API 调用、轮询实现、表单逻辑、录制逻辑。
- 预期行数：<200 行。

#### `useEmulatorManagement.ts`（列表与轮询）
- 职责：
  - `loadEmulators()`：加载全部模拟器配置（`getEmulatorApiEmulatorGetPost`）。
  - `refreshEmulatorConfig(uuid?)`：刷新单个/全部配置。
  - `activeKey` 管理 + localStorage 持久化。
  - 轮询生命周期：`startPolling`/`stopPolling`/`pollDevicesStatus`，含 epoch 防竞态 + visibility 暂停。
  - `loadDevices(uuid)`：手动加载设备状态（含 epoch 与轮询互斥）。
- 暴露：`emulatorIndex`、`emulatorData`、`devicesData`、`loading`、`loadingDevices`、`activeKey`、操作方法。
- 状态归属：`devicesData`、`emulatorData`、`emulatorIndex`、`activeKey`。

#### `useEmulatorConfig.ts`（配置编辑与保存）
- 职责：
  - `editingDataMap`：per-uuid 编辑态 `EmulatorInfo`。
  - `buildEditingData(config)`：从 `EmulatorConfig` 构建 `EmulatorInfo`。
  - `handleSaveChange(uuid, key, value)`：即时保存，含 per-uuid save epoch 防竞态。
  - `handleDelete(uuid)`：删除 + Tab 重选。
  - `handleAdd()`：新增 + 切换。
- 暴露：`editingDataMap`、`savingMap`、`getEditingData`、保存/删除/新增方法。
- 依赖：`useEmulatorManagement` 的 `refreshEmulatorConfig`、`loadEmulators`。

#### `useEmulatorOperations.ts`（设备操作与 WS）
- 职责：
  - `startEmulator(uuid, index)` / `stopEmulator` / `showEmulator`：per-device in-flight Set。
  - **不依赖** `/operate` 返回值判断成功（Q1 修复）。
  - 订阅 WS `emulator.notice`，根据 `level` 与 `message` 展示成功/失败 toast（Q2 修复）。
  - 操作后触发一次设备状态刷新（非轮询等待）。
- 暴露：`startingDevices`、`stoppingDevices`、`showingDevices`（`Set<string>`，key=`${uuid}-${index}`）、操作方法、`lastNotice`。
- 依赖：`useEmulatorManagement` 的 `loadDevices`、`useWebSocket`。

#### `useEmulatorDiscovery.ts`（搜索导入）
- 职责：
  - `handleSearch()`：调用搜索 API。
  - 去重：将 `searchResults` 与 `emulatorData` 中已存在的 path 比对，标记 `alreadyImported`。
  - type 合法性过滤：`result.type` 不在 `('general'|'mumu'|'ldplayer')` 内的结果标记 `invalid`。
  - `handleImport(result)`：两步导入（add + update），导入后聚焦新 Tab。
- 暴露：`searching`、`searchResults`（含 `alreadyImported`/`invalid` 标记）、`showSearchModal`、搜索/导入方法。
- 依赖：`useEmulatorManagement`、`useEmulatorConfig`。

#### `useBossKeyRecorder.ts`（老板键录制）
- 职责：
  - 录制状态机：`startRecord(uuid)` / `stopRecord(uuid)` / `cancelRecord(uuid)`。
  - keydown/keyup 处理：修饰键收集 + 主键校验 + Esc 取消 + IME 处理。
  - blur 自动取消。
  - 保存：`handleSaveChange(uuid, 'boss_keys', [combo])`。
- 暴露：`recordingUuid`（单录制锁定）、`recordedKeys`、录制控制方法。
- 依赖：`useEmulatorConfig` 的 `handleSaveChange`。

---

## 3. 组件树与 props/emits

### 3.1 组件树（proposed）

```
Emulator.vue (页面编排)
├── EmulatorToolbar.vue
│   props: { searching: boolean, hasEmulators: boolean }
│   emits: { search: void, add: void }
│
├── [空状态] v-if="!hasEmulators"
│   └── EmptyState.vue (v6 组件，复用)
│       props: { description: string, actions: ActionButton[] }
│
├── [主内容] v-else
│   ├── EmulatorTabs (a-tabs 包装，可选)
│   │   └── per-tab:
│   │       ├── EmulatorConfigPanel.vue
│   │       │   props: { uuid: string, editingData: EmulatorInfo, saving: boolean,
│   │       │           recordingUuid: string | null, typeOptions: TypeOption[] }
│   │       │   emits: { save: (key, value) => void, delete: (uuid) => void,
│   │       │            selectPath: (uuid) => void, startRecord: (uuid) => void,
│   │       │            stopRecord: (uuid) => void, setBossKey: (uuid, combo) => void }
│   │       │
│   │       └── EmulatorDeviceTable.vue
│   │           props: { uuid: string, devices: Record<string, DeviceInfo>,
│   │           │       loading: boolean, inFlight: Set<string> }
│   │           emits: { operate: (uuid, index, action) => void }
│   │           │
│   │           └── EmulatorDeviceActions.vue (行内按钮组)
│   │               props: { uuid: string, index: string, status: number,
│   │               │       inFlight: boolean, canStart: boolean, canStop: boolean }
│   │               emits: { start: void, stop: void, show: void }
│
└── EmulatorDiscoveryModal.vue
    props: { visible: boolean, searching: boolean,
             results: SearchResultItem[] (含 alreadyImported/invalid 标记) }
    emits: { import: (result) => void, close: void }
```

### 3.2 关键 props/emits 设计原则（proposed）

1. **单向数据流**：子组件不持有业务状态，仅通过 props 接收、emits 上报。
2. **per-uuid 隔离**：每个 Tab 的配置与设备数据独立，不共享 editing/in-flight 状态。
3. **操作粒度**：`EmulatorDeviceActions` 接收单个设备的 `inFlight` boolean（而非整个 Set），避免子组件遍历 Set。
4. **类型透传**：props 使用生成类型（`EmulatorInfo`、`DeviceInfo`），不引入 `any`。

---

## 4. 类型方案（消除 any）

### 4.1 已可用的生成类型（observed）

| 类型 | 来源文件 | 用途 |
|------|----------|------|
| `EmulatorConfig` | `api/models/EmulatorConfig.ts` | `{ Info?: EmulatorConfig_Info \| null }` |
| `EmulatorConfig_Info` | `api/models/EmulatorConfig_Info.ts` | `{ Name?, Type?: 'general'\|'mumu'\|'ldplayer'\|null, Path?, BossKey?, MaxWaitTime?, ForceKillOnClose? }` |
| `EmulatorConfigIndexItem` | `api/models/EmulatorConfigIndexItem.ts` | `{ uid: string; type: string }` |
| `EmulatorGetOut` | `api/models/EmulatorGetOut.ts` | `{ code?, status?, message?, index: EmulatorConfigIndexItem[], data: Record<string, EmulatorConfig> }` |
| `DeviceInfo` | `api/models/DeviceInfo.ts` | `{ title: string; status: number; adb_address: string }` |
| `EmulatorSearchResult` | `api/models/EmulatorSearchResult.ts` | `{ type: string; path: string; name: string }` |
| `EmulatorOperateIn.operate` | `api/models/EmulatorOperateIn.ts` | `enum { OPEN, CLOSE, SHOW }` |

### 4.2 提议的本地类型（proposed，放在 composable 或 `types.ts`）

```typescript
// useEmulatorManagement.ts
type EmulatorDataMap = Record<string, EmulatorConfig>           // 替换 Record<string, any>
type DevicesDataMap = Record<string, Record<string, DeviceInfo>> // 替换 Record<string, Record<string, Record<string, any>>>

// useEmulatorConfig.ts
interface EmulatorInfo {
  name: string
  type: 'general' | 'mumu' | 'ldplayer' | ''   // 空串表示未设置
  path: string
  max_wait_time: number
  boss_keys: string[]
  force_kill_on_close: boolean
}

// handleSaveChange 的 key-value 联合（替换 value: any）
type ConfigFieldKey = 'name' | 'path' | 'type' | 'max_wait_time' | 'boss_keys' | 'force_kill_on_close'
type ConfigFieldValue =
  | string                              // name, path
  | 'general' | 'mumu' | 'ldplayer'     // type
  | number                              // max_wait_time
  | string[]                            // boss_keys
  | boolean                             // force_kill_on_close

// 或用重载更精确：
function handleSaveChange(uuid: string, key: 'name' | 'path', value: string): Promise<void>
function handleSaveChange(uuid: string, key: 'type', value: 'general' | 'mumu' | 'ldplayer'): Promise<void>
function handleSaveChange(uuid: string, key: 'max_wait_time', value: number): Promise<void>
function handleSaveChange(uuid: string, key: 'boss_keys', value: string[]): Promise<void>
function handleSaveChange(uuid: string, key: 'force_kill_on_close', value: boolean): Promise<void>

// useEmulatorDiscovery.ts
interface SearchResultItem extends EmulatorSearchResult {
  alreadyImported: boolean    // path 已存在于 emulatorData
  invalid: boolean            // type 不在合法联合内
}

// 设备状态（替换硬编码数字）
type DeviceStatusCode = 0 | 1 | 2 | 3 | 4 | 5 | 10
interface DeviceStatusInfo {
  text: string
  color: 'success' | 'warning' | 'error' | 'info' | 'processing' | 'default'
}
```

### 4.3 `any` 消除映射表（proposed）

| 现状行号 | 现状 | 替换为 |
|----------|------|--------|
| 32 | `fallback: any = []` | `fallback: unknown = []` + 泛型 `<T = unknown>` |
| 57 | `Record<string, any>` | `Record<string, EmulatorConfig>` |
| 73 | `Record<string, Record<string, Record<string, any>>>` | `Record<string, Record<string, DeviceInfo>>` |
| 190 | `configData: any` | `configData: EmulatorConfig` |
| 225/278/303 | `as Record<string, any>` | 删除强转，直接用 `response.data`（类型已正确） |
| 324 | `value: any` | 重载或 `ConfigFieldValue` 联合 |
| 329 | `let configData: any = {}` | `let configData: Partial<EmulatorConfig> = {}` |
| 1060 | `({ text }: any)` | `({ text: string \| number })` 或 antd `Column` 内置类型 |

---

## 5. 页面状态机

### 5.1 顶层页面状态（proposed）

```
                    ┌─────────────┐
                    │  firstLoad  │ ← onMounted, loading=true
                    └──────┬──────┘
                           │ loadEmulators 完成
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  empty   │ │  ready   │ │  error   │
        │ (无模拟器)│ │ (正常展示)│ │ (加载失败)│
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             │ add/search │ polling    │ retry
             └─────→ ready│            └─→ firstLoad
                           │
                    ┌──────┼──────┬──────────┬──────────┐
                    ▼      ▼      ▼          ▼          ▼
               ┌──────┐┌──────┐┌────────┐┌─────────┐┌────────┐
               │search││adding││config  ││provider ││offline │
               │ing   ││      ││corrupt ││missing  ││(后端断) │
               └──────┘└──────┘└────────┘└─────────┘└────────┘
```

### 5.2 状态定义（proposed）

| 状态 | 触发条件 | UI 表现 | 退出条件 |
|------|----------|---------|----------|
| `firstLoad` | onMounted | `LoadingSkeleton`（v6）全屏 | loadEmulators 完成 |
| `empty` | `emulatorIndex.length === 0` 且非首次 | `EmptyState`（v6）+ 大按钮（搜索/添加） | add/search 成功 |
| `ready` | 有模拟器且数据正常 | Tabs + 配置 + 设备表 | — |
| `error` | loadEmulators 抛异常 | `ErrorState`（v6）+ 重试按钮 | retry 成功 |
| `searching` | handleSearch 进行中 | Toolbar 按钮 loading + 模态框 `LoadingSkeleton` | 搜索完成 |
| `configCorrupt` | 单个模拟器 config 缺 `Info` 或 type 非法 | 该 Tab 内显示 `ErrorState`「配置损坏」 | 用户修正 type/path |
| `providerMissing` | `get_emulator_instance` 抛 `ValueError`（未知 type）→ status 500 | 该 Tab 设备区显示 `ErrorState`「不支持的模拟器类型」 | 用户切换 type |
| `offline` | API 请求失败（网络错误） | 全页 `OfflineSkeleton`（v6）+ 重连提示 | 后端恢复 |

### 5.3 per-Tab 子状态（proposed）

每个 Tab（per-uuid）独立维护子状态，互不影响：

| 子状态 | 触发 | UI |
|--------|------|-----|
| `tabLoading` | loadDevices(uuid) 进行中 | 设备区 `LoadingSkeleton` |
| `tabEmpty` | devices[uuid] 为空 | 设备区 `EmptyState` + 启动按钮 |
| `tabError` | loadDevices 失败或 status 500 | 设备区 `ErrorState` |
| `tabReady` | 有设备数据 | 设备表正常 |
| `tabPolling` | 轮询命中此 uuid | 静默更新，无 loading 闪烁 |

### 5.4 保存状态（proposed，per-uuid）

```
idle ──blur/change──→ saving ──200──→ refreshing ──refresh done──→ idle
                         │                  │
                         └──error──→ saveError ──retry──→ saving
                                    (toast 提示)        │
                                                        └──cancel──→ idle
```

- `saving`：`updateEmulatorApiEmulatorUpdatePost` 进行中。
- `refreshing`：`refreshEmulatorConfig(uuid)` 进行中（保存后确认后端纠正）。
- 用 per-uuid epoch 防竞态（见 §6）。

---

## 6. 轮询与防竞态

### 6.1 核心问题（observed，见 behavior-baseline §5）

- Q3：串行 `for...of await`，慢模拟器阻塞整轮。
- Q4：无重入保护，`setInterval` 可能重叠。
- Q5：无 visibility 暂停。
- 手动 `loadDevices` 与轮询并发写 `devicesData[uuid]`。

### 6.2 提议方案（proposed）

#### 6.2.1 轮询改为并行 + epoch

```typescript
// useEmulatorManagement.ts (proposed)
let pollGeneration = 0          // 轮询 epoch，复用 useAppBackground 模式
let pollingInFlight = false     // 重入保护

const pollDevicesStatus = async () => {
  if (emulatorIndex.value.length === 0) return
  if (pollingInFlight) return           // Q4: 上一轮未完成，跳过本轮
  pollingInFlight = true
  const generation = ++pollGeneration

  try {
    // Q3: 改为并行 Promise.allSettled
    const results = await Promise.allSettled(
      emulatorIndex.value.map(emulator =>
        Service.getStatusApiEmulatorStatusPost({ emulatorId: emulator.uid })
          .then(response => ({ emulator, response }))
      )
    )

    // epoch 检查：若期间有新一轮启动，丢弃本次结果
    if (generation !== pollGeneration) return

    for (const result of results) {
      if (result.status === 'fulfilled' && result.value.response.code === 200) {
        const { emulator, response } = result.value
        const current = (response.data || {})[emulator.uid] || {}
        // 仅当该 uuid 无更新的手动加载 epoch 时才写入
        if (!manualLoadEpoch[emulator.uid] || manualLoadEpoch[emulator.uid] <= generation) {
          devicesData.value[emulator.uid] = current
        }
      }
    }
  } catch (e) {
    if (generation === pollGeneration) logger.warn(`轮询出错: ${...}`)
  } finally {
    if (generation === pollGeneration) pollingInFlight = false
  }
}
```

#### 6.2.2 手动 loadDevices epoch（防与轮询冲突）

```typescript
const manualLoadEpoch: Record<string, number> = {}

const loadDevices = async (uuid: string) => {
  const generation = ++manualLoadEpoch[uuid]   // 标记本次手动加载
  loadingDevices.value.add(uuid)
  try {
    const response = await Service.getStatusApiEmulatorStatusPost({ emulatorId: uuid })
    // epoch 检查：若期间有更新的手动加载或轮询，丢弃
    if (manualLoadEpoch[uuid] !== generation) return
    if (response.code === 200) {
      devicesData.value[uuid] = (response.data || {})[uuid] || {}
    }
  } finally {
    if (manualLoadEpoch[uuid] === generation) {
      loadingDevices.value.delete(uuid)
    }
  }
}
```

#### 6.2.3 visibility 暂停（Q5）

```typescript
// useEmulatorManagement.ts (proposed)
useEventListener(document, 'visibilitychange', () => {
  if (document.hidden) {
    stopPolling()
    logger.info('页面隐藏，暂停轮询')
  } else if (route.path === '/emulators') {
    startPolling()
    pollDevicesStatus()   // 恢复时立即拉一次
    logger.info('页面可见，恢复轮询')
  }
})
```

#### 6.2.4 保存防竞态（Q6，per-uuid epoch）

```typescript
// useEmulatorConfig.ts (proposed)
const saveGeneration: Record<string, number> = {}

const handleSaveChange = async (uuid: string, key: ConfigFieldKey, value: ConfigFieldValue) => {
  const generation = ++saveGeneration[uuid]
  savingMap.value.set(uuid, true)
  try {
    const response = await Service.updateEmulatorApiEmulatorUpdatePost({ emulatorId: uuid, data: buildUpdateData(key, value) })
    if (generation !== saveGeneration[uuid]) return        // 过期保存，丢弃
    if (response.code === 200) {
      await refreshEmulatorConfig(uuid)                      // 确认后端纠正
      if (generation !== saveGeneration[uuid]) return        // refresh 期间又有新保存
      logger.info(`配置已保存: ${key}`)
    } else {
      message.error(response.message || '保存失败')
    }
  } catch (e) {
    if (generation === saveGeneration[uuid]) message.error('保存失败')
  } finally {
    if (generation === saveGeneration[uuid]) savingMap.value.set(uuid, false)
  }
}
```

#### 6.2.5 AbortController（可选增强，proposed）

若需在卸载/切路由时取消 in-flight 请求：
- `useEmulatorManagement` 持有 `AbortController` 实例。
- `stopPolling` + `onUnmounted` 调 `controller.abort()`。
- 需确认 `@/api` 的 Service 方法是否支持传入 `signal`（**unverified**，需查 `request.ts`）。

---

## 7. 操作按钮状态机

### 7.1 现状（observed）

- `startingDevices`/`stoppingDevices`/`showingDevices` 三个 `Set<string>`，key=`${uuid}-${index}`。
- 按钮 `:loading` 查 Set，`:disabled` 按 status 判断。
- 问题：`/operate` 假成功后 loading 立即解除（Q1），用户以为成功但实际失败。

### 7.2 提议方案（proposed）

#### 7.2.1 per-device 操作状态机

```
idle ──click start──→ operating(start) ──/operate 200──→ pendingWs
                                                         │
                                              ┌──────────┤
                                              ▼          ▼
                                    ws notice(error)  ws notice(success)/
                                    → operatingError  超时(15s)→ pollRefresh
                                    → toast 错误       → idle
                                    → idle
```

- `operating`：`/operate` 请求进行中，按钮 loading。
- `pendingWs`：`/operate` 已返回 200（fire-and-forget），等待 WS `emulator.notice` 反馈。按钮保持 loading + 状态标签显示「操作中」。
- 超时兜底：15s 未收到 WS notice，主动 `loadDevices(uuid)` 刷新一次，解除 loading。
- `operatingError`：WS 返回 error，toast 提示，解除 loading。

#### 7.2.2 per-device 互斥规则（proposed）

| 当前状态 | start 可用 | stop 可用 | show 可用 |
|----------|-----------|-----------|-----------|
| ONLINE(0) | ✗ | ✓ | ✓ |
| OFFLINE(1) | ✓ | ✗ | ✗ |
| STARTING(2) | ✗ | ✓ | ✗ |
| CLOSING(3) | ✓ | ✗ | ✗ |
| ERROR(4) | ✓ | ✗ | ✗ |
| NOT_FOUND(5) | ✓ | ✗ | ✗ |
| UNKNOWN(10) | ✓ | ✗ | ✗ |
| operating/pendingWs | ✗ | ✗ | ✗ |

**关键**：互斥仅针对同一 `(uuid, index)`，不影响其他设备。不同设备的操作可并行。

#### 7.2.3 in-flight 数据结构（proposed）

```typescript
// useEmulatorOperations.ts (proposed)
type OperationKind = 'start' | 'stop' | 'show'
type OperationState = 'idle' | 'operating' | 'pendingWs' | 'error'

interface DeviceOperation {
  kind: OperationKind | null
  state: OperationState
  startedAt: number    // 用于超时兜底
}

// per-device，key = `${uuid}-${index}`
const operationMap = ref<Map<string, DeviceOperation>>(new Map())

const isInFlight = (uuid: string, index: string) => {
  const op = operationMap.value.get(`${uuid}-${index}`)
  return op?.state === 'operating' || op?.state === 'pendingWs'
}
```

---

## 8. 老板键录制方案

### 8.1 现状缺陷（observed，见 behavior-baseline §7）

- Q7a：无 Esc 取消。
- Q7b：无 blur 自动停止。
- Q7c：无 IME 组合处理。
- Q7f：keyup 无主键校验，纯修饰键可保存。

### 8.2 提议方案（proposed，`useBossKeyRecorder.ts`）

#### 8.2.1 录制状态机

```
idle ──click 录制──→ recording ──keydown(有主键)──→ keyDown captured
                       │              └──keyup──→ save → idle
                       │
                       ├──keydown(Esc)──→ canceled → idle (不保存)
                       ├──blur(窗口失焦)──→ canceled → idle
                       ├──click 取消──→ canceled → idle
                       └──keydown(纯修饰键)──→ (不保存，等待主键)
```

#### 8.2.2 单录制锁定（proposed）

```typescript
// useBossKeyRecorder.ts
const recordingUuid = ref<string | null>(null)   // 全局唯一，仅允许一个 uuid 录制

const startRecord = (uuid: string) => {
  if (recordingUuid.value && recordingUuid.value !== uuid) {
    message.warning('请先完成当前老板键录制')
    return
  }
  recordingUuid.value = uuid
  recordedKeys.value = new Set()
  bossKeyInputMap.value[uuid] = ''
  message.info('请按下快捷键组合（按 Esc 取消）')
}
```

#### 8.2.3 keydown 处理（含 Esc/IME/主键校验）

```typescript
const handleKeyDown = (event: KeyboardEvent) => {
  if (!recordingUuid.value) return

  // Q7a: Esc 取消
  if (event.key === 'Escape') {
    event.preventDefault()
    cancelRecord(recordingUuid.value)
    message.info('已取消录制')
    return
  }

  // Q7c: IME 组合状态
  if (event.isComposing || event.keyCode === 229) {
    event.preventDefault()
    return    // 忽略 IME 输入
  }

  event.preventDefault()
  event.stopPropagation()

  const keys: string[] = []
  if (event.ctrlKey) keys.push('Ctrl')
  if (event.shiftKey) keys.push('Shift')
  if (event.altKey) keys.push('Alt')
  if (event.metaKey) keys.push('Meta')

  const mainKey = event.key
  const isModifier = ['Control', 'Shift', 'Alt', 'Meta'].includes(mainKey)
  if (!isModifier) {
    keys.push(mainKey.length === 1 ? mainKey.toUpperCase() : mainKey)
  }

  if (keys.length > 0) {
    recordedKeys.value = new Set(keys)
  }
}
```

#### 8.2.4 keyup 处理（含主键校验，Q7f）

```typescript
const handleKeyUp = async (event: KeyboardEvent) => {
  if (!recordingUuid.value) return
  event.preventDefault()

  const recorded = recordedKeys.value
  if (recorded.size === 0) return

  // Q7f: 主键校验 — 必须含至少一个非修饰键
  const modifiers = new Set(['Ctrl', 'Shift', 'Alt', 'Meta'])
  const hasMainKey = Array.from(recorded).some(k => !modifiers.has(k))
  if (!hasMainKey) {
    // 纯修饰键，不保存，继续等待
    return
  }

  const combo = Array.from(recorded).join('+')
  const uuid = recordingUuid.value
  await handleSaveChange(uuid, 'boss_keys', [combo])
  bossKeyInputMap.value[uuid] = combo
  message.success(`老板键已设置为: ${combo}`)
  recordingUuid.value = null
  recordedKeys.value = new Set()
}
```

#### 8.2.5 blur 自动取消（Q7b）

```typescript
useEventListener(window, 'blur', () => {
  if (recordingUuid.value) {
    cancelRecord(recordingUuid.value)
    message.info('窗口失焦，已取消老板键录制')
  }
})
```

#### 8.2.6 系统快捷键说明（unverified）

- `Ctrl+Alt+Del` 等系统级组合 Electron 无法拦截，录制会卡住——依赖 Esc/blur 取消兜底。
- 浏览器级快捷键（如 `Ctrl+T`、`Ctrl+W`）`event.preventDefault()` 可能无效，需在 UI 提示「部分系统快捷键无法录制」。
- MuMu 不支持老板键（observed），type==='mumu' 时隐藏输入框并显示提示。

---

## 9. 路径选择方案

### 9.1 现状缺陷（observed，见 behavior-baseline §8）

- Q8a：无 `file-exists` 预校验。
- Q8b：filters 为 `['*']`，无 exe 提示。
- Q8c：路径纠正检测依赖 refresh 完成，竞态下可能不显示。

### 9.2 提议方案（proposed，`EmulatorPathPicker.vue`）

#### 9.2.1 流程

```
click 文件夹图标
  → selectFile(filters=[exe, *])
  → 用户选择路径
  → fileExists(path) IPC 预校验
      ├─ true → handleSaveChange(uuid, 'path', path)
      │         → refreshEmulatorConfig(uuid) (epoch 保护)
      │         → 对比 path 是否被后端纠正
      │            ├─ 一致 → toast 成功
      │            └─ 不一致 → toast「路径已调整: X → Y」
      └─ false → toast 错误「文件不存在」+ 不保存
```

#### 9.2.2 selectFile filters（proposed）

```typescript
const filters = [
  { name: '可执行文件', extensions: ['exe'] },
  { name: '所有文件', extensions: ['*'] },
]
```

#### 9.2.3 file-exists 预校验（proposed）

```typescript
const exists = await window.electronAPI.fileExists(path)
if (!exists) {
  message.error('所选文件不存在')
  return
}
```

#### 9.2.4 后端纠正回显（proposed，配合 §6 保存 epoch）

```typescript
await handleSaveChange(uuid, 'path', path)   // 内部已含 epoch
// handleSaveChange 完成后 editingDataMap 已被 refreshEmulatorConfig 更新
const correctedPath = editingDataMap.value.get(uuid)?.path || ''
if (path !== correctedPath && correctedPath) {
  message.info(`路径已自动调整: ${path} → ${correctedPath}`)
} else {
  message.success('路径已保存')
}
```

---

## 10. 自动搜索导入方案

### 10.1 现状缺陷（observed，见 behavior-baseline §9）

- Q9a：无去重。
- Q9b：无 type 合法性过滤。
- Q9c：导入后不自动聚焦（依赖包装函数）。
- Q9d：失败无状态展示。

### 10.2 提议方案（proposed，`useEmulatorDiscovery.ts`）

#### 10.2.1 去重 + type 过滤（proposed）

```typescript
const VALID_TYPES: ReadonlySet<string> = new Set(['general', 'mumu', 'ldplayer'])

const enrichedResults = computed<SearchResultItem[]>(() => {
  const existingPaths = new Set(
    Object.values(emulatorData.value)
      .map(cfg => cfg.Info?.Path)
      .filter((p): p is string => !!p)
  )
  return searchResults.value.map(r => ({
    ...r,
    alreadyImported: existingPaths.has(r.path),
    invalid: !VALID_TYPES.has(r.type),
  }))
})
```

#### 10.2.2 模态框展示（proposed）

- `alreadyImported` 的结果：按钮显示「已导入」并禁用。
- `invalid` 的结果：行内 a-tag 标记「不支持的类型」，导入按钮禁用。
- 正常结果：按钮「导入」可点击。

#### 10.2.3 导入流程（proposed）

```typescript
const handleImport = async (result: SearchResultItem) => {
  if (result.alreadyImported || result.invalid) return

  importingId.value = result.path   // per-result in-flight
  try {
    const addResp = await Service.addEmulatorApiEmulatorAddPost()
    if (addResp.code !== 200) { message.error(addResp.message || '导入失败'); return }

    const updateResp = await Service.updateEmulatorApiEmulatorUpdatePost({
      emulatorId: addResp.emulatorId,
      data: {
        Info: {
          Name: result.name,
          Type: result.type as 'general' | 'mumu' | 'ldplayer',
          Path: result.path,
          MaxWaitTime: 300,
          BossKey: JSON.stringify([]),
        },
      },
    })
    if (updateResp.code === 200) {
      message.success('导入成功')
      await loadEmulators()
      // Q9c: 导入后聚焦新项
      activeKey.value = addResp.emulatorId
      saveActiveKey(activeKey.value)
      await loadDevices(addResp.emulatorId)
      // 关闭模态框（若所有结果已导入）
    } else {
      message.error(updateResp.message || '导入失败')
    }
  } finally {
    importingId.value = null
  }
}
```

---

## 11. 插件兼容方案

### 11.1 后端兼容层（observed）

`app/plugins/emulator_compat.py` 提供 `get_emulator_service()`：
- 优先返回 `PluginManager.service.get("emulator")`（已安装的模拟器插件）。
- 若无插件，返回 `LegacyEmulatorService`（宿主内置实现）。
- 前端无需感知具体 provider，统一走 `/emulator/*` 端点。

### 11.2 前端兼容场景（proposed）

| 场景 | 后端行为 | 前端处理 |
|------|----------|----------|
| 正常（插件或 Legacy） | 端点正常返回 | 正常展示 |
| 未知 provider type | `get_emulator_instance` 抛 `ValueError` → `/status` 500 | 该 Tab 设备区显示 `ErrorState`「不支持的模拟器类型，请在配置中修改」 |
| 旧插件 type 不在联合 | 同上 500 | 同上 |
| 插件未安装（仅 Legacy） | Legacy 支持 general/mumu/ldplayer | 正常 |
| 模拟器配置缺 `Info` | `config.get("Info", "Type")` 返回 None → `ValueError` | 该 Tab 显示 `ErrorState`「配置损坏」 |

### 11.3 type 选项来源（proposed）

- **现状**（observed）：前端硬编码 `emulatorTypeOptions`（general/mumu/ldplayer）。
- **提议**：保持硬编码（因 OpenAPI 生成的 `EmulatorConfig_Info.Type` 联合即为这三个），但后端若有 `list_options` 端点可动态扩展时再改。
- **不变量**：前端 `emulatorTypeOptions` 必须与 `EmulatorConfig_Info.Type` 联合类型一致。

---

## 12. 响应式与可访问性

### 12.1 窗口尺寸（proposed）

| 尺寸 | 行为 |
|------|------|
| 最小 960×900 | 布局不溢出，表格可滚动 |
| 100% 缩放 | 基准 |
| 125% 缩放 | v6 token `--v6-ui-scale` 由 `useTheme` 设置，间距/圆角自动缩放 |
| 140% 缩放 | 同上，表格列宽可收窄 |

### 12.2 表格高度（Q13 修复，proposed）

**现状**（observed）：`:scroll="{ y: 'calc(100vh - 560px)' }"` magic number。

**提议**：
- 移除 magic number，改为 flex 布局让设备区 `flex: 1` + `min-height: 0` 自动填充剩余空间。
- 或用 CSS `calc(100vh - var(--v6-titlebar-height) - var(--emulator-header-height))`，其中 `--emulator-header-height` 为页面头部 + 配置区实测高度。
- 表格 `:scroll.y` 改为响应式：`useElementSize` 监听容器高度，动态计算。

### 12.3 主题适配（proposed）

- 浅色/深色/跟随系统：由 `useTheme` 全局控制，v6 token 自动切换。
- 移除局部 `--text-color-tertiary`，统一用 `--v6-color-text-tertiary`（observed，v6 token 已定义）。
- 移除渐变标题（行 1202–1205），改为 `color: var(--v6-color-text)` 纯色（符合 mas-frontend-ui 业务风格）。

### 12.4 低性能降级（proposed）

- `data-perf-mode='low'`（由 `useTheme` 写入 `<html>` dataset）：
  - v6 token 自动关闭 vibrancy/shadow/动效（observed，`v6-tokens.css` 行 118–142）。
  - 表格动画、Tab 切换动画收敛。
- `prefers-reduced-motion: reduce`：
  - v6 token 动效归零（observed，行 165–180）。
  - 轮询 loading 用骨架屏闪烁改为静态灰条。

### 12.5 可访问性（proposed）

| 项 | 方案 |
|----|------|
| 焦点环 | 所有可交互元素使用 `--v6-focus-ring`（v6 token），或 `FocusRing` 组件包裹 |
| 键盘导航 | Tab 切换可用方向键（a-tabs 原生支持）；设备表操作按钮可 Tab 聚焦 |
| ARIA | 设备状态 a-tag 添加 `role="status"` + `aria-label`；操作按钮 `aria-busy` 当 loading |
| 对比度 | v6 token 文本颜色已满足 WCAG AA（observed，`--v6-color-text` 系列 rgba 透明度 ≥ 46%） |
| 录制提示 | 录制中输入框 `aria-live="polite"` 通知屏幕阅读器 |

---

## 13. WS 通知订阅设计

### 13.1 现状（observed）

- 后端 `emulator_manager.py` 行 107–114：操作失败时 `Publisher.send(id="EmulatorManager", type="emulator.notice", data=WSTaskNoticeData(level="error", message=...))`。
- 前端 `useWebSocket.ts` 提供 `subscribe({ id, type }, handler)`。
- **Emulator.vue 未订阅**（Q2），操作失败用户无感知。

### 13.2 提议方案（proposed，`useEmulatorOperations.ts`）

```typescript
import { useWebSocket } from '@/composables/useWebSocket'

const { subscribe } = useWebSocket()

// 在 setup 中订阅
const unsubscribe = subscribe(
  { id: 'EmulatorManager', type: 'emulator.notice' },
  (data: WSTaskNoticeData) => {
    // data: { level: 'error' | 'warning' | 'info' | 'success', message: string }
    if (data.level === 'error') {
      message.error(data.message)
      // 解除所有 pendingWs 状态
      operationMap.value.forEach((op, key) => {
        if (op.state === 'pendingWs') {
          op.state = 'error'
          op.kind = null
        }
      })
    } else if (data.level === 'success') {
      message.success(data.message)
      // 解除 pendingWs，刷新设备
      operationMap.value.forEach((op, key) => {
        if (op.state === 'pendingWs') {
          const [uuid] = key.split('-')
          loadDevices(uuid)
          op.state = 'idle'
          op.kind = null
        }
      })
    }
  }
)

// onUnmounted 时 useWebSocket 自动清理（需确认 subscribe 返回的 unsubscribe 是否需手动调）
onUnmounted(() => unsubscribe?.())
```

### 13.3 超时兜底（proposed）

```typescript
// 操作发出后 15s 未收到 WS notice，主动刷新
const PENDING_WS_TIMEOUT = 15000

const startTimeoutGuard = (uuid: string, index: string) => {
  const key = `${uuid}-${index}`
  const timer = setTimeout(() => {
    const op = operationMap.value.get(key)
    if (op?.state === 'pendingWs') {
      logger.warn(`操作超时未收到 WS 通知: ${key}`)
      loadDevices(uuid)
      op.state = 'idle'
      op.kind = null
    }
  }, PENDING_WS_TIMEOUT)
  return () => clearTimeout(timer)
}
```

---

## 14. 与现有代码的边界

### 14.1 可修改（释放后）

| 文件 | 说明 |
|------|------|
| `frontend/src/views/Emulator.vue` | 重构为薄壳编排层 |
| `frontend/src/composables/useEmulator*.ts` | 新建 composable |
| `frontend/src/components/emulator/*.vue` | 新建子组件 |

### 14.2 不得修改（observed，独占约束）

| 文件 | 原因 |
|------|------|
| `frontend/src/api/**` | OpenAPI 生成 |
| `frontend/src/components/AppLayout.vue` | UI 重构组独占 |
| `frontend/src/components/TitleBar.vue` | UI 重构组独占 |
| `frontend/src/styles/**` | UI 重构组独占 |
| `frontend/src/components/v6/**` | UI 重构组独占（只复用） |
| `frontend/src/composables/useTheme.ts` | UI 重构组独占（只复用） |
| `frontend/src/composables/useAppBackground.ts` | UI 重构组独占（只复用 epoch 模式） |
| `frontend/src/composables/useWebSocket.ts` | 只复用 `subscribe` 接口 |
| `package.json` / lockfile | 不动 |

### 14.3 复用接口清单（observed）

| 接口 | 来源 | 用途 |
|------|------|------|
| `Service.*` | `@/api` | 全部 API 调用 |
| `useWebSocket().subscribe` | `composables/useWebSocket.ts` | WS 订阅 |
| `useEventListener` | `@vueuse/core` | 键盘/visibility 监听 |
| `useTheme()` | `composables/useTheme.ts` | 读取 perfMode |
| v6 token | `styles/v6-tokens.css` | CSS 变量 |
| `StatusBadge` | `components/v6/StatusBadge.vue` | 设备状态标签 |
| `EmptyState`/`ErrorState`/`OfflineSkeleton`/`LoadingSkeleton` | `components/v6/*` | 状态展示 |
| `FocusRing` | `components/v6/FocusRing.vue` | 焦点环 |
| `window.electronAPI.selectFile` | `electron/ipc/fileHandlers.ts` | 文件选择 |
| `window.electronAPI.fileExists` | `electron/ipc/fileHandlers.ts` | 文件存在校验 |
| `window.electronAPI.getLogger` | `electron/services/logger.ts` | 日志 |
| `loadGeneration` epoch 模式 | `composables/useAppBackground.ts` | 防竞态参考 |

---

> 本设计文件为 Subagent B 只读研究产出，未修改任何 `frontend/src/**` 文件。
> 释放后实装时，以本文件为设计基线，结合 Subagent A 后端契约与 Subagent C 测试矩阵协同。
