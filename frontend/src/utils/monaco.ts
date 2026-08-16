import { loader } from '@guolao/vue-monaco-editor'
import * as monaco from 'monaco-editor/esm/vs/editor/editor.main.js'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'

export const configureLocalMonaco = () => {
  globalThis.MonacoEnvironment = {
    getWorker: () => new EditorWorker(),
  }
  loader.config({ monaco })
}
