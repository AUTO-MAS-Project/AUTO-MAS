// 项目更新后任务队列与 interface 对不上的两种情况：
// - 队列里的任务 interface 已经没有了（多半是改了 name）：留成虚影，列出原来的设置，由用户自己删；
// - interface 里多出了用户没见过的任务：在「添加任务」里标 NEW，加进队列后消掉。
// 「见过哪些任务」只是提示用的本机状态，按脚本存在 localStorage，不进配置。

import { translate as t } from '@/i18n'
import { MAAFW_DUPLICATE_TASK_SEPARATOR } from '@/utils/maafwTaskInstance'
import type { MaaFWOptionInfo, MaaFWTaskOptionValue } from '@/types/script'

/** 对不上的实例 id → 原任务名：副本去掉 `__MAS_DUP__` 后缀 */
export const maafwMissingTaskName = (taskId: string) => {
  const separatorIndex = taskId.lastIndexOf(MAAFW_DUPLICATE_TASK_SEPARATOR)
  return separatorIndex > 0 ? taskId.slice(0, separatorIndex) : taskId
}

/** 加密存储的密码字段前缀，与后端 option_secrets 一致；这种值一律不显示 */
const SECRET_VALUE_PREFIX = 'mas-dpapi:'
const MASKED_VALUE = '******'

export type MaaFWMissingTaskSettingRow = { key: string; label: string; value: string }

const displayName = (item: { name: string; label?: string | null }) => item.label || item.name

const describeValue = (
  value: MaaFWTaskOptionValue,
  option: MaaFWOptionInfo | undefined
): string => {
  const caseLabel = (caseName: string) => {
    const matched = option?.cases.find(item => item.name === caseName)
    return matched ? displayName(matched) : caseName
  }
  if (Array.isArray(value)) return value.map(caseLabel).join(t('edit.missingTaskValueSeparator'))
  if (value && typeof value === 'object') {
    return Object.entries(value)
      .map(([field, fieldValue]) => {
        const input = option?.inputs.find(item => item.name === field)
        const text =
          input?.password || String(fieldValue).startsWith(SECRET_VALUE_PREFIX)
            ? MASKED_VALUE
            : String(fieldValue)
        return option && option.inputs.length <= 1
          ? text
          : `${input ? displayName(input) : field}: ${text}`
      })
      .join(t('edit.missingTaskFieldSeparator'))
  }
  const text = String(value ?? '')
  if (text.startsWith(SECRET_VALUE_PREFIX)) return MASKED_VALUE
  return caseLabel(text)
}

/**
 * 虚影任务原来的设置，给用户对照着在新任务里重设。选项还在 interface 里就用它的显示名、
 * 按 interface 里的顺序排，不在了就原样给键和值、排在后面；密码字段打码。
 */
export const describeMaaFWMissingTaskSettings = (
  values: Record<string, MaaFWTaskOptionValue> | undefined,
  options: readonly MaaFWOptionInfo[]
): MaaFWMissingTaskSettingRow[] => {
  if (!values) return []
  const optionByName = new Map(options.map(option => [option.name, option] as const))
  const optionIndex = new Map(options.map((option, index) => [option.name, index] as const))
  const entries = Object.entries(values).sort(
    ([a], [b]) => (optionIndex.get(a) ?? Infinity) - (optionIndex.get(b) ?? Infinity)
  )
  return entries.map(([key, value]) => {
    const option = optionByName.get(key)
    return {
      key,
      label: option ? displayName(option) : key,
      value: describeValue(value, option),
    }
  })
}

const seenStorageKey = (scriptId: string) => `maafw-seen-tasks:${scriptId}`

const readSeen = (scriptId: string): Set<string> | null => {
  try {
    const raw = localStorage.getItem(seenStorageKey(scriptId))
    if (raw === null) return null
    const parsed = JSON.parse(raw)
    return new Set(Array.isArray(parsed) ? parsed.filter(item => typeof item === 'string') : [])
  } catch {
    return null
  }
}

const writeSeen = (scriptId: string, names: Iterable<string>) => {
  try {
    localStorage.setItem(seenStorageKey(scriptId), JSON.stringify([...new Set(names)]))
  } catch {
    // 本机存不下只是少个提示
  }
}

/**
 * 当前 interface 里用户没见过的任务名。第一次打开这个脚本时把现有任务全记成见过，
 * 刚导入的项目不会满屏 NEW。
 */
export const resolveMaaFWNewTaskNames = (scriptId: string, taskNames: readonly string[]) => {
  if (!scriptId) return new Set<string>()
  const seen = readSeen(scriptId)
  if (seen === null) {
    writeSeen(scriptId, taskNames)
    return new Set<string>()
  }
  return new Set(taskNames.filter(name => !seen.has(name)))
}

/** 把任务记成见过（加进队列时调用） */
export const markMaaFWTasksSeen = (scriptId: string, taskNames: readonly string[]) => {
  if (!scriptId || taskNames.length === 0) return
  const seen = readSeen(scriptId) ?? new Set<string>()
  writeSeen(scriptId, [...seen, ...taskNames])
}
