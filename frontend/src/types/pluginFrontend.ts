export interface PluginFrontendElementDescriptor {
  frontend_plugin: string
  element_tag: string
  entry_asset_url: string
  style_asset_urls: string[]
  manifest_version: number | null
  dev_frontend_command?: string | null
  dev_frontend_error?: string | null
}

export interface PluginSchemaElementInput {
  scriptId: string
  userId?: string
  scriptConfig: Record<string, unknown>
  modelValue: Record<string, unknown>
  fieldPath?: string
  mode: 'create' | 'edit'
  extensionProps: Record<string, unknown>
}

export interface PluginSchemaFieldChangeDetail {
  path: string
  value: unknown
}

export interface PluginSchemaFormPatchDetail {
  patch: Record<string, unknown>
}
