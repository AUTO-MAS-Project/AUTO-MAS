// 与 vite-plugin-vue-devtools 同步升级，确保与插件注入的 overlay 使用相同事件入口。
type InspectorWindow = Window & { __VUE_INSPECTOR__?: { enabled: boolean; disable: () => void } }

export const cancelVueInspection = (): boolean => {
  const inspector = (window as InspectorWindow).__VUE_INSPECTOR__
  if (!inspector?.enabled) return false
  inspector.disable()
  return true
}

export const openVueDevtools = async (inspect = false) => {
  const { functions, getDevToolsClientUrl } = await import('@vue/devtools-core')
  if (!getDevToolsClientUrl()) return false
  if (inspect) {
    if (!(await functions.checkVueInspectorDetected())) return false
    functions.emit('toggle-panel', false)
    await functions.enableVueInspector()
  } else {
    functions.emit('toggle-panel', true)
  }
  return true
}
