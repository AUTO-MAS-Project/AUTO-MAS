/** 启动过程里展示给用户的一段进度。 */
export interface LaunchStep {
  /** 词表 key 与 aria 用的稳定标识。 */
  key: string
  /** 已经翻译好的段名，例如「程序文件」。 */
  label: string
  state: 'done' | 'current' | 'todo'
}
