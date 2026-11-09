# 前端批量收口与收益复测

## 基线与范围

本轮在主工作区继续已有任务。重新拉取 `origin/dev`，HEAD 仍为 `00e1e01766d624909ccbe8983b9efa4db3b7645f`；没有创建工作树、提交或推送。

收益以本轮修改前的实际工作区为起点，包含此前尚未提交的注册表和设置试点，不把这些历史改动再次算入收益。开始前冻结 2,171 个源码、测试和配置文本文件，记录 SHA-256、字节数与物理行数。原始资料留在 Git 忽略的 `.dev/frontend-governance/20261109-batch/`：

- `baseline-manifest.json`、`before/`：本轮起点清单与原始文本。
- `measure-batch.mjs`、`metrics.json`：基于冻结文本与当前源码的复测入口和结果；在仓库根运行 `node .dev/frontend-governance/20261109-batch/measure-batch.mjs`。
- `duplicates-before.json`、`duplicates-after.json`：同一 jscpd 配置扫描冻结源码和最终源码的报告。

渲染层统计复用 `frontend/scripts/audit-baseline.mjs` 的口径：手写 `.vue`、`.ts`、`.css` 物理行，包含空行和注释，排除测试、生成 API、词表与构建产物；新共享组件和工具的行数全部计入最终值。测量脚本会核对三个改动区域的净变化之和等于渲染层总变化，避免把其他改动混入。

## 实际改动

### 按压音效职责回收

原音效组件的 8 项状态与 5 个事件经过 `index.vue → TabBasic.vue → PressSoundSettings.vue`。实际数据始终属于既有 `usePressSoundStore`，中间两层没有独立业务决策。

[PressSoundSettings.vue](../../frontend/src/views/setting/components/PressSoundSettings.vue)现在直接复用同一个 store，并承接原有保存、导入、预览和错误反馈。删除父页和中间层转发，不另造 controller。原有文件大小上限、空内容拒绝、缓存失效、双文件就绪判断、store 串行保存及失败回滚均保留，样式未修改。配置读取随音效区域 setup 执行；主页仍自行加载同一 store，保存操作仍先等待初始化。

### 五个脚本页共享运行限制区域

OkNte、Okww、BetterGI、General、ZzzOd 的四字段区域由[ScriptRunLimitsSection.vue](../../frontend/src/views/EditView/Script/components/ScriptRunLimitsSection.vue)统一组合，继续复用原 `ScriptHardTimeoutField` 与 `ScriptRunLimitField`。

保留每页外框、标题、专项提示与 General 的增强样式。四个显式 model 连接页面草稿；区域失焦只发送保存字段键，父页读取自身最新 `Run[key]`，再通过原 `useScriptSaveMutation` 保存，不批量写入四字段。底层两个字段组件恢复/保留原实现，硬时限仍仅在清空时恢复 120。这样沿用原页面读取草稿的语义，避免消费尚未回刷的子组件值；详细失败与修复证据见下文兼容性补查。

BAAH 缺少每日次数字段，Whimbox 的区域含管理员选项，MAA/SRC/HSR 的布局或触发方式不同，本轮没有强行接入。

### 九个用户保存入口共享纯补丁构造

General、BAAH、Whimbox、SRC、BetterGI、Okww、OkNte、ZzzOd 用户编辑页，以及 MaaFW 用户持久化模块，复用 13 行的[buildFieldPatch](../../frontend/src/utils/fieldPatch.ts)。

只统一点分字段路径到嵌套补丁的构造。用户名别名、Whimbox 序列化、初始化守卫、保存队列位置、合并 key、General 规范化回读及各自失败语义均保留。MAA 的原对象读写、HSR 的计划所有者和 MaaEnd 的合并写入语义不同，继续使用原入口。

开发者入口同步到 [frontend/README.md](../../frontend/README.md)，这些实际实现可以直接作为后续任务范例。

## 同口径量化结果

| 指标 | 本轮前 | 本轮后 | 变化 |
| --- | ---: | ---: | ---: |
| 音效区域两层状态/事件转发 | 26 处 | 0 处 | 删除 26 处 |
| TabBasic 对外 props | 42 项 | 29 项 | 减少 13 项 |
| 音效组件对外 props / emits | 8 / 5 | 0 / 0 | 复用实际状态所有者 |
| 四字段运行限制组合布局 | 5 份 | 1 份 | 减少 4 个共同维护点 |
| 用户字段补丁构造 | 9 份 | 1 份 | 减少 8 个共同维护点 |
| 三个区域的生产代码 | 14,593 行 | 14,421 行 | 净减 172 行 |
| 全部手写渲染层 | 174,487 行 | 174,315 行 | 净减 172 行 |
| 超过 500 行的 Vue 组件 | 52 个 | 50 个 | 减少 2 个 |
| Vue 组件总数 | 336 个 | 337 个 | 新增 1 个共享组件 |
| jscpd 重复片段 | 156 组 | 150 组 | 减少 6 组 |
| jscpd 报告重复行 | 2,621 行 | 2,532 行 | 减少 89 个报告行 |

两条选定组件边上的全部 `bind/on` 指令由 55 个变为 29 个，剩余 29 个属于其他设置，删除的 26 个都是音效转发。按 Vue 模板 AST 计数，不把 props 声明、解构和模板使用重复累计。

三个生产区域分别净减 56 行、66 行、50 行，已计入新共享实现及兼容性修复。设置主页面为 542 → 408 行，ZzzOd 脚本页为 502 → 477 行。其余大文件仍按各自基线变短，不把局部整理宣称为全项目已清理完毕。

jscpd 保持仓库的 mild、5 行、70 token 阈值及相同忽略规则。它对 Vue 脚本、模板、样式分格式计数，报告行不能视为唯一物理源码行，也不能和净减 172 行相加。原报告扫描范围为手写 `src` 与 `electron`；排除生成 API、词表、测试和声明文件。

## 行为验证与执行成本

| 场景 | 可观察断言 | 执行结果 |
| --- | --- | --- |
| 五种脚本编辑页 | 每次失焦只写一个 Run 字段；四字段映射正确；重试 0 修正为 1、普通超时 10000 修正为 9999、硬时限 0 修正为 1、清空硬时限写入 120；其他 Run 值不变；重载一致 | 补强后的每个参数化场景断言仅 8 笔更新，最终结果见兼容性补查 |
| 音效设置 | 启用、预设、音量可保存及重载；一笔 IPC 拒绝后开关回滚、已保存值不变、有错误提示，下一次可重试 | 1 个场景通过；使用现有 browser bridge 配置替身 |
| 通用脚本与账号导航 | 创建、脚本及账号编辑入口、账号名称与备注保存及重载 | 既有场景通过，守住一个真实用户补丁消费者 |
| 启动与外观偏好 | 设置持久化、主题与导航相邻行为 | 既有场景通过 |
| 字段补丁公共函数 | 最小嵌套结构、false/null 和对象引用保持 | 新增 2 项契约单测通过 |

统一命令均从 `frontend/` 执行：

```powershell
yarn lint
yarn typecheck
yarn format:check
yarn audit:i18n --check
yarn audit:baseline --check 00e1e0176
yarn test
yarn e2e:check
yarn e2e --grep '@script-run-limits|persists press sound preferences|reads existing custom-pair|creates a general script|preserves startup and appearance preferences'
```

初轮完整单测为 50 个文件、269 项，运行 6.91 秒；隔离浏览器组合为 8 个场景、59.7 秒。兼容性补查修复后，269 项单测再次通过（6.55 秒），补强后的最终浏览器组合 9 项通过（报告为 1.1 分钟），`e2e:check` 的 6 项基础设施检查及 E2E 类型检查通过；lint、renderer 类型、格式、组件尺寸与差异检查通过。执行耗时来自本机单次运行，只表示各次验收成本，未做可比较的前后性能基准，不宣称重构提高了运行速度或开发速度。

浏览器连接真实临时后端，配置准备和删除走公开 API，没有启动真实脚本、游戏或账号。音效测试仅在现有 IPC 边界拒绝一笔写入，不验证真实 Electron 写盘或声音播放。运行限制测试没有注入写入失败，其证据范围是字段映射、清空默认值与持久化；失败回滚证据属于音效场景。

浏览器未捕获页面异常或 Vue 全局错误。存在未修改 `GlobalPowerCountdown` 的非致命 `mask` 属性警告；本轮不扩展修复。临时根 `auto-mas-e2e-Fz7yD2` 已删除，36174/5174 端口无残留监听。报告与截图位于本机忽略目录 `frontend/playwright-report/browser/`、`frontend/test-results/browser/`。

## 评审与剩余限制

初轮独立源码复核未发现可行动问题；随后升级兼容补查确实发现了下面记录的一处边界回归。这说明初轮复核与合法输入测试不足以证明全部行为等价。沿用已有 store/API 保存事件，不新增重复遥测，不改采集范围。

本轮未新增依赖、后端接口、生成 API、配置 schema 或版本号，属于内部重构与验证，不新增更新日志碎片。所有上一轮 WIP 保留；没有提交或推送，也未运行远端 CI、安装包或真实设备流程。全项目仍有 50 个超过 500 行的组件，后续应继续按实际业务职责逐批收口。

## 升级兼容性补查（2026-11-09）

用户追问升级安全后补查发现：AntD 在数字输入失焦时先同步修正越界值，再触发 blur；受控子组件的 model prop 可能尚未回刷。初版共享区域透传该旧值，改变了原页面直接读取自身草稿的行为。

真实浏览器复现：General 重试次数先为 4，输入 0 后失焦，预期最小值 1，实际请求仍写入 4。扩展既有 E2E 后，同一输入在修复前明确失败；原始日志为 `frontend/test-results/upgrade-clamp-general-red-20261109.log`，失败报告已单独保留在 `frontend/playwright-report/upgrade-clamp-general-red-20261109-011504/`。

修复采用最小 owner 方案：共享区域只发字段键，由五页读取各自最新 `Run[key]`。撤销对硬时限底层控件的事件修改，保留原 null/default 行为，没有新增 watch、影子状态、默认值或 nextTick。相同 General 用例修复后通过，另加硬字段越界回归；绿日志为 `frontend/test-results/upgrade-clamp-general-green-20261109.log`。

既有音效配置回归新增 `reads existing custom-pair`：一次性播种旧字段形态的 customPair、启用、音量 0、两个合成 Windows 路径和显示名，进入和刷新后核对 UI 与桥接读取值，刷新不重新播种。它证明渲染层保留已有字段，不代表真实桌面配置升级或声音播放。

最终 9 项组合全部通过，含五页相同输入边界、音效失败重试、既有 customPair/零音量配置读取、通用账号保存导航及相邻外观场景；报告另存 `frontend/playwright-report/upgrade-final-nine-scenarios-20261109-012040/index.html`，完整日志为 `frontend/test-results/upgrade-final-nine-scenarios-20261109.log`。临时数据根已删除，测试端口无残留监听，未捕获页面异常或 Vue 全局错误。

本次补查未改后端、生成 API、Electron 配置读写与 schema，因此没有新增数据格式迁移。以上是浏览器阶段的证据边界；随后对真实打包程序、配置副本、文件系统异常及音频播放的执行结果见[真实桌面验证记录](2026-11-09-frontend-desktop-validation.md)，仍不能承诺所有升级用户零回归。
