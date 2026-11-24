import { describe, expect, it } from 'vite-plus/test'
import {
  CREDENTIAL_ROWS,
  credentialCount,
  diffAccountForm,
  hasCredential,
  toAccountForm,
  type AccountForm,
  type AccountInstance,
} from './gameSignAccounts'

const baseForm: AccountForm = {
  Name: '主号',
  Enabled: true,
  MiyousheToken: 'miyoushe-cookie',
  CloudGenshinToken: 'combo-token',
  KuroToken: 'kuro-token',
  SklandToken: 'skland-token',
  TaygedoToken: 'taygedo-token',
}

const account: AccountInstance = {
  uid: '8e472fe6',
  ...baseForm,
  MiyousheDeviceId: 'device-id',
  MiyousheDeviceFp: 'device-fp',
}

describe('toAccountForm', () => {
  it('只带出抽屉可编辑的字段，设备标识不进表单', () => {
    const form = toAccountForm(account)

    expect(form).toEqual(baseForm)
    expect(Object.keys(form)).not.toContain('MiyousheDeviceId')
    expect(Object.keys(form)).not.toContain('MiyousheDeviceFp')
  })

  it('没有选中账号时返回空表单，名称留空由调用方决定默认值', () => {
    expect(toAccountForm(null)).toEqual({
      Name: '',
      Enabled: true,
      MiyousheToken: '',
      CloudGenshinToken: '',
      KuroToken: '',
      SklandToken: '',
      TaygedoToken: '',
    })
  })
})

describe('diffAccountForm', () => {
  it('没有改动时不产生补丁，调用方据此跳过请求', () => {
    expect(diffAccountForm(baseForm, { ...baseForm })).toEqual({})
  })

  it('只返回改动过的凭据，未改动的字段不回写', () => {
    const next: AccountForm = { ...baseForm, KuroToken: 'kuro-token-new' }

    expect(diffAccountForm(baseForm, next)).toEqual({ KuroToken: 'kuro-token-new' })
  })

  it('清空凭据会产生空字符串字段，而不是被当成无改动丢掉', () => {
    const next: AccountForm = { ...baseForm, TaygedoToken: '' }

    expect(diffAccountForm(baseForm, next)).toEqual({ TaygedoToken: '' })
  })

  it('名称与启用状态各自独立提交', () => {
    const next: AccountForm = { ...baseForm, Name: '副号', Enabled: false }

    expect(diffAccountForm(baseForm, next)).toEqual({ Name: '副号', Enabled: false })
  })
})

describe('凭据计数', () => {
  it('按去掉空白后的内容判断是否已绑定', () => {
    expect(hasCredential({ ...baseForm, KuroToken: '   ' }, 'KuroToken')).toBe(false)
    expect(hasCredential(baseForm, 'KuroToken')).toBe(true)
  })

  it('统计覆盖全部社区凭据行', () => {
    expect(credentialCount(baseForm)).toBe(CREDENTIAL_ROWS.length)

    const cleared: AccountForm = { ...baseForm, MiyousheToken: '', CloudGenshinToken: '' }
    expect(credentialCount(cleared)).toBe(CREDENTIAL_ROWS.length - 2)
  })
})
