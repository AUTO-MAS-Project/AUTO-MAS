import { loader } from '@guolao/vue-monaco-editor'
// EditorWorker 本身只是一个 Worker 构造器包装（很轻），保持静态导入
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'

let configurePromise: Promise<void> | null = null

export function configureLocalMonaco(): Promise<void> {
  if (configurePromise) return configurePromise

  configurePromise = import('monaco-editor/esm/vs/editor/editor.main.js')
    .then(monaco => {
      globalThis.MonacoEnvironment = {
        getWorker: () => new EditorWorker(),
      }
      loader.config({ monaco })
    })
    .catch(error => {
      configurePromise = null
      throw error
    })

  return configurePromise
}
