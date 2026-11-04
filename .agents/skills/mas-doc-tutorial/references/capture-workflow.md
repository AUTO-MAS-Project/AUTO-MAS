# 采集约定

从对应版本的 `frontend/e2e/run.mjs`、`frontend/playwright.config.ts`、`frontend/e2e/fixtures.ts` 和目标页面开始，复用现有依赖与启动入口。

正式截图使用目标版本的发布 renderer 或 Electron。浏览器采集在页面启动前接入该版本的 `frontend/src/utils/browserDevElectronAPI.ts`，按源码确认其初始化依赖。

构建注入的后端端口和桥接 HTTP/WebSocket 地址指向同一个隔离后端，前端 preview 使用独立端口。固定语言、时区、主题和窗口尺寸，使用演示数据。

先建立临时采集配置和带 tag 的流程，再从 `frontend/` 调用。下式中的配置与 tag 使用本次实际创建的值：

```text
yarn e2e --config <capture-config.ts> --grep <tutorial-tag>
```

按可见名称或页面语义定位控件，等待对应响应与可观察状态。定时时间按界面时区与 API 序列化约定换算后比较。截图保留必要导航，步骤编号和圈线以目标控件清晰可读为准。

`public/docs/img/<batch>/` 对应站点 `/docs/img/<batch>/`，构建后分别验证图片显示与可点击原图。

本地来源记录包含应用 commit、构建与桥接方式、语言/时区/主题/窗口、运行命令和结果、截图清单及实际验证范围。浏览器配置操作的结果按实际完成的步骤描述。
