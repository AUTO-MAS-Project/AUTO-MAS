import type { BuiltinScriptType } from '@/types/script'
import type { RouteLocationRaw } from 'vue-router'

/** 账号卡片标题的展示信息；保存状态仍由页面持有。 */
export interface UserAccountHeadingOptions {
  isEdit: boolean
  logoSrc: string
  saveStatus?: 'idle' | 'saving' | 'saved' | 'error'
  saveErrorMessage?: string
  onIconError?: (event: Event) => void
}

export interface UserEditHeaderProps {
  /** 所属脚本 ID，用于第二级面包屑跳回脚本编辑页 */
  scriptId: string
  /** 脚本名称，显示在第二级面包屑 */
  scriptName: string
  /** true 为编辑已有用户，false 为新增用户 */
  isEdit: boolean
  scriptType: BuiltinScriptType
  /** 脚本页命名路由；提供时优先于专项默认路由 */
  scriptRoute?: RouteLocationRaw
  /** 配置按钮文字，省略则不渲染配置按钮 */
  configLabel?: string
  /** 配置按钮 loading 态 */
  configLoading?: boolean
  /** 配置进行中，改为显示不可点击的「正在配置」 */
  configActive?: boolean
  /** 配置按钮禁用态 */
  configDisabled?: boolean
  /** 是否展示配置按钮，用于「简洁」模式下整体隐藏 */
  configVisible?: boolean
  /** 当前用户 ID，编辑已有用户时提供，用于渲染「配置文件夹」按钮 */
  userId?: string
  /** 返回按钮 loading 态，用于离开前等待保存或确认 */
  cancelLoading?: boolean
  /** 操作按钮尺寸，默认标准尺寸 */
  buttonSize?: 'small' | 'middle' | 'large'
  /** 操作按钮间距，默认中等 */
  actionsSize?: 'small' | 'middle' | 'large'
  userName: string
  logoSrc?: string
  onIconError?: (event: Event) => void
}
