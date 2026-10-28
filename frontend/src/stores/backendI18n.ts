import { defineStore } from 'pinia'
import { computed, ref, watch, type WatchStopHandle } from 'vue'
import { OpenAPI } from '@/api'
import {
  bootstrapMessages,
  fallbackLocales,
  i18n,
  SUPPORTED_LOCALES,
  t,
  type AppLocale,
  type LocaleMessages,
} from '@/i18n'
import { useBackendI18nApi } from '@/composables/useBackendI18nApi'
import { connectionState } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import { WS_ID_I18N, WS_I18N_UPDATED } from '@/services/websocket/types'
import { getApiErrorMessage } from '@/utils/apiError'

/** JSON 资源只允许文本与嵌套对象，后端不能覆盖初始化词表。 */
function readMessages(value: unknown): LocaleMessages {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(t('bootstrap.i18n.unavailable'))
  }
  const result: LocaleMessages = {}
  for (const [key, child] of Object.entries(value)) {
    if (['__proto__', 'prototype', 'constructor'].includes(key)) {
      throw new Error(t('bootstrap.i18n.unavailable'))
    }
    result[key] = typeof child === 'string' ? child : readMessages(child)
  }
  return result
}

export const useBackendI18nStore = defineStore('backend-i18n', () => {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const revision = ref('')
  const requested = ref(false)
  const loaded = ref<AppLocale[]>([])
  const ready = computed(() =>
    fallbackLocales(i18n.global.locale.value).every(locale => loaded.value.includes(locale))
  )
  const api = useBackendI18nApi()
  let endpoint = OpenAPI.BASE
  let generation = 0
  let requestId = 0
  let resourceEpoch = 0
  let cacheEpoch = -1
  let cache = new Map<AppLocale, LocaleMessages>()
  let active: { locale: AppLocale; promise: Promise<boolean> } | null = null
  let stopWatch: WatchStopHandle | null = null
  let subscription: string | null = null

  function invalidateRequests() {
    generation++
    requestId++
    active = null
    loading.value = false
  }

  function checkEndpoint() {
    if (endpoint === OpenAPI.BASE) return
    invalidateRequests()
    endpoint = OpenAPI.BASE
    cache = new Map()
    cacheEpoch = -1
    loaded.value = []
    revision.value = ''
    error.value = null
    for (const locale of SUPPORTED_LOCALES) {
      i18n.global.setLocaleMessage<LocaleMessages>(locale, { bootstrap: bootstrapMessages[locale] })
    }
  }

  async function load(locale: AppLocale, force: boolean): Promise<boolean> {
    checkEndpoint()
    requested.value = true
    if (active?.locale === locale) return active.promise
    // 切到缓存语言时也要接管进行中的刷新，避免旧请求发布的新版本删掉目标语言。
    if (
      !force &&
      !active &&
      cacheEpoch === resourceEpoch &&
      fallbackLocales(locale).every(item => cache.has(item))
    )
      return true

    const id = ++requestId
    const currentGeneration = generation
    const currentEndpoint = endpoint
    const isCurrent = () =>
      id === requestId && currentGeneration === generation && currentEndpoint === OpenAPI.BASE
    loading.value = true
    error.value = null

    // 先登记 active，再发请求；通知须续接同一目标语言的等待链。
    const promise = Promise.resolve().then(async () => {
      try {
        // 切换语言时，旧界面继续可用；新版本必须连同旧界面所需词表一起准备。
        const required = [
          ...new Set([
            ...fallbackLocales(locale),
            ...(ready.value ? fallbackLocales(i18n.global.locale.value) : []),
          ]),
        ]
        let mismatchedBatches = 0
        while (isCurrent()) {
          const epoch = resourceEpoch
          const state = await api.getLocales()
          if (!isCurrent()) return false
          const available = new Set<string>(state.available)
          if (!state.revision || required.some(item => !available.has(item))) {
            throw new Error(t('bootstrap.i18n.unavailable'))
          }
          const responses = await Promise.all(required.map(item => api.getMessages(item)))
          if (!isCurrent()) return false
          // 旧响应虽自洽，也不能吞掉在途期间收到的失效通知；
          // 沿同一目标语言的等待链重新读取，多个通知合并到下一批。
          if (epoch !== resourceEpoch) continue
          if (
            responses.some(
              (response, index) =>
                response.locale !== required[index] || response.revision !== state.revision
            )
          ) {
            if (mismatchedBatches++ === 0) continue
            throw new Error(t('bootstrap.i18n.changed'))
          }

          const next =
            state.revision === revision.value
              ? new Map(cache)
              : new Map<AppLocale, LocaleMessages>()
          for (const response of responses) {
            // TODO(插件迁移)：与后端同步允许 core 和 plugins.<插件标识>；
            // 保留 bootstrap 的前端所有权，并拒绝其他无归属命名空间。
            if (Object.keys(response.messages).some(key => key !== 'core')) {
              throw new Error(t('bootstrap.i18n.unavailable'))
            }
            next.set(response.locale, readMessages(response.messages.core))
          }
          // 所有响应校验完才统一应用，不能将一半新词表与一半旧词表发布给界面。
          // TODO(插件迁移)：缓存须保存完整 core + plugins 快照，再与本地 bootstrap 组合；
          // 保持回退语言的 revision 一致并整体替换，使停用、卸载后的插件词条不再残留。
          for (const item of SUPPORTED_LOCALES) {
            const core = next.get(item)
            i18n.global.setLocaleMessage<LocaleMessages>(item, {
              bootstrap: bootstrapMessages[item],
              ...(core ? { core } : {}),
            })
          }
          cache = next
          cacheEpoch = resourceEpoch
          loaded.value = [...next.keys()]
          revision.value = state.revision
          return true
        }
        return false
      } catch (reason) {
        if (isCurrent()) error.value = getApiErrorMessage(reason, t('bootstrap.i18n.unavailable'))
        return false
      } finally {
        if (isCurrent()) {
          loading.value = false
          active = null
        }
      }
    })
    active = { locale, promise }
    return promise
  }

  const ensure = (locale: AppLocale = i18n.global.locale.value) => load(locale, false)
  function refreshResources(updatedRevision?: string): Promise<boolean> {
    checkEndpoint()
    if (
      !active &&
      cacheEpoch === resourceEpoch &&
      updatedRevision &&
      updatedRevision === revision.value
    ) {
      return Promise.resolve(true)
    }
    resourceEpoch++
    return load(active?.locale ?? i18n.global.locale.value, true)
  }
  const refresh = () => refreshResources()

  function bootstrap() {
    if (stopWatch) return
    subscription = subscribe({ id: WS_ID_I18N, type: WS_I18N_UPDATED }, message => {
      if (!requested.value) return
      const revision = message?.data.revision
      void refreshResources(typeof revision === 'string' ? revision : undefined)
    })
    stopWatch = watch([connectionState(), i18n.global.locale], ([state, locale], previous) => {
      if (state !== previous?.[0]) {
        invalidateRequests()
        if (state !== 'open' && requested.value && !ready.value) {
          error.value = t('bootstrap.i18n.unavailable')
        }
      }
      if (!requested.value) return
      if (state === 'open' && state !== previous?.[0]) void refresh()
      else if (locale !== previous?.[1]) void ensure(locale)
    })
  }

  function dispose() {
    stopWatch?.()
    stopWatch = null
    if (subscription) unsubscribe(subscription)
    subscription = null
    requested.value = false
    invalidateRequests()
  }

  function cancelEntry() {
    requested.value = false
    error.value = null
    invalidateRequests()
  }

  return {
    loading,
    error,
    revision,
    requested,
    ready,
    ensure,
    refresh,
    bootstrap,
    dispose,
    cancelEntry,
  }
})
