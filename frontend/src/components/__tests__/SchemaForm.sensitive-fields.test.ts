import { describe, expect, it } from 'vitest'
import type { SchemaDefinition, SchemaFieldDefinition } from '@/types/schemaForm'
import {
  buildSensitiveSavePatch,
  collectSensitiveFieldPaths,
  getSensitiveDisplayValue,
  getSensitivePlaceholder,
  hasSensitiveDirtyChange,
  isSensitiveFieldCleared,
  resolveSensitiveSaveIntent,
  SENSITIVE_PLACEHOLDER,
  SENSITIVE_CLEARED_PLACEHOLDER,
  assertNoSensitiveLeak,
  sanitizeModelForLog,
} from '@/composables/useSensitiveFieldStrategy'

/**
 * SchemaForm 敏感字段 DOM 不泄漏测试（Lane 06 任务书第 1、3 条 + 第 8 条测试要求）
 *
 * 测试目标：验证 SchemaForm.vue 内部的敏感字段处理逻辑不会把明文泄漏到：
 * 1. DOM 初值（通过 `getSensitiveDisplayValue()` 始终返回空串）
 * 2. modelValue（敏感字段输入只更新草稿，不污染 modelValue）
 * 3. 保存 patch（未触碰字段省略，符合后端 keep 语义）
 * 4. 日志/错误消息（脱敏后不含明文）
 *
 * 由于 vitest 默认 node 环境无 DOM，本测试通过验证 SchemaForm.vue 使用的
 * composable 函数（useSensitiveFieldStrategy + useSchemaFormModel）行为，
 * 间接验证组件内部的敏感字段处理逻辑。
 *
 * 真实 schema 来源：
 * - HSR 用户：build/w/b2/automas_script_hsr/source/src/automas_script_hsr/schema.py
 *   - HSRUserSRAConfig.Id / Password（format='password', sensitive=True）
 *   - HSRUserNotifyConfig.ServerChanKey（sensitive=True）
 * - MaaEnd 用户：app/models/config.py MaaEndUserConfig
 *   - Info.Password / Info.SklandToken（EncryptValidator）
 *   - Notify.ServerChanKey（EncryptValidator）
 */

const field = (overrides: Partial<SchemaFieldDefinition> = {}): SchemaFieldDefinition => ({
  type: 'string',
  ...overrides,
})

/**
 * HSR 用户 schema（真实后端 Pydantic 模型对应字段）。
 */
const hsrUserSchema: SchemaDefinition = {
  groups: [
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
 * MaaEnd 用户 schema（真实后端 ConfigBase 字段）。
 */
const maaEndUserSchema: SchemaDefinition = {
  groups: [
    {
      key: 'Info',
      label: '基础信息',
      fields: [
        field({ key: 'Info.Name', type: 'string', label: '用户名' }),
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
          sensitive: true,
          label: '鹰角网络通行证登录凭证',
        }),
      ],
    },
    {
      key: 'Notify',
      label: '通知配置',
      fields: [
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
 * 模拟真实后端返回的 HSR 用户数据（含解密后的明文敏感字段）。
 * 后端 update_user 会用 EncryptValidator 加密保存，getUsers 返回时解密为明文。
 */
const hsrBackendDecryptedModel = {
  SRA: {
    Id: 'hsr-account-plaintext-12345',
    Password: 'hsr-password-plaintext-67890',
  },
  Notify: {
    ServerChanKey: 'hsr-serverchan-key-plaintext-abcdef',
  },
}

/**
 * 模拟真实后端返回的 MaaEnd 用户数据（含解密后的明文敏感字段）。
 */
const maaEndBackendDecryptedModel = {
  Info: {
    Name: 'test-user',
    Password: 'maaend-password-plaintext-12345',
    SklandToken: 'maaend-skland-token-plaintext-67890',
  },
  Notify: {
    ServerChanKey: 'maaend-serverchan-key-plaintext-abcdef',
  },
}

describe('SchemaForm 敏感字段 DOM 不泄漏（Lane 06 任务书第 1 条）', () => {
  describe('HSR schema：敏感字段明文不进入 DOM 初值', () => {
    it('getSensitiveDisplayValue 始终返回空串，即使后端返回明文', () => {
      // 模拟 SchemaForm.vue 中 :value="getSensitiveDraft(...)" 的行为
      // getSensitiveDraft 内部调用 getSensitiveDisplayValue
      const sensitivePaths = collectSensitiveFieldPaths(hsrUserSchema)
      expect(sensitivePaths).toContain('SRA.Id')
      expect(sensitivePaths).toContain('SRA.Password')
      expect(sensitivePaths).toContain('Notify.ServerChanKey')

      sensitivePaths.forEach(path => {
        // 无论后端 modelValue 中该字段是什么值，DOM 显示值始终为空串
        const displayValue = getSensitiveDisplayValue()
        expect(displayValue).toBe('')
      })
    })

    it('HSR 明文密码不出现在 DOM 显示值中', () => {
      const plaintextValues = [
        hsrBackendDecryptedModel.SRA.Id,
        hsrBackendDecryptedModel.SRA.Password,
        hsrBackendDecryptedModel.Notify.ServerChanKey,
      ]
      plaintextValues.forEach(plaintext => {
        const displayValue = getSensitiveDisplayValue()
        expect(displayValue).not.toContain(plaintext)
        expect(displayValue).toBe('')
      })
    })

    it('HSR placeholder 不泄漏明文（仅显示固定占位文本）', () => {
      const sraPasswordField = hsrUserSchema.groups[0].fields[1]
      const placeholder = getSensitivePlaceholder(hsrBackendDecryptedModel, sraPasswordField)
      // placeholder 只能是 SENSITIVE_PLACEHOLDER 或 SENSITIVE_CLEARED_PLACEHOLDER
      expect([SENSITIVE_PLACEHOLDER, SENSITIVE_CLEARED_PLACEHOLDER]).toContain(placeholder)
      // placeholder 不含明文
      expect(placeholder).not.toContain(hsrBackendDecryptedModel.SRA.Password)
    })
  })

  describe('MaaEnd schema：敏感字段明文不进入 DOM 初值', () => {
    it('getSensitiveDisplayValue 始终返回空串，即使后端返回明文', () => {
      const sensitivePaths = collectSensitiveFieldPaths(maaEndUserSchema)
      expect(sensitivePaths).toContain('Info.Password')
      expect(sensitivePaths).toContain('Info.SklandToken')
      expect(sensitivePaths).toContain('Notify.ServerChanKey')

      sensitivePaths.forEach(() => {
        const displayValue = getSensitiveDisplayValue()
        expect(displayValue).toBe('')
      })
    })

    it('MaaEnd 明文密码/SklandToken/ServerChanKey 不出现在 DOM 显示值中', () => {
      const plaintextValues = [
        maaEndBackendDecryptedModel.Info.Password,
        maaEndBackendDecryptedModel.Info.SklandToken,
        maaEndBackendDecryptedModel.Notify.ServerChanKey,
      ]
      plaintextValues.forEach(plaintext => {
        const displayValue = getSensitiveDisplayValue()
        expect(displayValue).not.toContain(plaintext)
        expect(displayValue).toBe('')
      })
    })

    it('MaaEnd placeholder 不泄漏明文', () => {
      const passwordField = maaEndUserSchema.groups[0].fields[1]
      const sklandTokenField = maaEndUserSchema.groups[0].fields[2]
      const serverChanKeyField = maaEndUserSchema.groups[1].fields[0]

      const passwordPlaceholder = getSensitivePlaceholder(
        maaEndBackendDecryptedModel,
        passwordField
      )
      const sklandPlaceholder = getSensitivePlaceholder(
        maaEndBackendDecryptedModel,
        sklandTokenField
      )
      const serverChanPlaceholder = getSensitivePlaceholder(
        maaEndBackendDecryptedModel,
        serverChanKeyField
      )

      ;[passwordPlaceholder, sklandPlaceholder, serverChanPlaceholder].forEach(p => {
        expect([SENSITIVE_PLACEHOLDER, SENSITIVE_CLEARED_PLACEHOLDER]).toContain(p)
      })

      expect(passwordPlaceholder).not.toContain(maaEndBackendDecryptedModel.Info.Password)
      expect(sklandPlaceholder).not.toContain(maaEndBackendDecryptedModel.Info.SklandToken)
      expect(serverChanPlaceholder).not.toContain(maaEndBackendDecryptedModel.Notify.ServerChanKey)
    })
  })
})

describe('SchemaForm 草稿不污染 modelValue（Lane 06 任务书第 3 条）', () => {
  it('HSR：用户输入草稿后，buildSensitiveSavePatch 只包含被触碰的字段', () => {
    // 模拟用户在 SRA.Password 中输入新密码
    const drafts = { 'SRA.Password': 'new-hsr-password-typed-by-user' }
    const explicitClears = new Set<string>()

    const patch = buildSensitiveSavePatch(hsrUserSchema, drafts, explicitClears)

    // patch 只含 SRA.Password，不含 SRA.Id 和 Notify.ServerChanKey
    expect(patch).toEqual({ SRA: { Password: 'new-hsr-password-typed-by-user' } })
    expect(patch).not.toHaveProperty('Notify')
  })

  it('MaaEnd：用户输入草稿后，buildSensitiveSavePatch 只包含被触碰的字段', () => {
    const drafts = { 'Info.Password': 'new-maaend-password-typed' }
    const explicitClears = new Set<string>()

    const patch = buildSensitiveSavePatch(maaEndUserSchema, drafts, explicitClears)

    expect(patch).toEqual({ Info: { Password: 'new-maaend-password-typed' } })
    expect(patch).not.toHaveProperty('Notify')
  })

  it('草稿为空且未显式清空时，buildSensitiveSavePatch 返回空对象（不污染 modelValue）', () => {
    const patch = buildSensitiveSavePatch(maaEndUserSchema, {}, new Set())
    expect(patch).toEqual({})
  })
})

describe('SchemaForm draft reload 行为（Lane 06 任务书第 3 条：保存/权威 reload 后清理 DOM draft）', () => {
  it('HSR：reload 后调用 buildSensitiveSavePatch(空 drafts, 空 explicitClears) 返回空 patch', () => {
    // 模拟父组件 reload 后调用 resetSensitiveDrafts()：
    // sensitiveDrafts.value = {}; sensitiveExplicitClears.value = new Set();
    // 然后调用 collectSensitiveSavePatch() 应返回空 patch
    const patch = buildSensitiveSavePatch(hsrUserSchema, {}, new Set())
    expect(patch).toEqual({})
  })

  it('MaaEnd：reload 后所有敏感字段 dirty 状态为 false', () => {
    // 模拟父组件 reload 后调用 resetSensitiveDrafts()：
    // hasSensitiveDirty() 应返回 false
    const isDirty = hasSensitiveDirtyChange(maaEndUserSchema, {}, new Set())
    expect(isDirty).toBe(false)
  })

  it('HSR：reload 前用户输入了草稿，reload 后 dirty 状态归零', () => {
    // reload 前有草稿
    const beforeReload = hasSensitiveDirtyChange(
      hsrUserSchema,
      { 'SRA.Password': 'typed-but-not-saved' },
      new Set()
    )
    expect(beforeReload).toBe(true)

    // reload 后清空草稿
    const afterReload = hasSensitiveDirtyChange(hsrUserSchema, {}, new Set())
    expect(afterReload).toBe(false)
  })
})

describe('SchemaForm 保存协议：keep/replace/clear 与后端契约一致（Lane 06 任务书第 2 条）', () => {
  describe('HSR schema 保存协议', () => {
    it('keep：用户未触碰 SRA.Id → 不在 patch 中（后端保持原密文）', () => {
      const patch = buildSensitiveSavePatch(hsrUserSchema, { 'SRA.Password': 'new-pwd' }, new Set())
      expect(patch).not.toHaveProperty('SRA.Id')
      // 后端 update_user 不会调用 set('SRA', 'Id', ...)，原密文保持
    })

    it('replace：用户输入新 SRA.Password → patch 含新明文（后端加密为新密文）', () => {
      const patch = buildSensitiveSavePatch(
        hsrUserSchema,
        { 'SRA.Password': 'new-hsr-pwd-123' },
        new Set()
      )
      expect(patch.SRA.Password).toBe('new-hsr-pwd-123')
    })

    it('clear：用户显式清空 Notify.ServerChanKey → patch 含空串（后端加密为空密文）', () => {
      const patch = buildSensitiveSavePatch(hsrUserSchema, {}, new Set(['Notify.ServerChanKey']))
      expect(patch.Notify.ServerChanKey).toBe('')
    })

    it('同时 keep + replace + clear：三种意图混合', () => {
      const patch = buildSensitiveSavePatch(
        hsrUserSchema,
        { 'SRA.Password': 'new-pwd' }, // replace
        new Set(['Notify.ServerChanKey']) // clear
        // SRA.Id 未触碰 → keep（不在 patch 中）
      )
      expect(patch).toEqual({
        SRA: { Password: 'new-pwd' },
        Notify: { ServerChanKey: '' },
      })
      expect(patch).not.toHaveProperty('SRA.Id')
    })
  })

  describe('MaaEnd schema 保存协议', () => {
    it('keep：用户未触碰 Info.Password → 不在 patch 中', () => {
      const patch = buildSensitiveSavePatch(
        maaEndUserSchema,
        { 'Info.SklandToken': 'new-token' },
        new Set()
      )
      expect(patch).not.toHaveProperty('Info.Password')
      expect(patch).not.toHaveProperty('Notify')
    })

    it('replace：用户输入新 Info.Password → patch 含新明文', () => {
      const patch = buildSensitiveSavePatch(
        maaEndUserSchema,
        { 'Info.Password': 'new-maaend-pwd' },
        new Set()
      )
      expect(patch.Info.Password).toBe('new-maaend-pwd')
    })

    it('clear：用户显式清空 Info.SklandToken → patch 含空串', () => {
      const patch = buildSensitiveSavePatch(maaEndUserSchema, {}, new Set(['Info.SklandToken']))
      expect(patch.Info.SklandToken).toBe('')
    })

    it('三字段全部 clear：patch 含三个空串', () => {
      const patch = buildSensitiveSavePatch(
        maaEndUserSchema,
        {},
        new Set(['Info.Password', 'Info.SklandToken', 'Notify.ServerChanKey'])
      )
      expect(patch).toEqual({
        Info: { Password: '', SklandToken: '' },
        Notify: { ServerChanKey: '' },
      })
    })
  })
})

describe('SchemaForm 错误脱敏与日志不泄密（Lane 06 任务书第 3 条）', () => {
  it('HSR：sanitizeModelForLog 不泄漏明文密码到日志', () => {
    const sanitized = sanitizeModelForLog(hsrBackendDecryptedModel, hsrUserSchema)
    const serialized = JSON.stringify(sanitized)
    expect(serialized).not.toContain('hsr-account-plaintext-12345')
    expect(serialized).not.toContain('hsr-password-plaintext-67890')
    expect(serialized).not.toContain('hsr-serverchan-key-plaintext-abcdef')
    expect(serialized).toContain('***')
  })

  it('MaaEnd：sanitizeModelForLog 不泄漏明文密码/SklandToken/ServerChanKey', () => {
    const sanitized = sanitizeModelForLog(maaEndBackendDecryptedModel, maaEndUserSchema)
    const serialized = JSON.stringify(sanitized)
    expect(serialized).not.toContain('maaend-password-plaintext-12345')
    expect(serialized).not.toContain('maaend-skland-token-plaintext-67890')
    expect(serialized).not.toContain('maaend-serverchan-key-plaintext-abcdef')
    expect(serialized).toContain('***')
    // 非敏感字段保留
    expect(serialized).toContain('test-user')
  })

  it('HSR：assertNoSensitiveLeak 检测到日志中包含明文密码', () => {
    const logText = `保存字段: SRA.Password = ${hsrBackendDecryptedModel.SRA.Password}`
    const result = assertNoSensitiveLeak(logText, hsrBackendDecryptedModel, hsrUserSchema)
    expect(result.leaked).toBe(true)
    expect(result.leakedPaths).toContain('SRA.Password')
  })

  it('MaaEnd：assertNoSensitiveLeak 检测到错误消息中包含明文 SklandToken', () => {
    const errorText = `森空岛签到失败：token ${maaEndBackendDecryptedModel.Info.SklandToken} 无效`
    const result = assertNoSensitiveLeak(errorText, maaEndBackendDecryptedModel, maaEndUserSchema)
    expect(result.leaked).toBe(true)
    expect(result.leakedPaths).toContain('Info.SklandToken')
  })

  it('HSR + MaaEnd：脱敏后 assertNoSensitiveLeak 不再检测到泄漏', () => {
    const hsrSanitized = sanitizeModelForLog(hsrBackendDecryptedModel, hsrUserSchema)
    const hsrLogText = `model = ${JSON.stringify(hsrSanitized)}`
    expect(assertNoSensitiveLeak(hsrLogText, hsrSanitized, hsrUserSchema).leaked).toBe(false)

    const maaEndSanitized = sanitizeModelForLog(maaEndBackendDecryptedModel, maaEndUserSchema)
    const maaEndLogText = `model = ${JSON.stringify(maaEndSanitized)}`
    expect(assertNoSensitiveLeak(maaEndLogText, maaEndSanitized, maaEndUserSchema).leaked).toBe(
      false
    )
  })
})

describe('SchemaForm isSensitiveFieldCleared 与 placeholder 联动', () => {
  it('HSR：后端返回空密码时 placeholder 显示“已清空”提示', () => {
    const emptyPasswordModel = { SRA: { Password: '' } }
    const sraPasswordField = hsrUserSchema.groups[0].fields[1]
    expect(isSensitiveFieldCleared(emptyPasswordModel, sraPasswordField)).toBe(true)
    expect(getSensitivePlaceholder(emptyPasswordModel, sraPasswordField)).toBe(
      SENSITIVE_CLEARED_PLACEHOLDER
    )
  })

  it('MaaEnd：后端返回非空密码时 placeholder 显示“已保存”提示', () => {
    const passwordField = maaEndUserSchema.groups[0].fields[1]
    expect(isSensitiveFieldCleared(maaEndBackendDecryptedModel, passwordField)).toBe(false)
    expect(getSensitivePlaceholder(maaEndBackendDecryptedModel, passwordField)).toBe(
      SENSITIVE_PLACEHOLDER
    )
  })
})

describe('SchemaForm resolveSensitiveSaveIntent 与 buildSensitiveSavePatch 一致性', () => {
  it('HSR：单个字段意图解析与 patch 构造结果一致', () => {
    // keep
    expect(resolveSensitiveSaveIntent('', false).kind).toBe('keep')
    // replace
    expect(resolveSensitiveSaveIntent('new-value', false).kind).toBe('replace')
    // clear
    expect(resolveSensitiveSaveIntent('', true).kind).toBe('clear')

    // patch 构造与意图一致
    const keepPatch = buildSensitiveSavePatch(hsrUserSchema, {}, new Set())
    expect(keepPatch).toEqual({})

    const replacePatch = buildSensitiveSavePatch(hsrUserSchema, { 'SRA.Id': 'new-id' }, new Set())
    expect(replacePatch).toEqual({ SRA: { Id: 'new-id' } })

    const clearPatch = buildSensitiveSavePatch(hsrUserSchema, {}, new Set(['SRA.Id']))
    expect(clearPatch).toEqual({ SRA: { Id: '' } })
  })

  it('MaaEnd：三字段混合意图与 patch 构造结果一致', () => {
    const drafts = {
      'Info.Password': 'new-pwd', // replace
    }
    const explicitClears = new Set(['Info.SklandToken']) // clear
    // Notify.ServerChanKey 未触碰 → keep

    const patch = buildSensitiveSavePatch(maaEndUserSchema, drafts, explicitClears)
    expect(patch.Info.Password).toBe('new-pwd')
    expect(patch.Info.SklandToken).toBe('')
    expect(patch).not.toHaveProperty('Notify')
  })
})
