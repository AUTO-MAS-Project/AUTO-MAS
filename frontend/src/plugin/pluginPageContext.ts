export interface PluginPageContext {
  pageId: string
  path: string
  title: string
  renderer: string
  source: string
  pluginId: string | null
  elementTag: string | null
}

let currentPageContext: PluginPageContext | null = null

export function setPluginPageContext(context: PluginPageContext | null): void {
  currentPageContext = context
}

export function getPluginPageContext(): PluginPageContext | null {
  return currentPageContext
}
