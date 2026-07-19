import { loader } from '@guolao/vue-monaco-editor'
// EditorWorker 本身只是一个 Worker 构造器包装（很轻），保持静态导入
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'

let _configured = false

/**
 * 懒加载配置 Monaco Editor。
 * 调用方无需 await —— 在后台加载 monaco 主包（约 3MB），
 * 在用户打开任何编辑器之前必然已完成。
 */
export async function configureLocalMonaco(): Promise<void> {
  if (_configured) return
  _configured = true
  // 动态 import：不阻塞 createApp，与 Vue 首屏渲染并行
  const monaco = await import('monaco-editor/esm/vs/editor/editor.main.js')
  globalThis.MonacoEnvironment = {
    getWorker: () => new EditorWorker(),
  }
  loader.config({ monaco })
}
