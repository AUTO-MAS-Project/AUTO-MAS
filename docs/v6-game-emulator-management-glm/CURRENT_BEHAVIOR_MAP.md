# 当前行为映射 — 游戏/模拟器管理（前端部分）

> Subagent B 前端只读研究产出
> 工作树：`D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration`
> 证据来源：`frontend/src/views/Emulator.vue`（1539 行，observed）
> 标注规则：`observed` = 直接读取确认；`inferred` = 基于代码推断
> 说明：本文件为前端部分，后端行为映射由 Subagent A 产出追加。

---

## 1. 页面生命周期行为（observed）

### 1.1 挂载流程

```
onMounted (行 716)
  ├─ loadEmulators()                           ← 行 219: GET /emulator/get
  │    ├─ loading = true
  │    ├─ Service.getEmulatorApiEmulatorGetPost({ emulatorId: null })
  │    ├─ response.code === 200?
  │    │    ├─ 是 → emulatorIndex = response.index
  │    │    │        emulatorData = response.data
  │    │    │        初始化 editingDataMap (per-uuid)
  │    │    │        同步 bossKeyInputMap
  │    │    └─ 否 → message.error
  │    └─ loading = false
  │
  ├─ onEmulatorsLoaded()                       ← 行 723
  │    ├─ emulatorIndex.length > 0?
  │    │    ├─ 恢复 activeKey (localStorage)
  │    │    │    ├─ savedKey 有效 → 保持
  │    │    │    └─ savedKey 无效 → 选第一个
  │    │    └─ loadDevices(activeKey)          ← 行 467: GET /emulator/status
  │    └─ (无模拟器 → 不操作)
  │
  └─ 路由监听 (行 700, immediate: true)
       ├─ route.path === '/emulators' → startPolling()
       └─ 否 → stopPolling()
```

### 1.2 卸载流程

```
onUnmounted (行 751)
  └─ stopPolling()
       └─ clearInterval(pollingTimer)
```

**问题**（inferred）：卸载时不取消 in-flight 请求，响应回来后仍写 `devicesData`（组件已卸载，Vue 3 ref 写入无害但浪费）。

### 1.3 keep-alive 行为（observed）

- `AppLayout.vue` 的 `keep-alive :include="['Scheduler']"` 不含 Emulator。
- 每次进入 `/emulators` 页面重新 mount → 重新 `loadEmulators` + 重新 `loadDevices`。
- 离开页面 `onUnmounted` → `stopPolling`。
- **无状态保留**：editingDataMap、devicesData 全部丢失。

---

## 2. 轮询行为（observed）

### 2.1 轮询时序

```
startPolling() (行 114)
  └─ setInterval(pollDevicesStatus, 5000)
       │
       每 5s 触发:
       pollDevicesStatus() (行 87)
         ├─ emulatorIndex.length === 0? → return
         ├─ for (const emulator of emulatorIndex):    ← 串行!
         │    └─ await Service.getStatusApiEmulatorStatusPost({ emulatorId })
         │         ├─ code === 200 → devicesData[uid] = response.data[uid]
         │         └─ error → logger.warn (静默)
         └─ (无重入保护，无 epoch)
```

### 2.2 轮询与手动加载交互

```
用户切 Tab (onTabChange, 行 740)
  ├─ activeKey = key
  ├─ saveActiveKey(key)
  └─ loadDevices(key)                      ← 手动加载
       └─ await getStatusApiEmulatorStatusPost({ emulatorId: key })
            └─ devicesData[key] = response.data[key]

同时: pollingTimer 每 5s 也在写 devicesData[uid]
  → 并发写入，无互斥，无 epoch
  → 后写者覆盖先写者（可能旧数据覆盖新数据）
```

### 2.3 路由切换行为（observed）

```
watch(route.path) (行 700, immediate: true)
  ├─ 进入 /emulators → startPolling()
  └─ 离开 /emulators → stopPolling()
```

**问题**（inferred）：无 `visibilitychange` 监听。Electron 窗口最小化或切到其他窗口时，页面仍 hidden 但路由未变，轮询继续。

---

## 3. 配置编辑与保存行为（observed）

### 3.1 即时保存流

```
表单字段 @blur / @change / @press-enter
  └─ handleSaveChange(uuid, key, value)        ← 行 324
       ├─ savingMap.set(uuid, true)             ← 仅 boolean
       ├─ 构建 configData (按 key 分支)
       │    ├─ name → { Info: { Name: value } }
       │    ├─ path → { Info: { Path: value } }
       │    ├─ type → { Info: { Type: value } }
       │    ├─ max_wait_time → { Info: { MaxWaitTime: value } }
       │    ├─ boss_keys → { Info: { BossKey: JSON.stringify(value) } }
       │    └─ force_kill_on_close → { Info: { ForceKillOnClose: value } }
       ├─ await Service.updateEmulatorApiEmulatorUpdatePost({ emulatorId, data })
       │    ├─ code === 200 → await refreshEmulatorConfig(uuid)
       │    │                  └─ GET /emulator/get (单个)
       │    │                      └─ 更新 emulatorData[uuid] + editingDataMap[uuid]
       │    └─ 否 → message.error
       └─ savingMap.set(uuid, false)
```

### 3.2 保存触发点（observed）

| 字段 | 触发事件 | 行号 |
|------|----------|------|
| name | `@blur` | 889 |
| type | `@change` | 908 |
| path | 选择后立即（selectEmulatorPath 内） | 603 |
| max_wait_time | `@blur` | 944 |
| boss_keys | `@press-enter` + `@blur` | 971-972 |
| force_kill_on_close | `@change` | 1010 |

### 3.3 编辑数据初始化（observed）

```
getEditingData(uuid) (行 200)
  ├─ editingDataMap.has(uuid)?
  │    ├─ 是 → 返回缓存
  │    └─ 否 → buildEditingData(emulatorData[uuid])
  │              ├─ name = configData?.Info?.Name || ''
  │              ├─ type = configData?.Info?.Type || ''
  │              ├─ path = configData?.Info?.Path || ''
  │              ├─ max_wait_time = configData?.Info?.MaxWaitTime || 300
  │              ├─ boss_keys = safeJsonParse(configData?.Info?.BossKey, [])
  │              └─ force_kill_on_close = configData?.Info?.ForceKillOnClose !== false
  └─ 存入 editingDataMap 并返回
```

---

## 4. 设备操作行为（observed）

### 4.1 启动/关闭/显示流程

```
startEmulator(uuid, index) (行 498)
  ├─ startingDevices.add(`${uuid}-${index}`)
  ├─ await Service.operationEmulatorApiEmulatorOperatePost({
  │     emulatorId: uuid, operate: OPEN, index
  │   })
  ├─ code === 200?
  │    ├─ 是 → message.success('启动成功')     ← Q1: 假成功!
  │    │      await loadDevices(uuid)          ← 刷新设备状态
  │    └─ 否 → message.error
  └─ startingDevices.delete(key)

stopEmulator(uuid, index) (行 528) — 同上，operate: CLOSE
showEmulator(uuid, index) (行 558) — 同上，operate: SHOW，但不调 loadDevices
```

### 4.2 后端实际行为（observed，跨读后端）

```
POST /emulator/operate
  └─ EmulatorManager.operate_emulator(operate, emulator_id, index)
       └─ asyncio.create_task(operate_emulator_task(...))   ← fire-and-forget
            └─ 立即返回 200
            └─ 后台任务:
                 ├─ get_emulator_instance(emulator_id)
                 ├─ temp_emulator.open/close/setVisible(index)
                 └─ 异常 → Publisher.send(EmulatorManager, emulator.notice, {level: error, message})
```

**关键**：前端 `message.success` 时操作尚未执行，错误仅通过 WS 广播（前端未订阅）。

### 4.3 按钮可用性（observed）

```
canStartDevice(status) (行 176):
  OFFLINE(1) | ERROR(4) | NOT_FOUND(5) | UNKNOWN(10) → true

canStopDevice(status) (行 186):
  ONLINE(0) | STARTING(2) → true

show 按钮: :disabled="record.status !== 0"   ← 行 1091, 硬编码 0
```

---

## 5. 老板键录制行为（observed）

### 5.1 录制流程

```
click 录制按钮 (行 980)
  └─ startRecordBossKey(uuid) (行 619)
       ├─ recordingBossKeyMap.set(uuid, true)
       ├─ recordedKeysMap.set(uuid, new Set())
       ├─ bossKeyInputMap[uuid] = ''
       └─ message.info('请按下快捷键组合...')

keydown (全局, 行 696 useEventListener)
  └─ handleKeyDown(event) (行 634)
       ├─ find recordingUuid (第一个 true 的)
       ├─ 无 → return
       ├─ preventDefault + stopPropagation
       ├─ 收集修饰键: Ctrl/Shift/Alt/Meta
       ├─ 收集主键 (非修饰键, 字母转大写)
       └─ recordedKeysMap.set(uuid, new Set(keys))

keyup (全局, 行 697)
  └─ handleKeyUp(event) (行 665)
       ├─ find recordingUuid
       ├─ recordedKeys.size > 0?
       │    ├─ 是 → keyCombo = join('+')
       │    │        editData.boss_keys = [keyCombo]
       │    │        bossKeyInputMap[uuid] = keyCombo
       │    │        message.success
       │    │        await handleSaveChange(uuid, 'boss_keys', [keyCombo])
       │    │        recordingBossKeyMap.delete(uuid)
       │    └─ 否 → (无操作)
       └─ (无 Esc, 无 IME, 无主键校验)
```

### 5.2 手动输入老板键（observed）

```
输入框 @press-enter / @blur (行 971-972)
  └─ handleSetBossKey(uuid) (行 779)
       ├─ recordingBossKeyMap.get(uuid)? → return (录制中不处理手动输入)
       ├─ bossKeyInput = bossKeyInputMap[uuid]
       ├─ trim 非空?
       │    ├─ 是 → editData.boss_keys = [trim]
       │    │        message.success
       │    │        await handleSaveChange(uuid, 'boss_keys', [trim])
       │    └─ 否 → (无操作)
       └─ (不清空输入框)

输入框 @input (行 973)
  └─ handleBossKeyInputChange(uuid) (行 801)
       └─ editData.boss_keys = [trim] 或 []  (仅更新本地, 不保存)
```

---

## 6. 路径选择行为（observed）

```
click FolderOpenOutlined (行 922)
  └─ selectEmulatorPath(uuid) (行 586)
       ├─ window.electronAPI 可用?
       │    └─ 否 → message.error + return
       ├─ editData = editingDataMap.get(uuid)
       ├─ paths = await window.electronAPI.selectFile([{ name: '所有文件', extensions: ['*'] }])
       ├─ paths.length > 0?
       │    ├─ 是 → editData.path = paths[0]
       │    │        message.success('路径选择成功')
       │    │        await handleSaveChange(uuid, 'path', paths[0])
       │    │        newPath = editingDataMap.get(uuid)?.path
       │    │        paths[0] !== newPath && newPath?
       │    │          ├─ 是 → message.info('路径已调整: X -> Y')
       │    │          └─ 否 → (无提示)
       │    └─ 否 → (无操作)
       └─ (无 file-exists 预校验)
```

---

## 7. 搜索导入行为（observed）

### 7.1 搜索流程

```
click 自动搜索 (行 831 或 1137)
  └─ handleSearch() (行 402)
       ├─ searching = true
       ├─ await Service.searchEmulatorsApiEmulatorEmulatorSearchPost()
       ├─ code === 200?
       │    ├─ 是 → searchResults = response.emulators || []
       │    │        length > 0?
       │    │          ├─ 是 → showSearchModal = true
       │    │          │        message.success(`找到 N 个`)
       │    │          └─ 否 → message.info('未找到')
       │    └─ 否 → message.error
       └─ searching = false
```

### 7.2 导入流程

```
click 导入 (模态框内, 行 1167)
  └─ handleSearchAndImport(item) (行 769)
       ├─ handleImportFromSearch(result) (行 427)
       │    ├─ await Service.addEmulatorApiEmulatorAddPost()
       │    ├─ code === 200?
       │    │    ├─ 是 → await Service.updateEmulatorApiEmulatorUpdatePost({
       │    │    │              emulatorId, data: { Info: { Name, Type, Path, MaxWaitTime:300, BossKey:[] } }
       │    │    │            })
       │    │    │      code === 200?
       │    │    │        ├─ 是 → message.success('导入成功')
       │    │    │        │        await loadEmulators()
       │    │    │        │        showSearchModal = false
       │    │    │        └─ 否 → message.error
       │    │    └─ 否 → message.error
       │    └─ (无去重, 无 type 校验)
       │
       └─ loadEmulators 完成后:
            ├─ newEmulator = emulatorIndex[last]
            ├─ activeKey = newEmulator.uid
            ├─ saveActiveKey
            └─ loadDevices(newEmulator.uid)
```

---

## 8. Tab 管理行为（observed）

### 8.1 Tab 渲染

```
a-tabs v-model:active-key="activeKey" type="editable-card" hide-add (行 842)
  └─ v-for="element in emulatorIndex" (行 851)
       └─ a-tab-pane :key="element.uid" :closable="false"
            ├─ #tab: emulatorData[uid]?.Info?.Name || '未命名'
            └─ 内容: 配置区 + 设备列表区
```

### 8.2 Tab 切换

```
@change="onTabChange" (行 848)
  └─ onTabChange(key) (行 740)
       ├─ activeKey = key
       ├─ saveActiveKey(key) → localStorage
       └─ emulatorIndex.some(e => e.uid === key)?
            └─ loadDevices(key)
```

### 8.3 Tab 持久化

```
activeKey 初始值 (行 63):
  localStorage.getItem('emulator_active_key') || ''

saveActiveKey(key) (行 66):
  if (key) localStorage.setItem('emulator_active_key', key)

删除时清理 (行 384-388):
  若删除当前 activeKey:
    ├─ 跳到下一个或上一个
    └─ 若无其他 → activeKey = '' + localStorage.removeItem
```

---

## 9. 删除行为（observed）

```
click 删除 (行 872, a-popconfirm)
  └─ @confirm="handleDelete(uuid)" (行 369)
       ├─ await Service.deleteEmulatorApiEmulatorDeletePost({ emulatorId: uuid })
       ├─ code === 200?
       │    ├─ 是 → activeKey === uuid?
       │    │         ├─ 是 → 重选 Tab (下一个/上一个/空)
       │    │         │        saveActiveKey
       │    │         └─ 否 → (不切换)
       │    │         await loadEmulators()
       │    └─ 否 → message.error
       └─ (不清理 editingDataMap/devicesData 中已删除 uuid 的残留, inferred)
```

**问题**（inferred）：删除后 `editingDataMap`、`devicesData`、`bossKeyInputMap` 中已删除 uuid 的条目未清理，内存泄漏（量小但不规范）。

---

## 10. 数据流总览（observed）

```
                    ┌─────────────────────────────┐
                    │       Backend API            │
                    │  /emulator/get               │
                    │  /emulator/add               │
                    │  /emulator/update            │
                    │  /emulator/delete            │
                    │  /emulator/status            │
                    │  /emulator/operate           │
                    │  /emulator/search            │
                    │  WS: emulator.notice (未订阅) │
                    └──────────┬──────────────────┘
                               │ Service.* (HTTP)
                               ▼
┌──────────────────────────────────────────────────┐
│              Emulator.vue (<script setup>)        │
│                                                   │
│  状态:                                            │
│  ├─ emulatorIndex: EmulatorConfigIndexItem[]      │
│  ├─ emulatorData: Record<string, any>             │
│  ├─ devicesData: Record<string, Record<string,    │
│  │                 Record<string, any>>>          │
│  ├─ editingDataMap: Map<string, EmulatorInfo>     │
│  ├─ activeKey: string (localStorage)              │
│  ├─ loading / searching: boolean                  │
│  ├─ loadingDevices: Set<string>                   │
│  ├─ startingDevices / stoppingDevices /           │
│  │  showingDevices: Set<string>                   │
│  ├─ savingMap: Map<string, boolean>               │
│  ├─ recordingBossKeyMap: Map<string, boolean>     │
│  ├─ recordedKeysMap: Map<string, Set<string>>     │
│  ├─ bossKeyInputMap: Record<string, string>       │
│  ├─ searchResults: EmulatorSearchResult[]         │
│  ├─ showSearchModal: boolean                      │
│  └─ pollingTimer: ReturnType<typeof setTimeout>   │
│                                                   │
│  事件:                                            │
│  ├─ useEventListener(document, 'keydown')         │
│  ├─ useEventListener(document, 'keyup')           │
│  └─ watch(route.path) → start/stopPolling         │
│                                                   │
│  (无 visibilitychange, 无 WS subscribe)           │
└──────────────────┬───────────────────────────────┘
                   │ v-model / props
                   ▼
┌──────────────────────────────────────────────────┐
│              <template>                           │
│  ├─ 空状态: a-empty + 搜索/添加按钮               │
│  ├─ a-tabs (editable-card)                        │
│  │   └─ per-tab:                                  │
│  │       ├─ a-descriptions (配置表单)              │
│  │       │   ├─ a-input (name) @blur save         │
│  │       │   ├─ a-select (type) @change save      │
│  │       │   ├─ a-input (path) + FolderOpen       │
│  │       │   ├─ a-input-number (wait) @blur save  │
│  │       │   ├─ a-input (boss_key) + 录制按钮      │
│  │       │   └─ a-switch (force_kill) @change     │
│  │       └─ a-table (设备列表)                     │
│  │           ├─ a-tag (状态)                      │
│  │           └─ a-space (操作按钮)                │
│  └─ a-modal (搜索结果)                            │
└──────────────────────────────────────────────────┘
```

---

## 11. 已知行为缺陷汇总（前端，observed + inferred）

| ID | 行为缺陷 | 影响 | 证据行号 |
|----|----------|------|----------|
| Q1 | 操作假成功：`/operate` 返回 200 即 `message.success`，实际操作后台异步执行 | 用户误信成功 | 510-511 |
| Q2 | WS `emulator.notice` 未订阅，操作失败无反馈 | 失败静默 | 无订阅代码 |
| Q3 | 轮询串行 `for...of await`，慢请求阻塞整轮 | 轮询延迟 | 95-105 |
| Q4 | 轮询无重入保护，`setInterval` 可重叠 | 数据竞态 | 87-111 |
| Q5 | 无 `visibilitychange` 暂停 | 资源浪费 | 无监听 |
| Q6 | 保存无 epoch/队列，并发保存 refresh 乱序 | 数据覆盖 | 324-366 |
| Q7a | 老板键录制无 Esc 取消 | 交互卡死 | 634-663 |
| Q7b | 老板键录制无 blur 停止 | 状态残留 | 无 blur 监听 |
| Q7c | 老板键录制无 IME 处理 | 误录中文 | 634-663 |
| Q7f | 老板键 keyup 无主键校验 | 纯修饰键可保存 | 665-693 |
| Q8a | 路径选择无 `file-exists` 预校验 | 可选不存在路径 | 586-616 |
| Q9a | 搜索导入无去重 | 重复导入 | 427-459 |
| Q9b | 搜索导入无 type 合法性校验 | 后端 ValueError | 427-459 |
| Q10a | 无拖拽排序 UI（后端已支持 reorder） | 功能缺失 | 无 reorder 调用 |
| Q11 | 10 处 `any` | 类型不安全 | 32/57/73/190/225/278/303/324/329/1060 |
| Q12 | CSS 渐变标题 + 本地变量与 v6 并行 | 样式不规范 | 1202-1205, 995 |
| Q13 | `calc(100vh - 560px)` magic number | 缩放不自适应 | 1079 |
| Q14 | 未用 v6 `StatusBadge`，用 a-tag | 组件不统一 | 1083 |
| Q15 | 未用 v6 `EmptyState`/`ErrorState`/`OfflineSkeleton` | 组件不统一 | 824, 1031 |
| Q16 | 未用 v6 `LoadingSkeleton`，用 a-spin | 组件不统一 | 821, 1023 |
| Q17 | 删除后未清理 editingDataMap/devicesData 残留 | 内存泄漏(小) | 369-399 |
| Q18 | show 按钮硬编码 `record.status !== 0` 而非 `DeviceStatus.ONLINE` | 可读性差 | 1091 |

---

> 前端当前行为映射完毕。后端行为映射由 Subagent A 追加。
> 证据详见 `_alpha_build/a1/glm-game-emulator-management-20260723/subagent-B/behavior-baseline.md`。
