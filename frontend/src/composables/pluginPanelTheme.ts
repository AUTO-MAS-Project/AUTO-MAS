import { shallowRef } from 'vue'

export interface PluginPanelTheme {
  mode: 'dark' | 'light'
  tokens: Record<string, string>
}

export const pluginPanelTheme = shallowRef<PluginPanelTheme>({ mode: 'light', tokens: {} })
