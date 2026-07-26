// Monaco 及其 Vue 包装约 4.2 MB。任何静态 import 都会让 vendor-monaco 进入
// 应用入口的静态依赖闭包，Vite 会为它写入 modulepreload 与阻塞式 stylesheet，
// 首屏必须先下载解析完整个编辑器。这里全部改为动态 import，让该 chunk 只在
// 真正需要编辑器时才加载。
let configurePromise: Promise<void> | null = null

export function configureLocalMonaco(): Promise<void> {
  if (configurePromise) return configurePromise

  configurePromise = Promise.all([
    import('monaco-editor/esm/vs/editor/editor.main.js'),
    import('@guolao/vue-monaco-editor'),
    import('monaco-editor/esm/vs/editor/editor.worker?worker'),
  ])
    .then(([monaco, { loader }, { default: EditorWorker }]) => {
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
