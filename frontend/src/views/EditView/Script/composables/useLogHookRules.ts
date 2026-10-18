import { translate as t } from '@/i18n'
import { computed, nextTick, ref, watch, type Ref } from 'vue'
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

const normalizeHookType = (raw: unknown): LogHookType => (raw === 'replace' ? 'replace' : 'drop')

let uidCounter = 0
const newUid = (): string => `hook_${Date.now()}_${++uidCounter}`

const createHookRule = (type: LogHookType): LogHookRule => ({
  _uid: newUid(),
  type,
  enabled: true,
  match: '',
  ...(type === 'replace' ? { replace: '' } : {}),
})

const parseLogHookRules = (json: string): LogHookRule[] => {
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

const serializeLogHookRules = (rules: LogHookRule[]): string => {
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

interface UseLogHookRulesOptions {
  rulesJson: Ref<string>
  onChange?: (json: string) => void
  /** 总开关（日志预处理启用状态）：关闭时没有任何规则会实际执行 */
  masterEnabled?: Ref<boolean>
}

export function useLogHookRules(options: UseLogHookRulesOptions) {
  const { rulesJson, onChange, masterEnabled } = options
  // 默认不展示任何规则卡片，首次点击「添加规则」后才出现，避免误导用户已存在生效规则
  const rules = ref<LogHookRule[]>([])

  const syncFromJson = () => {
    rules.value = parseLogHookRules(rulesJson.value || '')
  }

  // 标记本次 rulesJson 回写来自本地 save，watcher 需跳过以防已添加的空规则被立即移除
  let localEcho = false
  const emitJson = (json: string) => {
    localEcho = true
    onChange?.(json)
    nextTick(() => {
      localEcho = false
    })
  }

  /**
   * 保存当前规则到 json。结构性操作（新增/删除/切类型/排序）时传入 { warn: false }，
   * 避免新建空规则或切换类型在用户尚未编辑时立即弹出「缺匹配正则」的提示；
   * 仅在实际字段编辑时对缺匹配正则或正则非法的启用规则给出可见提示。
   */
  const save = (options: { warn?: boolean } = {}) => {
    const json = serializeLogHookRules(rules.value)
    if (options.warn !== false) {
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
    }
    emitJson(json)
  }

  watch(
    rulesJson,
    () => {
      // 本次回写来自本地 save 同步写回的 v-model（nextTick 内），跳过防止刚添加的空规则被立即移除
      if (localEcho) return
      // 异步保存后父组件 refreshScript 会回写后端序列化结果：若该值与当前本地规则的序列化结果
      // 等价（空/待编辑规则会被 serialize 暂时剔除），说明仅是本地 save 的回显而非外部改动，
      // 应保留本地尚未落盘的空规则卡片，避免刚添加的空规则被异步刷新清掉或类型被重置
      if ((rulesJson.value || '') === serializeLogHookRules(rules.value)) {
        return
      }
      syncFromJson()
    },
    { immediate: true }
  )

  const addRule = (type: LogHookType) => {
    rules.value.push(createHookRule(type))
    save({ warn: false })
  }

  const removeRule = (idx: number) => {
    rules.value.splice(idx, 1)
    save({ warn: false })
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
    save({ warn: false })
  }

  const onRuleFieldChange = () => {
    save()
  }

  // 与运行/序列化语义一致才算生效：总开关开启、规则启用且填写了匹配正则
  // （匹配正则为空的启用规则会在序列化时被剔除，后端也不会编译它）
  const activeRuleCount = computed(() =>
    masterEnabled?.value !== false
      ? rules.value.filter(r => r.enabled !== false && (r.match || '').trim()).length
      : 0
  )

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
