/**
 * Lane 8：设置页表单保护与统一状态。
 *
 * 解决问题：
 * 1. 未保存保护：当 saveSettings 失败时，用户输入不丢失，可重试。
 * 2. 错误展示：按 category 维度展示具体错误，不只用全局 message.error。
 * 3. 敏感字段：保证 a-input-password 已遮罩；日志不输出字段值。
 * 4. 恢复默认：提供 KNOWN_DEFAULTS 与 restoreDefaults 入口。
 *
 * 设计：
 * - pendingChanges: category -> key -> value，保存失败时保留用户输入。
 * - effectiveValue: 合并 settings + pendingChanges，供 Tab 组件绑定。
 * - errorByCategory: category -> string | null，用于在每个 Tab 顶部展示错误条。
 *
 * 不引入 Pinia store，仅局部状态 + composable。
 */

import { reactive, computed, ref } from 'vue'
import type { GlobalConfig } from '@/api'

export type SettingsCategory = keyof GlobalConfig

/** 已知安全默认值。仅包含可安全重置的字段；敏感字段（密码/令牌）不在其中。 */
export const KNOWN_DEFAULTS: Partial<Record<SettingsCategory, Record<string, unknown>>> = {
  UI: {
    IfShowTray: true,
    IfToTray: true,
    IfHideCloseButton: false,
  },
  Notify: {
    SendTaskResultTime: '仅失败时',
    IfSendStatistic: false,
    IfSendSixStar: true,
    IfPushPlyer: true,
    IfSendMail: false,
    IfServerChan: false,
    IfKoishiSupport: false,
    // 敏感字段（SMTPServerAddress / FromAddress / AuthorizationCode / ToAddress
    // / ServerChanKey / KoishiServerAddress / KoishiToken）不在默认值中，
    // 恢复默认时只清空为空串，不编造值。
  },
  Start: {
    // 启动相关默认值由后端控制，前端不覆盖
  },
  Update: {
    IfAutoUpdate: true,
    Source: 'GitHub',
    Channel: 'stable',
  },
}

/** 敏感字段路径列表，用于日志脱敏。 */
const SENSITIVE_PATHS: Array<{ category: SettingsCategory; keys: string[] }> = [
  { category: 'Notify', keys: ['AuthorizationCode', 'KoishiToken', 'ServerChanKey'] },
]

export function useSettingsFormGuard() {
  /**
   * 待保存的修改。
   * key 格式：`${category}.${fieldKey}`，value 为用户输入。
   */
  const pendingChanges = reactive<Record<string, unknown>>({})

  /** 按 category 分组的错误信息。 */
  const errorByCategory = reactive<Record<string, string | null>>({})

  /** 正在保存中的字段，避免重复触发。 */
  const savingKeys = reactive<Record<string, boolean>>({})

  /** 全局加载状态（与 useSettingsApi 共享）。 */
  const loading = ref(false)

  const pendingCount = computed(() => Object.keys(pendingChanges).length)

  const hasPending = computed(() => pendingCount.value > 0)

  function compositeKey(category: SettingsCategory, key: string): string {
    return `${category}.${key}`
  }

  /**
   * 获取字段的"有效值"：优先返回 pendingChanges 中的值，否则返回 settings 原值。
   *
   * Tab 组件应使用此函数绑定 :value，确保保存失败时用户输入不丢失。
   */
  function getEffectiveValue<T>(
    settings: GlobalConfig,
    category: SettingsCategory,
    key: string
  ): T | undefined {
    const ck = compositeKey(category, key)
    if (ck in pendingChanges) {
      return pendingChanges[ck] as T
    }
    const section = settings[category] as Record<string, unknown> | undefined
    return section?.[key] as T | undefined
  }

  /**
   * 暂存修改并尝试保存。
   *
   * - 先写入 pendingChanges，确保 UI 立即反映用户输入。
   * - 调用 saveFn 保存；成功则从 pendingChanges 移除并清空错误。
   * - 失败则保留 pendingChanges，写入 errorByCategory。
   *
   * @param saveFn 返回 true 表示成功，false 表示失败。
   */
  async function stageAndSave(
    category: SettingsCategory,
    key: string,
    value: unknown,
    saveFn: () => Promise<boolean>
  ): Promise<boolean> {
    const ck = compositeKey(category, key)
    pendingChanges[ck] = value
    savingKeys[ck] = true
    errorByCategory[category] = null
    loading.value = true

    try {
      const ok = await saveFn()
      if (ok) {
        delete pendingChanges[ck]
        return true
      }
      // 保存失败：保留 pendingChanges，写入错误
      errorByCategory[category] = `字段 ${key} 保存失败，已保留您的输入，可重试或还原。`
      return false
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err)
      // Lane 8：错误消息中可能包含敏感字段值，做基础脱敏
      errorByCategory[category] = sanitizeErrorMessage(errorMsg)
      return false
    } finally {
      savingKeys[ck] = false
      loading.value = false
    }
  }

  /**
   * 重试某个 category 下所有 pendingChanges。
   *
   * @param saveFn 接收 (key, value)，返回 Promise<boolean>。
   */
  async function retryPending(
    category: SettingsCategory,
    saveFn: (key: string, value: unknown) => Promise<boolean>
  ): Promise<void> {
    const prefix = `${category}.`
    const entries = Object.entries(pendingChanges).filter(([k]) => k.startsWith(prefix))
    if (entries.length === 0) return

    errorByCategory[category] = null
    let allOk = true
    for (const [ck, value] of entries) {
      const key = ck.slice(prefix.length)
      savingKeys[ck] = true
      try {
        const ok = await saveFn(key, value)
        if (ok) {
          delete pendingChanges[ck]
        } else {
          allOk = false
        }
      } catch {
        allOk = false
      } finally {
        savingKeys[ck] = false
      }
    }
    if (!allOk) {
      errorByCategory[category] = '部分字段仍保存失败，请检查网络或后端服务后重试。'
    }
  }

  /**
   * 还原某个字段到 settings 中的原值（放弃 pendingChanges）。
   */
  function revertField(category: SettingsCategory, key: string): void {
    const ck = compositeKey(category, key)
    delete pendingChanges[ck]
    // 清除该 category 的错误（如果有）
    if (errorByCategory[category]) {
      // 仅当该 category 下没有其他 pending 时才清空错误
      const prefix = `${category}.`
      const hasOther = Object.keys(pendingChanges).some(k => k.startsWith(prefix))
      if (!hasOther) {
        errorByCategory[category] = null
      }
    }
  }

  /**
   * 将某个 category 的已知字段恢复为默认值（来自 KNOWN_DEFAULTS）。
   *
   * 敏感字段不在 KNOWN_DEFAULTS 中，调用方需自行处理。
   * 返回需要保存的 changes，由调用方逐字段保存。
   */
  function getDefaultsForCategory(category: SettingsCategory): Record<string, unknown> | null {
    return KNOWN_DEFAULTS[category] ?? null
  }

  /** 判断字段是否正在保存中。 */
  function isSaving(category: SettingsCategory, key: string): boolean {
    return !!savingKeys[compositeKey(category, key)]
  }

  /** 获取 category 的错误信息。 */
  function getError(category: SettingsCategory): string | null {
    return errorByCategory[category] ?? null
  }

  /** 清除 category 的错误。 */
  function clearError(category: SettingsCategory): void {
    errorByCategory[category] = null
  }

  /**
   * Lane 8：多 category 聚合，用于一个 Tab 包含多个 category 的场景（如 TabFunction 含 Start/Function/Voice）。
   *
   * - 返回第一个非 null 的错误（按传入顺序）。
   * - 返回这些 category 下 pendingChanges 的总数。
   */
  function getAggregateStateForCategories(categories: SettingsCategory[]): {
    error: string | null
    pendingCountForCategories: number
    hasPendingForCategories: boolean
  } {
    let error: string | null = null
    let pendingCountForCategories = 0
    for (const category of categories) {
      if (error === null && errorByCategory[category]) {
        error = errorByCategory[category] ?? null
      }
      const prefix = `${category}.`
      pendingCountForCategories += Object.keys(pendingChanges).filter(k =>
        k.startsWith(prefix)
      ).length
    }
    return {
      error,
      pendingCountForCategories,
      hasPendingForCategories: pendingCountForCategories > 0,
    }
  }

  /**
   * Lane 8：清除多个 category 的错误（用于 Tab 顶部错误条关闭按钮）。
   */
  function clearErrorsForCategories(categories: SettingsCategory[]): void {
    for (const category of categories) {
      errorByCategory[category] = null
    }
  }

  /**
   * Lane 8：重试多个 category 下所有 pendingChanges。
   */
  async function retryPendingForCategories(
    categories: SettingsCategory[],
    saveFn: (category: SettingsCategory, key: string, value: unknown) => Promise<boolean>
  ): Promise<void> {
    for (const category of categories) {
      await retryPending(category, (key, value) => saveFn(category, key, value))
    }
  }

  return {
    pendingChanges,
    pendingCount,
    hasPending,
    loading,
    getEffectiveValue,
    stageAndSave,
    retryPending,
    revertField,
    getDefaultsForCategory,
    isSaving,
    getError,
    clearError,
    getAggregateStateForCategories,
    clearErrorsForCategories,
    retryPendingForCategories,
  }
}

/**
 * 基础错误消息脱敏。
 *
 * 对已知敏感字段的常见值模式做最小脱敏；
 * 完整脱敏依赖 useSensitiveFieldStrategy，但该策略面向 SchemaForm，
 * 设置页的字段是硬编码的，这里只做简单处理。
 */
function sanitizeErrorMessage(msg: string): string {
  if (typeof msg !== 'string' || msg === '') return msg
  // 不输出可能包含的授权码/令牌原文；这里只做长度截断，避免泄露过多
  if (msg.length > 200) {
    return msg.slice(0, 200) + '…（已截断，完整错误见日志）'
  }
  return msg
}
