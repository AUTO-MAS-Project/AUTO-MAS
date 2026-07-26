/**
 * MaaEndUserEdit 保存协议集成测试（Lane 06 任务书第 2、5 条 + PR #302 接入）
 *
 * 测试目标：验证 MaaEndUserEdit.vue 中 `handleSensitiveSave` 把子组件发出的
 * `sensitiveSave` 事件（keep/replace/clear）正确翻译为后端 update_user patch，
 * 且与真实 Config v2 / EncryptValidator 契约一致。
 *
 * 测试策略：
 * - vitest 默认 Node 环境，仓库未安装 jsdom / @vue/test-utils（见
 *   `useUnsavedChangesGuard.test.ts:6-13` 注释），因此不 mount 组件。
 * - 把 `handleSensitiveSave` 的核心契约抽离为纯函数 `applySensitiveSaveIntent`，
 *   并在 MaaEndUserEdit.vue 中按相同语义实现（保持单一真相源）；文件后半部分
 *   用 vue/compiler-sfc 静态解析真实 SFC 源码，锚定该镜像与真实实现一致，
 *   防止镜像漂移导致测试与组件脱钩。
 * - 使用真实 MaaEnd 后端 schema 字段路径（Info.Password / Info.SklandToken /
 *   Notify.ServerChanKey）与真实 update_user payload 结构 `{ group: { name: value } }`。
 * - 不使用硬编码数组自证；通过参数化 + 真实 schema 枚举敏感字段。
 *
 * 真实后端契约证据（observed，详见 START_SNAPSHOT.md）：
 * - `app/core/config.py:1451-1513` update_user：按 `data[group][name]` 逐字段 set。
 * - `app/models/ConfigBase.py:891-946` ConfigItem.setValue 对 EncryptValidator：
 *   - 明文未变化 → return False（不写盘）。
 *   - 明文变化 → 加密为新密文并写盘。
 * - 因此：keep=省略字段；replace=传新明文；clear=传空串 ""。
 */

import { existsSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import type { parse as SfcParseFn } from 'vue/compiler-sfc'
import { buildNestedPatch } from '@/composables/useUserEditShared'
import type { SensitiveSaveIntent } from '@/composables/useSensitiveFieldStrategy'
import { resolveSensitiveSaveIntent } from '@/composables/useSensitiveFieldStrategy'

// ============================================================
// 真实 MaaEnd 用户敏感字段路径（来源：app/models/config.py MaaEndUserConfig）
// ============================================================

/**
 * MaaEnd 真实敏感字段路径（observed，app/models/config.py:331,428,767,803,855）：
 * - Info.Password：ConfigItem("Info", "Password", "", EncryptValidator())
 * - Info.SklandToken：ConfigItem("Info", "SklandToken", "", EncryptValidator())
 * - Notify.ServerChanKey：ConfigItem("Notify", "ServerChanKey", "", EncryptValidator())
 *
 * 这些是后端 update_user payload 的真实 group.name 路径。
 */
const MAA_END_SENSITIVE_FIELDS = [
  'Info.Password',
  'Info.SklandToken',
  'Notify.ServerChanKey',
] as const

type MaaEndSensitiveField = (typeof MAA_END_SENSITIVE_FIELDS)[number]

// ============================================================
// 模拟 MaaEndUserEdit.vue 中 handleSensitiveSave 的核心契约
// ============================================================

/**
 * 模拟 MaaEndUserEdit.vue:handleSensitiveSave 的 patch 构造逻辑。
 *
 * 真实实现（observed，frontend/src/views/EditView/User/MaaEndUserEdit.vue:418-460）：
 * ```ts
 * const handleSensitiveSave = async (key, intent, value?) => {
 *   if (intent === 'keep') {
 *     sensitiveDirtyMap[key] = false
 *     return  // 不发送给后端
 *   }
 *   const patchValue = intent === 'replace' ? (value ?? '') : ''
 *   const patch = buildNestedPatch(key, patchValue)
 *   isSaving.value = true
 *   try {
 *     await updateUser(scriptId, userId, patch)
 *     sensitiveDirtyMap[key] = false
 *     // 调用子组件 reset 草稿
 *   } catch (error) {
 *     // 保留输入；标记 dirty；展示脱敏错误
 *   } finally {
 *     isSaving.value = false
 *   }
 * }
 * ```
 *
 * 本函数仅负责 patch 构造与意图判定，不执行真实 API 调用；
 * 由测试用 vi.fn() 模拟 updateUser 并断言调用 payload。
 */
const applySensitiveSaveIntent = (
  key: string,
  intent: SensitiveSaveIntent
): { shouldCallApi: boolean; patch: Record<string, any> } => {
  if (intent.kind === 'keep') {
    return { shouldCallApi: false, patch: {} }
  }
  const patchValue = intent.kind === 'replace' ? (intent.value ?? '') : ''
  const patch = buildNestedPatch(key, patchValue)
  return { shouldCallApi: true, patch }
}

// ============================================================
// 测试：keep/replace/clear 意图 → 后端 patch 契约
// ============================================================

describe('MaaEndUserEdit 敏感字段保存协议（Lane 06 任务书第 2 条）', () => {
  describe('keep 意图：未触碰字段省略，不调用后端', () => {
    MAA_END_SENSITIVE_FIELDS.forEach(field => {
      it(`${field}：blur 时草稿为空且未显式清空 → 不调用 updateUser`, () => {
        const intent = resolveSensitiveSaveIntent('', false)
        expect(intent.kind).toBe('keep')

        const result = applySensitiveSaveIntent(field, intent)
        expect(result.shouldCallApi).toBe(false)
        expect(result.patch).toEqual({})
      })
    })
  })

  describe('replace 意图：发送新明文，后端加密为新密文', () => {
    const replaceCases: Array<{ field: MaaEndSensitiveField; value: string }> = [
      { field: 'Info.Password', value: 'new-maaend-pwd-12345' },
      { field: 'Info.SklandToken', value: 'new-skland-token-abcdef' },
      { field: 'Notify.ServerChanKey', value: 'new-sendkey-xyz-789' },
    ]

    replaceCases.forEach(({ field, value }) => {
      it(`${field}：用户输入新值 → patch 含新明文`, () => {
        const intent = resolveSensitiveSaveIntent(value, false)
        expect(intent.kind).toBe('replace')
        expect(intent.kind === 'replace' && intent.value).toBe(value)

        const result = applySensitiveSaveIntent(field, intent)
        expect(result.shouldCallApi).toBe(true)

        // 断言 patch 结构与真实后端 update_user 契约一致
        const [group, name] = field.split('.')
        expect(result.patch).toEqual({ [group]: { [name]: value } })
      })
    })
  })

  describe('clear 意图：发送空串 ""，后端加密为空密文', () => {
    MAA_END_SENSITIVE_FIELDS.forEach(field => {
      it(`${field}：用户点击“清空原值” → patch 含空串`, () => {
        const intent = resolveSensitiveSaveIntent('', true)
        expect(intent.kind).toBe('clear')

        const result = applySensitiveSaveIntent(field, intent)
        expect(result.shouldCallApi).toBe(true)

        const [group, name] = field.split('.')
        expect(result.patch).toEqual({ [group]: { [name]: '' } })
      })
    })
  })

  describe('混合意图：三字段同时操作', () => {
    it('Password=replace + SklandToken=keep + ServerChanKey=clear → patch 只含 Password 和 ServerChanKey=""', () => {
      const passwordResult = applySensitiveSaveIntent(
        'Info.Password',
        resolveSensitiveSaveIntent('new-pwd', false)
      )
      const sklandResult = applySensitiveSaveIntent(
        'Info.SklandToken',
        resolveSensitiveSaveIntent('', false)
      )
      const serverChanResult = applySensitiveSaveIntent(
        'Notify.ServerChanKey',
        resolveSensitiveSaveIntent('', true)
      )

      // 合并 patch（模拟批量保存）
      const mergedPatch: Record<string, any> = {}
      ;[passwordResult, sklandResult, serverChanResult].forEach(({ shouldCallApi, patch }) => {
        if (shouldCallApi) {
          Object.keys(patch).forEach(group => {
            mergedPatch[group] = { ...(mergedPatch[group] ?? {}), ...patch[group] }
          })
        }
      })

      // keep 字段 SklandToken 不在 patch 中（保持原密文）
      expect(mergedPatch).not.toHaveProperty('Info.SklandToken')
      // 也不应该有 Info.SklandToken 字段
      expect(mergedPatch.Info).not.toHaveProperty('SklandToken')

      // replace 字段含新明文
      expect(mergedPatch.Info.Password).toBe('new-pwd')
      // clear 字段含空串
      expect(mergedPatch.Notify.ServerChanKey).toBe('')
    })
  })
})

// ============================================================
// 测试：handleSensitiveSave 完整流程（含 API 调用与错误处理）
// ============================================================

/**
 * 模拟 MaaEndUserEdit.vue 中 handleSensitiveSave 的完整流程：
 * - keep：不调用 updateUser，清除 dirty 标志
 * - replace/clear：调用 updateUser，成功后清除 dirty + reset 草稿；失败保留输入
 */
const simulateHandleSensitiveSave = async (
  key: string,
  intent: SensitiveSaveIntent,
  updateUser: (patch: Record<string, unknown>) => Promise<unknown>,
  options: {
    resetDraft?: () => void
    setDirty?: (key: string, dirty: boolean) => void
    setSaveError?: (msg: string) => void
    clearSaveError?: () => void
  } = {}
): Promise<{ success: boolean }> => {
  const { resetDraft, setDirty, setSaveError, clearSaveError } = options

  if (intent.kind === 'keep') {
    setDirty?.(key, false)
    return { success: true }
  }

  const patchValue = intent.kind === 'replace' ? (intent.value ?? '') : ''
  const patch = buildNestedPatch(key, patchValue)

  try {
    const saved = await updateUser(patch)
    if (saved === false) {
      throw new Error('用户配置更新未成功')
    }
    setDirty?.(key, false)
    resetDraft?.()
    clearSaveError?.()
    return { success: true }
  } catch (error) {
    const rawMsg = error instanceof Error ? error.message : String(error)
    const safeMsg = rawMsg.length > 200 ? `${rawMsg.slice(0, 200)}…` : rawMsg
    setSaveError?.(`敏感字段 ${key} 保存失败: ${safeMsg}`)
    setDirty?.(key, true)
    return { success: false }
  }
}

describe('MaaEndUserEdit handleSensitiveSave 完整流程（Lane 06 任务书第 5 条）', () => {
  it('keep：不调用 updateUser，清除 dirty 标志', async () => {
    const updateUser = vi.fn().mockResolvedValue(undefined)
    const setDirty = vi.fn()
    const resetDraft = vi.fn()

    const result = await simulateHandleSensitiveSave(
      'Info.Password',
      resolveSensitiveSaveIntent('', false),
      updateUser,
      { resetDraft, setDirty }
    )

    expect(result.success).toBe(true)
    expect(updateUser).not.toHaveBeenCalled()
    expect(setDirty).toHaveBeenCalledWith('Info.Password', false)
    // keep 意图不应调用 resetDraft（草稿本来就是空）
    expect(resetDraft).not.toHaveBeenCalled()
  })

  it('replace：调用 updateUser 传新明文，成功后清除 dirty + reset 草稿', async () => {
    const updateUser = vi.fn().mockResolvedValue(undefined)
    const setDirty = vi.fn()
    const resetDraft = vi.fn()
    const clearSaveError = vi.fn()

    const result = await simulateHandleSensitiveSave(
      'Info.Password',
      resolveSensitiveSaveIntent('new-maaend-pwd-123', false),
      updateUser,
      { resetDraft, setDirty, clearSaveError }
    )

    expect(result.success).toBe(true)
    expect(updateUser).toHaveBeenCalledTimes(1)
    // 关键：patch 结构符合后端 update_user 真实契约
    expect(updateUser).toHaveBeenCalledWith({ Info: { Password: 'new-maaend-pwd-123' } })
    expect(setDirty).toHaveBeenCalledWith('Info.Password', false)
    expect(resetDraft).toHaveBeenCalledTimes(1)
    expect(clearSaveError).toHaveBeenCalledTimes(1)
  })

  it('clear：调用 updateUser 传空串，成功后清除 dirty + reset 草稿', async () => {
    const updateUser = vi.fn().mockResolvedValue(undefined)
    const setDirty = vi.fn()
    const resetDraft = vi.fn()

    const result = await simulateHandleSensitiveSave(
      'Notify.ServerChanKey',
      resolveSensitiveSaveIntent('', true),
      updateUser,
      { resetDraft, setDirty }
    )

    expect(result.success).toBe(true)
    expect(updateUser).toHaveBeenCalledWith({ Notify: { ServerChanKey: '' } })
    expect(setDirty).toHaveBeenCalledWith('Notify.ServerChanKey', false)
    expect(resetDraft).toHaveBeenCalledTimes(1)
  })

  it('replace 保存失败：保留输入（不清空草稿），标记 dirty，设置 saveError', async () => {
    const updateUser = vi.fn().mockRejectedValue(new Error('服务器 500'))
    const setDirty = vi.fn()
    const resetDraft = vi.fn()
    const setSaveError = vi.fn()

    const result = await simulateHandleSensitiveSave(
      'Info.SklandToken',
      resolveSensitiveSaveIntent('new-token-value', false),
      updateUser,
      { resetDraft, setDirty, setSaveError }
    )

    expect(result.success).toBe(false)
    expect(updateUser).toHaveBeenCalledWith({ Info: { SklandToken: 'new-token-value' } })
    // 关键：保存失败时不调用 resetDraft，保留用户输入
    expect(resetDraft).not.toHaveBeenCalled()
    // 标记 dirty
    expect(setDirty).toHaveBeenCalledWith('Info.SklandToken', true)
    // 设置 saveError，且错误消息经过脱敏（截断）
    expect(setSaveError).toHaveBeenCalledWith(
      expect.stringContaining('敏感字段 Info.SklandToken 保存失败')
    )
    expect(setSaveError).toHaveBeenCalledWith(expect.stringContaining('服务器 500'))
  })

  it('updateUser 返回 false 时同样按保存失败处理', async () => {
    const updateUser = vi.fn().mockResolvedValue(false)
    const setDirty = vi.fn()
    const resetDraft = vi.fn()
    const setSaveError = vi.fn()

    const result = await simulateHandleSensitiveSave(
      'Info.Password',
      resolveSensitiveSaveIntent('not-saved', false),
      updateUser,
      { resetDraft, setDirty, setSaveError }
    )

    expect(result.success).toBe(false)
    expect(resetDraft).not.toHaveBeenCalled()
    expect(setDirty).toHaveBeenCalledWith('Info.Password', true)
    expect(setSaveError).toHaveBeenCalledWith(expect.stringContaining('用户配置更新未成功'))
  })

  it('clear 保存失败：保留 explicitCleared 状态，标记 dirty', async () => {
    const updateUser = vi.fn().mockRejectedValue(new Error('网络错误'))
    const setDirty = vi.fn()
    const resetDraft = vi.fn()
    const setSaveError = vi.fn()

    const result = await simulateHandleSensitiveSave(
      'Info.Password',
      resolveSensitiveSaveIntent('', true),
      updateUser,
      { resetDraft, setDirty, setSaveError }
    )

    expect(result.success).toBe(false)
    expect(updateUser).toHaveBeenCalledWith({ Info: { Password: '' } })
    expect(resetDraft).not.toHaveBeenCalled()
    expect(setDirty).toHaveBeenCalledWith('Info.Password', true)
    expect(setSaveError).toHaveBeenCalledWith(
      expect.stringContaining('敏感字段 Info.Password 保存失败')
    )
  })

  it('错误消息超 200 字符时被截断（脱敏）', async () => {
    const longErrorMsg = 'x'.repeat(300)
    const updateUser = vi.fn().mockRejectedValue(new Error(longErrorMsg))
    const setSaveError = vi.fn()

    await simulateHandleSensitiveSave(
      'Info.Password',
      resolveSensitiveSaveIntent('new-pwd', false),
      updateUser,
      { setSaveError }
    )

    const capturedMsg = setSaveError.mock.calls[0][0] as string
    // 截断后应包含前 200 字符 + 省略号
    expect(capturedMsg.length).toBeLessThan(longErrorMsg.length + 50)
    expect(capturedMsg).toContain('…')
    expect(capturedMsg).toContain('x'.repeat(200))
  })
})

// ============================================================
// 测试：buildNestedPatch 与后端 update_user 契约一致
// ============================================================

describe('buildNestedPatch 与后端 update_user 契约一致', () => {
  /**
   * 真实后端 update_user 实现（observed，app/core/config.py:1451-1513）：
   * ```python
   * for group, items in data.items():
   *     for name, value in items.items():
   *         await self.ScriptConfig[script_uid].UserData[user_uid].set(group, name, value)
   * ```
   *
   * 即：前端 patch 必须是 `{ group: { name: value } }` 嵌套结构。
   */

  it('Info.Password → { Info: { Password: value } }', () => {
    expect(buildNestedPatch('Info.Password', 'new-pwd')).toEqual({
      Info: { Password: 'new-pwd' },
    })
  })

  it('Info.SklandToken → { Info: { SklandToken: value } }', () => {
    expect(buildNestedPatch('Info.SklandToken', 'new-token')).toEqual({
      Info: { SklandToken: 'new-token' },
    })
  })

  it('Notify.ServerChanKey → { Notify: { ServerChanKey: value } }', () => {
    expect(buildNestedPatch('Notify.ServerChanKey', 'new-key')).toEqual({
      Notify: { ServerChanKey: 'new-key' },
    })
  })

  it('空串 clear 值：{ Info: { Password: "" } }', () => {
    expect(buildNestedPatch('Info.Password', '')).toEqual({
      Info: { Password: '' },
    })
  })

  it('单层路径：userName → { userName: value }（不嵌套）', () => {
    expect(buildNestedPatch('userName', 'alice')).toEqual({ userName: 'alice' })
  })

  it('空路径返回空对象', () => {
    expect(buildNestedPatch('', 'value')).toEqual({})
  })

  it('三层路径：A.B.C → { A: { B: { C: value } } }', () => {
    expect(buildNestedPatch('A.B.C', 'val')).toEqual({ A: { B: { C: 'val' } } })
  })
})

// ============================================================
// 源码级静态解析：真实组件 SFC 与后端契约验证
//
// vitest 运行在 Node 环境（无 jsdom / @vue/test-utils），无法 mount 组件；
// 以下各节用 vue/compiler-sfc 解析真实 SFC，对模板与 <script setup> 的真实
// 内容断言：组件回归（改字段绑定、改保存协议、改 reset 链）会使断言真实失败。
//
// 原「PR #302 MaaEnd 新登录接入契约」一节只对测试自建的布尔量与硬编码字符串
// 断言（不读源码、不挂载组件），且其注释引用的后端 game_on_stop / GAME_ON_STOP
// 在本工作树不存在（app/ 与 frontend/src 全文无此符号）；该节已整体替换为
// 下方对真实前后端源码的断言。
// ============================================================

const frontendRoot = resolve(__dirname, '../../../..')
const repoRoot = resolve(frontendRoot, '..')

// vite.config.ts 把裸导入 `vue` alias 到 vue.runtime.esm-bundler.js（文件路径），
// 这会连带把 `vue/compiler-sfc` 子路径改写坏；用 Node 自身的解析器加载真实包。
const requireModule = createRequire(import.meta.url)
const { parse } = requireModule('vue/compiler-sfc') as { parse: typeof SfcParseFn }

interface ParsedSfc {
  source: string
  template: string
  script: string
}

const parseSfc = (absolutePath: string): ParsedSfc => {
  const source = readFileSync(absolutePath, 'utf8')
  const { descriptor, errors } = parse(source, { filename: absolutePath })
  if (errors.length > 0) {
    throw new Error(`SFC 解析失败: ${absolutePath}: ${String(errors[0])}`)
  }
  return {
    source,
    template: descriptor.template?.content ?? '',
    script: descriptor.scriptSetup?.content ?? '',
  }
}

/** 按声明起点提取大括号平衡的完整代码块（模板字符串插值 ${} 的括号自平衡）。 */
const extractBlock = (script: string, startMarker: string): string => {
  const start = script.indexOf(startMarker)
  if (start === -1) {
    throw new Error(`未找到源码块: ${startMarker}`)
  }
  const braceStart = script.indexOf('{', start)
  if (braceStart === -1) {
    throw new Error(`源码块无函数体: ${startMarker}`)
  }
  let depth = 0
  for (let index = braceStart; index < script.length; index += 1) {
    if (script[index] === '{') {
      depth += 1
    } else if (script[index] === '}') {
      depth -= 1
      if (depth === 0) {
        return script.slice(start, index + 1)
      }
    }
  }
  throw new Error(`源码块大括号不平衡: ${startMarker}`)
}

/** 按正则提取捕获组 1，匹配不到时抛错（保证断言的是真实源码而非空串）。 */
const mustMatch = (source: string, pattern: RegExp): string => {
  const matched = source.match(pattern)
  if (!matched || matched[1] === undefined) {
    throw new Error(`未在源码中匹配到: ${String(pattern)}`)
  }
  return matched[1]
}

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const basicInfo = parseSfc(resolve(frontendRoot, 'src/views/MaaEndUserEdit/BasicInfoSection.vue'))
const skyland = parseSfc(resolve(frontendRoot, 'src/views/MaaEndUserEdit/SkylandConfigSection.vue'))
const notify = parseSfc(resolve(frontendRoot, 'src/views/MaaEndUserEdit/NotifyConfigSection.vue'))
const parentSfc = parseSfc(resolve(frontendRoot, 'src/views/EditView/User/MaaEndUserEdit.vue'))

describe('MaaEnd 密码字段与登录契约（源码级验证）', () => {
  it('BasicInfoSection 真实渲染密码字段：a-input-password 草稿驱动 + blur 保存协议', () => {
    expect(basicInfo.template).toContain('<a-input-password')
    expect(basicInfo.template).toContain(':value="passwordDraft"')
    expect(basicInfo.template).toContain('@blur="handlePasswordBlur"')
    expect(basicInfo.template).toContain('autocomplete="new-password"')
    expect(basicInfo.template).toContain('@click="handleClearPassword"')
    expect(basicInfo.template).toContain('清空原值')
  })

  it('密码明文不直接绑定 formData：草稿初值为空串，存在性判断只产出布尔', () => {
    expect(basicInfo.template).not.toContain('v-model:value="formData.Info.Password"')
    expect(basicInfo.template).not.toContain('v-model="formData.Info.Password"')
    expect(basicInfo.script).toContain("const passwordDraft = ref('')")
    const hasStored = extractBlock(basicInfo.script, 'const hasStoredPassword')
    expect(hasStored).toContain("typeof stored === 'string' && stored.length > 0")
  })

  // 后端源码位于同一仓库工作树；仅当 frontend 目录被单独检出（无 app/）时跳过。
  const autoProxyPath = resolve(repoRoot, 'app/task/MaaEnd/AutoProxy.py')
  const manualReviewPath = resolve(repoRoot, 'app/task/MaaEnd/ManualReview.py')
  const modelsConfigPath = resolve(repoRoot, 'app/models/config.py')
  const backendAvailable =
    existsSync(autoProxyPath) && existsSync(manualReviewPath) && existsSync(modelsConfigPath)

  it.skipIf(!backendAvailable)(
    '后端登录真实消费 Info.Id + Info.Password（AutoProxy / ManualReview 源码）',
    () => {
      const loginCallPattern =
        /await login\(\s*self\.cur_user_config\.get\("Info", "Id"\),\s*self\.cur_user_config\.get\("Info", "Password"\),\s*emulator_info,?\s*\)/
      expect(readFileSync(autoProxyPath, 'utf8')).toMatch(loginCallPattern)
      expect(readFileSync(manualReviewPath, 'utf8')).toMatch(loginCallPattern)
      // 若未来后端移除密码登录（如 PR #302 真正落地），此断言应当失败，
      // 提示同步更新 BasicInfoSection 密码字段的文案与保存协议说明。
    }
  )

  it.skipIf(!backendAvailable)(
    'MaaEndUserConfig schema 以 EncryptValidator 声明本测试覆盖的全部敏感字段',
    () => {
      const modelsSource = readFileSync(modelsConfigPath, 'utf8')
      const classStart = modelsSource.indexOf('class MaaEndUserConfig')
      const classEnd = modelsSource.indexOf('class MaaEndConfig')
      expect(classStart).toBeGreaterThan(-1)
      expect(classEnd).toBeGreaterThan(classStart)
      const classBlock = modelsSource.slice(classStart, classEnd)
      MAA_END_SENSITIVE_FIELDS.forEach(field => {
        const [group, name] = field.split('.')
        expect(classBlock).toMatch(
          new RegExp(`ConfigItem\\(\\s*"${group}",\\s*"${name}",\\s*"",\\s*EncryptValidator\\(\\)`)
        )
      })
    }
  )

  it('game_on_stop / GAME_ON_STOP 未接入 MaaEndUserEdit 组件族（真实源码验证）', () => {
    const familySources = [parentSfc.source, basicInfo.source, skyland.source, notify.source]
    familySources.forEach(source => {
      expect(source).not.toContain('game_on_stop')
      expect(source).not.toContain('GAME_ON_STOP')
      expect(source).not.toContain('GameOnStop')
    })
  })
})

// ============================================================
// 子组件 sensitiveSave 事件契约（源码级静态解析，Lane 06 任务书第 2 条）
//
// 原实现在测试内重新拼写 simulateXxxBlur 函数并断言其自身行为，与组件源码
// 脱钩（组件回归不会使其失败）；「签名一致」用例更是字面量与字面量比较。
// 现改为逐组件解析真实 <script setup>：断言真实 blur/input 处理器、真实
// defineEmits 签名与真实 defineExpose 暴露面。
// ============================================================

interface SensitiveComponentContract {
  name: string
  sfc: ParsedSfc
  key: string
  blurMarker: string
  inputMarker: string
  draftVar: string
  clearedVar: string
  resetMethod: string
  dirtyMethod: string
  watchPattern: RegExp
}

const sensitiveComponents: SensitiveComponentContract[] = [
  {
    name: 'BasicInfoSection',
    sfc: basicInfo,
    key: 'Info.Password',
    blurMarker: 'const handlePasswordBlur',
    inputMarker: 'const handlePasswordInput',
    draftVar: 'passwordDraft',
    clearedVar: 'passwordExplicitlyCleared',
    resetMethod: 'resetPasswordDraft',
    dirtyMethod: 'isPasswordDirty',
    watchPattern: /watch\(\s*\(\) => props\.formData\?\.Info\?\.Password,/,
  },
  {
    name: 'SkylandConfigSection',
    sfc: skyland,
    key: 'Info.SklandToken',
    blurMarker: 'const handleTokenBlur',
    inputMarker: 'const handleTokenInput',
    draftVar: 'tokenDraft',
    clearedVar: 'tokenExplicitlyCleared',
    resetMethod: 'resetTokenDraft',
    dirtyMethod: 'isTokenDirty',
    watchPattern: /watch\(\s*\(\) => props\.formData\?\.Info\?\.SklandToken,/,
  },
  {
    name: 'NotifyConfigSection',
    sfc: notify,
    key: 'Notify.ServerChanKey',
    blurMarker: 'const handleServerChanKeyBlur',
    inputMarker: 'const handleServerChanKeyInput',
    draftVar: 'serverChanKeyDraft',
    clearedVar: 'serverChanKeyExplicitlyCleared',
    resetMethod: 'resetServerChanKeyDraft',
    dirtyMethod: 'isServerChanKeyDirty',
    watchPattern: /watch\(\s*\(\) => props\.formData\?\.Notify\?\.ServerChanKey,/,
  },
]

describe('子组件 sensitiveSave 事件契约（源码级静态解析）', () => {
  const unifiedEmitSignature =
    "sensitiveSave: [key: string, intent: 'keep' | 'replace' | 'clear', value?: string]"

  sensitiveComponents.forEach(({ name, sfc }) => {
    it(`${name} defineEmits 声明统一的 sensitiveSave / sensitiveDirtyChange 签名`, () => {
      expect(sfc.script).toContain(unifiedEmitSignature)
      expect(sfc.script).toContain('sensitiveDirtyChange: [key: string, dirty: boolean]')
    })
  })

  sensitiveComponents.forEach(({ name, sfc, key, blurMarker, draftVar, clearedVar }) => {
    it(`${name} blur 真实发出 keep/replace/clear，且 clear 优先于 keep/replace`, () => {
      const handler = extractBlock(sfc.script, blurMarker)
      // clear：显式清空 → 发送空串
      expect(handler).toContain(`emit('sensitiveSave', '${key}', 'clear', '')`)
      // keep：不带 value 参数（对应后端「省略字段 = 保持原值」语义）
      expect(handler).toContain(`emit('sensitiveSave', '${key}', 'keep')`)
      // replace：携带草稿明文
      expect(handler).toContain(`emit('sensitiveSave', '${key}', 'replace', ${draftVar}.value)`)
      // 分支顺序：explicitCleared 守卫先于草稿判空 → clear 优先于 keep
      const clearGuardIndex = handler.indexOf(`${clearedVar}.value`)
      const keepGuardIndex = handler.indexOf(`${draftVar}.value === ''`)
      expect(clearGuardIndex).toBeGreaterThan(-1)
      expect(keepGuardIndex).toBeGreaterThan(clearGuardIndex)
    })
  })

  sensitiveComponents.forEach(({ name, sfc, key, inputMarker, clearedVar }) => {
    it(`${name} 重新输入撤销显式清空（replace 优先于 clear），并发出真实 dirty 状态`, () => {
      const handler = extractBlock(sfc.script, inputMarker)
      expect(handler).toContain(`if (val !== '' && ${clearedVar}.value)`)
      expect(handler).toContain(`${clearedVar}.value = false`)
      expect(handler).toMatch(
        new RegExp(
          `emit\\(\\s*'sensitiveDirtyChange',\\s*'${escapeRegExp(key)}',\\s*val !== '' \\|\\| ${clearedVar}\\.value,?\\s*\\)`
        )
      )
    })
  })

  sensitiveComponents.forEach(({ name, sfc, resetMethod, dirtyMethod, watchPattern }) => {
    it(`${name} defineExpose 提供草稿 reset 与 dirty 查询，权威值变化时自清草稿`, () => {
      expect(sfc.script).toContain('defineExpose({')
      expect(sfc.script).toContain(`${resetMethod}: `)
      expect(sfc.script).toContain(`${dirtyMethod}: `)
      expect(sfc.script).toMatch(watchPattern)
    })
  })

  it('父组件对三个子组件统一绑定 @sensitive-save / @sensitive-dirty-change', () => {
    const sensitiveSaveBindings =
      parentSfc.template.match(/@sensitive-save="handleSensitiveSave"/g) ?? []
    const dirtyChangeBindings =
      parentSfc.template.match(/@sensitive-dirty-change="handleSensitiveDirtyChange"/g) ?? []
    expect(sensitiveSaveBindings).toHaveLength(3)
    expect(dirtyChangeBindings).toHaveLength(3)
    expect(parentSfc.template).toContain('<BasicInfoSection')
    expect(parentSfc.template).toContain('<SkylandConfigSection')
    expect(parentSfc.template).toContain('<NotifyConfigSection')
  })
})

// ============================================================
// MaaEndUserEdit isDirty 综合状态：从真实源码提取表达式并求值
//
// 原实现在测试内重新拼写 (a || b) && !c 布尔式并对其自身断言，组件表达式
// 回归（如误改 || 为 &&、去掉 !isSaving）不会使其失败。现改为从
// MaaEndUserEdit.vue 提取真实 computed 表达式求值，表达式变化即失败。
// ============================================================

describe('MaaEndUserEdit 未保存保护 isDirty 综合状态（真实源码表达式求值）', () => {
  it('isSensitiveDirty：任一敏感字段 dirty 即为 true（真实表达式）', () => {
    const expression = mustMatch(
      parentSfc.script,
      /const isSensitiveDirty = computed\(\(\) => ([^\r\n]+)\)\r?\n/
    )
    expect(expression).toContain('sensitiveDirtyMap')
    const evaluate = new Function('sensitiveDirtyMap', `return ${expression}`) as (
      map: Record<string, boolean>
    ) => boolean

    expect(evaluate({})).toBe(false)
    expect(evaluate({ 'Info.Password': false })).toBe(false)
    expect(evaluate({ 'Info.Password': true })).toBe(true)
    expect(evaluate({ 'Info.Password': false, 'Info.SklandToken': false })).toBe(false)
    expect(evaluate({ 'Info.Password': false, 'Info.SklandToken': true })).toBe(true)
    expect(
      evaluate({ 'Info.Password': false, 'Info.SklandToken': false, 'Notify.ServerChanKey': true })
    ).toBe(true)
  })

  it('isDirty：常规脏 OR 敏感脏，且保存中不算 dirty（真实表达式）', () => {
    const expression = mustMatch(
      parentSfc.script,
      /const isDirty = computed\(\s*\(\) =>\s*([^\r\n]+)\r?\n\)/
    )
    const evaluate = new Function(
      'dirtyTracker',
      'isSensitiveDirty',
      'isSaving',
      `return ${expression}`
    ) as (
      dirtyTracker: { hasUnsavedChanges: { value: boolean } },
      isSensitiveDirty: { value: boolean },
      isSaving: { value: boolean }
    ) => boolean
    const run = (regularDirty: boolean, sensitiveDirty: boolean, saving: boolean): boolean =>
      evaluate(
        { hasUnsavedChanges: { value: regularDirty } },
        { value: sensitiveDirty },
        { value: saving }
      )

    expect(run(true, false, false)).toBe(true)
    expect(run(false, true, false)).toBe(true)
    expect(run(true, true, true)).toBe(false)
    expect(run(false, false, false)).toBe(false)
  })

  it('子组件 dirty 事件真实写入 sensitiveDirtyMap 并联动 dirtyTracker', () => {
    const handler = extractBlock(parentSfc.script, 'const handleSensitiveDirtyChange')
    expect(handler).toContain('sensitiveDirtyMap[key] = dirty')
    expect(handler).toContain('dirtyTracker.markDirty()')
  })

  it('useUnsavedChangesGuard 接入真实 isDirty / isSaving', () => {
    expect(parentSfc.script.replace(/\s+/g, ' ')).toContain(
      'useUnsavedChangesGuard({ isDirty, isSaving,'
    )
  })
})

// ============================================================
// 权威 reload 与 handleSensitiveSave 真实实现（源码级锚定，Lane 06 任务书第 3、5 条）
//
// 原实现在测试内自建 dirtyMap / vi.fn 并由测试自己调用后断言「被调用过」，
// 与 loadUserData 真实清理链无关。现改为解析 MaaEndUserEdit.vue 真实函数体，
// 同时锚定本文件前半部分镜像函数（applySensitiveSaveIntent /
// simulateHandleSensitiveSave）与真实 handleSensitiveSave 的语义一致性。
// ============================================================

describe('权威 reload 与 handleSensitiveSave 真实实现（源码级锚定）', () => {
  it('loadUserData 权威 reload 后重置全部敏感草稿、dirtyMap、tracker 与错误横幅', () => {
    const body = extractBlock(parentSfc.script, 'const loadUserData')
    expect(body).toContain('basicInfoRef.value?.resetPasswordDraft?.()')
    expect(body).toContain('skylandRef.value?.resetTokenDraft?.()')
    expect(body).toContain('notifyRef.value?.resetServerChanKeyDraft?.()')
    expect(body).toContain('sensitiveDirtyMap[k] = false')
    expect(body).toContain('dirtyTracker.reset()')
    expect(body).toContain('clearSaveError()')
  })

  it('handleSensitiveSave 真实实现与本文件镜像函数语义一致（防镜像漂移）', () => {
    const body = extractBlock(parentSfc.script, 'const handleSensitiveSave')

    // keep：清 dirty 后直接 return，不构造 patch（keep 守卫先于 patch 构造）
    const keepGuardIndex = body.indexOf("if (intent === 'keep')")
    const patchIndex = body.indexOf('buildNestedPatch(key, patchValue)')
    expect(keepGuardIndex).toBeGreaterThan(-1)
    expect(patchIndex).toBeGreaterThan(keepGuardIndex)

    // replace/clear 的 patch 值语义与镜像一致：replace 用 value，clear 用空串
    expect(body).toContain("const patchValue = intent === 'replace' ? (value ?? '') : ''")

    // 成功路径：清 dirty、按 key 路由到对应子组件 reset、清除错误横幅
    expect(body).toContain('sensitiveDirtyMap[key] = false')
    expect(body).toContain("if (key === 'Info.Password')")
    expect(body).toContain('basicInfoRef.value?.resetPasswordDraft?.()')
    expect(body).toContain("} else if (key === 'Info.SklandToken')")
    expect(body).toContain('skylandRef.value?.resetTokenDraft?.()')
    expect(body).toContain("} else if (key === 'Notify.ServerChanKey')")
    expect(body).toContain('notifyRef.value?.resetServerChanKeyDraft?.()')
    expect(body).toContain('clearSaveError()')

    // 失败路径：标 dirty、错误消息 200 字符截断脱敏；finally 复位 isSaving
    expect(body).toContain('sensitiveDirtyMap[key] = true')
    expect(body).toContain('rawMsg.length > 200')
    expect(body).toContain('rawMsg.slice(0, 200)')
    expect(body).toContain('setSaveError(`敏感字段 ${key} 保存失败: ${safeMsg}`)')
    expect(body).toContain('isSaving.value = false')
  })

  it('updateUserOrThrow 把 updateUser === false 升级为异常（镜像 saved === false 分支的真实来源）', () => {
    const body = extractBlock(parentSfc.script, 'const updateUserOrThrow')
    expect(body).toContain('if (saved === false)')
    expect(body).toContain("throw new Error('用户配置更新未成功')")
  })
})
