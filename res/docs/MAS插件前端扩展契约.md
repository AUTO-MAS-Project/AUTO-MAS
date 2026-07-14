# MAS 插件前端扩展契约

> 版本：v1  
> 生效日期：2026-07-14  
> 适用范围：Script Adapter 在通用 SchemaForm 中追加插件 custom element

## 1. 目标与边界

本契约允许 Script Adapter 在 `script_schema` 或 `user_schema` 的指定位置插入插件提供的 custom element。宿主继续负责通用编辑页、配置加载、校验入口和最终保存；插件组件负责脚本领域内的复杂编辑区域。

当前版本只支持追加 Schema 组件，不支持通过 Adapter 接管完整编辑页面。插件已有的独立 `pages` 能力保持不变，但不属于本契约。

核心原则：

- 组件位置由 Schema 分组与字段顺序决定，宿主不得按插件名或 ScriptType 添加分支；
- custom element 是非持久化 Schema 节点，不得产生虚构配置字段；
- 插件归属来自 Adapter 注册时已有的 `PluginContext`，插件不重复声明 package ID；
- 对象通过 DOM property 传递，不序列化到 HTML attribute；
- 插件只更新当前表单，最终保存仍由通用编辑页执行；
- 组件加载失败不得清空表单或阻止其他字段编辑和保存。

## 2. Adapter 声明

推荐使用 `script_groups` / `user_groups` 中的 `PluginField.plugin_element`：

```python
from app.plugins import PluginField, ScriptAdapterDefinition

definition = ScriptAdapterDefinition(
    type_key="ExampleSchemaElement",
    display_name="Schema 组件示例",
    hooks_factory=ExampleHooks,
    script_groups=[
        PluginField.group(
            "Info",
            "脚本信息",
            [PluginField.string("Name", "脚本名称", "Schema 组件示例")],
        )
    ],
    user_groups=[
        PluginField.group(
            "Info",
            "用户信息",
            [PluginField.string("Name", "用户名称", "新用户")],
        ),
        PluginField.group(
            "Task",
            "任务配置",
            [
                PluginField.string(
                    "SelectedPreset",
                    "当前预设",
                    "",
                    hidden=True,
                ),
                PluginField.json(
                    "TaskSnapshot",
                    "任务快照",
                    "{ }",
                    hidden=True,
                ),
                PluginField.plugin_element(
                    "TaskEditor",
                    "schema-plugin-element-example",
                    size="1/1",
                    props={"title": "任务队列示例"},
                )
            ],
        ),
    ],
)
```

声明生成的 Schema 节点语义如下：

```ts
interface PluginSchemaElementDefinition {
  type: "plugin-element";
  frontend_element: string;
  frontend_extension: PluginFrontendElementDescriptor;
  props?: Record<string, unknown>;
  size?: SchemaFieldSize;
  persisted: false;
}
```

`plugin_element` 的 `name` 只用于生成稳定的 Schema 路径和渲染 key，不会生成 `ConfigItem`，也不会写入最终配置。组件通过事件更新的目标路径必须对应 Adapter 中真实声明的持久化字段；不需要由 SchemaForm 重复渲染的字段可以声明为 `hidden=True`。

## 3. frontend manifest

插件 Python package 必须携带 `frontend/manifest.json`：

```json
{
  "version": 1,
  "renderer": "custom-element",
  "entry": "frontend/index.js",
  "style": ["frontend/index.css"],
  "elements": [
    {
      "tag": "schema-plugin-element-example"
    }
  ]
}
```

约束：

- `entry` 和 `style` 必须位于当前插件 package 的 `frontend/` 目录；
- 路径不得包含空段、`.` 或 `..`，不得逃逸插件 package；
- `frontend_element` 必须出现在 `elements[].tag` 中；
- 生产资源必须存在，资源 URL 由宿主生成；
- 同一 custom element tag 应保持全局唯一，建议使用插件名作为前缀；
- 不允许通过生产 manifest 加载任意远程脚本。

Adapter provider 构建时，宿主使用 `plugin_context.plugin_name` 查找当前插件资源并完成上述校验。插件无需调用 `ctx` 注册前端组件，也不存在页面与 Adapter 的注册顺序要求。

## 4. 输入 property

custom element 注册完成后，宿主通过 DOM property 注入：

```ts
interface PluginSchemaElementInput {
  scriptId: string;
  userId?: string;
  scriptConfig: Record<string, unknown>;
  modelValue: Record<string, unknown>;
  fieldPath?: string;
  mode: "create" | "edit";
  extensionProps: Record<string, unknown>;
}
```

| Property         | 说明                                                       |
| ---------------- | ---------------------------------------------------------- |
| `scriptId`       | 当前脚本 ID                                                |
| `userId`         | 用户编辑时的用户 ID；脚本编辑时为空                        |
| `scriptConfig`   | 当前脚本配置；脚本编辑页中与 `modelValue` 指向同一业务配置 |
| `modelValue`     | 当前通用表单的完整配置快照                                 |
| `fieldPath`      | 当前非持久化 Schema 节点路径，例如 `Task.TaskEditor`       |
| `mode`           | 创建或编辑模式                                             |
| `extensionProps` | Adapter 声明中的 `props`                                   |

插件不得修改收到的对象引用。需要更新表单时必须派发标准事件，并在 property setter 中避免反向派发事件形成响应式循环。

## 5. 输出事件

### 5.1 单字段更新

```ts
element.dispatchEvent(
  new CustomEvent("field-change", {
    detail: {
      path: "Task.SelectedPreset",
      value: "Daily",
    },
    bubbles: true,
    composed: true,
  }),
);
```

Payload：

```ts
interface PluginSchemaFieldChangeDetail {
  path: string;
  value: unknown;
}
```

`path` 是相对于表单根节点的点分路径，不是相对于 `fieldPath` 的路径。

目标路径必须对应 Adapter 的真实配置字段。宿主保存时会通过 Adapter 配置模型重新构造数据，未声明字段不会成为可依赖的持久化配置。

### 5.2 跨字段更新

```ts
element.dispatchEvent(
  new CustomEvent("form-patch", {
    detail: {
      patch: {
        Info: { Controller: "Desktop" },
        Task: {
          SelectedPreset: "Daily",
          TaskSnapshot: '{"taskOrder":["Daily"]}',
        },
      },
    },
    bubbles: true,
    composed: true,
  }),
);
```

Payload：

```ts
interface PluginSchemaFormPatchDetail {
  patch: Record<string, unknown>;
}
```

宿主对普通对象执行递归合并，对数组、标量和 `null` 执行整体替换。Patch 未出现的兄弟字段保持不变。

## 6. 保存与生命周期

- `field-change` 和 `form-patch` 只更新通用页内存中的表单模型；
- 插件组件不得直接调用脚本或用户保存接口；
- 用户点击通用页“保存配置”后，宿主统一校验并持久化完整表单；
- 宿主配置刷新后会重新同步所有输入 property；
- 组件卸载时宿主移除事件监听；
- JS/CSS 加载失败时宿主显示错误和重试入口，当前表单模型保持不变；
- 插件组件内部的请求、订阅和定时器必须在 `disconnectedCallback` 或组件卸载钩子中清理。

## 7. 调用插件后端

复杂编辑组件可以通过全局插件 API 调用当前 AUTO-MAS 后端：

```ts
const result = await window.pluginAPI.call("example/interface/preview", {
  scriptId: this.scriptId,
});
```

不以 `/` 开头的路径会映射到 `/plugin/<path>`，应由插件通过 `ctx.server.http(...)` 注册。以 `/` 开头的路径用于调用宿主公共 API；脚本领域接口优先放在插件自己的 `/plugin/` 命名空间，避免主程序硬绑定插件业务。

组件订阅 WebSocket 后必须保存并调用取消函数：

```ts
const unsubscribe = window.pluginAPI.subscribe("topic-id", (message) => {
  // 更新插件内部状态
});

// disconnectedCallback / onBeforeUnmount
unsubscribe();
```

## 8. 开发模式

设置 `AUTO_MAS_DEV=1` 后，可以在插件源码根目录提供 `frontend-src/plugin.frontend.dev.json`：

```json
{
  "version": 0,
  "renderer": "custom-element",
  "entry_url": "http://localhost:5174/src/main.ts",
  "style_urls": [],
  "elements": [
    {
      "tag": "schema-plugin-element-example"
    }
  ],
  "command": "npm run dev"
}
```

`entry_url` 和 `style_urls` 仅允许 `localhost`、`127.0.0.1` 或 `::1`。也可以使用不含 `.` / `..` 的相对 `entry`，由宿主生成 Vite `/@fs/` 地址。

## 9. 打包要求

构建产物和 manifest 必须作为 Python package data 进入 wheel：

```toml
[tool.setuptools.package-data]
schema_plugin_element_example = [
  "frontend/*.json",
  "frontend/*.js",
  "frontend/*.css",
]
```

插件前端不得：

- 从 `../../../frontend/src` 导入宿主源码；
- 复制宿主业务组件的构建产物；
- 依赖具体宿主路由或手工解析 `window.location.pathname`；
- 在主程序中新增插件名、ScriptType、element tag 或业务字段判断；
- 将 `TaskEditor` 等非持久化节点写入配置。