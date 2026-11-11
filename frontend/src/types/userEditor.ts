/** 账号卡片标题的展示信息；保存状态仍由页面持有。 */
export interface UserAccountHeadingOptions {
  isEdit: boolean
  logoSrc: string
  saveStatus?: 'idle' | 'saving' | 'saved' | 'error'
  saveErrorMessage?: string
  onIconError?: (event: Event) => void
}
