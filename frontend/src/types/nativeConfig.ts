/** 原生配置描述的通用表单契约；各专项负责转换来源格式。 */
export interface NativeConfigField {
  name: string
  disabled?: boolean
  integer?: boolean
  minimum?: number | null
  maximum?: number | null
  type: 'bool' | 'number' | 'string' | 'select' | 'multi_selection' | 'json'
  options?: string[]
  parent?: string | null
  choices?: string[]
}

export type OkwwPanelKind = 'daily' | 'echo' | 'nightmare' | 'combat' | 'character' | 'monthly'
