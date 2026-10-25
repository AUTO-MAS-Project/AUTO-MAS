<!--
  AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
  Copyright © 2025-2026 AUTO-MAS Team
-->

# 前端多语言（i18n）工作手册

本目录是前端界面文案的唯一来源。改文案、加文案、审文案前先读这一页；
哪条规则由谁把关写在每节末尾，能跑就别靠记性。

## 1. 文件结构

```
src/i18n/
├── index.ts          # createI18n 实例、locale 归一化、t / translate 导出
├── status.ts         # 把「运行 / 等待 / 异常」等状态值映射成当前语言的标签
├── locales/
│   ├── zh-CN.ts      # 源语言，4495 条，25 个命名空间
│   ├── en-US.ts
│   └── ja-JP.ts
└── locales.test.ts   # 词表契约断言（见 §4）
```

- **源语言是 `zh-CN`**：中文词表是唯一真值，en / ja 必须与之逐条对齐。
- 回退链是 `ja-JP → en-US → zh-CN`；回退只用来兜底，不是可以缺译的理由。
- 命名空间按界面区域划分，常用的几个：`common`（跨页面通用词）、`comp`（通用组件）、
  `edit`（账号/脚本编辑页，最大，2232 条）、`setting`（设置页）、`plan`、`queue`、
  `scheduler`、`emulator`、`emulator2`、`logs`、`status`、`apiErrors`。

## 2. 加一条文案

1. **先想清楚它放在哪个命名空间**：页面私有的别塞 `common`，通用按钮/提示才进 `common`。
2. 三个语言文件里**同时**加同一条 key（只加中文会被 `locales.test.ts` 拦下）。
3. 模板与 script 都用 `useI18n()` 取 `t`（`globalInjection` 未开启，模板里不认 `$t`）：

   ```vue
   <script setup lang="ts">
   import { useI18n } from 'vue-i18n'

   const { t } = useI18n()
   </script>

   <template>
     <a-button>{{ t('common.confirm') }}</a-button>
     <a-tag>{{ t('status.running') }}</a-tag>
   </template>
   ```

   状态值（`运行` / `等待` / `异常` …）不要自己写映射表，用 `useStatusLabel()`
   （`src/i18n/status.ts`）——这些中文同时是后端和前端比较用的取值，不能改字面量。

4. 组件外（store、纯函数模块）从 `@/i18n` 取 `t` / `translate`。
   这类地方**不要**硬编码中文，也不要缓存 t() 的结果——语言切换不会重载页面。
5. 提交前跑 `yarn audit:i18n`（见 §5），0 才算完。

## 3. key 命名约定

- 结构是 `命名空间.分组.字段`，全小驼峰：`edit.maaCultivateSkipActivity`、
  `setting.basic.mascotTask`。
- 字段名描述**这条文案在界面上的角色**，不是它的内容：
  `empty` / `emptyTitle` / `emptyDesc` / `placeholder` / `hint` / `toast.*` /
  `modal.*` / `title` / `label`。
- 布尔或状态类加语义前缀：`isRunning`、`hasUpdate`、`notChecked`。
- 别把整句话当 key（`please_select_a_server` 是反例）。
- 同一个动作在同一命名空间里复用同一条 key，别为了措辞微调复制一份。
- 复数与数字用 vue-i18n 的内建能力，不要手写 `items`/`items_plural` 两条 key：

  ```ts
  userCount: '{count} 个账号 | {count} 个账号'   // zh 两段写一样的；en / ja 按 one / other 写
  ```

  因为 `|` 是消息语法，这类 key 要在 `locales.test.ts` 的 `PLURAL_KEYS` 白名单里登记
  （目前 4 条）。数字、日期、货币走 `Intl` 或 dayjs，不要拼字符串
  （`dayjs.locale` 已跟随界面语言）。

## 4. 硬规则（违反会被门禁拦下）

| 规则 | 谁把关 |
| --- | --- |
| 三种语言的 key 集合必须完全一致（多一条、少一条都报错） | `locales.test.ts` + `yarn audit:i18n --check` |
| 同一条 key 在各语言里的占位符必须一致（`{name}`、`{count}`） | 同上 |
| 值里出现 `|` `{` `}` `@` 必须转义，否则被当成消息语法 | `locales.test.ts` |
| 源码里字面量 `t('ns.key')` 的 key 必须存在于 zh-CN | `locales.test.ts` |
| 词表里没有引用的 key 必须删掉 | `yarn audit:i18n --check` |
| 模板里不许写死中文文案 | `yarn audit:i18n --check` |
| 同一概念不许出现术语表外的第二种说法 | `yarn audit:i18n --check` |
| 词表改完必须过格式检查 | `yarn format:check` |

两个例外通道：

- **开发页面**（`devtools`、`OCRdev`、`TestRouter`、`UpdateDownloadDev`、`OverlayMaskDev`）不参与硬编码检查。
- `src/views/SRCUserEdit/StageConfigSection.vue` 里的游戏名保留原文，登记在
  `scripts/i18n-audit.mjs` 的 `HARDCODED_ALLOWLIST`。

需要新增豁免时改脚本里的白名单，并在 PR 里写清理由——不要在组件里堆 `// i18n-ignore`。

## 5. 工具

```bash
yarn audit:i18n              # 全量报告
yarn audit:i18n --verbose    # 列出每一条明细
yarn audit:i18n --json       # 机器可读
yarn audit:i18n --check      # 超阈值退出 1（CI 用，阈值默认全 0）
yarn audit:i18n --max-missing=5  # 单项阈值，调试时放宽
```

报告七段：缺译、源码在用但 zh 里没有、占位符不一致、术语偏离、死词条、模板硬编码中文、
动态拼接前缀（`t('a.' + x)` 这类静态审计看不到的调用）。术语偏离的判定表在
`scripts/i18n-audit.mjs` 的 `FORBIDDEN_TERMS`，改术语时与 §6 一起改。

CI 在 `.github/workflows/format-check.yml` 的「检查词表完整性」一步跑
`yarn audit:i18n --check`，与格式检查同一个 job。

编辑器侧推荐装 [i18n-ally](https://github.com/lokalise/i18n-ally)（仓库根 `.vscode/extensions.json`
已列出）。它的用途是**悬停看译文、跳转定义、发现缺失 key**；不要用它保存/批量翻译——
它会重写整个语言文件，把分节注释冲掉，落盘一律手工改。

## 6. 术语表

同一个概念在三种语言里只允许一种说法。改文案时照这张表，发现表外的不一致就在 PR 里顺手统一。

| 概念 | 中文 | English | 日本語 |
| --- | --- | --- | --- |
| 计划 / 计划表 | 计划、计划表 | plan | プラン |
| 队列 / 调度队列 | 队列、调度队列 | queue | キュー |
| 运行面板 | 运行面板 | run panel | 実行パネル |
| 调度中心 | 调度中心 | Scheduler | スケジューラ |
| 任务 | 任务 | task | タスク |
| 脚本 | 脚本 | script | スクリプト |
| 账号 | 账号 | account | アカウント |
| 用户（人） | 用户 | user | ユーザー |
| 模拟器 | 模拟器 | emulator | エミュレーター |
| 实例 | 实例 | instance | インスタンス |
| 关卡 | 关卡 | stage | ステージ |
| 理智 | 理智 | sanity | 理性 |
| 干员 | 干员 | operator | オペレーター |
| 材料 | 材料 | material | 素材 |
| 遗器 / 饰品 | 遗器、饰品 | relic / ornament | 遺物、オーナメント |
| 剿灭 | 剿灭 | Annihilation | 殲滅 |
| 通知 | 通知 | notification | 通知 |
| 日志 | 日志 | log | ログ |
| 历史记录 | 历史记录 | history | 履歴 |
| 设置 | 设置 | settings | 設定 |
| 配置 | 配置 | configuration | 設定 |
| 保存 | 保存 | Save | 保存 |
| 刷新 | 刷新 | Refresh | 更新 |
| 启用 / 禁用 | 启用、禁用 | On / Off、Enable / Disable | オン / オフ、有効化 / 無効化 |
| 状态 | 状态 | status | 状態 |
| 检查更新 | 检查更新 | Check for updates | 更新を確認 |
| 魔改 AVD | 魔改 AVD | modded AVD | 改造 AVD |
| 内测包 | 内测包 | test package | ベータパッケージ |

补充约定：

- 「账号」是界面实体，「用户」只指人（QQ 群、其他用户）。不要用「用户」指账号。
- 中文用全角标点，English 用半角 + 直引号，日本語用「」和「。」；省略号统一用 `…`，不要 `...`。
- 日语的文体统一用「です・ます」体，短标签可以用体言止め，不要与常体混排。
- 品牌名、脚本名（MAA、MaaEnd、BetterGI、BAAH、ok-ww、HSR、ZzzOd、MSS…）不翻译。

## 7. 后端文案

现状：后端 `app/api` 里仍有 300+ 处 `message="中文句子"`，前端以
`response.message || t('apiErrors.x')` 兜底，这条链路**不随界面语言变化**。

约定：

- 新增接口的失败响应优先返回稳定的 `code`，前端用 `t('apiErrors.<code>')` 展示，
  后端 `message` 只作为取不到 code 时的兜底（日志、未知错误）。
- `apiErrors` 里已有的 25 条是历史人工映射，新增 code 时一并补三语。
- 把中文漏给英文界面属于 bug，按 bug 修；不要指望回退链。

## 8. 常见坑

- **语言切换不重载页面**：不要缓存 `t()` 的结果，也不要在模块加载时把文案写进常量
  （这会拿不到切换后的新语言）。
- **keepAlive 页面**：`/scheduler` 等路由保留组件实例，切换语言时已烘焙进 ref 的
  label 不会自动更新；这类列表要么存 key、要么 `watch` 语言重新生成。
- **占位符别翻译**：`{name}`、`{count}` 原样保留；改完跑一次 `yarn audit:i18n`。
- **单条消息里别塞 HTML**：词表被当成消息编译，`<` `>` 会被判成标签；需要富文本时用组件拼。
- **删词条前先跑审计**：`--verbose` 能看到「疑似死词条」，那些只出现在字符串里、
  由后端 `labelKey` 驱动的 key 不要删。
