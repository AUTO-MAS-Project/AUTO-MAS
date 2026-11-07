export type ConfigModeOption = {
  value: boolean | string
  title: string
  description: string
  /** 窄容器中保留的关键区别；未提供时继续显示完整说明。 */
  summary?: string
  icon?: 'database' | 'file' | 'setting'
  /** 该选项不可选（如该专项运行时不存在脚本级共享配置）。 */
  disabled?: boolean
  /** 不可选原因；在卡片内显示，窄屏也能读取。 */
  disabledReason?: string
}
