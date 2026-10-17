# 桌宠菜单协议 v1

桌宠包提供声明式菜单 UI，宿主提供能力和当前状态。菜单通过独立入口渲染，不加载主界面的业务模块。

在 `mascot.json` 的 `mascot` 中添加 `menu`。主题包附带桌宠使用相同字段；旧包未声明时使用默认菜单。示例中的图片位于 ZIP 内的 `assets/pet.png`：

```json
{
  "formatVersion": 1,
  "id": "my-pet",
  "name": "我的桌宠",
  "mascot": {
    "path": "assets/pet.png",
    "menu": {
      "protocolVersion": 1,
      "layout": "grid",
      "items": [
        { "capability": "idle.refresh", "icon": "↻" },
        { "capability": "task.start", "icon": "▶" },
        { "separator": true },
        { "capability": "task.stop", "icon": "■" },
        { "capability": "animation.toggle", "icon": "☆" },
        { "capability": "idle.toggle" }
      ],
      "style": {
        "width": 320,
        "radius": 16,
        "fontSize": 14,
        "itemHeight": 48,
        "background": "#15243b",
        "text": "#eef6ff",
        "border": "#365072",
        "accent": "#81bbff"
      }
    }
  }
}
```

- `protocolVersion`：当前为 `1`，不支持的版本会拒绝导入。
- `layout`：`list`（默认）或双列 `grid`。
- `items`：1–24 项，至少一项能力；顺序即显示顺序，能力不可重复。`icon` 是最多 8 个字符的文本。未知能力显示为不可用，不能执行。
- `style` 可省略，缺少的配色与圆角跟随宿主当前主题；包内显式声明的字段优先。默认宽度 180、字号 13、行高 32。`width` 范围 160–480，`radius` 为 0–32，`fontSize` 为 12–20，`itemHeight` 为 32–64；颜色为 `#RRGGBB` 或 `#RRGGBBAA`。弹层大小会适应屏幕，长列表可滚动。

## 宿主能力

| 标识 | 行为 |
| --- | --- |
| `task.start` | 获取配置任务选项，按选项值快速启动 AutoProxy |
| `task.stop` | 获取正在运行的实例选项，中止对应实例，排除脚本配置会话 |
| `idle.refresh` | 刷新与首页共用的留言；暂停留言或工作中不可用 |
| `idle.toggle` | 暂停或恢复待机留言 |
| `animation.toggle` | 暂停或恢复动画，兼容系统减少动态效果偏好 |

业务文案、任务名称、选项值、可用状态及执行结果由宿主提供，包只提供表现。任务服务离线不会禁用本地留言和动画能力。

## 双向交互与生命周期

菜单入口只使用 `DesktopMascotMenuAPI`：`getData()` 获取菜单及能力快照，`onChanged()` 接收更新，`execute({ capability, value? })` 请求操作并取得 `{ success, message? }`，`close()` 关闭。

包内无需编写 JavaScript。菜单只显示声明的能力；宿主只执行已声明、受支持且当前可用的能力，动态选项值必须来自宿主。打开期间任务/连接状态改变会更新可用性，执行时再次检查。操作请求成功表示宿主已受理，任务最终结果继续走原有任务事件。

Esc 或失焦关闭菜单；方向键、Home/End 和 Tab 可导航。切换包、禁用桌宠、主窗口重建或退出时关闭弹层并使旧请求失效，销毁时释放监听与 IPC。卸载桌宠不会销毁 MAS 共享连接或任务状态。
