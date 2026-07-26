import { describe, expect, it } from 'vitest'
import type { SchemaDefinition, SchemaFieldDefinition } from '@/types/schemaForm'
import {
  SENSITIVE_PLACEHOLDER,
  SENSITIVE_CLEARED_PLACEHOLDER,
  isSensitiveField,
  getSensitiveDisplayValue,
  sanitizeFieldValueForLog,
  sanitizeModelForLog,
  sanitizeErrorForLog,
  resolveSensitiveSaveIntent,
  applySensitiveIntentToPatch,
  buildSensitiveSavePatch,
  buildSchemaSavePayload,
  hasSensitiveDirtyChange,
  isSensitiveFieldCleared,
  getSensitivePlaceholder,
  collectSensitiveFieldPaths,
  assertNoSensitiveLeak,
} from './useSensitiveFieldStrategy'

// ============================================================
// 真实 schema fixtures（与后端 Pydantic 声明一一对应，禁止硬编码自证）
// ============================================================

const field = (overrides: Partial<SchemaFieldDefinition> = {}): SchemaFieldDefinition => ({
  type: 'string',
  ...overrides,
})

/**
 * HSR 用户配置 schema（来源：build/w/b2/automas_script_hsr/source/src/automas_script_hsr/schema.py）
 *
 * 真实敏感字段：
 * - SRA.Id: format='password', sensitive=True
 * - SRA.Password: format='password', sensitive=True
 * - Notify.ServerChanKey: sensitive=True（无 format=password）
 */
const hsrUserSchema: SchemaDefinition = {
  groups: [
    {
      key: 'Info',
      label: '基础信息',
      fields: [
        field({ key: 'Info.Name', type: 'string', label: '用户名称' }),
        field({ key: 'Info.Status', type: 'boolean', label: '启用用户' }),
      ],
    },
    {
      key: 'SRA',
      label: 'SRA 账号',
      fields: [
        field({
          key: 'SRA.Id',
          type: 'string',
          format: 'password',
          sensitive: true,
          label: '账号',
        }),
        field({
          key: 'SRA.Password',
          type: 'string',
          format: 'password',
          sensitive: true,
          label: '密码',
        }),
      ],
    },
    {
      key: 'Notify',
      label: '通知',
      fields: [
        field({ key: 'Notify.Enabled', type: 'boolean', label: '启用通知' }),
        field({
          key: 'Notify.ServerChanKey',
          type: 'string',
          sensitive: true,
          label: 'ServerChan Key',
        }),
      ],
    },
  ],
}

/**
 * MaaEnd 用户配置 schema（来源：app/models/config.py MaaEndUserConfig）
 *
 * 真实敏感字段（后端用 EncryptValidator）：
 * - Info.Password: format='password', sensitive=True
 * - Info.SklandToken: sensitive=True
 * - Notify.ServerChanKey: sensitive=True
 */
const maaEndUserSchema: SchemaDefinition = {
  groups: [
    {
      key: 'Info',
      label: '基础信息',
      fields: [
        field({ key: 'Info.Name', type: 'string', label: '用户名' }),
        field({ key: 'Info.Status', type: 'boolean', label: '启用状态' }),
        field({
          key: 'Info.Password',
          type: 'string',
          format: 'password',
          sensitive: true,
          label: '密码',
        }),
        field({
          key: 'Info.SklandToken',
          type: 'string',
          format: 'password',
          sensitive: true,
          label: '鹰角网络通行证登录凭证',
        }),
      ],
    },
    {
      key: 'Notify',
      label: '通知配置',
      fields: [
        field({ key: 'Notify.Enabled', type: 'boolean', label: '启用通知' }),
        field({
          key: 'Notify.ServerChanKey',
          type: 'string',
          sensitive: true,
          label: 'ServerChan Key',
        }),
      ],
    },
  ],
}

// ============================================================
// 测试：isSensitiveField
// ============================================================

describe('isSensitiveField（Lane 06 任务书第 1 条：敏感分支优先于普通字符串）', () => {
  it('检测 format=password 字段为敏感字段（HSR SRA.Id / SRA.Password / MaaEnd Info.Password）', () => {
    const hsrSraId = hsrUserSchema.groups[1].fields[0]
    const hsrSraPassword = hsrUserSchema.groups[1].fields[1]
    const maaEndPassword = maaEndUserSchema.groups[0].fields[2]
    expect(isSensitiveField(hsrSraId)).toBe(true)
    expect(isSensitiveField(hsrSraPassword)).toBe(true)
    expect(isSensitiveField(maaEndPassword)).toBe(true)
  })

  it('检测 sensitive=true 字段为敏感字段（HSR Notify.ServerChanKey / MaaEnd Info.SklandToken）', () => {
    const hsrServerChanKey = hsrUserSchema.groups[2].fields[1]
    const maaEndSklandToken = maaEndUserSchema.groups[0].fields[3]
    const maaEndServerChanKey = maaEndUserSchema.groups[1].fields[1]
    expect(isSensitiveField(hsrServerChanKey)).toBe(true)
    expect(isSensitiveField(maaEndSklandToken)).toBe(true)
    expect(isSensitiveField(maaEndServerChanKey)).toBe(true)
  })

  it('不误判普通字符串字段为敏感字段（Info.Name / Info.Status / Notify.Enabled）', () => {
    const hsrName = hsrUserSchema.groups[0].fields[0]
    const hsrStatus = hsrUserSchema.groups[0].fields[1]
    const hsrNotifyEnabled = hsrUserSchema.groups[2].fields[0]
    expect(isSensitiveField(hsrName)).toBe(false)
    expect(isSensitiveField(hsrStatus)).toBe(false)
    expect(isSensitiveField(hsrNotifyEnabled)).toBe(false)
  })

  it('不通过字段名硬编码判定（避免 token/secret/key 误判）', () => {
    expect(isSensitiveField(field({ type: 'string', key: 'api_token' }))).toBe(false)
    expect(isSensitiveField(field({ type: 'string', key: 'secret_value' }))).toBe(false)
    expect(isSensitiveField(field({ type: 'string', key: 'private_key' }))).toBe(false)
  })
})

// ============================================================
// 测试：getSensitiveDisplayValue（DOM 初值不泄漏明文）
// ============================================================

describe('getSensitiveDisplayValue（Lane 06 任务书第 1、3 条：密文不进入 DOM 初值）', () => {
  it('始终返回空串，无论后端原值为何', () => {
    const scenarios = ['', 'short', 'super-long-secret-token-12345', null, undefined]
    scenarios.forEach(() => {
      const displayValue = getSensitiveDisplayValue()
      expect(displayValue).toBe('')
    })
  })
})

// ============================================================
// 测试：resolveSensitiveSaveIntent（保持/替换/清空意图）
// ============================================================

describe('resolveSensitiveSaveIntent（Lane 06 任务书第 2 条：与后端真实保存契约对齐）', () => {
  it('未触碰（draft 空 + 未显式清空）→ keep', () => {
    expect(resolveSensitiveSaveIntent(undefined, false)).toEqual({ kind: 'keep' })
    expect(resolveSensitiveSaveIntent('', false)).toEqual({ kind: 'keep' })
  })

  it('用户输入新值（draft 非空）→ replace', () => {
    expect(resolveSensitiveSaveIntent('new-password-123', false)).toEqual({
      kind: 'replace',
      value: 'new-password-123',
    })
  })

  it('用户显式点击清空（explicitClear=true）→ clear（即使草稿非空也优先清空）', () => {
    expect(resolveSensitiveSaveIntent(undefined, true)).toEqual({ kind: 'clear' })
    expect(resolveSensitiveSaveIntent('', true)).toEqual({ kind: 'clear' })
    expect(resolveSensitiveSaveIntent('new-value', true)).toEqual({ kind: 'clear' })
  })

  it('不返回任何 sentinel 值（空串、null、undefined 等）', () => {
    const intents = [
      resolveSensitiveSaveIntent(undefined, false),
      resolveSensitiveSaveIntent('new-value', false),
      resolveSensitiveSaveIntent(undefined, true),
    ]
    intents.forEach(intent => {
      expect(intent).toHaveProperty('kind')
      expect(['keep', 'replace', 'clear']).toContain(intent.kind)
      // replace 才有 value，keep/clear 没有 value 字段
      if (intent.kind === 'replace') {
        expect(typeof intent.value).toBe('string')
      } else {
        expect(intent).not.toHaveProperty('value')
      }
    })
  })
})

// ============================================================
// 测试：applySensitiveIntentToPatch（意图 → patch）
// ============================================================

describe('applySensitiveIntentToPatch（Lane 06 任务书第 2 条：patch 构造）', () => {
  it('keep：不写入 patch（保持原值，后端不调用 set）', () => {
    const patch: Record<string, any> = {}
    applySensitiveIntentToPatch(patch, 'Info.Password', { kind: 'keep' })
    expect(patch).toEqual({})
  })

  it('replace：按点路径写入新明文', () => {
    const patch: Record<string, any> = {}
    applySensitiveIntentToPatch(patch, 'Info.Password', { kind: 'replace', value: 'new-pwd' })
    expect(patch).toEqual({ Info: { Password: 'new-pwd' } })
  })

  it('clear：按点路径写入空串 ""（后端加密为空密文）', () => {
    const patch: Record<string, any> = {}
    applySensitiveIntentToPatch(patch, 'Info.Password', { kind: 'clear' })
    expect(patch).toEqual({ Info: { Password: '' } })
  })

  it('多层嵌套路径（Notify.ServerChanKey）正确构造', () => {
    const patch: Record<string, any> = {}
    applySensitiveIntentToPatch(patch, 'Notify.ServerChanKey', {
      kind: 'replace',
      value: 'SNDKEY123',
    })
    expect(patch).toEqual({ Notify: { ServerChanKey: 'SNDKEY123' } })
  })
})

// ============================================================
// 测试：buildSensitiveSavePatch（基于真实 HSR/MaaEnd schema）
// ============================================================

describe('buildSensitiveSavePatch（Lane 06 任务书第 2 条：基于真实 schema 构造 patch）', () => {
  it('HSR schema：未触碰任何字段 → 空 patch', () => {
    const patch = buildSensitiveSavePatch(hsrUserSchema, {}, new Set())
    expect(patch).toEqual({})
  })

  it('HSR schema：仅替换 SRA.Password → patch 只含 SRA.Password', () => {
    const drafts = { 'SRA.Password': 'new-hsr-password' }
    const patch = buildSensitiveSavePatch(hsrUserSchema, drafts, new Set())
    expect(patch).toEqual({ SRA: { Password: 'new-hsr-password' } })
    // 关键：未触碰字段不在 patch 中（保持原值）
    expect(patch).not.toHaveProperty('SRA.Id')
    expect(patch).not.toHaveProperty('Notify')
  })

  it('HSR schema：清空 Notify.ServerChanKey → patch 含空串', () => {
    const explicitClears = new Set(['Notify.ServerChanKey'])
    const patch = buildSensitiveSavePatch(hsrUserSchema, {}, explicitClears)
    expect(patch).toEqual({ Notify: { ServerChanKey: '' } })
  })

  it('HSR schema：同时替换 SRA.Id 和清空 SRA.Password → patch 含两者', () => {
    const drafts = { 'SRA.Id': 'new-account-id' }
    const explicitClears = new Set(['SRA.Password'])
    const patch = buildSensitiveSavePatch(hsrUserSchema, drafts, explicitClears)
    expect(patch).toEqual({ SRA: { Id: 'new-account-id', Password: '' } })
  })

  it('MaaEnd schema：未触碰任何字段 → 空 patch', () => {
    const patch = buildSensitiveSavePatch(maaEndUserSchema, {}, new Set())
    expect(patch).toEqual({})
  })

  it('MaaEnd schema：替换 Info.Password → patch 只含 Info.Password', () => {
    const drafts = { 'Info.Password': 'new-maaend-pwd' }
    const patch = buildSensitiveSavePatch(maaEndUserSchema, drafts, new Set())
    expect(patch).toEqual({ Info: { Password: 'new-maaend-pwd' } })
    expect(patch).not.toHaveProperty('Notify')
  })

  it('MaaEnd schema：清空 Info.SklandToken → patch 含空串', () => {
    const explicitClears = new Set(['Info.SklandToken'])
    const patch = buildSensitiveSavePatch(maaEndUserSchema, {}, explicitClears)
    expect(patch).toEqual({ Info: { SklandToken: '' } })
  })

  it('MaaEnd schema：替换 Password + 清空 SklandToken + 清空 ServerChanKey → 全部进入 patch', () => {
    const drafts = { 'Info.Password': 'new-pwd-456' }
    const explicitClears = new Set(['Info.SklandToken', 'Notify.ServerChanKey'])
    const patch = buildSensitiveSavePatch(maaEndUserSchema, drafts, explicitClears)
    expect(patch).toEqual({
      Info: { Password: 'new-pwd-456', SklandToken: '' },
      Notify: { ServerChanKey: '' },
    })
  })
})

describe('buildSchemaSavePayload（生产保存入口：移除解密原值后合入显式敏感 patch）', () => {
  const decryptedModel = {
    Info: {
      Name: 'alice',
      Status: true,
      Password: 'old-password-plaintext',
      SklandToken: 'old-skland-token-plaintext',
    },
    Notify: {
      Enabled: true,
      ServerChanKey: 'old-server-chan-key-plaintext',
    },
    Extra: { retries: 3 },
  }

  it('未触碰敏感字段时省略全部敏感值，并完整保留非敏感字段', () => {
    const payload = buildSchemaSavePayload(decryptedModel, maaEndUserSchema, {})

    expect(payload).toEqual({
      Info: { Name: 'alice', Status: true },
      Notify: { Enabled: true },
      Extra: { retries: 3 },
    })
    expect(JSON.stringify(payload)).not.toContain('old-password-plaintext')
    expect(JSON.stringify(payload)).not.toContain('old-skland-token-plaintext')
    expect(JSON.stringify(payload)).not.toContain('old-server-chan-key-plaintext')
  })

  it('只写回明确替换和清空的敏感字段', () => {
    const payload = buildSchemaSavePayload(decryptedModel, maaEndUserSchema, {
      Info: { Password: 'replacement-password', SklandToken: '' },
    })

    expect(payload.Info).toEqual({
      Name: 'alice',
      Status: true,
      Password: 'replacement-password',
      SklandToken: '',
    })
    expect(payload.Notify).toEqual({ Enabled: true })
  })

  it('不修改后端加载得到的原始 model', () => {
    const before = JSON.parse(JSON.stringify(decryptedModel))
    buildSchemaSavePayload(decryptedModel, maaEndUserSchema, {
      Notify: { ServerChanKey: 'replacement-key' },
    })
    expect(decryptedModel).toEqual(before)
  })

  it('仅含敏感字段的空分组在 keep 时一并移除', () => {
    const payload = buildSchemaSavePayload(
      { SRA: { Id: 'old-id', Password: 'old-password' } },
      hsrUserSchema,
      {}
    )
    expect(payload).toEqual({})
  })
})

// ============================================================
// 测试：hasSensitiveDirtyChange
// ============================================================

describe('hasSensitiveDirtyChange（Lane 06 任务书第 4 条：未保存保护 dirty 状态）', () => {
  it('HSR schema：无草稿无清空 → false', () => {
    expect(hasSensitiveDirtyChange(hsrUserSchema, {}, new Set())).toBe(false)
  })

  it('HSR schema：有草稿 → true', () => {
    expect(hasSensitiveDirtyChange(hsrUserSchema, { 'SRA.Password': 'x' }, new Set())).toBe(true)
  })

  it('HSR schema：有显式清空 → true', () => {
    expect(hasSensitiveDirtyChange(hsrUserSchema, {}, new Set(['Notify.ServerChanKey']))).toBe(true)
  })

  it('MaaEnd schema：三个敏感字段均未触碰 → false', () => {
    expect(hasSensitiveDirtyChange(maaEndUserSchema, {}, new Set())).toBe(false)
  })

  it('MaaEnd schema：任一字段 dirty → true', () => {
    expect(hasSensitiveDirtyChange(maaEndUserSchema, { 'Info.Password': 'x' }, new Set())).toBe(
      true
    )
    expect(hasSensitiveDirtyChange(maaEndUserSchema, {}, new Set(['Info.SklandToken']))).toBe(true)
    expect(hasSensitiveDirtyChange(maaEndUserSchema, {}, new Set(['Notify.ServerChanKey']))).toBe(
      true
    )
  })
})

// ============================================================
// 测试：sanitizeFieldValueForLog
// ============================================================

describe('sanitizeFieldValueForLog（Lane 06 任务书第 3 条：日志不泄密）', () => {
  it('非敏感字段原样返回', () => {
    expect(sanitizeFieldValueForLog(field({ type: 'string' }), 'hello')).toBe('hello')
    expect(sanitizeFieldValueForLog(field({ type: 'number' }), 42)).toBe(42)
  })

  it('敏感字段非空值替换为 ***，空值保留', () => {
    expect(sanitizeFieldValueForLog(field({ type: 'string', format: 'password' }), 'secret')).toBe(
      '***'
    )
    expect(sanitizeFieldValueForLog(field({ type: 'password' }), 'secret')).toBe('***')
    expect(sanitizeFieldValueForLog(field({ type: 'string', sensitive: true }), 'secret')).toBe(
      '***'
    )
    expect(sanitizeFieldValueForLog(field({ type: 'string', format: 'password' }), '')).toBe('')
    expect(sanitizeFieldValueForLog(field({ type: 'string', format: 'password' }), null)).toBeNull()
    expect(
      sanitizeFieldValueForLog(field({ type: 'string', format: 'password' }), undefined)
    ).toBeUndefined()
  })
})

// ============================================================
// 测试：sanitizeModelForLog
// ============================================================

describe('sanitizeModelForLog（Lane 06 任务书第 3 条：整体 model 脱敏）', () => {
  it('HSR model：敏感字段替换为 ***，非敏感字段保留', () => {
    const model = {
      Info: { Name: 'alice', Status: true },
      SRA: { Id: 'hsr-account-123', Password: 'hsr-pwd-456' },
      Notify: { Enabled: false, ServerChanKey: 'sk-abc' },
    }
    const sanitized = sanitizeModelForLog(model, hsrUserSchema)
    expect(sanitized.Info.Name).toBe('alice')
    expect(sanitized.Info.Status).toBe(true)
    expect(sanitized.SRA.Id).toBe('***')
    expect(sanitized.SRA.Password).toBe('***')
    expect(sanitized.Notify.Enabled).toBe(false)
    expect(sanitized.Notify.ServerChanKey).toBe('***')
    // 原对象不被修改
    expect(model.SRA.Id).toBe('hsr-account-123')
  })

  it('MaaEnd model：敏感字段替换为 ***', () => {
    const model = {
      Info: {
        Name: 'bob',
        Status: true,
        Password: 'maaend-pwd-789',
        SklandToken: 'skland-token-xyz',
      },
      Notify: { Enabled: false, ServerChanKey: 'sk-def' },
    }
    const sanitized = sanitizeModelForLog(model, maaEndUserSchema)
    expect(sanitized.Info.Name).toBe('bob')
    expect(sanitized.Info.Password).toBe('***')
    expect(sanitized.Info.SklandToken).toBe('***')
    expect(sanitized.Notify.ServerChanKey).toBe('***')
  })

  it('缺失字段不抛错', () => {
    const model = { Info: { Name: 'bob' } }
    const sanitized = sanitizeModelForLog(model, maaEndUserSchema)
    expect(sanitized.Info.Name).toBe('bob')
  })
})

// ============================================================
// 测试：sanitizeErrorForLog
// ============================================================

describe('sanitizeErrorForLog（Lane 06 任务书第 3 条：错误消息脱敏）', () => {
  it('HSR：错误消息中包含的明文密码替换为 ***', () => {
    const model = { SRA: { Password: 'hsr-pwd-456' } }
    const msg = '登录失败：密码 hsr-pwd-456 不正确'
    const sanitized = sanitizeErrorForLog(msg, model, hsrUserSchema)
    expect(sanitized).toBe('登录失败：密码 *** 不正确')
  })

  it('MaaEnd：错误消息中包含的 SklandToken 替换为 ***', () => {
    const model = { Info: { SklandToken: 'skland-token-xyz' } }
    const msg = '森空岛签到失败：token skland-token-xyz 已过期'
    const sanitized = sanitizeErrorForLog(msg, model, maaEndUserSchema)
    expect(sanitized).toBe('森空岛签到失败：token *** 已过期')
  })

  it('空串或非字符串输入原样返回', () => {
    expect(sanitizeErrorForLog('', {}, hsrUserSchema)).toBe('')
    expect(sanitizeErrorForLog(null as any, {}, hsrUserSchema)).toBeNull()
  })

  it('短于 4 字符的值不替换（避免误报）', () => {
    const model = { Info: { Password: 'ab' } }
    const msg = '密码 ab 不正确'
    expect(sanitizeErrorForLog(msg, model, maaEndUserSchema)).toBe('密码 ab 不正确')
  })
})

// ============================================================
// 测试：isSensitiveFieldCleared / getSensitivePlaceholder
// ============================================================

describe('isSensitiveFieldCleared / getSensitivePlaceholder', () => {
  const pwdField = field({ key: 'Info.Password', type: 'string', format: 'password' })

  it('已清空状态：null / 空串 / undefined', () => {
    expect(isSensitiveFieldCleared({ Info: { Password: null } }, pwdField)).toBe(true)
    expect(isSensitiveFieldCleared({ Info: { Password: '' } }, pwdField)).toBe(true)
    expect(isSensitiveFieldCleared({ Info: {} }, pwdField)).toBe(true)
  })

  it('未清空状态：有原值', () => {
    expect(isSensitiveFieldCleared({ Info: { Password: 'secret' } }, pwdField)).toBe(false)
  })

  it('placeholder 反映 cleared vs has-value', () => {
    const clearedModel = { Info: { Password: null } }
    const hasValueModel = { Info: { Password: 'secret' } }
    expect(getSensitivePlaceholder(clearedModel, pwdField)).toBe(SENSITIVE_CLEARED_PLACEHOLDER)
    expect(getSensitivePlaceholder(hasValueModel, pwdField)).toBe(SENSITIVE_PLACEHOLDER)
  })
})

// ============================================================
// 测试：collectSensitiveFieldPaths
// ============================================================

describe('collectSensitiveFieldPaths（Lane 06 任务书第 8 条测试要求：覆盖所有敏感字段）', () => {
  it('HSR schema：列出 SRA.Id / SRA.Password / Notify.ServerChanKey', () => {
    const paths = collectSensitiveFieldPaths(hsrUserSchema)
    expect(paths).toEqual(
      expect.arrayContaining(['SRA.Id', 'SRA.Password', 'Notify.ServerChanKey'])
    )
    expect(paths).toHaveLength(3)
    // 非敏感字段不出现
    expect(paths).not.toContain('Info.Name')
    expect(paths).not.toContain('Info.Status')
    expect(paths).not.toContain('Notify.Enabled')
  })

  it('MaaEnd schema：列出 Info.Password / Info.SklandToken / Notify.ServerChanKey', () => {
    const paths = collectSensitiveFieldPaths(maaEndUserSchema)
    expect(paths).toEqual(
      expect.arrayContaining(['Info.Password', 'Info.SklandToken', 'Notify.ServerChanKey'])
    )
    expect(paths).toHaveLength(3)
  })

  it('无敏感字段的 schema 返回空数组', () => {
    const safeSchema: SchemaDefinition = {
      groups: [{ key: 'g', fields: [field({ key: 'name', type: 'string' })] }],
    }
    expect(collectSensitiveFieldPaths(safeSchema)).toEqual([])
  })
})

// ============================================================
// 测试：assertNoSensitiveLeak
// ============================================================

describe('assertNoSensitiveLeak（Lane 06 任务书第 3 条：密文不泄漏断言）', () => {
  it('HSR：检测到明文泄漏', () => {
    const model = { SRA: { Password: 'hsr-pwd-456' } }
    const text = 'error: invalid password hsr-pwd-456'
    const result = assertNoSensitiveLeak(text, model, hsrUserSchema)
    expect(result.leaked).toBe(true)
    expect(result.leakedPaths).toEqual(['SRA.Password'])
  })

  it('MaaEnd：多个敏感字段同时泄漏', () => {
    const model = {
      Info: { Password: 'maaend-pwd-789', SklandToken: 'skland-token-xyz' },
    }
    const text = 'error: password=maaend-pwd-789 token=skland-token-xyz'
    const result = assertNoSensitiveLeak(text, model, maaEndUserSchema)
    expect(result.leaked).toBe(true)
    expect(result.leakedPaths).toEqual(
      expect.arrayContaining(['Info.Password', 'Info.SklandToken'])
    )
  })

  it('无泄漏时返回 false', () => {
    const model = { Info: { Password: 'maaend-pwd-789' } }
    const text = 'error: something went wrong'
    const result = assertNoSensitiveLeak(text, model, maaEndUserSchema)
    expect(result.leaked).toBe(false)
    expect(result.leakedPaths).toEqual([])
  })

  it('短于 4 字符的值不视为泄漏', () => {
    const model = { Info: { Password: 'ab' } }
    const text = 'error: password ab is bad'
    expect(assertNoSensitiveLeak(text, model, maaEndUserSchema).leaked).toBe(false)
  })
})

// ============================================================
// 集成断言：Lane 06 任务书第 1、2、3 条
// ============================================================

describe('Lane 06 集成断言：密文不进入 DOM 初值 + 保持/替换/清空语义 + 日志/错误不泄密', () => {
  it('敏感字段 DOM 显示值始终为空串，无论后端原值为何', () => {
    const scenarios = ['', 'short', 'super-long-secret-token-12345', null, undefined]
    scenarios.forEach(() => {
      const displayValue = getSensitiveDisplayValue()
      expect(displayValue).toBe('')
    })
  })

  it('保存语义与后端契约一致：keep 省略、replace 新值、clear 空串', () => {
    // HSR schema 测试
    const hsrPatch = buildSensitiveSavePatch(
      hsrUserSchema,
      { 'SRA.Password': 'new-hsr-pwd' },
      new Set(['Notify.ServerChanKey'])
    )
    // keep 字段（SRA.Id）不在 patch 中
    expect(hsrPatch).not.toHaveProperty('SRA.Id')
    // replace 字段含新值
    expect(hsrPatch.SRA.Password).toBe('new-hsr-pwd')
    // clear 字段含空串
    expect(hsrPatch.Notify.ServerChanKey).toBe('')

    // MaaEnd schema 测试
    const maaEndPatch = buildSensitiveSavePatch(
      maaEndUserSchema,
      { 'Info.Password': 'new-maaend-pwd' },
      new Set(['Info.SklandToken'])
    )
    expect(maaEndPatch.Info.Password).toBe('new-maaend-pwd')
    expect(maaEndPatch.Info.SklandToken).toBe('')
    // 未触碰的 Notify.ServerChanKey 不在 patch 中
    expect(maaEndPatch).not.toHaveProperty('Notify')
  })

  it('HSR 日志输出中不得包含明文密码', () => {
    const model = {
      SRA: { Id: 'plaintext-account-123', Password: 'plaintext-pwd-456' },
      Notify: { ServerChanKey: 'plaintext-sk-789' },
    }
    const sanitized = sanitizeModelForLog(model, hsrUserSchema)
    const serialized = JSON.stringify(sanitized)
    expect(serialized).not.toContain('plaintext-account-123')
    expect(serialized).not.toContain('plaintext-pwd-456')
    expect(serialized).not.toContain('plaintext-sk-789')
    expect(serialized).toContain('***')
  })

  it('MaaEnd 错误消息中不得包含明文密码/SklandToken/ServerChanKey', () => {
    const model = {
      Info: {
        Password: 'maaend-plaintext-pwd',
        SklandToken: 'maaend-plaintext-token',
      },
      Notify: { ServerChanKey: 'maaend-plaintext-sk' },
    }
    const errorMsg =
      '保存失败：password=maaend-plaintext-pwd token=maaend-plaintext-token sk=maaend-plaintext-sk'
    const sanitized = sanitizeErrorForLog(errorMsg, model, maaEndUserSchema)
    expect(sanitized).not.toContain('maaend-plaintext-pwd')
    expect(sanitized).not.toContain('maaend-plaintext-token')
    expect(sanitized).not.toContain('maaend-plaintext-sk')
    expect(sanitized).toContain('***')
  })

  it('HSR + MaaEnd schema 的 collectSensitiveFieldPaths 覆盖所有声明为敏感的字段', () => {
    const hsrPaths = collectSensitiveFieldPaths(hsrUserSchema)
    const maaEndPaths = collectSensitiveFieldPaths(maaEndUserSchema)
    expect(hsrPaths).toEqual(['SRA.Id', 'SRA.Password', 'Notify.ServerChanKey'])
    expect(maaEndPaths).toEqual(['Info.Password', 'Info.SklandToken', 'Notify.ServerChanKey'])
  })
})
