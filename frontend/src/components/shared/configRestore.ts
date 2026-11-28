export interface ConfigRestoreProps {
  /** 弹窗开关（v-model） */
  open: boolean
  /** 配置写入锁定（任务运行中禁用恢复与查看详细） */
  disabled?: boolean
  scriptId?: string
  userId?: string | null
  dirty?: boolean
  /** 脚本名（文案参数化用，如「一条龙」） */
  scriptName: string
  /** 目标池：顺序即 segmented 展示顺序（MAS 在前脚本在后） */
  targets: Array<{ key: string; kind: 'user' | 'script' }>
  /** 后端 API：list/preview/restore（父组件按自身端点包装） */
  api: {
    list: (target: string) => Promise<{
      code?: number
      message?: string
      data?: Array<{ time: string; base?: string | null }>
      /** 当前配置来源（仅三态专项返回；据此比对是否需要跨来源提示） */
      base?: string | null
    }>
    preview: (
      target: string,
      time: string
    ) => Promise<{
      code?: number
      message?: string
      info?: { key: string; value: string }[]
      account?: { key: string; value: string }[]
      tasks?: { app_id: string; app_name: string; enabled: boolean }[]
      instances?: {
        idx: number
        name: string
        active: boolean
        account: { key: string; value: string }[]
        tasks: { app_id: string; app_name: string; enabled: boolean }[]
      }[]
      /** 通用端点把专项载荷包在 data 里；缺省回落到顶层平铺结构 */
      data?: Record<string, unknown> | null
    }>
    restore: (
      target: string,
      time: string,
      force?: boolean
    ) => Promise<{
      code?: number
      message?: string
    }>
    /** 只读读取备份内文本文件（预览「备份文件」点击查看；未提供时点击提示） */
    readFile?: (
      target: string,
      time: string,
      path: string
    ) => Promise<{
      code?: number
      message?: string
      path?: string
      size?: number
      content?: string
    }>
  }
  /** 预览字段标签映射（key → 展示标题） */
  fieldLabels?: Record<string, string>
  /** 描述文案覆写（缺省用 i18n 通用词条；专项的归档时机措辞不同时传入） */
  userDesc?: string
  scriptDesc?: string
  /** 预览字段值格式化（枚举值转词表文案） */
  formatValue?: (key: string, raw: string) => string
  /** 恢复后回调（一键恢复成功后通知父组件刷新表单等） */
  onRestored?: (target: string, item: { time: string }) => void | Promise<void>
  /** 查看详细配置回调（父组件执行恢复 + 拉起脚本查看会话）。
      第三个参数为当前配置来源（仅三态专项非空），供专项比对跨来源并追加提示。
      返回 ``Promise<boolean>``（true=已恢复）——组件据此决定预览弹窗是否关闭，
      取消/失败保持预览打开。 */
  onDetail?: (
    target: string,
    item: { time: string; base?: string | null },
    currentMode?: string | null
  ) => Promise<boolean>
}

export interface BackupItem {
  time: string
  /** 备份时点的配置来源（shared/independent/native）；无标注为 null */
  base?: string | null
}

export interface BackupFileItem {
  path: string
  size: number
}

export const formatBackupTime = (ts: string) =>
  `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)} ${ts.slice(9, 11)}:${ts.slice(11, 13)}:${ts.slice(13, 15)}`

// 用户级摘要展示顺序：基本信息（信息字段 + 账号字段）→ 任务配置
export function backupSummaryRows(
  data: Pick<Awaited<ReturnType<ConfigRestoreProps['api']['preview']>>, 'info' | 'account'>,
  formatValue: (key: string, raw: string) => string,
  t: (key: string) => string
) {
  const info = new Map((data.info ?? []).map(f => [f.key, f.value]))
  const account = new Map((data.account ?? []).map(f => [f.key, f.value]))
  const rows: { label: string; value: string }[] = []
  const order: Array<{ key: string; label: string; src: 'info' | 'account' }> = [
    { key: 'name', label: t('core.edit.username'), src: 'info' },
    { key: 'status', label: t('core.edit.enabled'), src: 'info' },
    { key: 'base', label: t('core.edit.configRestorePreviewMode'), src: 'info' },
    { key: 'launcher_mode', label: t('core.edit.configRestorePreviewLauncher'), src: 'info' },
    { key: 'game_region', label: t('core.edit.configRestorePreviewRegion'), src: 'account' },
    { key: 'game_path', label: t('core.edit.configRestorePreviewGamePath'), src: 'account' },
    { key: 'game_language', label: t('core.edit.configRestorePreviewLanguage'), src: 'account' },
    { key: 'account', label: t('core.edit.configRestorePreviewAccount'), src: 'account' },
    { key: 'password', label: t('core.edit.configRestorePreviewPassword'), src: 'account' },
    {
      key: 'bilibili_account_name',
      label: t('core.edit.configRestorePreviewBilibili'),
      src: 'account',
    },
    {
      key: 'use_custom_win_title',
      label: t('core.edit.configRestorePreviewUseCustomWinTitle'),
      src: 'account',
    },
    {
      key: 'custom_win_title',
      label: t('core.edit.configRestorePreviewCustomWinTitle'),
      src: 'account',
    },
    { key: 'remained_day', label: t('core.edit.daysLeft'), src: 'info' },
    { key: 'notes', label: t('core.edit.note'), src: 'info' },
    { key: 'push_log_mode', label: t('core.edit.collectNodeDetails'), src: 'info' },
  ]
  for (const spec of order) {
    const raw = spec.src === 'info' ? info.get(spec.key) : account.get(spec.key)
    if (raw === undefined) continue
    rows.push({ label: spec.label, value: formatValue(spec.key, raw) })
  }
  return rows
}

export const formatFileSize = (size: number): string => {
  if (!Number.isFinite(size) || size < 0) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}
