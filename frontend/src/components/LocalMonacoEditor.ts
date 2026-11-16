import { defineAsyncComponent } from 'vue'
import { configureLocalMonaco } from '@/utils/monaco'

// 先完成本地配置再挂载编辑器，避免冷启动时使用默认 CDN。
export default defineAsyncComponent(async () => {
  await configureLocalMonaco()
  return (await import('@guolao/vue-monaco-editor')).VueMonacoEditor
})
