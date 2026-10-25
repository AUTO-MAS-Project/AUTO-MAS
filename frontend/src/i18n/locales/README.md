# 词表

界面文案的唯一定义处。三个语言各一个 JSON 文件，键结构完全一致的嵌套对象：

| 文件 | 语言 | 说明 |
| --- | --- | --- |
| `zh-CN.json` | 简体中文 | **源语言**。新词条先加在这里，键与文案以它为准 |
| `en-US.json` | English | 词表可少于中文，缺的键按回退链显示中文 |
| `ja-JP.json` | 日本語 | 同上；回退链是 ja → en → zh，所以日文缺的键优先显示英文 |

## 加一条文案

1. 在 `zh-CN.json` 里按既有命名空间加键（`ns.key`，两层即可，别拉平也别套太深）。
2. 在 `en-US.json` / `ja-JP.json` 的同位置补译文；暂时没有译文可以不加，界面会回退。
3. 组件里用 `$t('ns.key')`（模板，已在 `src/i18n/index.ts` 开了 `globalInjection`）；
   脚本块里用 `const { t } = useI18n()`；组件外的工具函数用 `@/i18n` 导出的 `t` / `translate`。

## 会被单测拦下来的写法

`src/i18n/locales.test.ts` 守着以下几条，改完跑 `yarn test` 即可发现：

- 用了 `t('ns.key')` / `$t('ns.key')` 但中文词表里没有这个键；
- 其它语言词表里出现了中文词表没有的键（中文是源语言，反向不允许）；
- 词条里有未转义的 `|` `{` `}` `@` —— 这些字符在 vue-i18n 里有语法含义，
  漏转义时页面只会静默少一截文案，不会报错。字面量用 `{'|'}` 包一层；
- 词条里出现形似 HTML 标签的片段（`<b>` 之类会触发 vue-i18n 的 HTML 警告）。

复数消息用 vue-i18n 的 `|` 语法，但只有登记在 `PLURAL_KEYS` 里的键才允许出现裸 `|`。

## 词表怎么进包

- `zh-CN.json` 被 `src/i18n/index.ts` 静态 import，随主包加载（源语言必须随时可用）。
- `en-US.json` / `ja-JP.json` 走动态 `import()`，由 `ensureLocaleMessages(locale)` 在切换语言前拉取。
  日语会连带加载英文，因为回退链是 ja → en → zh。
- 构建期由 `@intlify/unplugin-vue-i18n`（见 `vite.config.ts`）把这些 JSON 预编译成消息函数，
  运行时因此不必打包 vue-i18n 的消息编译器。**不要手写编译后的消息**，这里只放原始 JSON。

## 编辑器（i18n-ally）

`frontend/.vscode/extensions.json` 已推荐 `lokalise.i18n-ally`。个人 `.vscode/settings.json`
不进版本库，需要提示、内联译文和跳转时把这段贴进去：

```jsonc
{
  "i18n-ally.localesPaths": ["src/i18n/locales"],
  "i18n-ally.pathMatcher": "{locale}.json",
  "i18n-ally.sourceLanguage": "zh-CN",
  "i18n-ally.displayLanguage": "zh-CN",
  "i18n-ally.enabledFrameworks": ["vue"],
  "i18n-ally.keystyle": "nested",
  "i18n-ally.editor.preferEditor": true
}
```

## 历史

这三张表原本是 `zh-CN.ts` / `en-US.ts` / `ja-JP.ts` 三个 TS 对象文件，随主包整体加载。
改成 JSON 是为了让构建期预编译和按语言分包成为可能；键结构、文案与命名空间没有变。
