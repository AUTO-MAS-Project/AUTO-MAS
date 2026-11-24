# 桌宠动画图集

独立桌宠和主题附带桌宠共用 `mascot.animation`。每个动作支持 2 到 120 帧，播放帧率仍由包内的
`idleFps`、`workingFps` 或用户设置的自定义 FPS 决定，范围为 1 到 120。

```json
{
  "path": "assets/animation.png",
  "columns": 12,
  "frameCount": 120,
  "idleFps": 30,
  "workingFps": 60,
  "resultPath": "assets/results.png",
  "dragPath": "assets/drag.png"
}
```

- `columns`：每行格数，2 到 120 的整数。
- `frameCount`：每个动作的实际帧数，不小于 `columns`，最多 120；省略时等于 `columns`，旧包无需修改。
- 每个动作占 `ceil(frameCount / columns)` 行，从左到右、从上到下排列；末行未用的格子留空，不参与播放或鼠标命中。
- 主图集先完整排列待机动作，再排列工作动作；结果图集先失败、后成功；拖拽图集只含一个动作。各图集共用列数和帧数。
- `lookPath` 继续使用固定的 3×3 静态视线图，不受 `frameCount` 影响。

上例每个动作占 10 行。每格 256×256 像素时，主图集和结果图集各为 3072×5120，拖拽图集为
3072×2560。保留原有资源限制：图片宽高各不超过 8192 像素，单文件不超过 8 MiB，ZIP 不超过
16 MiB，解压后总大小不超过 32 MiB。
