import { translate as t } from '@/i18n'
import { computed, ref, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'

import { validateRegexPattern } from '../logRegex'

export type LogHookType = 'drop' | 'replace'

export interface LogHookRule {
  type: LogHookType
  /** 规则标题（供说明展示），留空时前端按 规则1/规则2 兜底 */
  name?: string
  /** 单条规则启用/停用开关：停用时保留配置但不参与处理 */
  enabled?: boolean
  /** 匹配正则（Python 语法，由后端编译） */
  match?: string
  /** 改写规则的替换文本，支持 \1 反向引用；丢弃规则不使用 */
  replace?: string
  /** 运行时唯一标识，仅用于前端列表渲染，不参与序列化 */
  _uid?: string
}

export const normalizeHookType = (raw: unknown): LogHookType =>
  raw === 'replace' ? 'replace' : 'drop'

let uidCounter = 0
const newUid = (): string => `hook_${Date.now()}_${++uidCounter}`

export const createHookRule = (type: LogHookType): LogHookRule => ({
  _uid: newUid(),
  type,
  enabled: true,
  match: '',
  ...(type === 'replace' ? { replace: '' } : {}),
})

export const parseLogHookRules = (json: string): LogHookRule[] => {
  if (!json) return []
  try {
    const items = JSON.parse(json)
    if (!Array.isArray(items)) return []
    return items
      .filter((item: unknown) => item && typeof item === 'object')
      .map((item: Record<string, unknown>) => {
        const type = normalizeHookType(item.type)
        const rule: LogHookRule = {
          _uid: newUid(),
          type,
          name: typeof item.name === 'string' && item.name.trim() ? item.name.trim() : undefined,
          enabled: item.enabled === false ? false : true,
          match: typeof item.match === 'string' ? item.match : '',
        }
        if (type === 'replace') {
          rule.replace = typeof item.replace === 'string' ? item.replace : ''
        }
        return rule
      })
  } catch {
    return []
  }
}

export const serializeLogHookRules = (rules: LogHookRule[]): string => {
  const cleaned: LogHookRule[] = []
  for (const rule of rules) {
    const enabled = rule.enabled === false ? false : true
    const match = (rule.match || '').trim()
    // 匹配正则留空则该规则不生效（与后端 compile_hook 对齐）
    if (enabled && !match) continue
    const cleanedRule: LogHookRule = {
      type: rule.type,
      name: rule.name?.trim() || undefined,
      enabled,
      match,
    }
    if (rule.type === 'replace') {
      cleanedRule.replace = rule.replace || ''
    }
    cleaned.push(cleanedRule)
  }
  return JSON.stringify(cleaned)
}

const ruleDisplayName = (rule: LogHookRule, idx: number): string =>
  (rule.name || '').trim() || `规则${idx + 1}`

export interface UseLogHookRulesOptions {
  rulesJson: Ref<string>
  onChange?: (json: string) => void
}

export function useLogHookRules(options: UseLogHookRulesOptions) {
  const { rulesJson, onChange } = options
  const rules = ref<LogHookRule[]>([createHookRule('drop')])

  const syncFromJson = () => {
    const parsed = parseLogHookRules(rulesJson.value || '')
    rules.value = parsed.length > 0 ? parsed : [createHookRule('drop')]
  }

  const save = () => {
    const json = serializeLogHookRules(rules.value)
    // 启用中的规则缺少匹配正则或正则语法非法时后端会跳过，保存配置与运行行为
    // 不一致，这里给出可见提示而非静默失效
    const dropped: string[] = []
    const invalid: string[] = []
    rules.value.forEach((rule, idx) => {
      if (rule.enabled === false) return
      const match = (rule.match || '').trim()
      if (!match) {
        dropped.push(ruleDisplayName(rule, idx))
        return
      }
      if (validateRegexPattern(match)) {
        invalid.push(ruleDisplayName(rule, idx))
      }
    })
    if (dropped.length > 0) {
      message.warning(t('edit.p0HasNoMatch', { p0: dropped.join('、') }))
    }
    if (invalid.length > 0) {
      message.warning(t('edit.matchPatternP0Has', { p0: invalid.join('、') }))
    }
    onChange?.(json)
  }

  watch(rulesJson, syncFromJson, { immediate: true })

  const addRule = (type: LogHookType) => {
    rules.value.push(createHookRule(type))
    save()
  }

  const removeRule = (idx: number) => {
    rules.value.splice(idx, 1)
    // 删除后若为空，保留一个空丢弃规则作为占位，避免用户困惑
    if (rules.value.length === 0) {
      rules.value.push(createHookRule('drop'))
    }
    save()
  }

  const updateRuleType = (idx: number, type: LogHookType) => {
    const old = rules.value[idx]
    if (!old || old.type === type) return
    // 类型切换保留标题、开关与匹配正则，仅重置类型专属字段
    rules.value[idx] = {
      ...old,
      type,
      replace: type === 'replace' ? old.replace || '' : undefined,
    }
    save()
  }

  const onRuleFieldChange = () => {
    save()
  }

  const activeRuleCount = computed(() => rules.value.filter(r => r.enabled !== false).length)

  return {
    rules,
    activeRuleCount,
    addRule,
    removeRule,
    updateRuleType,
    onRuleFieldChange,
    save,
    syncFromJson,
  }
}
