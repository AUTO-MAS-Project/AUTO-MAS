// 用 Node 自定义渲染器驱动真实 Vue 客户端模板，无需 DOM。
export default {
  name: 'vue-client',
  viteEnvironment: 'client',
  setup: () => ({ teardown() {} }),
}
