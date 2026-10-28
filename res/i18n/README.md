# 界面语言资源

初始化完成后的词条在本目录维护，Python 只负责加载资源，Vue I18n 负责插值、复数和语言回退。
初始化、启动恢复、日志窗口等无需后端即可使用的词条在 `frontend/src/i18n/bootstrap/` 独立维护。

| 界面/API 语言 | 本目录文件 |
| --- | --- |
| `zh-CN` | `zh_CN.json` |
| `en-US` | `en.json` |
| `ja-JP` | `ja.json` |

每种语言一份 UTF-8 单语 JSON，使用扁平的 `core.*` key 和字符串 value。中文是源语言，其他语言可以省略未翻译的 key；有意使用的空字符串仍是有效译文。保留 `{name}`、复数分隔符等 Vue I18n 消息语法，不在 Python 中提前插值或填入回退译文。

Weblate 组件使用以下配置：

- 文件掩码：`res/i18n/*.json`
- 单语源语言文件：`res/i18n/zh_CN.json`
- 源语言：简体中文
- 文件格式：JSON file（`json`，保持点分 key 的扁平结构）
- 新语言模板：留空
- 翻译检查标记：`vue-format`

参见 [Weblate JSON 格式](https://docs.weblate.org/en/latest/formats/json.html)及 [Vue I18n 格式检查](https://docs.weblate.org/en/latest/user/checks.html#vue-i18n-formatting)。

前端通过 `/api/i18n/locales` 与 `/api/i18n/messages?locale=zh-CN` 读取资源。内容 revision 标识整套资源；同一批语言加载必须使用相同 revision。前端只保存运行期间的内存缓存，首次读取失败时保留初始化恢复界面。

两个入口均使用 `OutBase` 包络，调用者先检查 `code === 200`，再读取 `data`：

- `locales`：`{ available, revision }`，使用上表中的界面语言标记。
- `messages`：`{ locale, revision, messages: { core: ... } }`，按点分 key 组织为嵌套对象，仅包含该语言实际拥有的词条。

Renderer 使用单个 Vue I18n 实例，挂载前装入全部 `bootstrap` 词表。进入业务页面或切换语言时，通过生成客户端取得目标语言与回退语言，使用 `setLocaleMessage()` 组合本地 `bootstrap` 和后端 `core`；每次整体替换，避免已删除的词条残留。日语依次回退英语、中文，英语回退中文。语言偏好保存在 Electron，初始化期间切换语言不请求后端。

后端按请求检查文件变更，校验完整快照后更新缓存，并发送 `I18n / i18n.updated` 通知（数据为 `{ revision }`）。前端收到通知或连接恢复后刷新；资源替换失败保留当前可用词表。没有文件轮询器，也不把词表写入用户配置或浏览器持久化存储。首次失败的“重试”只读取资源，不重新安装依赖或启动后端。

词条名称直接用于调用点，禁止建立旧 key 别名。修改业务 key 时同步更新静态调用、动态 key、后端返回的文案 key，并运行 `yarn audit:i18n` 和全局词表检查。

初始化调用链所需词条必须放入 `bootstrap`；同一文字在业务阶段有独立用途时，可以另设 `core` 词条。新增初始化界面时也需检查其标题栏、关闭确认、日志和错误恢复依赖。本说明仅约定 Weblate 接入配置，不包含服务部署。

本目录的 `okww.po` 继续服务既有脚本日志翻译，不属于上述 JSON 资源。
