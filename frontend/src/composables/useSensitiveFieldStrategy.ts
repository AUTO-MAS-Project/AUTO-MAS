/**
 * 敏感字段（密码 / 令牌 / 密钥）安全策略。
 *
 * 设计目标（对应 Lane 06 任务书第 2、3 条）：
 * - 默认不回显明文：进入 DOM 的初始值始终为空串，避免明文泄露到 DOM、日志或错误。
 * - 不使用前端臆造的 KEEP/CLEAR sentinel。保存语义严格对齐后端真实契约：
 *   - 保持原值：用户未触碰该字段 → patch 中**省略**该字段，后端不调用 `set`。
 *   - 替换：用户输入了新值 → patch 中传新字符串，后端 `set` 后加密为新密文。
 *   - 清空：用户显式清空 → patch 中传空串 `""`，后端 `set` 后加密为空密文。
 * - 前端日志与错误不得泄露敏感数据：`sanitizeForLog` 把敏感字段值替换为 `'***'`。
 *
 * 后端契约证据（observed，详见 START_SNAPSHOT.md）：
 * - `app/core/config.py:1507-1513` `update_user` 按 `data[group][name]` 逐字段 `set`。
 * - `app/models/ConfigBase.py:1260-1284` `ConfigBase.set` 调用 `ConfigItem.setValue`。
 * - `app/models/ConfigBase.py:891-946` `ConfigItem.setValue` 对 EncryptValidator：
 *   - 明文未变化 → return False（不写盘）。
 *   - 明文变化 → 加密为新密文并写盘。
 * - 因此：省略字段 = 保持；传新值 = 替换；传空串 = 清空（真实清空，非 sentinel）。
 */

import type { SchemaFieldDefinition } from '@/types/schemaForm'
import {
  getFieldPath,
  getFieldOptions,
  isPasswordField,
  isStringField,
  normalizeSchemaGroups,
  setValueByPath,
} from '@/utils/schemaFormCore'

/**
 * 敏感字段保存意图。
 *
 * 与后端真实契约严格对应：
 * - `keep`：用户未触碰，patch 中省略该字段。
 * - `replace`：用户输入新值，patch 中传新字符串。
 * - `clear`：用户显式清空，patch 中传空串 `""`。
 */
export type SensitiveSaveIntent =
  | { kind: 'keep' }
  | { kind: 'replace'; value: string }
  | { kind: 'clear' }

/** 用于 DOM 显示的占位文本，提示用户该字段已存在值但未回显明文。 */
export const SENSITIVE_PLACEHOLDER = '已保存。留空保持原值，输入新值替换'

/** 用于 DOM 显示的“清空后”占位文本。 */
export const SENSITIVE_CLEARED_PLACEHOLDER = '已清空。留空保持清空状态，输入新值替换'

/**
 * 判断字段是否为敏感字段。
 *
 * 覆盖范围：
 * - `format === 'password'` 的 string 类字段（原有 SchemaForm 行为）
 * - `type === 'password'`（原有 SchemaForm 行为）
 * - `field.sensitive === true`（schema 显式声明敏感）
 *
 * 不把 token / secret / key 等关键词硬编码到字段名匹配中，避免误判；
 * schema 显式 `sensitive: true` 是首选声明方式。
 */
export const isSensitiveField = (field: SchemaFieldDefinition): boolean =>
  isPasswordField(field) || field.sensitive === true

/**
 * 获取敏感字段在 DOM 中应显示的值。
 *
 * 始终返回空串，确保明文不进入 DOM 初值。
 * 用户输入由 `a-input-password` 自行管理，保存时由 `getSensitiveSavePatch` 构造 patch。
 */
export const getSensitiveDisplayValue = (): string => ''

/**
 * 根据草稿状态与显式清空标志计算保存意图。
 *
 * - `explicitClear === true` → `clear`：用户显式点击“清空”按钮。
 * - `draft` 为空串或 undefined → `keep`：用户未输入。
 * - `draft` 非空 → `replace`：用户输入新值。
 *
 * 不返回任何 sentinel 值；调用方通过 `applySensitiveIntentToPatch` 把意图写入 patch。
 */
export const resolveSensitiveSaveIntent = (
  draft: string | undefined,
  explicitClear = false
): SensitiveSaveIntent => {
  if (explicitClear) {
    return { kind: 'clear' }
  }
  if (draft === undefined || draft === '') {
    return { kind: 'keep' }
  }
  return { kind: 'replace', value: draft }
}

/**
 * 把单个敏感字段的保存意图应用到 patch 对象。
 *
 * - `keep`：不写入 patch（保持原值，后端不调用 `set`）。
 * - `replace`：按点路径写入新值。
 * - `clear`：按点路径写入空串 `""`。
 *
 * 这是对后端真实契约的直接映射，不引入任何 sentinel。
 */
export const applySensitiveIntentToPatch = (
  patch: Record<string, any>,
  fieldPath: string,
  intent: SensitiveSaveIntent
): void => {
  if (intent.kind === 'keep') {
    return
  }
  setValueByPath(patch, fieldPath, intent.kind === 'clear' ? '' : intent.value)
}

/**
 * 把字段值脱敏后返回；敏感字段值统一替换为 `'***'`，非敏感字段原样返回。
 *
 * 用于 logger.debug / logger.info 等可能记录字段值的场景。
 * 错误消息脱敏见 `sanitizeErrorForLog`。
 */
export const sanitizeFieldValueForLog = (field: SchemaFieldDefinition, value: unknown): unknown => {
  if (!isSensitiveField(field)) {
    return value
  }
  if (value === undefined || value === null || value === '') {
    return value
  }
  return '***'
}

/**
 * 把整个 modelValue 脱敏后返回新对象；原对象不被修改。
 *
 * 用于把表单数据写入日志前的统一脱敏。
 */
export const sanitizeModelForLog = (
  modelValue: Record<string, any>,
  schema: Parameters<typeof normalizeSchemaGroups>[0]
): Record<string, any> => {
  const groups = normalizeSchemaGroups(schema)
  const sensitivePaths = new Set<string>()
  groups.forEach(group => {
    group.fields.forEach(field => {
      if (isSensitiveField(field)) {
        sensitivePaths.add(getFieldPath(field))
      }
    })
  })

  const sanitized = JSON.parse(JSON.stringify(modelValue)) as Record<string, any>
  sensitivePaths.forEach(path => {
    const segments = path.split('.')
    let current: any = sanitized
    for (let i = 0; i < segments.length - 1; i += 1) {
      if (current && typeof current === 'object' && segments[i] in current) {
        current = current[segments[i]]
      } else {
        return
      }
    }
    const last = segments[segments.length - 1]
    if (current && typeof current === 'object' && last in current) {
      const v = current[last]
      if (v !== undefined && v !== null && v !== '') {
        current[last] = '***'
      }
    }
  })
  return sanitized
}

/**
 * 把错误消息中可能包含的敏感字段值替换为 `'***'`。
 *
 * 错误消息通常由后端返回，可能包含字段值；前端展示前必须脱敏。
 * 实现策略：对 schema 中声明的敏感字段，把其当前值作为子串替换为 `'***'`。
 */
export const sanitizeErrorForLog = (
  message: string,
  modelValue: Record<string, any>,
  schema: Parameters<typeof normalizeSchemaGroups>[0]
): string => {
  if (typeof message !== 'string' || message === '') {
    return message
  }
  const groups = normalizeSchemaGroups(schema)
  let sanitized = message
  groups.forEach(group => {
    group.fields.forEach(field => {
      if (!isSensitiveField(field)) {
        return
      }
      const path = getFieldPath(field)
      const value = path.split('.').reduce<any>((current, key) => {
        if (current == null || typeof current !== 'object') {
          return undefined
        }
        return current[key]
      }, modelValue)
      if (typeof value === 'string' && value.length >= 4 && sanitized.includes(value)) {
        sanitized = sanitized.split(value).join('***')
      }
    })
  })
  return sanitized
}

/**
 * 判断敏感字段当前是否处于“已清空”状态。
 *
 * 当 modelValue 中该字段为空串、null 或 undefined 时视为已清空。
 * 用于决定 DOM 占位文本。
 */
export const isSensitiveFieldCleared = (
  modelValue: Record<string, any>,
  field: SchemaFieldDefinition
): boolean => {
  const path = getFieldPath(field)
  const value = path.split('.').reduce<any>((current, key) => {
    if (current == null || typeof current !== 'object') {
      return undefined
    }
    return current[key]
  }, modelValue)
  return value === null || value === '' || value === undefined
}

/**
 * 提供敏感字段在 DOM 中的占位文本。
 *
 * - 字段已清空（modelValue 中为空）：返回 `SENSITIVE_CLEARED_PLACEHOLDER`。
 * - 字段有原值（modelValue 中非空）：返回 `SENSITIVE_PLACEHOLDER`。
 */
export const getSensitivePlaceholder = (
  modelValue: Record<string, any>,
  field: SchemaFieldDefinition
): string => {
  if (isSensitiveFieldCleared(modelValue, field)) {
    return SENSITIVE_CLEARED_PLACEHOLDER
  }
  return SENSITIVE_PLACEHOLDER
}

/**
 * 列出 schema 中所有敏感字段的路径。
 *
 * 用于测试断言“密文不泄漏”覆盖了所有声明为敏感的字段。
 */
export const collectSensitiveFieldPaths = (
  schema: Parameters<typeof normalizeSchemaGroups>[0]
): string[] => {
  const groups = normalizeSchemaGroups(schema)
  const paths: string[] = []
  groups.forEach(group => {
    group.fields.forEach(field => {
      if (isSensitiveField(field)) {
        paths.push(getFieldPath(field))
      }
    })
  })
  return paths
}

/**
 * 校验：给定 modelValue 中，所有敏感字段是否均未以明文形式出现在指定文本中。
 *
 * 用于测试断言“密文不泄漏到日志/错误/DOM 初值”。
 */
export const assertNoSensitiveLeak = (
  text: string,
  modelValue: Record<string, any>,
  schema: Parameters<typeof normalizeSchemaGroups>[0]
): { leaked: boolean; leakedPaths: string[] } => {
  const groups = normalizeSchemaGroups(schema)
  const leakedPaths: string[] = []
  groups.forEach(group => {
    group.fields.forEach(field => {
      if (!isSensitiveField(field)) {
        return
      }
      const path = getFieldPath(field)
      const value = path.split('.').reduce<any>((current, key) => {
        if (current == null || typeof current !== 'object') {
          return undefined
        }
        return current[key]
      }, modelValue)
      if (typeof value === 'string' && value.length >= 4 && text.includes(value)) {
        leakedPaths.push(path)
      }
    })
  })
  return { leaked: leakedPaths.length > 0, leakedPaths }
}

/**
 * 根据敏感字段的草稿状态构造保存 patch。
 *
 * 输入：
 * - `schema`：当前表单 schema，用于枚举所有敏感字段。
 * - `drafts`：用户输入的草稿（字段路径 → 草稿值）。
 * - `explicitClears`：用户显式清空的字段路径集合。
 *
 * 输出：
 * - 一个 patch 对象，**只包含**用户实际触碰（替换或清空）的敏感字段；
 *   未触碰的字段被**省略**，由后端保持原值。
 *
 * 这是对后端真实契约（payload omission = keep）的直接映射。
 *
 * 调用方应把此 patch 与非敏感字段 patch 合并后送后端。
 */
export const buildSensitiveSavePatch = (
  schema: Parameters<typeof normalizeSchemaGroups>[0],
  drafts: Record<string, string>,
  explicitClears: Set<string> = new Set()
): Record<string, any> => {
  const patch: Record<string, any> = {}
  const sensitivePaths = collectSensitiveFieldPaths(schema)
  sensitivePaths.forEach(path => {
    const draft = drafts[path]
    const explicitClear = explicitClears.has(path)
    const intent = resolveSensitiveSaveIntent(draft, explicitClear)
    applySensitiveIntentToPatch(patch, path, intent)
  })
  return patch
}

/**
 * 构造 SchemaForm 的最终保存 payload。
 *
 * 后端返回的 model 可能包含已解密的敏感值，因此不能直接把 model 原样提交：
 * - 先从深拷贝中移除 schema 声明的全部敏感字段；
 * - 再仅写回用户明确替换或清空的敏感 patch；
 * - 非敏感字段完整保留，输入 model 不被修改。
 */
export const buildSchemaSavePayload = (
  modelValue: Record<string, any>,
  schema: Parameters<typeof normalizeSchemaGroups>[0],
  sensitivePatch: Record<string, any>
): Record<string, any> => {
  const payload = JSON.parse(JSON.stringify(modelValue || {})) as Record<string, any>

  const deletePath = (target: Record<string, any>, path: string): void => {
    const segments = path.split('.')
    const parents: Array<{ value: Record<string, any>; key: string }> = []
    let current: Record<string, any> = target
    for (let index = 0; index < segments.length - 1; index += 1) {
      const key = segments[index]
      const next: unknown = current[key]
      if (!next || typeof next !== 'object' || Array.isArray(next)) {
        return
      }
      parents.push({ value: current, key })
      current = next as Record<string, any>
    }
    delete current[segments[segments.length - 1]]
    for (let index = parents.length - 1; index >= 0; index -= 1) {
      const { value, key } = parents[index]
      const child = value[key]
      if (
        child &&
        typeof child === 'object' &&
        !Array.isArray(child) &&
        Object.keys(child).length === 0
      ) {
        delete value[key]
      } else {
        break
      }
    }
  }

  const readOwnPath = (
    target: Record<string, any>,
    path: string
  ): { found: boolean; value?: any } => {
    const segments = path.split('.')
    let current: any = target
    for (const key of segments) {
      if (
        current == null ||
        typeof current !== 'object' ||
        !Object.prototype.hasOwnProperty.call(current, key)
      ) {
        return { found: false }
      }
      current = current[key]
    }
    return { found: true, value: current }
  }

  collectSensitiveFieldPaths(schema).forEach(path => {
    deletePath(payload, path)
    const replacement = readOwnPath(sensitivePatch, path)
    if (replacement.found) {
      setValueByPath(payload, path, replacement.value)
    }
  })

  return payload
}

/**
 * 检查敏感字段是否存在用户触碰（需要保存）的变更。
 *
 * 用于 `useUnsavedChangesGuard` 的 `isDirty` 判断：当任何敏感字段有草稿或显式清空时返回 true。
 */
export const hasSensitiveDirtyChange = (
  schema: Parameters<typeof normalizeSchemaGroups>[0],
  drafts: Record<string, string>,
  explicitClears: Set<string> = new Set()
): boolean => {
  const sensitivePaths = collectSensitiveFieldPaths(schema)
  return sensitivePaths.some(path => {
    const draft = drafts[path]
    const explicitClear = explicitClears.has(path)
    const intent = resolveSensitiveSaveIntent(draft, explicitClear)
    return intent.kind !== 'keep'
  })
}

// 保留 isStringField / getFieldOptions 引用，避免 tree-shaking 误删（用于未来扩展非密码型 token 字段）。
void isStringField
void getFieldOptions
