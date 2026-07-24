# AUTO-MAS Browser Runtime

这是 dev2 MAS 插件系统中的内置单例插件，不是 Chrome 扩展或独立程序：

- 插件名：`browser`
- 系统实例：`browser:system`
- 进程内服务：`browser.runtime.v1`
- 源码目录：`plugins/browser`

插件管理 Chrome for Testing、Chrome 或 Edge 会话。每个账号使用独立的 Chromium
Profile，因此 Cookie、Local Storage、IndexedDB 和站点权限可以在 MAS 重启后继续使用。

## 边界与安全

- 登录状态只保存在浏览器原生 Profile，不写入插件 JSON 配置、日志或 HTTP 响应。
- Profile 按 `owner_instance_id / namespace / profile_id` 分目录，同一 Profile 同时只允许
  一个写入会话；浏览器无法确认退出时会保留隔离锁。
- 每个会话返回随机 `session_token`，后续导航、截图、CDP、接管和关闭都必须携带。
- 未鉴权的插件 HTTP 网关只注册固定的“打开/关闭默认页面”动作，且响应不返回 URL、
  标题、Profile、会话 ID 或 token；全局会话与 Profile 列表不暴露到 HTTP。
- 不提供专用 Cookie 导出 API。进程内插件属于受信任的特权代码；持有会话 token 的插件
  可以执行 JavaScript/CDP，因此这里的 owner 是存储命名隔离，不是恶意插件沙箱。
- 不复用用户日常 Chrome/Edge 的默认 Profile。

## HSR 与 M7A 兼容接管

HSR 专项应把 `browser.runtime.v1` 声明为软依赖；服务缺失或返回 `UNAVAILABLE` 时，
仍保留原有本地 `StarRail.exe` 链路。首次登录使用有窗口模式，并为云星铁单独配置权限：

原版 M7A 不能安全复用 MAS 持有的浏览器：附着前会按 driver 可执行文件路径清理
chromedriver，退出流程还可能终止带 M7A 标记的浏览器。所以下面的 handoff 只面向
MAS-compatible external-owner 构建；返回值会明确包含
`compatibility="requires-mas-external-owner-build"` 和 `upstream_supported=False`。

```python
from auto_mas_core import BROWSER_RUNTIME_SERVICE, BrowserRuntimeError

browser = ctx.service.get(BROWSER_RUNTIME_SERVICE)
session = await browser.open_session(
    {
        "owner_instance_id": ctx.instance_id,
        "namespace": "hsr",
        "profile_id": user_id,
        "initial_url": "https://sr.mihoyo.com/cloud",
        "headless": False,
        "automation_engine": "m7a",
        "preferences": {
            "profile": {
                "content_settings": {
                    "exceptions": {
                        "keyboard_lock": {
                            "https://sr.mihoyo.com:443,*": {"setting": 1}
                        },
                        "clipboard": {
                            "https://sr.mihoyo.com:443,*": {"setting": 1}
                        },
                    }
                }
            }
        },
    }
)
```

用户完成网页登录后，HSR 调用 `automation_handoff()`。返回值包含三月七附着所需的
调试端口、浏览器/驱动路径、环境变量与 `config_patch`。接管期间 MAS 会话进入
`leased` 状态，禁止另一方同时发送输入：

```python
handoff = await browser.automation_handoff(
    session["session_id"],
    session_token=session["session_token"],
)
try:
    # 仅交给完成 external-owner 适配的 M7A 构建。
    await run_mas_compatible_m7a(handoff)
finally:
    await browser.release_automation_handoff(
        session["session_id"],
        session_token=session["session_token"],
        lease_token=handoff["lease_token"],
    )
    await browser.close_session(
        session["session_id"],
        session_token=session["session_token"],
    )
```

兼容构建必须直接使用 handoff 的 `debugger_address`，不得按共享 driver 路径清理进程，
也不得关闭 `runtime_owns_browser=True` 的浏览器。即使使用兼容构建，HSR 释放租约后仍要
重新读取会话状态，并把外部进程异常视为可恢复状态。

## SRA 兼容状态

SRA 2.16.1 已有独立的云星铁能力，但其 `BrowserOperator` 会自行创建 Edge，并将 Cookie
保存到 SRA 自己的账号 JSON 文件；它没有附着外部 Selenium 会话的入口。现有 MAS HSR
适配器又按 `single <Task>` 为每个任务新建 SRA 进程，非 StartGame 任务不会得到已启动的
browser driver。因此只设置 `general["cloudGame.enabled"] = True` 不能完成这条链路。

浏览器插件允许用 `automation_engine="sra"` 创建会话并取得通用 handoff，但返回值会明确
标记 `compatibility="requires-mas-external-session-build"` 和
`upstream_supported=False`。MAS-compatible SRA 至少需要：

1. 通过 handoff 的 `debugger_address` 附着 MAS 浏览器，而不是调用 `webdriver.Edge()`；
2. 跨 `single` 任务复用同一 BrowserOperator；
3. 已处于 `.game-player` 时跳过登录，不读写 SRA Cookie JSON；
4. external-owner 模式退出时不能关闭 MAS 持有的浏览器。

在这个兼容构建完成前，只能把 SRA 自己的云模式作为独立运行方式，不能宣称它复用了
MAS Browser Profile。仅传 HWND 也无法可靠解决 Chromium 视频截图与输入问题。

云游戏排队、时长检测、DOM 选择器、任务识别和输入策略仍属于 HSR/M7A/SRA 专项层，
通用浏览器插件只负责浏览器、持久登录、会话授权和安全生命周期。
