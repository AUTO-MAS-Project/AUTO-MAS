import type { GlobalConfig } from '@/api'

export type SettingChangeHandler = <
  Category extends keyof GlobalConfig,
  Key extends keyof NonNullable<GlobalConfig[Category]> & string,
>(
  category: Category,
  key: Key,
  value: NonNullable<GlobalConfig[Category]>[Key]
) => Promise<boolean>

// 通知字段由后端描述表提供，静态字段不使用这条动态边界。
export type DynamicSettingChangeHandler = (
  category: keyof GlobalConfig,
  key: string,
  value: unknown
) => Promise<boolean>
