# 采集约定

从对应版本的 `frontend/e2e/run.mjs`、`frontend/playwright.config.ts`、`frontend/e2e/fixtures.ts` 和目标页面开始，复用现有依赖与启动入口。

正式截图使用目标版本的发布 renderer 或 Electron。浏览器采集在页面启动前接入该版本的 `frontend/src/utils/browserDevElectronAPI.ts`，按源码确认其初始化依赖。

构建注入的后端端口和桥接 HTTP/WebSocket 地址指向同一个隔离后端，前端 preview 使用独立端口。固定语言、时区、主题和窗口尺寸，使用演示数据。

先建立临时采集配置和带 tag 的流程，再从 `frontend/` 调用。下式中的配置与 tag 使用本次实际创建的值：

```text
yarn e2e --config <capture-config.ts> --grep <tutorial-tag>
```

按可见名称或页面语义定位控件，等待对应响应与可观察状态。定时时间按界面时区与 API 序列化约定换算后比较。

## 截图标注与验收

采集前确定本图对应的正文步骤和目标。一图突出一个小步骤，或少量紧密相关的动作；焦点分散时拆图，每张主图仍保留完整窗口参照。正文写出从导航到目标分组的路径，图中编号与相邻正文步骤对应。仅展示结果时，给经断言确认的结果加编号和框线，图注说明这是查看项。

使用正常桌面窗口尺寸，保留尽可能完整的应用界面，让读者看到导航、当前页标题和页签、目标所在分组及相邻区域。弹窗和下拉菜单保留父页面背景及入口关系。目标在下方时先滚动到所在分组，再保留当前窗口的导航和标题。主图只裁去应用外部的无关区域；独立按钮或开关的小图无法承担定位指引。

先让目标进入视口，等待动画结束、布局稳定，再用本次流程的语义 locator 获取实际边界，例如调用 `boundingBox()`。截图前在 DOM 中绘制临时框线与步骤编号，框选目标控件或其带标签的所在行，编号放在附近空白处，必要时用连线明确指向。标注不遮挡文字、控件或定位参照。可用 `position: fixed` 对齐视口坐标、`pointer-events: none` 避免拦截操作。滚动或布局变化后重新取边界，在 `finally` 中移除标注。只叠加教学标记，保留真实 UI 与状态，不用 AI 重绘或补造控件、文本和结果。

先验收位置：仅凭主图和相邻正文，能否指出当前页面、目标所属区域以及相对导航的位置。再验收操作：框线指向明确、编号清晰，与正文动作或查看项一致。以文档实际桌面和窄屏显示检查这两点；需要辨认细小文字时，在完整主图之后补充带相同编号的局部放大图，并保留原图链接。完整主图始终承担定位作用，不以收紧裁切或缩窄采集视口重排桌面界面来换取文字大小。

`public/docs/img/<batch>/` 对应站点 `/docs/img/<batch>/`，构建后分别验证图片显示与可点击原图。

本地来源记录包含应用 commit、构建与桥接方式、语言/时区/主题/窗口、运行命令和结果、截图清单及实际验证范围。浏览器配置操作的结果按实际完成的步骤描述。

## 指引依据

- [GitHub：Creating screenshots](https://docs.github.com/en/contributing/writing-for-github-docs/creating-screenshots)：周边上下文应帮助读者在自己的界面中找到目标，正文提供完整操作说明。
- [ScreenSteps：Getting the Size Right](https://blog.screensteps.com/adding-screen-captures-to-software-documentation-getting-the-size-right)：只截按钮会丢失位置参照，界面边缘和相邻元素有助于定位。

本项目采用接近完整应用窗口的主图，是用户明确的教程要求；上述来源支持保留定位上下文，并非都要求所有截图完整全屏。
