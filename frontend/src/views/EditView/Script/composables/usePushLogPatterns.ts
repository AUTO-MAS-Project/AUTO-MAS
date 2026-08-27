import { computed, ref, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'

export type PushLogPatternType = 'split' | 'regex' | 'multiline'

export interface PushLogPattern {
  type: PushLogPatternType
  /** 规则标题（供分享站展示/说明），留空时前端按 规则1/规则2 兜底 */
  name?: string
  /** 单条规则启用/停用开关：停用时保留配置但不参与采集 */
  enabled?: boolean
  /** 日志类型：普通 = 任何推送报告均包含；失败 = 仅在存在未完成用户的报告中包含 */
  logType?: string
  // split
  match?: string
  head?: string
  headInclude?: boolean
  tail?: string
  tailInclude?: boolean
  // regex
  extract?: string
  // multiline
  start?: string
  end?: string
  maxLines?: number
  /** 运行时唯一标识，仅用于前端列表渲染，不参与序列化 */
  _uid?: string
}

const LOG_TYPE_NORMAL = '普通'
const LOG_TYPE_ERROR = '失败'

export const normalizePatternType = (raw: unknown): PushLogPatternType => {
  if (raw === 'split') return 'split'
  if (raw === 'multiline') return 'multiline'
  return 'regex'
}

/** 日志类型归一：仅接受 普通/失败（旧值「错误」「异常」归一为「失败」），其余回退 普通 */
export const normalizeLogType = (raw: unknown): string => {
  return raw === LOG_TYPE_ERROR || raw === '错误' || raw === '异常'
    ? LOG_TYPE_ERROR
    : LOG_TYPE_NORMAL
}

export const getDefaultPatternName = (idx: number): string => `规则${idx + 1}`

let uidCounter = 0
const newUid = (): string => `pattern_${Date.now()}_${++uidCounter}`

const defaultSplitPattern = (): PushLogPattern => ({
  _uid: newUid(),
  type: 'split',
  enabled: true,
  logType: LOG_TYPE_NORMAL,
  match: '',
  head: '',
  headInclude: false,
  tail: '',
  tailInclude: false,
})

const defaultRegexPattern = (): PushLogPattern => ({
  _uid: newUid(),
  type: 'regex',
  enabled: true,
  logType: LOG_TYPE_NORMAL,
  match: '',
  extract: '',
})

const defaultMultilinePattern = (): PushLogPattern => ({
  _uid: newUid(),
  type: 'multiline',
  enabled: true,
  logType: LOG_TYPE_NORMAL,
  start: '',
  end: '',
  extract: '',
  maxLines: 50,
})

export const createPattern = (type: PushLogPatternType): PushLogPattern => {
  if (type === 'split') return defaultSplitPattern()
  if (type === 'multiline') return defaultMultilinePattern()
  return defaultRegexPattern()
}

export const parsePushLogPatterns = (json: string): PushLogPattern[] => {
  if (!json) return []
  try {
    const items = JSON.parse(json)
    if (!Array.isArray(items)) return []
    return items
      .filter((item: unknown) => item && typeof item === 'object')
      .map((item: Record<string, unknown>) => {
        const type = normalizePatternType(item.type)
        const enabled = item.enabled === false ? false : true
        const name =
          typeof item.name === 'string' && item.name.trim() ? item.name.trim() : undefined
        const logType = normalizeLogType(item.logType)

        if (type === 'split') {
          return {
            _uid: newUid(),
            type: 'split',
            name,
            enabled,
            logType,
            match: typeof item.match === 'string' ? item.match : '',
            head: typeof item.head === 'string' ? item.head : '',
            headInclude: !!item.headInclude,
            tail: typeof item.tail === 'string' ? item.tail : '',
            tailInclude: !!item.tailInclude,
          }
        }
        if (type === 'regex') {
          return {
            _uid: newUid(),
            type: 'regex',
            name,
            enabled,
            logType,
            match: typeof item.match === 'string' ? item.match : '',
            extract: typeof item.extract === 'string' ? item.extract : '',
          }
        }
        return {
          _uid: newUid(),
          type: 'multiline',
          name,
          enabled,
          logType,
          start: typeof item.start === 'string' ? item.start : '',
          end: typeof item.end === 'string' ? item.end : '',
          extract: typeof item.extract === 'string' ? item.extract : '',
          maxLines: typeof item.maxLines === 'number' ? item.maxLines : 50,
        }
      })
  } catch {
    return []
  }
}

/** 规则是否具备后端编译所需的必填字段（与后端 _compile_* 的条件一致）：
 * - split 需匹配关键字；regex 需匹配正则；multiline 需起始正则。
 * 停用（enabled=false）时保留配置不参与采集，视为可保存，不做字段要求。 */
const ruleHasRequiredField = (p: PushLogPattern): boolean => {
  if (p.enabled === false) return true
  if (p.type === 'split') return !!(p.match || '').trim()
  if (p.type === 'regex') return !!(p.match || '').trim()
  if (p.type === 'multiline') return !!(p.start || '').trim()
  return false
}

const ruleDisplayName = (p: PushLogPattern, idx: number): string =>
  (p.name || '').trim() || `规则${idx + 1}`

export const serializePushLogPatterns = (patterns: PushLogPattern[]): string => {
  const cleaned: PushLogPattern[] = []
  for (const p of patterns) {
    const enabled = p.enabled === false ? false : true
    const name = p.name?.trim() || undefined
    const logType = normalizeLogType(p.logType)

    if (p.type === 'split') {
      const match = (p.match || '').trim()
      const head = (p.head || '').trim()
      const tail = (p.tail || '').trim()
      // 匹配关键字留空则该规则不生效（与后端 _compile_split 对齐）
      if (enabled && !match) continue
      cleaned.push({
        type: 'split',
        name,
        enabled,
        logType,
        match,
        head,
        headInclude: !!p.headInclude,
        tail,
        tailInclude: !!p.tailInclude,
      })
    } else if (p.type === 'regex') {
      const match = (p.match || '').trim()
      const extract = (p.extract || '').trim()
      // 匹配正则留空则该规则不生效（与后端 _compile_regex_matcher 对齐）
      if (enabled && !match) continue
      cleaned.push({ type: 'regex', name, enabled, logType, match, extract })
    } else {
      const start = (p.start || '').trim()
      const end = (p.end || '').trim()
      const extract = (p.extract || '').trim()
      // 起始正则留空则该规则不生效（与后端 _compile_multiline_matcher 对齐）
      if (enabled && !start) continue
      cleaned.push({
        type: 'multiline',
        name,
        enabled,
        logType,
        start,
        end,
        extract,
        maxLines: p.maxLines || 50,
      })
    }
  }
  return JSON.stringify(cleaned)
}

/**
 * 类型切换时保留可复用字段，减少用户重复输入。
 * - match / start 语义相近：regex.match -> multiline.start
 * - extract 在 regex / multiline 之间通用
 */
export const migratePatternOnTypeChange = (
  oldPattern: PushLogPattern,
  newType: PushLogPatternType
): PushLogPattern => {
  const base: PushLogPattern = {
    _uid: oldPattern._uid || newUid(),
    type: newType,
    name: oldPattern.name,
    enabled: oldPattern.enabled === false ? false : true,
    logType: normalizeLogType(oldPattern.logType),
  }

  if (newType === 'split') {
    return {
      ...base,
      match: oldPattern.match || '',
      head: '',
      headInclude: false,
      tail: '',
      tailInclude: false,
    }
  }

  if (newType === 'regex') {
    return {
      ...base,
      match: oldPattern.match || oldPattern.start || '',
      extract: oldPattern.extract || '',
    }
  }

  return {
    ...base,
    start: oldPattern.start || oldPattern.match || '',
    end: '',
    extract: oldPattern.extract || '',
    maxLines: oldPattern.maxLines || 50,
  }
}

export interface UsePushLogPatternsOptions {
  patternsJson: Ref<string>
  onChange?: (json: string) => void
}

export function usePushLogPatterns(options: UsePushLogPatternsOptions) {
  const { patternsJson, onChange } = options
  const patterns = ref<PushLogPattern[]>([defaultSplitPattern()])

  const syncFromJson = () => {
    const parsed = parsePushLogPatterns(patternsJson.value || '')
    patterns.value = parsed.length > 0 ? parsed : [defaultSplitPattern()]
  }

  const save = () => {
    const json = serializePushLogPatterns(patterns.value)
    // 启用中的规则缺少必填字段（后端编译时会跳过），保存配置与运行采集不一致，
    // 这里给出可见提示而非静默失效
    const dropped = patterns.value
      .map((p, i) => ({ p, i }))
      .filter(({ p }) => p.enabled !== false && !ruleHasRequiredField(p))
      .map(({ p, i }) => ruleDisplayName(p, i))
    if (dropped.length > 0) {
      message.warning(
        `${dropped.join('、')}缺少必填字段已停用保存：split/regex 需填匹配关键字(正则)，multiline 需填起始正则`
      )
    }
    onChange?.(json)
  }

  watch(patternsJson, syncFromJson, { immediate: true })

  const addPattern = (type: PushLogPatternType) => {
    patterns.value.push(createPattern(type))
    save()
  }

  const removePattern = (idx: number) => {
    patterns.value.splice(idx, 1)
    // 删除后若为空，保留一个空 split 规则作为占位，避免用户困惑
    if (patterns.value.length === 0) {
      patterns.value.push(defaultSplitPattern())
    }
    save()
  }

  const updatePatternType = (idx: number, newType: PushLogPatternType) => {
    const old = patterns.value[idx]
    if (!old || old.type === newType) return
    patterns.value[idx] = migratePatternOnTypeChange(old, newType)
    save()
  }

  const onPatternFieldChange = () => {
    save()
  }

  const reorderPatterns = (newOrder: PushLogPattern[]) => {
    patterns.value = newOrder
    save()
  }

  const activePatternCount = computed(() => patterns.value.filter(p => p.enabled !== false).length)

  return {
    patterns,
    activePatternCount,
    addPattern,
    removePattern,
    updatePatternType,
    onPatternFieldChange,
    reorderPatterns,
    save,
    syncFromJson,
  }
}
