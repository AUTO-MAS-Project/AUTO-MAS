/**
 * 游戏社区帐号的展示与提交数据。
 *
 * 这里全部是纯函数，不依赖 Vue 响应式和后端接口。
 * 提交只用 diffAccountForm：账号组里的凭据是页面加载时的快照，
 * 全量回写会把后台在这期间轮换出的新凭据覆盖回旧值（一次性 refreshToken 尤其致命）。
 */
import type { SignFlowAccountGroupConfig } from '@/api'

/** 账号列表里一个账号组的本地形态：字段全部归一成字符串，便于输入框双向绑定 */
export interface AccountInstance {
  uid: string
  Name: string
  Enabled: boolean
  MiyousheToken: string
  MiyousheDeviceId: string
  MiyousheDeviceFp: string
  CloudGenshinToken: string
  KuroToken: string
  SklandToken: string
  TaygedoToken: string
}

/** 抽屉里可编辑的字段；设备标识由后端写入，界面不展示也不回写 */
export interface AccountForm {
  Name: string
  Enabled: boolean
  MiyousheToken: string
  CloudGenshinToken: string
  KuroToken: string
  SklandToken: string
  TaygedoToken: string
}

export type AccountPatch = Partial<SignFlowAccountGroupConfig>

export const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}

export const asString = (value: unknown): string => (typeof value === 'string' ? value : '')

/** 账号卡片与编辑抽屉里逐项展示的社区凭据，顺序固定；placeholder 是手动粘贴时的提示 */
export const CREDENTIAL_ROWS = [
  {
    field: 'SklandToken',
    label: 'core.signflow.edit.skland',
    placeholder: 'core.signflow.edit.sklandPlaceholder',
  },
  {
    field: 'MiyousheToken',
    label: 'core.signflow.edit.miyoushe',
    placeholder: 'core.signflow.edit.miyoushePlaceholder',
  },
  {
    field: 'CloudGenshinToken',
    label: 'core.signflow.cred.cloudGenshin',
    placeholder: 'core.signflow.edit.miyoushePlaceholder',
  },
  {
    field: 'TaygedoToken',
    label: 'core.signflow.edit.taygedo',
    placeholder: 'core.signflow.edit.taygedoPlaceholder',
  },
  {
    field: 'KuroToken',
    label: 'core.signflow.edit.kuro',
    placeholder: 'core.signflow.edit.kuroPlaceholder',
  },
] as const

export type CredentialField = (typeof CREDENTIAL_ROWS)[number]['field']

/** 账号组里是否有该凭据 */
export const hasCredential = (form: AccountForm, field: CredentialField): boolean =>
  form[field].trim().length > 0

/** 已绑定的社区数量 */
export const credentialCount = (form: AccountForm): number =>
  CREDENTIAL_ROWS.filter(row => hasCredential(form, row.field)).length

const EMPTY_FORM: AccountForm = {
  Name: '',
  Enabled: true,
  MiyousheToken: '',
  CloudGenshinToken: '',
  KuroToken: '',
  SklandToken: '',
  TaygedoToken: '',
}

/** 从后端返回的账号组快照取出本地形态；没有选中账号时返回空表单 */
export const toAccountForm = (account: AccountInstance | null): AccountForm =>
  account
    ? {
        Name: account.Name,
        Enabled: account.Enabled,
        MiyousheToken: account.MiyousheToken,
        CloudGenshinToken: account.CloudGenshinToken,
        KuroToken: account.KuroToken,
        SklandToken: account.SklandToken,
        TaygedoToken: account.TaygedoToken,
      }
    : { ...EMPTY_FORM }

/** 只保留与基线不同的字段；没有改动时返回空对象 */
export const diffAccountForm = (baseline: AccountForm, next: AccountForm): AccountPatch => {
  const patch: AccountPatch = {}
  if (baseline.Name !== next.Name) patch.Name = next.Name
  if (baseline.Enabled !== next.Enabled) patch.Enabled = next.Enabled
  for (const row of CREDENTIAL_ROWS) {
    if (baseline[row.field] !== next[row.field]) patch[row.field] = next[row.field]
  }
  return patch
}
