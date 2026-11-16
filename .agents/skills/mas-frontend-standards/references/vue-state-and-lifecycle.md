# Vue 状态与生命周期

用于组件职责调整、动态输入、组件双向绑定、异步读取和路由复用。只读取与当前改动相关的部分；现有生成客户端、页面业务流程和测试边界仍按主 Skill 执行。

## 职责与状态归属

- 按共同维护的业务约束划分组件或 composable，把相关状态、操作和清理放在同一所有者中。只有一个调用者不妨碍提取有实质职责的单元；简单开关或单个草稿不因此需要单独提取。
- 页面协调跨能力的业务顺序，各单元只暴露消费者需要的状态和操作。拆分后仍需传递大部分内部 ref、整套 controller 或相互回调时，先重新判断状态归属。
- 同一次共享流程应使用同一个实例；分别调用有状态的 composable 通常会创建独立状态。需要多层后代共享、而中间层只负责转发时，可在最近的所有者按实例提供带 `InjectionKey` 的上下文，暴露只读状态和明确操作；缺少必需 provider 时不要静默创建另一份状态。
- 组件优先通过类型明确的 props/emits 通信；命令式组件 ref 只暴露必要的 `defineExpose` 操作，不让父组件读取子组件私有表单或 DOM 状态。

## 响应式选择与动态输入

- 按更新方式选择 `ref`、`reactive` 或 `shallowRef`。需要嵌套编辑的表单保留深层响应；外部实例、不应代理的对象或整体替换的大型数据可用 `shallowRef`，必要时用 `markRaw`。不要仅因值是基本类型就强制替换现有 `ref`。
- 派生值用无副作用的 `computed`；过滤、排序不得原地改变源集合。普通 `reactive` 属性解构可能丢失后续替换的响应性，按需使用属性访问、getter 或 `toRefs`。Pinia 状态和 getter 解构用 `storeToRefs`，action 可直接解构。
- Vue 3.5 的 `<script setup>` 支持直接解构 `defineProps()` 并保留同一块内访问的响应性；将其传给 watcher 或 composable 时仍要传 getter，例如 `watch(() => id, ...)`，不能把当前值当成响应式来源。保留可用的 `props.id` / `withDefaults` 写法，不为语法统一做批量迁移。
- 只有需要跟随输入变化的可复用入口才接受 `MaybeRefOrGetter<T>`。在 `computed` / `watchEffect` 的跟踪范围内调用 `toValue`；命令式操作则在每次调用时解析当前值，避免捕获新建用户时的空 ID。回调函数本身是值时，不把它当 getter 交给 `toValue`。

## 组件模型与模板 ref

- 新增真正的双向组件契约时可用类型明确的 `defineModel`；保留现有可用的 props/emits 契约。父组件未传值而子组件单独设默认值时，核对双方的初始值是否一致。
- 对象模型的嵌套赋值可能通过共享引用改变父状态，却不会因此触发 `update:modelValue`。若保存、校验或防抖依赖更新事件，要通过替换模型值或明确操作履行该契约；不要把所有嵌套编辑判成失去响应性，也不要直接套用深克隆。
- Vue 3.5 可用 `useTemplateRef` 表达 DOM/组件引用；现有带类型的 `ref` 仍可沿用。首次挂载前和 `v-if` 卸载后均可能为空；读取更新后的 DOM 时按需等待 `nextTick` 或使用 `flush: 'post'`。

## 异步读取与副作用

- 搜索、选项或详情读取随输入变化时，旧任务失效后不得再写当前的 data、error 或 loading，包括 `catch` / `finally`。按实际客户端能力取消旧请求，不能取消时用任务标记或序号忽略旧结果；取消请求也不能替代结果归属检查。
- 在发起异步操作前注册清理。`onWatcherCleanup` 要在 watcher 的同步阶段、首次 `await` 前调用；第三参数 `onCleanup` 绑定 watcher，可用于清理当前轮次。`watchEffect` 只跟踪首次 `await` 前访问的依赖。
- 同步在 setup 中创建 watcher；在定时器、Promise 回调或异步生命周期回调恢复后创建的 watcher，不要假定会随组件自动停止。优先同步创建并在内部判断就绪状态；确需动态创建时，由所属 scope 保存并停止它，且防止卸载后再创建。
- 定时器、DOM 监听器、Electron/事件总线订阅和独立 effect scope 随所有者清理。缓存页面还要确认停用时是否继续工作，按业务需要处理激活和停用；不要把停用等同于卸载。
- **区分读取失效与写入完成。** 页面卸载不代表已排队的保存应被丢弃。核对所属保存队列的排空、回滚和离开拦截契约，不能把“清理旧读取”的策略套到保存、归档或恢复操作，也不能只用 Promise 超时释放仍可能写入的任务。

## 路由参数变化

- 同一路由组件从一个脚本或用户切换到另一个时，可能复用实例；只在 `onMounted` 中读取一次 ID 不足以处理该变化。监听实际依赖的 params/query 或使用 `onBeforeRouteUpdate`，并覆盖初次加载；路由级 `beforeEnter` 不负责同一记录内的参数变化。
- 切换前明确草稿保留、保存等待和离开确认语义，切换后的读取也要遵守旧结果失效规则。不要为了刷新数据给全局 `RouterView` 增加 `route.fullPath` key，连带销毁无关页面状态。

## 按改动选择验证

- 读取竞态用受控 Promise 验证“先发请求后完成”，确认旧结果、旧错误及旧 `finally` 不改变当前状态；同时覆盖输入清空或卸载。
- 副作用验证连续挂载/卸载后没有遗留订阅、计时器或卸载后创建的 watcher；带缓存的页面另外核对停用行为。
- 参数变化验证同组件内切换实际使用的新 ID，并保持草稿与待保存任务的既有语义；模型变化验证父状态和依赖更新事件的操作均符合契约。
- 沿用[前端测试保留边界](../../../../frontend/TESTING.md)和 [MAS E2E](../../mas-e2e/SKILL.md)，不为这些规则增加永久测试矩阵或测试依赖。

## 来源与许可

参考并按 MAS 约束改写自 vuejs-ai/skills，提交 f5d4b3b869bb8a86ddfea148196f7db64aeefeab，含 vue-best-practices 19.0.1。第三方部分按以下 MIT 许可使用；来源按本目录要求保留纯文本署名。

```text
MIT License

Copyright (c) 2025 hyf0, SerKo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
