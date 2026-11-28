# 界面语言资源

本目录维护应用初始化完成后的业务词条（Python 仅负责加载文件，插值、复数与语言回退由前端 Vue I18n 完成）。初始化、启动恢复、日志窗口等无后端阶段所需词条独立维护在 `frontend/src/i18n/bootstrap/`。

## 文件与格式约定

| 界面 / API 语言 | 本目录文件 |
| --- | --- |
| `zh-CN` | `zh_CN.json` |
| `en-US` | `en.json` |
| `ja-JP` | `ja.json` |

- 每种语言为一份 UTF-8 单语 JSON，采用扁平的 `core.*` 键名与字符串值。
- 简体中文（`zh_CN.json`）为源语言，其他语言可省略未翻译键；保留 `{name}`、复数分隔符等 Vue I18n 语法，不在后端提前插值或填充回退文案。
- 禁止为旧 key 建立别名。修改业务 key 时需同步更新所有静态/动态调用点与后端返回的文案 key，并运行 `yarn audit:i18n` 检查。

## 加载、回退与热刷新

- **接口**：前端通过 `/api/i18n/locales`（返回 `{ available, revision }`）与 `/api/i18n/messages?locale=<lang>`（返回 `{ locale, revision, messages: { core: ... } }`）读取，均使用 `OutBase` 包络。同批加载的语言必须拥有相同 `revision`。
- **组合与回退**：Renderer 使用单个 Vue I18n 实例，启动先载入全部 `bootstrap` 词表；进入业务页或切换语言时用 `setLocaleMessage()` 整体组合 `bootstrap + core`（`ja-JP → en-US → zh-CN`，`en-US → zh-CN`）。
- **变更刷新**：后端按请求检查文件变化，校验完整快照后更新缓存并推送 WebSocket `I18n / i18n.updated`（`{ revision }`）；前端收到通知或重连后刷新，失败时保留当前可用词表。词表仅存内存，不落盘到浏览器存储或用户配置。

## Weblate 组件配置

- 文件掩码：`res/i18n/*.json`
- 单语源语言文件：`res/i18n/zh_CN.json`（简体中文）
- 文件格式：JSON file（`json`，保持扁平点分 key）
- 新语言模板：留空
- 翻译检查标记：`vue-format`

参考：[Weblate JSON 格式](https://docs.weblate.org/en/latest/formats/json.html) · [Vue I18n 格式检查](https://docs.weblate.org/en/latest/user/checks.html#vue-i18n-formatting)
