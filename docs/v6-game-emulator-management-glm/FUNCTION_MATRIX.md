# 功能矩阵 — 游戏/模拟器管理（前端部分）

> Subagent B 前端只读研究产出
> 工作树：`D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration`
> 证据来源：`frontend/src/views/Emulator.vue`（1539 行，observed）
> 标注规则：`observed` = 直接读取确认；`inferred` = 基于代码推断
> 说明：本文件为前端部分，后端功能矩阵由 Subagent A 产出追加。

---

## 1. 功能清单与状态

### 1.1 模拟器配置管理

| 功能 ID | 功能名称 | 现状 | 实现行号 | 问题 | 优先级 |
|---------|----------|------|----------|------|--------|
| F-CFG-01 | 加载模拟器列表 | ✅ 已实现 | 219-247 | — | — |
| F-CFG-02 | 新增模拟器 | ✅ 已实现 | 250-267 | — | — |
| F-CFG-03 | 删除模拟器 | ✅ 已实现 | 369-399 | Q17: 未清理残留 Map | P3 |
| F-CFG-04 | 编辑名称 | ✅ 已实现 | 882-893 | @blur 保存，Q6 竞态 | P1 |
| F-CFG-05 | 编辑类型 | ✅ 已实现 | 894-910 | @change 保存，Q6 竞态 | P1 |
| F-CFG-06 | 编辑路径 | ✅ 已实现 | 911-926 | Q8a: 无 file-exists 校验 | P2 |
| F-CFG-07 | 编辑最大等待时间 | ✅ 已实现 | 927-952 | @blur 保存，Q6 竞态 | P1 |
| F-CFG-08 | 编辑老板键 | ✅ 已实现 | 953-998 | Q7a-Q7f: 录制缺陷 | P1 |
| F-CFG-09 | 编辑强力关闭 | ✅ 已实现 | 999-1012 | 仅 mumu 显示 | — |
| F-CFG-10 | 即时保存单字段 | ✅ 已实现 | 324-366 | Q6: 无 epoch 防竞态 | P1 |
| F-CFG-11 | 保存后刷新确认 | ✅ 已实现 | 355 | 依赖 refreshEmulatorConfig | — |
| F-CFG-12 | 拖拽排序 Tab | ❌ 未实现 | — | Q10a: 后端有 reorder 端点 | P3 |
| F-CFG-13 | 路径后端纠正回显 | ✅ 已实现 | 606-609 | Q8c: 竞态下可能不显示 | P2 |

### 1.2 设备状态管理

| 功能 ID | 功能名称 | 现状 | 实现行号 | 问题 | 优先级 |
|---------|----------|------|----------|------|--------|
| F-DEV-01 | 加载设备状态 | ✅ 已实现 | 467-493 | Q4: 与轮询竞态 | P1 |
| F-DEV-02 | 轮询设备状态 | ✅ 已实现 | 87-129 | Q3/Q4/Q5: 串行/无重入/无暂停 | P1 |
| F-DEV-03 | 设备状态显示 | ✅ 已实现 | 1083-1085 | Q14: 用 a-tag 非 v6 StatusBadge | P3 |
| F-DEV-04 | 设备状态枚举 | ✅ 已实现 | 143-151 | 前端 CLOSING vs 后端 CLOSEING，值一致 | — |
| F-DEV-05 | canStart 判断 | ✅ 已实现 | 176-183 | — | — |
| F-DEV-06 | canStop 判断 | ✅ 已实现 | 186-188 | — | — |
| F-DEV-07 | show 按钮可用性 | ✅ 已实现 | 1091 | Q18: 硬编码 `!== 0` | P3 |
| F-DEV-08 | 空设备状态 | ✅ 已实现 | 1024-1043 | Q15: 用 a-empty 非 v6 EmptyState | P3 |

### 1.3 设备操作

| 功能 ID | 功能名称 | 现状 | 实现行号 | 问题 | 优先级 |
|---------|----------|------|----------|------|--------|
| F-OP-01 | 启动设备 | ✅ 已实现 | 498-525 | Q1: 假成功; Q2: 无 WS 反馈 | P0 |
| F-OP-02 | 关闭设备 | ✅ 已实现 | 528-555 | 同上 | P0 |
| F-OP-03 | 显示设备窗口 | ✅ 已实现 | 558-583 | 同上; 不刷新设备 | P0 |
| F-OP-04 | per-device in-flight | ✅ 已实现 | 500/530/560 | Set<string> key=`${uuid}-${index}` | — |
| F-OP-05 | 操作互斥 | ⚠️ 部分 | 1091/1098/1107 | 仅按 status 判断，无 pendingWs 状态 | P1 |
| F-OP-06 | WS 操作结果反馈 | ❌ 未实现 | — | Q2: 未订阅 emulator.notice | P0 |
| F-OP-07 | 操作超时兜底 | ❌ 未实现 | — | 无超时机制 | P1 |

### 1.4 老板键录制

| 功能 ID | 功能名称 | 现状 | 实现行号 | 问题 | 优先级 |
|---------|----------|------|----------|------|--------|
| F-KEY-01 | 开始录制 | ✅ 已实现 | 619-624 | — | — |
| F-KEY-02 | 停止/取消录制 | ⚠️ 部分 | 627-631 | Q7a: 无 Esc 取消 | P1 |
| F-KEY-03 | keydown 收集按键 | ✅ 已实现 | 634-663 | Q7c: 无 IME 处理 | P2 |
| F-KEY-04 | keyup 保存 | ✅ 已实现 | 665-693 | Q7f: 无主键校验 | P1 |
| F-KEY-05 | 手动输入老板键 | ✅ 已实现 | 779-798 | — | — |
| F-KEY-06 | blur 自动取消 | ❌ 未实现 | — | Q7b | P2 |
| F-KEY-07 | 单录制锁定 | ⚠️ 隐式 | 636-638 | find 第一个，无显式约束 | P3 |
| F-KEY-08 | MuMu 不支持提示 | ✅ 已实现 | 961/996 | — | — |

### 1.5 自动搜索与导入

| 功能 ID | 功能名称 | 现状 | 实现行号 | 问题 | 优先级 |
|---------|----------|------|----------|------|--------|
| F-SRH-01 | 自动搜索 | ✅ 已实现 | 402-424 | — | — |
| F-SRH-02 | 搜索结果展示 | ✅ 已实现 | 1157-1176 | — | — |
| F-SRH-03 | 从结果导入 | ✅ 已实现 | 427-459 | Q9b: 无 type 校验 | P1 |
| F-SRH-04 | 去重标记 | ❌ 未实现 | — | Q9a | P2 |
| F-SRH-05 | 无效 type 过滤 | ❌ 未实现 | — | Q9b | P1 |
| F-SRH-06 | 导入后聚焦 | ⚠️ 包装实现 | 769-777 | Q9c: 依赖列表顺序 | P3 |
| F-SRH-07 | 空结果提示 | ✅ 已实现 | 411-413 | — | — |

### 1.6 Tab 管理

| 功能 ID | 功能名称 | 现状 | 实现行号 | 问题 | 优先级 |
|---------|----------|------|----------|------|--------|
| F-TAB-01 | Tab 列表渲染 | ✅ 已实现 | 842-852 | — | — |
| F-TAB-02 | Tab 切换 | ✅ 已实现 | 740-748 | — | — |
| F-TAB-03 | activeKey 持久化 | ✅ 已实现 | 62-70 | Q10c: 失效 key 间接修复 | P3 |
| F-TAB-04 | 删除后重选 | ✅ 已实现 | 376-388 | — | — |
| F-TAB-05 | 拖拽排序 | ❌ 未实现 | — | Q10a | P3 |
| F-TAB-06 | keep-alive 缓存 | ❌ 不缓存 | — | Q10b: AppLayout 不含 Emulator | P2 |

### 1.7 页面状态

| 功能 ID | 功能名称 | 现状 | 实现行号 | 问题 | 优先级 |
|---------|----------|------|----------|------|--------|
| F-STA-01 | 首次加载 loading | ✅ 已实现 | 821 | Q16: 用 a-spin 非 v6 LoadingSkeleton | P3 |
| F-STA-02 | 空状态 | ✅ 已实现 | 823-839 | Q15: 用 a-empty 非 v6 EmptyState | P3 |
| F-STA-03 | 加载错误状态 | ❌ 未实现 | — | 仅 message.error，无 ErrorState | P2 |
| F-STA-04 | 后端离线状态 | ❌ 未实现 | — | 无 OfflineSkeleton | P2 |
| F-STA-05 | 配置损坏状态 | ❌ 未实现 | — | 无 per-tab ErrorState | P2 |
| F-STA-06 | provider 缺失状态 | ❌ 未实现 | — | 无 ErrorState for 未知 type | P2 |
| F-STA-07 | 搜索中状态 | ✅ 已实现 | 830/1158 | — | — |
| F-STA-08 | 保存中状态 | ✅ 已实现 | 865 | a-spin small | — |

### 1.8 响应式与可访问性

| 功能 ID | 功能名称 | 现状 | 实现行号 | 问题 | 优先级 |
|---------|----------|------|----------|------|--------|
| F-RSP-01 | 最小窗口适配 | ⚠️ 部分 | 1511 | @media 768px 不适用 Electron | P3 |
| F-RSP-02 | 缩放自适应 | ❌ 未实现 | — | Q13: magic 560px | P2 |
| F-RSP-03 | 浅色/深色 | ⚠️ 部分 | — | v6 token 支持，但局部变量并行 | P2 |
| F-RSP-04 | 低性能降级 | ❌ 未实现 | — | 未用 data-perf-mode | P2 |
| F-RSP-05 | 减弱动效 | ❌ 未实现 | — | 未用 prefers-reduced-motion | P2 |
| F-RSP-06 | 焦点环 | ❌ 未实现 | — | 未用 v6 FocusRing | P3 |
| F-RSP-07 | ARIA 标签 | ❌ 未实现 | — | 无 aria-* 属性 | P3 |
| F-RSP-08 | 键盘导航 | ⚠️ 原生 | — | a-tabs/a-table 原生支持 | — |

---

## 2. API 端点使用矩阵

| API 端点 | 前端调用函数 | 使用场景 | 返回处理 | 问题 |
|----------|-------------|----------|----------|------|
| `POST /emulator/get` | `loadEmulators` (行 222), `refreshEmulatorConfig` (行 272) | 加载全部/单个配置 | code===200 → index+data | 强转 any (Q11) |
| `POST /emulator/add` | `handleAdd` (行 252), `handleImportFromSearch` (行 429) | 新增/导入 | emulatorId | — |
| `POST /emulator/update` | `handleSaveChange` (行 347), `handleImportFromSearch` (行 432) | 保存/导入 | code===200 → refresh | Q6 竞态 |
| `POST /emulator/delete` | `handleDelete` (行 371) | 删除 | code===200 → reload | Q17 残留 |
| `POST /emulator/status` | `loadDevices` (行 472), `pollDevicesStatus` (行 96) | 设备状态 | data[uid] | Q3/Q4 竞态 |
| `POST /emulator/operate` | `startEmulator` (行 504), `stopEmulator` (行 534), `showEmulator` (行 564) | 启动/关闭/显示 | code===200 → 假成功 | Q1/Q2 |
| `POST /emulator/search` | `handleSearch` (行 405) | 搜索已安装 | emulators[] | Q9a/Q9b |
| `POST /emulator/reorder` | ❌ 未调用 | — | — | Q10a 功能缺失 |
| WS `emulator.notice` | ❌ 未订阅 | — | — | Q2 |

---

## 3. 组件使用矩阵

| 场景 | 现用组件 | v6 推荐组件 | 替换优先级 |
|------|----------|------------|-----------|
| 页面 loading | `a-spin` (行 821) | `LoadingSkeleton` | P3 |
| 空模拟器 | `a-empty` (行 824) | `EmptyState` | P3 |
| 空设备 | `a-empty` (行 1031) | `EmptyState` | P3 |
| 设备状态标签 | `a-tag` (行 1083) | `StatusBadge` | P3 |
| 加载错误 | `message.error` (全局) | `ErrorState` (内联) | P2 |
| 后端离线 | 无 | `OfflineSkeleton` | P2 |
| 配置表单 | `a-descriptions` (行 881) | 保持（业务合适） | — |
| 设备表 | `a-table` (行 1046) | 保持（业务合适） | — |
| Tab | `a-tabs` (行 842) | 保持（业务合适） | — |
| 模态框 | `a-modal` (行 1157) | 保持（业务合适） | — |
| 确认删除 | `a-popconfirm` (行 866) | 保持（业务合适） | — |
| 焦点环 | 无 | `FocusRing` / `--v6-focus-ring` | P3 |

---

## 4. 状态变量矩阵

| 变量名 | 类型 | 作用域 | 问题 | 提议 |
|--------|------|--------|------|------|
| `loading` | `ref<boolean>` | 全局 | — | — |
| `searching` | `ref<boolean>` | 全局 | — | — |
| `emulatorIndex` | `ref<EmulatorConfigIndexItem[]>` | 全局 | — | — |
| `emulatorData` | `ref<Record<string, any>>` | 全局 | Q11: any | `Record<string, EmulatorConfig>` |
| `devicesData` | `ref<Record<string, Record<string, Record<string, any>>>>` | 全局 | Q11: any | `Record<string, Record<string, DeviceInfo>>` |
| `searchResults` | `ref<EmulatorSearchResult[]>` | 全局 | — | — |
| `showSearchModal` | `ref<boolean>` | 全局 | — | — |
| `activeKey` | `ref<string>` | 全局 | — | — |
| `loadingDevices` | `ref<Set<string>>` | 全局 | — | — |
| `startingDevices` | `ref<Set<string>>` | 全局 | — | — |
| `stoppingDevices` | `ref<Set<string>>` | 全局 | — | — |
| `showingDevices` | `ref<Set<string>>` | 全局 | — | — |
| `pollingTimer` | `ref<ReturnType<typeof setTimeout> \| null>` | 全局 | — | — |
| `editingDataMap` | `ref<Map<string, EmulatorInfo>>` | 全局 | — | — |
| `savingMap` | `ref<Map<string, boolean>>` | 全局 | Q6: 仅 boolean | per-uuid epoch |
| `recordingBossKeyMap` | `ref<Map<string, boolean>>` | 全局 | Q7e: 无单录制锁 | `ref<string \| null>` |
| `recordedKeysMap` | `ref<Map<string, Set<string>>>` | 全局 | — | — |
| `bossKeyInputMap` | `ref<Record<string, string>>` | 全局 | — | — |

---

## 5. 优先级汇总

### P0（阻断性，必须修复）

| ID | 问题 | 影响 |
|----|------|------|
| Q1 | 操作假成功 | 用户误信操作成功 |
| Q2 | WS 未订阅 | 操作失败无反馈 |

### P1（高优先级，影响正确性）

| ID | 问题 | 影响 |
|----|------|------|
| Q3 | 轮询串行阻塞 | 轮询延迟 |
| Q4 | 轮询无重入保护 | 数据竞态 |
| Q6 | 保存无 epoch 防竞态 | 数据覆盖 |
| Q7a | 老板键无 Esc 取消 | 交互卡死 |
| Q7f | 老板键无主键校验 | 纯修饰键可保存 |
| Q9b | 搜索导入无 type 校验 | 后端 ValueError |

### P2（中优先级，影响体验）

| ID | 问题 | 影响 |
|----|------|------|
| Q5 | 无 visibility 暂停 | 资源浪费 |
| Q7b/Q7c | 老板键 blur/IME | 交互不规范 |
| Q8a | 路径无 file-exists | 可选不存在路径 |
| Q9a | 搜索无去重 | 重复导入 |
| Q10b | keep-alive 不缓存 | 每次重载 |
| Q11 | 10 处 any | 类型不安全 |
| Q12 | CSS 不规范 | 样式不统一 |
| F-STA-03~06 | 缺少错误/离线/损坏状态 | 体验差 |

### P3（低优先级，优化项）

| ID | 问题 | 影响 |
|----|------|------|
| Q10a | 无拖拽排序 | 功能缺失 |
| Q13 | magic number | 缩放不自适应 |
| Q14/Q15/Q16 | 未用 v6 组件 | 组件不统一 |
| Q17 | 删除后残留 | 内存泄漏(小) |
| Q18 | 硬编码状态值 | 可读性 |

---

## 6. 测试矩阵输入（为 Subagent C 提供）

### 6.1 功能测试用例

| 用例 ID | 场景 | 前置条件 | 步骤 | 预期（当前行为） | 预期（重构后） | 问题 ID |
|---------|------|----------|------|-----------------|---------------|---------|
| T-01 | 首次加载 | 无模拟器 | 进入 /emulators | a-empty + 按钮 | EmptyState + 按钮 | Q15 |
| T-02 | 首次加载 | 有模拟器 | 进入 /emulators | Tabs + 配置 + 设备 | 同 + LoadingSkeleton | Q16 |
| T-03 | 加载失败 | 后端断开 | 进入 /emulators | message.error | OfflineSkeleton | F-STA-04 |
| T-04 | 新增模拟器 | 有模拟器 | 点击添加 | 新 Tab + 加载设备 | 同 | — |
| T-05 | 删除模拟器 | 删除当前 Tab | popconfirm 确认 | 重选 Tab + reload | 同 + 清理残留 | Q17 |
| T-06 | 编辑名称 | 有模拟器 | 输入 + blur | 即时保存 | 同 + epoch 防竞态 | Q6 |
| T-07 | 编辑类型 | 有模拟器 | 切换 select | 即时保存 | 同 + epoch | Q6 |
| T-08 | 选择路径 | 有模拟器 | 点击文件夹 | 选文件即保存 | + file-exists 校验 | Q8a |
| T-09 | 路径不存在 | — | 选不存在文件 | 保存成功(后端可能纠正) | 前端拦截 | Q8a |
| T-10 | 启动设备 | 设备 OFFLINE | 点击启动 | message.success(假) | pendingWs + WS 反馈 | Q1/Q2 |
| T-11 | 启动失败 | 后端操作异常 | 点击启动 | 无反馈(WS 未订阅) | WS error toast | Q1/Q2 |
| T-12 | 关闭设备 | 设备 ONLINE | 点击关闭 | message.success(假) | pendingWs + WS | Q1/Q2 |
| T-13 | 显示设备 | 设备 ONLINE | 点击显示 | message.success(假) | pendingWs + WS | Q1/Q2 |
| T-14 | 快速连点启动 | 设备 OFFLINE | 连续点击 | 多次请求 | in-flight 互斥 | F-OP-05 |
| T-15 | 录制老板键 | 非 mumu | 点击录制+按键 | 保存组合 | + Esc/IME/主键校验 | Q7a/Q7c/Q7f |
| T-16 | Esc 取消录制 | 录制中 | 按 Esc | Esc 被录入 | 取消录制 | Q7a |
| T-17 | 纯修饰键录制 | 录制中 | 只按 Ctrl+放开 | 保存 ['Ctrl'] | 不保存，等待主键 | Q7f |
| T-18 | IME 录制 | 中文输入法 | 录制中打字 | 中文字符录入 | 忽略 IME | Q7c |
| T-19 | 窗口失焦录制 | 录制中 | Alt+Tab | 录制状态残留 | 自动取消 | Q7b |
| T-20 | 自动搜索 | 有已安装 | 点击搜索 | 模态框+结果 | 同 + 去重标记 | Q9a |
| T-21 | 导入重复 | path 已存在 | 点击导入 | 重复导入 | 禁用+标记已导入 | Q9a |
| T-22 | 导入非法 type | type 不在联合 | 点击导入 | 后端 ValueError | 禁用+标记无效 | Q9b |
| T-23 | Tab 切换 | 多模拟器 | 切 Tab | 加载设备 | 同 + epoch | Q4 |
| T-24 | 轮询中切 Tab | 轮询进行中 | 切 Tab | 并发写 devicesData | epoch 互斥 | Q4 |
| T-25 | 页面隐藏 | 轮询中 | 最小化窗口 | 轮询继续 | 暂停轮询 | Q5 |
| T-26 | 页面恢复 | 已隐藏 | 恢复窗口 | — | 立即拉一次+恢复 | Q5 |
| T-27 | 未知 type | type 非法 | 加载设备 | 500 + message.error | ErrorState | F-STA-05 |
| T-28 | 配置损坏 | 缺 Info | 加载配置 | buildEditingData 返回默认 | ErrorState | F-STA-06 |
| T-29 | 125% 缩放 | — | 设置 125% | 表格高度可能溢出 | v6 token 自适应 | Q13 |
| T-30 | 140% 缩放 | — | 设置 140% | 同上 | 自适应 | Q13 |
| T-31 | 低性能模式 | — | perfMode=low | 无降级 | 关闭动效/vibrancy | F-RSP-04 |
| T-32 | 深色模式 | — | 切换深色 | 局部变量不跟随 | v6 token 统一 | Q12 |
| T-33 | 删除后残留 | 删除模拟器 | 检查 Map | editingDataMap 残留 | 清理 | Q17 |
| T-34 | 快速保存多字段 | 连续 blur | name+type 快速改 | 并发保存乱序 | epoch 防竞态 | Q6 |
| T-35 | WS 操作成功 | 后端正常 | 启动设备 | 假成功 | WS success → 刷新 | Q1/Q2 |

### 6.2 竞态测试用例

| 用例 ID | 场景 | 触发方式 | 预期（重构后） |
|---------|------|----------|---------------|
| T-RACE-01 | 轮询重叠 | 5s 内模拟器 >3 个，status 慢 | pollingInFlight 跳过本轮 |
| T-RACE-02 | 轮询 vs 手动加载 | 切 Tab 时轮询在跑 | epoch 互斥，手动加载优先 |
| T-RACE-03 | 保存并发 | 快速改 name + type | per-uuid epoch，后者丢弃前者 refresh |
| T-RACE-04 | 删除 vs 轮询 | 删除模拟器时轮询在跑 | 轮询跳过已删除 uuid |
| T-RACE-05 | 卸载 vs in-flight | 操作未完成时切路由 | AbortController 取消(若支持) |

### 6.3 可访问性测试用例

| 用例 ID | 场景 | 预期（重构后） |
|---------|------|---------------|
| T-A11Y-01 | 键盘 Tab 导航 | 所有按钮可 Tab 聚焦，焦点环可见 |
| T-A11Y-02 | 屏幕阅读器 | 状态标签 aria-label，操作按钮 aria-busy |
| T-A11Y-03 | 录制提示 | aria-live 通知录制状态 |
| T-A11Y-04 | 对比度 | v6 token 满足 WCAG AA |

---

> 前端功能矩阵完毕。后端功能矩阵由 Subagent A 追加。
> 测试用例为 Subagent C 提供输入，标注了当前行为与重构后预期。

---

# 功能矩阵 — 游戏/模拟器管理（后端部分）

> Subagent A 后端可靠性研究产出
> 工作树：`D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration`
> 分支：`integration/dev-v2-dev-all-plugins`，HEAD：`b5e872815`
> 证据来源：源码直接读取 + pytest 58 passed
> 标注规则：`observed` = 直接读取确认；`inferred` = 基于代码推断；`proposed` = 提议但未实现；`fixed` = 本次修复

---

## B1. 配置 CRUD 端点

| 功能 ID | 功能名称 | 现状 | 实现文件:行 | 问题 | 优先级 |
|---------|----------|------|------------|------|--------|
| B-CFG-01 | 查询模拟器配置 | ✅ observed | `app/api/emulator.py:58-78` | — | — |
| B-CFG-02 | 新增模拟器 | ✅ observed | `app/api/emulator.py:81-100` | — | — |
| B-CFG-03 | 更新模拟器 | ✅ observed | `app/api/emulator.py:103-119` | — | — |
| B-CFG-04 | 删除模拟器 | ✅ observed | `app/api/emulator.py:122-136` | — | — |
| B-CFG-05 | 重排序模拟器 | ✅ observed | `app/api/emulator.py:139-153` | — | — |
| B-CFG-06 | 错误码映射 | ✅ observed | `app/api/emulator.py:32-35` | ValueError/KeyError/FileNotFoundError → 400, 其它 → 500 | — |

### CRUD 返回语义

- **get**: `EmulatorGetOut(code, status, message, index[], data{})` — 成功 code=200/status=success；失败 code=400|500/status=error
- **add**: `EmulatorCreateOut(code, status, message, emulatorId, data)` — 成功返回新 UUID 和空配置
- **update/delete/reorder**: `OutBase(code, status, message)` — 成功 code=200/status=success

---

## B2. 操作端点（accepted / operation-id 契约）

| 功能 ID | 功能名称 | 现状 | 实现文件:行 | 问题 | 优先级 |
|---------|----------|------|------------|------|--------|
| B-OP-01 | 同步校验后返回 operation_id | ✅ fixed | `app/core/emulator_manager.py:112-145` | 消除假成功 | P0→已修复 |
| B-OP-02 | 后台 _run_operate + WS 推送 | ✅ fixed | `app/core/emulator_manager.py:147-192` | — | — |
| B-OP-03 | 同设备并发操作拒绝 | ✅ fixed | `app/core/emulator_manager.py:136-138` | RuntimeError("已有操作进行中") | — |
| B-OP-04 | WS 推送失败不掩盖原始结果 | ✅ fixed | `app/core/emulator_manager.py:179-192` | 内层 try/except 隔离 WS 异常 | P0→已修复 |
| B-OP-05 | operate 枚举校验 | ✅ observed | `app/models/schema.py:1715` | Literal["open","close","show"]，非法值 → 422 | — |
| B-OP-06 | in-flight 清理 | ✅ fixed | `app/core/emulator_manager.py:144` | task.add_done_callback 自动清理 _inflight | — |

### accepted / operation-id 契约

```
HTTP /operate → 同步校验 (UUID/Type/Path/并发)
  ├─ 失败 → raise → 400/500, status=error, accepted=false, operationId=null
  └─ 成功 → 返回 operation_id (UUID)
            HTTP 响应: code=200, status="accepted", accepted=true, operationId=<uuid>
            后台 _run_operate:
              ├─ 成功 → WS emulator.notice {level=info, operationId, message="完成"}
              └─ 失败 → WS emulator.notice {level=error, operationId, message="失败: <err>"}
                         WS 推送本身失败 → logger.warning，不传播
```

---

## B3. 状态查询

| 功能 ID | 功能名称 | 现状 | 实现文件:行 | 问题 | 优先级 |
|---------|----------|------|------------|------|--------|
| B-STA-01 | 单点故障隔离 | ✅ fixed | `app/core/emulator_manager.py:194-219` | 单个损坏配置返回空 dict，不阻断整列 | P0→已修复 |
| B-STA-02 | DeviceStatus 枚举映射 | ✅ observed | `app/models/emulator.py` | ONLINE=0/OFFLINE=1/STARTING=2/CLOSEING=3/ERROR=4/NOT_FOUND=5/UNKNOWN=10；前后端值一致，无 drift | — |
| B-STA-03 | status int 强转 | ✅ observed | `app/core/emulator_manager.py:209` | `int(device_info.status)` 保证 IntEnum 序列化为 number | — |

---

## B4. 广告屏蔽与进程边界

| 功能 ID | 功能名称 | 现状 | 实现文件:行 | 问题 | 优先级 |
|---------|----------|------|------------|------|--------|
| B-ADB-01 | 文件操作异常隔离 | ✅ fixed | `app/core/emulator_manager.py:77-91` | 仅捕获 (OSError, PermissionError)，logger.warning | P0→已修复 |
| B-ADB-02 | ldplayer globalsetting 隔离 | ✅ fixed | `app/core/emulator_manager.py:93-103` | 仅捕获 (RuntimeError, asyncio.TimeoutError, OSError) | P0→已修复 |
| B-ADB-03 | suppress(Exception) 消除 | ✅ fixed | `app/core/emulator_manager.py:67-103` | 原 suppress(Exception) 已拆分为命名异常捕获 | P0→已修复 |
| B-ADB-04 | MuMu force-kill 边界 | ⚠️ observed | `app/utils/emulator/mumu.py` (out of scope) | ForceKillOnClose 配置存在，具体实现需进一步审查 | P2 |

---

## B5. Provider / Fallback 契约

| 功能 ID | 功能名称 | 现状 | 实现文件:行 | 问题 | 优先级 |
|---------|----------|------|------------|------|--------|
| B-PFB-01 | provider 启动 → fallback 不共存 | ✅ observed | `app/plugins/loader.py:1086-1091` | 先 drop host，再 set real | — |
| B-PFB-02 | provider 失败 → fallback 恢复 | ✅ observed | `app/plugins/loader.py:1148-1164` | 异常路径 drop+restore | — |
| B-PFB-03 | shutdown → owner 释放 | ✅ observed | `app/plugins/loader.py:1302-1307,1463` | unload_plugin finally 分支 restore；unload_all 末尾 drop | — |
| B-PFB-04 | ServiceRegistry provide 去重 | ✅ observed | `app/plugins/service_registry.py:86-108` | 同 owner no-op，异 owner raise ValueError | — |
| B-PFB-05 | _configure_host_compat_services | ✅ observed | `app/plugins/loader.py:159-174` | 有真实 provider → drop+skip；无 → register | — |
| B-PFB-06 | LegacyEmulatorService.operate 返回 str | ✅ fixed | `app/plugins/emulator_compat.py:44-47` | 返回 operation_id 而非 None | — |

---

## B6. 搜索

| 功能 ID | 功能名称 | 现状 | 实现文件:行 | 问题 | 优先级 |
|---------|----------|------|------------|------|--------|
| B-SRH-01 | 注册表枚举搜索 | ✅ observed | `app/utils/emulator/tools.py` | 仅读注册表卸载表 | — |
| B-SRH-02 | 大小写去重 | ✅ observed | `app/utils/emulator/tools.py` | case-insensitive 去重 | — |
| B-SRH-03 | 异步包装 | ✅ observed | `app/plugins/emulator_compat.py:54-59` | asyncio.to_thread 避免阻塞事件循环 | — |

---

## B7. 边界校验矩阵

| 边界 | 校验位置 | 异常类型 | HTTP 状态码 | observed |
|------|----------|----------|------------|----------|
| emulator_id 非 UUID | `emulator_manager.py:58` | ValueError | 400 | ✅ |
| emulator_id 未找到 | `emulator_manager.py:61` | KeyError | 400 | ✅ |
| Type 不在 EMULATOR_TYPE_BOOK | `emulator_manager.py:63-64` | ValueError | 400 | ✅ |
| Path 不存在 | `emulator_manager.py:129-132` | FileNotFoundError | 400 | ✅ |
| 同设备已有操作进行中 | `emulator_manager.py:136-138` | RuntimeError | 500 | ✅ |
| operate 非法枚举值 | Pydantic Literal 校验 | ValidationError | 422 | ✅ |
| MaxWaitTime | `schema.py:112` Optional[int] | — | — | observed |

---

## B8. WS 通知契约

| 消息类型 | type | data 字段 | observed |
|----------|------|----------|----------|
| 操作完成 | `emulator.notice` | `{level="info", message, operationId}` | ✅ |
| 操作失败 | `emulator.notice` | `{level="error", message, operationId}` | ✅ |
| WSTaskNoticeData | — | `level: Literal["info","warning","error"], message: str, operationId: Optional[str]` | ✅ |

- WS 推送通过 `Publisher.send(id=protocol.ID_EMULATOR_MANAGER, type=protocol.EMULATOR_NOTICE, data=WSTaskNoticeData(...))`
- `operationId` 为 Optional，向后兼容（旧消费者忽略此字段）

---

## B9. 测试矩阵

| 测试文件 | 测试数 | 覆盖范围 | 结果 |
|----------|--------|----------|------|
| `tests/emulator/test_emulator_manager.py` | 18 | operate 校验/accepted/并发/WS通知/status隔离/ad-blocking/inflight清理/WS失败隔离 | 18 passed |
| `tests/emulator/test_provider_fallback_contract.py` | 17 | ServiceRegistry原语/host-compat方法/三大契约不变式 | 17 passed |
| `tests/api/test_emulator_api.py` | 23 | 全端点 CRUD/operate accepted/错误码映射/枚举校验 | 23 passed |
| **合计** | **58** | — | **58 passed, 0 failed** |

> 证据：`_alpha_build/a1/glm-game-emulator-management-20260723/subagent-A/pytest-run-final.log`

---

## B10. 修改文件清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `app/core/emulator_manager.py` | 重写 | 消除假成功/隔离/suppress→命名异常/WS失败隔离 |
| `app/api/emulator.py` | 修改 | operate 返回 EmulatorOperateOut + _error_code 映射 |
| `app/models/schema.py` | 修改 | 新增 EmulatorOperateOut + WSTaskNoticeData.operationId |
| `app/plugins/emulator_compat.py` | 修改 | operate 返回 str (operation_id) |
| `tests/emulator/__init__.py` | 新增 | 包标识 |
| `tests/emulator/conftest.py` | 新增 | FakeConfig/FakePublisher/FakeDeviceBase + patch fixture |
| `tests/emulator/test_emulator_manager.py` | 新增 | 18 个确定性测试 |
| `tests/emulator/test_provider_fallback_contract.py` | 新增 | 17 个契约测试 |
| `tests/api/test_emulator_api.py` | 新增 | 23 个 API 端点测试 |

---

> 后端功能矩阵完毕。与前端矩阵互补，前端 Q1/Q2（假成功/WS未订阅）已在后端侧修复。

---

# 功能矩阵 — 游戏/模拟器管理（脚本联动部分）

> Subagent C 测试与可用性研究产出
> 工作树：`D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration`
> 分支：`integration/dev-v2-dev-all-plugins`，HEAD：`b5e872815`
> 证据来源：`app/task/*/manager.py`、`app/task/general/adapter.py`、`frontend/src/views/EditView/Script/*ScriptEdit.vue` 源码直接读取
> 标注规则：`observed` = 直接读取确认；`inferred` = 基于代码推断；`unverified` = 未实机验证

---

## C1. 脚本联动总览

各脚本类型通过模拟器选择器将 emulator uid 和 index 写入脚本配置，后端 task manager 读取配置并通过 `EmulatorManager.get_emulator_instance()` 获取实例，脚本完成后调用 `emulator_manager.close()` 收尾。

存在**两套字段命名约定**：

| 约定 | 配置节 | 字段 | 使用者 |
|------|--------|------|--------|
| 约定 A | `Emulator` | `Id` / `Index` | MAA、SRC、M9A |
| 约定 B | `Game` | `EmulatorId` / `EmulatorIndex` | MaaEnd、General |

---

## C2. 脚本联动矩阵

| 脚本 | 前端文件 | 前端字段 | 后端文件 | 后端读取 | 收尾 | 标注 |
|------|----------|----------|----------|----------|------|------|
| **MAA** | `MAAScriptEdit.vue:106,145` | `maaConfig.Emulator.Id` / `maaConfig.Emulator.Index` | `app/task/MAA/manager.py:133-134` | `script_config.get("Emulator", "Id")` | `manager.py:202-203` `close(Index)` | `observed` |
| **MaaEnd** | `MaaEndScriptEdit.vue:236,270` | `maaEndConfig.Game.EmulatorId` / `maaEndConfig.Game.EmulatorIndex` | `app/task/MaaEnd/manager.py:112-113` | `script_config.get("Game", "EmulatorId")` | `manager.py:184-185` `close(EmulatorIndex)` | `observed` |
| **SRC** | `SRCScriptEdit.vue:67,106` | `srcConfig.Emulator.Id` / `srcConfig.Emulator.Index` | `app/task/SRC/manager.py:135-136` | `script_config.get("Emulator", "Id")` | `manager.py:205-206` `close(Index)` | `observed` |
| **M9A** | （无独立 ScriptEdit 视图） | — | `app/task/M9A/manager.py:167-168` | `script_config.get("Emulator", "Id")` | `close(Index)` | `observed` (后端) / `inferred` (前端无独立视图) |
| **General** | `GeneralScriptEdit.vue:574,635` | `generalConfig.Game.EmulatorId` / `generalConfig.Game.EmulatorIndex` | `app/task/general/adapter.py:288-289,297,313` | `Game.EmulatorId` / `Game.EmulatorIndex` | — | `observed` |
| **MaaFW** | `MaaFWScriptEdit.vue:89-109` | composable props (`emulatorOptions`, `emulatorDeviceOptions`, `handleEmulatorSelectChange`) | （走 plugin，非 task manager） | plugin 内部 | plugin 内部 | `observed` (前端) / `inferred` (后端) |
| **OK Script** | （无 Emulator 引用） | — | （plugin 内部） | — | — | `observed` (前端无引用) |
| **Okww** | （无 Emulator 引用） | — | （plugin 内部） | — | — | `observed` (前端无引用) |

---

## C3. 前端模拟器选择器行为

各脚本编辑页的模拟器选择器共享相同的行为模式（`observed`）：

| 行为 | MAA | MaaEnd | SRC | General | MaaFW | 标注 |
|------|------|--------|-----|---------|-------|------|
| 模拟器下拉列表 | `loadEmulatorOptions()` | 同 | 同 | 同 | composable `emulatorOptions` | `observed` |
| 设备 index 下拉列表 | `loadEmulatorDeviceOptions(emulatorId)` | 同 | 同 | 同 | composable `emulatorDeviceOptions` | `observed` |
| 切换模拟器时清空 index | `handleEmulatorSelectChange` 清空 `Emulator.Index` | 清空 `Game.EmulatorIndex` | 清空 `Emulator.Index` | 清空 `Game.EmulatorIndex` | composable 处理 | `observed` |
| index 下拉禁用条件 | `!Emulator.Id` | `!Game.EmulatorId` | `!Emulator.Id` | `!Game.EmulatorId` | composable 处理 | `observed` |
| 加载设备选项时 loading | `emulatorDeviceLoading` | 同 | 同 | 同 | composable `emulatorDeviceLoading` | `observed` |

---

## C4. 后端 emulator 获取与收尾

所有 task manager（MAA/MaaEnd/SRC/M9A）共享相同的 emulator 生命周期模式（`observed`）：

```
脚本启动:
  1. script_config.get(<Section>, <IdKey>) → emulator_id
  2. EmulatorManager.get_emulator_instance(emulator_id) → emulator_manager
  3. emulator_manager.open(<IndexKey>) → 启动指定 index

脚本执行:
  ... 任务逻辑 ...

脚本收尾:
  emulator_manager.close(<IndexKey>) → 关闭指定 index
```

| 步骤 | MAA | MaaEnd | SRC | M9A | 标注 |
|------|-----|--------|-----|-----|------|
| 获取 id | `get("Emulator", "Id")` | `get("Game", "EmulatorId")` | `get("Emulator", "Id")` | `get("Emulator", "Id")` | `observed` |
| 获取 index | `get("Emulator", "Index")` | `get("Game", "EmulatorIndex")` | `get("Emulator", "Index")` | `get("Emulator", "Index")` | `observed` |
| 跳过条件 | `Id == "-"` | `EmulatorId == "-"` or `EmulatorIndex in ["", "-"]` | `Id == "-"` | `Id == "-"` or `Index == "-"` | `observed` |
| 获取实例 | `EmulatorManager.get_emulator_instance(Id)` | 同 | 同 | 同 | `observed` |
| 收尾关闭 | `close(Index)` | `close(EmulatorIndex)` | `close(Index)` | `close(Index)` | `observed` |

> General 脚本通过 `app/task/general/adapter.py` 构建 schema options，不直接调用 `EmulatorManager`；实际 emulator 操作由 General 任务内部逻辑处理（`observed` adapter.py:288-322）。
> MaaFW 脚本通过 plugin 机制处理 emulator，不走 task manager 路径（`inferred`）。

---

## C5. 联动测试覆盖

| 测试 ID | 覆盖内容 | 状态 | 证据 |
|---------|----------|------|------|
| LINK-MAA | 前端 `Emulator.Id/Index` → 后端 `get("Emulator", "Id/Index")` → `get_emulator_instance` → `close` | `observed` (代码) / `unverified` (实机) | `MAAScriptEdit.vue:106,145` + `MAA/manager.py:133-134,202-203` |
| LINK-MaaEnd | 前端 `Game.EmulatorId/EmulatorIndex` → 后端 `get("Game", "EmulatorId/EmulatorIndex")` | `observed` (代码) / `unverified` (实机) | `MaaEndScriptEdit.vue:236,270` + `MaaEnd/manager.py:112-113,184-185` |
| LINK-SRC | 前端 `Emulator.Id/Index` → 后端 `get("Emulator", "Id/Index")` | `observed` (代码) / `unverified` (实机) | `SRCScriptEdit.vue:67,106` + `SRC/manager.py:135-136,205-206` |
| LINK-M9A | 后端 `get("Emulator", "Id/Index")` → `get_emulator_instance` → `close` | `observed` (后端) / `inferred` (前端) | `M9A/manager.py:167-168` |
| LINK-General | 前端 `Game.EmulatorId/EmulatorIndex` → 后端 adapter.py schema options | `observed` (代码) / `unverified` (实机) | `GeneralScriptEdit.vue:574,635` + `general/adapter.py:288-322` |
| LINK-MaaFW | 前端 composable props → plugin 内部 | `observed` (前端) / `inferred` (后端) | `MaaFWScriptEdit.vue:89-109` |
| LINK-OkScript | 前端无 emulator 引用，plugin 内部处理 | `observed` (前端无引用) | grep 无命中 |
| LINK-Okww | 前端无 emulator 引用，plugin 内部处理 | `observed` (前端无引用) | grep 无命中 |

> 实机联动验证见手测卡 `MANUAL_TEST_CARDS.md` GM-014。

---

## C6. 已知联动风险

| 风险 ID | 描述 | 影响 | 优先级 | 标注 |
|---------|------|------|--------|------|
| R-LINK-01 | 删除模拟器后脚本配置中的 `Emulator.Id` / `Game.EmulatorId` 成为悬空引用 | 运行脚本时 `get_emulator_instance` 抛 `KeyError` → HTTP 400 | P2 | `observed` (代码) / `unverified` (实机) |
| R-LINK-02 | M9A 无独立 ScriptEdit 视图，配置可能需通过其他方式编辑 | 用户无法在前端直观选择模拟器 | P3 | `inferred` |
| R-LINK-03 | MaaFW 通过 composable + plugin 处理 emulator，不走 task manager 路径 | emulator 生命周期不受 task manager 的 `close()` 收尾保护 | P2 | `inferred` |
| R-LINK-04 | 两套字段命名约定（`Emulator.Id/Index` vs `Game.EmulatorId/EmulatorIndex`）增加维护成本 | 新增脚本类型时需选择正确约定 | P3 | `observed` |

---

> 脚本联动部分完毕。实机验证依赖 GM-014 手测卡回填。
