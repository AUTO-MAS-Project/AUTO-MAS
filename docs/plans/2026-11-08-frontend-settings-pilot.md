# 前端收口试点：设置字段与开发入口

本轮从调研进入一个有限试点。基线为 `00e1e01766d624909ccbe8983b9efa4db3b7645f`，在主工作区执行；拉取 `origin/dev` 后仅快进同步一条无重叠的后端修复，保留此前所有未提交改动。

## 现状差异与选择

| 代表区域 | 已有职责划分 | 本轮判断 |
| --- | --- | --- |
| 功能设置、更新设置 | `index.vue` 持有设置，`useSettingPersistence` 保存/回读/同步，`useSettingsApi` 调用生成服务，UI 使用 SectionCard/SettingRow | 沿用这些入口；修正重复且宽泛的保存类型，以及页面向下转发业务选项的问题 |
| 脚本列表 | `Scripts.vue` 通过 `useScriptList` 管理列表，创建与导航已有独立流程 | 保留上一轮注册表 WIP，不混入设置试点 |
| General 专项编辑 | 脚本编辑使用 `useScriptSaveMutation`；用户编辑另有 `useSaveQueue` | 保存语义不同，保留独立入口，不套用设置字段契约 |

设置区域已经具备共享布局与集中保存能力，没有再次封装通用表单的实际需要。本轮选择功能设置作为普通字段范例，更新设置作为第二个消费者，检验同一保存契约能否覆盖两者。

## 最终职责与实现

- [开发入口](../../frontend/README.md)列出开发顺序、权威规范、验证入口及真实代码范例，并修正过时目录树。
- [settingTypes.ts](../../frontend/src/views/setting/settingTypes.ts)从生成的 `GlobalConfig` 派生静态字段的组、字段和值关系，不重复定义后端模型。通知描述表使用独立动态类型，未新增字段白名单或第二套校验。
- [useSettingPersistence.ts](../../frontend/src/views/setting/useSettingPersistence.ts)继续统一字段补丁、规范化回读、Electron 同步及已有联动，只暴露实际需要的读取和保存入口。
- [TabFunction.vue](../../frontend/src/views/setting/TabFunction.vue)拥有历史保留选项；[UpdateSettingsSection.vue](../../frontend/src/views/setting/UpdateSettingsSection.vue)拥有更新源、渠道和镜像选项。控件事件从这些有限选项取得值，再调用静态保存入口。
- [VoiceSettings.vue](../../frontend/src/views/setting/components/VoiceSettings.vue)承接原语音区域、语音选项和禁用关系，只接收语音设置与保存函数，沿用原有组件及样式。
- [MirrorCdkSettings.vue](../../frontend/src/views/setting/components/MirrorCdkSettings.vue)直接消费布尔保存结果，删除中间的空返回适配；保存成功且没有后续草稿时才确认本次草稿。原队列、失焦保存和草稿保护保留。
- [format-check.yml](../../.github/workflows/format-check.yml)在既有依赖安装后执行 `yarn test`，失败会阻止该检查通过；浏览器 E2E 继续按项目策略在作者本机运行。

本轮不改变布局、主题、保存时机、全局设置并发调度、Replay 保存失败抛错或特殊字段回读范围。既有保存统计仍由 `useSettingsApi` 的 `config_write_finished`、设置/通知变更观察入口负责，不增加重复事件，也不扩大采集范围。

## 尺寸与剩余边界

全文件行数包含模板、脚本、样式、注释及空行，最终格式化后与上述基线对比：

| 文件 | 基线 | 最终 |
| --- | --- | --- |
| 设置 index.vue | 580 | 542 |
| TabFunction.vue | 475 | 471 |
| TabOthers.vue | 375 | 364 |
| UpdateSettingsSection.vue | 216 | 246 |
| VoiceSettings.vue | 新增 | 57 |

其余本轮修改组件均低于 500 行。`index.vue` 仍然超限，本轮只收回选项归属和收紧既有契约，没有扩展业务行为；剩余外观、音效等协调职责不在本次迁移范围。行数变化不作为收口效果的唯一证据。

## 验收与证据

- 开发者可以从 README 找到推荐入口、状态归属、保存规则和检查命令。
- 静态字段的错误组、错误字段、错误值类型及非法选项会被 TypeScript 拒绝，合法字段和可空值仍可使用；本地编译探针已执行验证，无新增探针文件。
- [保存契约单测](../../frontend/src/views/setting/useSettingPersistence.test.ts)使用真实 API composable，只替换生成服务传输、桌面与展示边界；验证确认后才应用补丁、桌面数据可克隆、规范化回读完成前保存仍未完成，以及失败保留值、可重试和 Replay 拒绝语义。
- [浏览器场景](../../frontend/e2e/settings.pw.ts)复用隔离后端与现有启动器。已有普通设置/启动偏好场景继续运行；新增更新设置场景通过真实 UI 验证选项、CDK 保存回读、新草稿保护、拒绝后的重试及重载结果。CDK 状态查询替换外部传输，配置保存和回读使用真实隔离后端。

已执行的检查：

- `yarn lint`、`yarn typecheck`、`yarn format:check` 通过。
- `yarn test`：49 个文件、267 项通过；补强回读等待断言后，相关 3 项再次通过。
- `yarn audit:baseline --check 00e1e0176` 通过：336 个组件无违反尺寸策略的文件，不表示所有存量组件都小于 500 行。
- `yarn audit:i18n` 与 `yarn e2e:check` 通过。
- 首轮隔离浏览器组合 5 项通过；去除更新源默认值假设后，新增场景再次通过（24.7 秒）。最终代码的 `e2e:check` 也再次通过。
- 独立复核补强了保存等待回读的断言，未发现其他可行动问题。浏览器未捕获页面异常或 Vue 全局错误；仍有来自未修改组件的非致命 `mask` 属性警告，本轮未处理。
- 两次隔离数据根均已删除，测试端口无残留监听。首轮报告保存在 `frontend/playwright-report/settings-pilot-five-scenarios-20261108-2357/index.html`；最终更新设置截图位于 `frontend/test-results/browser/settings.pw.ts--settings-u-8ed0b-aft-through-saves-and-retry/`，本地已查看。

## 与已有 WIP 的关系

此前的脚本元数据、编辑器路由、导航回归和尺寸门禁仍是未提交改动；本轮没有撤销或自动提交它们。CI 文件同时保留了此前尺寸检查和本轮单测步骤。后续交付时应按这些职责解释差异，不能把整份工作区状态都归到设置试点。

本轮属于内部重构、开发入口与验证补齐，不新增更新日志碎片，不改版本号。未运行安装包构建、真实系统启动项、真实更新下载、账号或游戏流程；浏览器结果只证明共用渲染层及实际隔离 HTTP/WS 行为。
